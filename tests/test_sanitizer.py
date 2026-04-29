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
    
    def test_only_pipes(self):
        assert sanitize_for_table("|||") == "///"

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
    
    def test_invalid_limit(self):
        assert truncate("hello", -1) == "h..."
        assert truncate("hello", None) == "hello"

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

    def test_regex_patterns(self):
        # Test all patterns in clean_license (Line 52-67)
        patterns = [
            ("MIT License" + " a" * 100, "MIT"),
            ("Apache License 2.0" + " a" * 100, "Apache"),
            ("BSD 3-Clause License" + " a" * 100, "BSD"),
            ("GNU General Public License v3" + " a" * 100, "GNU"),
            ("GPL-2.0+" + " a" * 100, "GPL"),
            ("LGPL-2.1" + " a" * 100, "LGPL"),
            ("MPL-2.0" + " a" * 100, "MPL"),
            ("ISC License" + " a" * 100, "ISC"),
            ("Unlicense" + " a" * 100, "Unlicense"),
        ]
        for text, expected in patterns:
            assert expected in clean_license(text)


    def test_long_license_no_match(self):
        # Force enter if len(cleaned) > 100 and no regex match
        long_text = "This is a very long license that does not match any patterns" + " a" * 50
        result = clean_license(long_text)
        assert len(result) <= 100
        assert result.endswith("...")

    def test_classifier_fallback(self):
        classifiers = [
            "Programming Language :: Python :: 3",
            "License :: OSI Approved :: BSD License",
        ]
        result = clean_license("", classifiers)
        assert result == "BSD License"
        
        classifiers_simple = ["License :: MIT"]
        result_simple = clean_license("", classifiers_simple)
        assert result_simple == "MIT"

    def test_license_expression_priority(self):
        result = clean_license(
            "MIT",
            ["License :: OSI Approved :: MIT License"],
            "BSD-3-Clause",
        )
        assert result == "BSD-3-Clause"

    def test_license_expression_none_fallback(self):
        result = clean_license("Apache-2.0", None, None)
        assert result == "Apache-2.0"

    def test_license_expression_compound(self):
        result = clean_license(None, None, "Apache-2.0 OR BSD-3-Clause")
        assert result == "Apache-2.0 OR BSD-3-Clause"

    def test_all_none(self):
        result = clean_license(None, [], None)
        assert result == "N/A"
