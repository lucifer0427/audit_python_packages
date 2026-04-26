"""外部 LLM API 客戶端 — 選用功能
提供 OpenAI GPT 和 Google Gemini 的統一抽象層，
用於將套件的英文摘要翻譯為繁體中文，提升報告的可讀性。
"""

import json
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# 設定 LLM 的系統指令 (System Prompt)
# 透過明確的規則約束 AI 回傳格式，確保結果能被程式解析為 JSON
SYSTEM_PROMPT = """你是一位資安稽核翻譯專家。請將以下 Python 套件的英文功能摘要翻譯為專業繁體中文描述。

規則：
1. 每個翻譯結果必須在 15-30 字之間
2. 使用專業技術用語
3. 回傳 JSON 格式: {"套件名稱": "中文描述", ...}
4. 不要加任何額外說明，只回傳 JSON"""


class LLMClient(ABC):
    """
    LLM 客戶端抽象基類 (Abstract Base Class)
    定義統一的介面，讓不同供應商的 LLM (OpenAI, Gemini) 可以互換。
    """

    @abstractmethod
    async def translate_summaries(self, items: list[dict]) -> dict[str, str]:
        """
        批次翻譯套件摘要的非同步介面
        
        Args:
            items: 包含套件名稱與英文摘要的列表: [{"name": "requests", "summary": "..."}]
        Returns:
            翻譯後的對照字典: {"requests": "中文描述", ...}
        """
        ...


class OpenAIClient(LLMClient):
    """OpenAI GPT 實作客戶端"""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        from openai import AsyncOpenAI
        # 使用非同步客戶端以避免阻塞 FastAPI 事件迴圈
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def translate_summaries(self, items: list[dict]) -> dict[str, str]:
        if not items:
            return {}

        # 將多個套件摘要組合成一個請求，減少 API 呼叫次數 (Batching)
        user_content = "\n".join(
            f"- {item['name']}: {item['summary']}" for item in items
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.3, # 低隨機性，確保翻譯結果穩定且專業
                response_format={"type": "json_object"}, # 強制要求回傳 JSON 格式
            )
            content = response.choices[0].message.content
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                # 捕捉 AI 回傳非合法 JSON 的情況
                logger.error("OpenAI 回傳非法 JSON: %s, 原始內容: %s", e, content)
                return {}
        except Exception as e:
            logger.error("OpenAI API 呼叫失敗: %s", e)
            return {}


class GeminiClient(LLMClient):
    """Google Gemini 實作客戶端"""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.model = model

    async def translate_summaries(self, items: list[dict]) -> dict[str, str]:
        if not items:
            return {}
            
        from google.genai import types

        # 同樣採用批次處理方式
        user_content = "\n".join(
            f"- {item['name']}: {item['summary']}" for item in items
        )
        prompt = f"{SYSTEM_PROMPT}\n\n{user_content}"

        try:
            # 使用 google-genai 的 aio 模組進行非同步呼叫
            response = await self.client.aio.models.generate_content(
                model=self.model,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json" # 告知 API 僅需回傳 JSON
                ),
                contents=prompt,
            )
            text = response.text.strip()
            
            # 處理 Gemini 可能將 JSON 包在 Markdown 程式碼塊 (```json ... ```) 中的情況
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0].strip()
            
            try:
                return json.loads(text)
            except json.JSONDecodeError as e:
                logger.error("Gemini 回傳非法 JSON: %s, 原始內容: %s", e, text)
                return {}
        except Exception as e:
            logger.error("Gemini API 呼叫失敗: %s", e)
            return {}


def create_llm_client(mode: str, **kwargs) -> LLMClient | None:
    """
    LLM 客戶端工廠函式
    根據設定中的 TRANSLATION_MODE 建立對應的實作類別。
    """
    try:
        if mode == "openai":
            return OpenAIClient(
                api_key=kwargs["api_key"],
                model=kwargs.get("model", "gpt-4o-mini"),
            )
        elif mode == "gemini":
            return GeminiClient(
                api_key=kwargs["api_key"],
                model=kwargs.get("model", "gemini-2.0-flash"),
            )
    except Exception as e:
        logger.error("LLM 客戶端建立失敗 [%s]: %s", mode, e)

    return None
