"""parser 模組測試"""

from app.services.parser import detect_encoding, parse_requirements


class TestDetectEncoding:
    def test_utf8(self):
        assert detect_encoding(b"hello") == "utf-8"

    def test_utf8_bom(self):
        assert detect_encoding(b"\xef\xbb\xbfhello") == "utf-8-sig"

    def test_utf16_le(self):
        assert detect_encoding(b"\xff\xfeh\x00e\x00") == "utf-16-le"

    def test_utf16_be(self):
        assert detect_encoding(b"\xfe\xff\x00h\x00e") == "utf-16-be"


class TestParseRequirements:
    def test_basic_package(self):
        result = parse_requirements("requests\n")
        assert len(result) == 1
        assert result[0].name == "requests"
        assert result[0].version is None

    def test_pinned_version(self):
        result = parse_requirements("requests==2.31.0\n")
        assert result[0].name == "requests"
        assert result[0].version == "2.31.0"
        assert result[0].version_spec == "==2.31.0"

    def test_minimum_version(self):
        result = parse_requirements("flask>=2.0.0\n")
        assert result[0].name == "flask"
        assert result[0].version is None
        assert result[0].version_spec == ">=2.0.0"

    def test_compatible_version(self):
        result = parse_requirements("django~=4.2\n")
        assert result[0].name == "django"
        assert result[0].version_spec == "~=4.2"

    def test_skip_comments(self):
        content = "# this is a comment\nrequests\n"
        result = parse_requirements(content)
        assert len(result) == 1

    def test_skip_empty_lines(self):
        content = "\n\nrequests\n\n"
        result = parse_requirements(content)
        assert len(result) == 1

    def test_skip_options(self):
        content = "-r base.txt\n--index-url https://pypi.org/simple\nrequests\n"
        result = parse_requirements(content)
        assert len(result) == 1

    def test_inline_comment(self):
        result = parse_requirements("requests==2.31.0  # HTTP lib\n")
        assert result[0].name == "requests"

    def test_extras(self):
        result = parse_requirements("uvicorn[standard]>=0.34.0\n")
        assert result[0].name == "uvicorn"
        assert result[0].version_spec == ">=0.34.0"

    def test_environment_markers(self):
        result = parse_requirements('pywin32; sys_platform == "win32"\n')
        assert result[0].name == "pywin32"

    def test_multiple_packages(self):
        content = "requests==2.31.0\nflask>=2.0.0\nnumpy\n"
        result = parse_requirements(content)
        assert len(result) == 3

    def test_bytes_input_utf8(self):
        content = b"requests==2.31.0\n"
        result = parse_requirements(content)
        assert len(result) == 1
        assert result[0].name == "requests"

    def test_complex_version(self):
        result = parse_requirements("package>=1.0,<2.0\n")
        assert result[0].name == "package"
        assert result[0].version_spec == ">=1.0"

    def test_none_input(self):
        result = parse_requirements(None)
        assert result == []

    def test_empty_input(self):
        result = parse_requirements("")
        assert result == []

    def test_invalid_package_names(self):
        # Invalid name with version (Line 90-91)
        result = parse_requirements("!invalid==1.0\n")
        assert len(result) == 0

        # Invalid name without version (Line 102-103)
        result = parse_requirements("!!!invalid\n")
        assert len(result) == 0
