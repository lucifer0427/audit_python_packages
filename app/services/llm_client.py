"""外部 LLM API 客戶端 — 選用功能

提供 OpenAI GPT 和 Google Gemini 的統一抽象層，
用於批次翻譯套件英文摘要為繁體中文。
"""

import json
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位資安稽核翻譯專家。請將以下 Python 套件的英文功能摘要翻譯為專業繁體中文描述。

規則：
1. 每個翻譯結果必須在 15-30 字之間
2. 使用專業技術用語
3. 回傳 JSON 格式: {"套件名稱": "中文描述", ...}
4. 不要加任何額外說明，只回傳 JSON"""


class LLMClient(ABC):
    """LLM 客戶端抽象基類"""

    @abstractmethod
    def translate_summaries(self, items: list[dict]) -> dict[str, str]:
        """批次翻譯套件摘要

        Args:
            items: [{"name": "requests", "summary": "HTTP library..."}]

        Returns:
            {"requests": "中文描述", ...}
        """
        ...


class OpenAIClient(LLMClient):
    """OpenAI GPT 客戶端"""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)
        self.model = model

    def translate_summaries(self, items: list[dict]) -> dict[str, str]:
        if not items:
            return {}

        user_content = "\n".join(
            f"- {item['name']}: {item['summary']}" for item in items
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            logger.error("OpenAI API 呼叫失敗: %s", e)
            return {}


class GeminiClient(LLMClient):
    """Google Gemini 客戶端"""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.model = model

    def translate_summaries(self, items: list[dict]) -> dict[str, str]:
        if not items:
            return {}

        user_content = "\n".join(
            f"- {item['name']}: {item['summary']}" for item in items
        )
        prompt = f"{SYSTEM_PROMPT}\n\n{user_content}"

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            # 提取 JSON 部分
            text = response.text.strip()
            # 處理可能被 markdown code block 包裹的情況
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0].strip()
            return json.loads(text)
        except Exception as e:
            logger.error("Gemini API 呼叫失敗: %s", e)
            return {}


def create_llm_client(mode: str, **kwargs) -> LLMClient | None:
    """工廠函式: 根據模式建立對應的 LLM 客戶端

    Args:
        mode: "openai" 或 "gemini"
        **kwargs: api_key, model 等參數

    Returns:
        LLMClient 實例，建立失敗則回傳 None
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
