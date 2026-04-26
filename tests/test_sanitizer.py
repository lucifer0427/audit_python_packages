"""sanitizer 模組測試"""

from app.utils.sanitizer import sanitize_for_table, truncate, clean_license


class TestSanitizeForTable:
    def test_newlines(self):
        assert sanitize_for_table("line1\nline2") == "line1<br>line2"

    def test_pipes(self):
        assert sanitize_for_table("col1|col2") == "col1/col2"

    def test_combined(self):
        assert sanitize_for_table("a|b\nc") == "a/b<br>c"

    def test_none(self):
        assert sanitize_for_table(None) == ""

    def test_empty(self):
        assert sanitize_for_table("") == ""

    def test_whitespace(self):
        assert sanitize_for_table("  hello   world  ") == "hello world"


class TestTruncate:
    def test_short_string(self):
        assert truncate("hello", 100) == "hello"

    def test_long_string(self):
        result = truncate("a" * 200, 100)
        assert len(result) == 100
        assert result.endswith("...")

    def test_none(self):
        assert truncate(None) == ""

    def test_exact_length(self):
        text = "a" * 100
        assert truncate(text, 100) == text


class TestCleanLicense:
    def test_simple_license(self):
        assert clean_license("MIT") == "MIT"

    def test_apache(self):
        assert clean_license("Apache 2.0") == "Apache 2.0"

    def test_unknown(self):
        assert clean_license("UNKNOWN") == "N/A"

    def test_none(self):
        assert clean_license(None) == "N/A"

    def test_from_classifiers(self):
        classifiers = ["License :: OSI Approved :: MIT License"]
        assert clean_license(None, classifiers) == "MIT License"

    def test_long_license_text(self):
        long_text = "MIT License\n" + "x" * 200
        result = clean_license(long_text)
        assert "MIT" in result
        assert len(result) <= 100

    def test_classifier_fallback(self):
        classifiers = [
            "Programming Language :: Python :: 3",
            "License :: OSI Approved :: BSD License",
        ]
        result = clean_license("", classifiers)
        assert result == "BSD License"
