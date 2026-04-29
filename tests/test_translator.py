import pytest

from app.services.translator import TranslatorService

@pytest.mark.asyncio
async def test_rule_based_translate():
    service = TranslatorService()
    assert service._rule_based_translate("") == "Python 套件。"
    
    # 冗餘前綴移除
    assert service._rule_based_translate("A fast HTTP client") == "快速 HTTP 客戶端。"
    
    # 詞彙替換
    assert "函式庫" in service._rule_based_translate("A python library")
    
    # 截斷
    long_text = "a" * 50
    assert len(service._rule_based_translate(long_text)) <= 35  # 27 chars + ... + 。 = 31 + 原文
    
    # 標記
    assert "(原文)" in service._rule_based_translate("Very English text here indeed")
    assert "(原文)" not in service._rule_based_translate("這是一個中文測試")

@pytest.mark.asyncio
async def test_translate_summaries_builtin():
    service = TranslatorService()
    items = [{"name": "requests", "summary": "Python HTTP for Humans"}]
    # requests 是已知套件，應該回傳內建翻譯
    res = await service.translate_summaries(items)
    assert "專業的 HTTP 請求庫" in res["requests"] or "HTTP" in res["requests"]
    
    items = [{"name": "unknown-pkg", "summary": "Unknown framework"}]
    res = await service.translate_summaries(items)
    # framework 會被替換為 框架
    assert "框架" in res["unknown-pkg"]
