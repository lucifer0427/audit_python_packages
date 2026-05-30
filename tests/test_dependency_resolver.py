import json
import subprocess
from unittest.mock import MagicMock, patch

from app.services.dependency_resolver import clear_cache, get_offline_download_urls, resolve_dependencies


def test_resolve_dependencies_success():
    def mock_run(cmd, **kwargs):
        resolved_file = cmd[5]
        with open(resolved_file, "w", encoding="utf-8") as f:
            f.write("# Compiled by uv\n\nrequests==2.31.0\nurllib3==2.0.0; python_version < '3.12'\n")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=mock_run):
        new_content, pkgs = resolve_dependencies(b"requests\n", python_version="3.11")
        assert len(pkgs) == 2
        assert pkgs[0] == ("requests", "2.31.0")
        assert pkgs[1] == ("urllib3", "2.0.0")
        assert b"requests==2.31.0\nurllib3==2.0.0" in new_content


def test_resolve_dependencies_subprocess_error():
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, [], stderr="error")):
        new_content, pkgs = resolve_dependencies(b"requests\n")
        assert pkgs == []
        assert new_content == b"requests\n"


def test_resolve_dependencies_no_report():
    with patch("subprocess.run"):
        # subprocess.run succeeds but does not write resolved file
        new_content, pkgs = resolve_dependencies(b"requests\n")
        assert pkgs == []
        assert new_content == b"requests\n"


def test_resolve_dependencies_missing_metadata():
    def mock_run(cmd, **kwargs):
        resolved_file = cmd[5]
        with open(resolved_file, "w", encoding="utf-8") as f:
            f.write("requests\n")  # Invalid format, no ==
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=mock_run):
        new_content, pkgs = resolve_dependencies(b"requests\n")
        assert len(pkgs) == 0
        assert new_content == b"requests\n"


def test_resolve_dependencies_cache_hit():
    """Second call with same input should hit cache and skip subprocess."""
    clear_cache()

    content = b"requests\n"

    def mock_run(cmd, **kwargs):
        resolved_file = cmd[5]
        with open(resolved_file, "w", encoding="utf-8") as f:
            f.write("# Compiled by uv\n\nrequests==2.31.0\n")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=mock_run) as mock_run:
        new_content1, pkgs1 = resolve_dependencies(content, python_version="3.11")
        assert len(pkgs1) == 1
        assert pkgs1[0] == ("requests", "2.31.0")

        # Second call — should hit cache, subprocess not called again
        new_content2, pkgs2 = resolve_dependencies(content, python_version="3.11")
        assert len(pkgs2) == 1
        assert pkgs2[0] == ("requests", "2.31.0")
        assert new_content1 == new_content2

        assert mock_run.call_count == 1


def test_get_offline_download_urls_cache_hit():
    """Second call with same input should hit cache and skip subprocess."""
    clear_cache()

    content = b"requests==2.31.0"

    def mock_run(cmd, **kwargs):
        report_file = cmd[6]
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "install": [
                        {
                            "metadata": {"name": "requests"},
                            "download_info": {"url": "https://example.com/requests-2.31.0-py2.py3-none-any.whl"},
                        }
                    ]
                },
                f,
            )
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=mock_run) as mock_run:
        result1 = get_offline_download_urls(content, python_version="3.11", platform="linux_x86_64")
        assert result1 == {"requests": "https://example.com/requests-2.31.0-py2.py3-none-any.whl"}

        # Second call — should hit cache
        result2 = get_offline_download_urls(content, python_version="3.11", platform="linux_x86_64")
        assert result2 == {"requests": "https://example.com/requests-2.31.0-py2.py3-none-any.whl"}

        assert mock_run.call_count == 1


def test_clear_cache():
    """clear_cache should empty the cache so subprocess is called again."""
    clear_cache()

    content = b"requests\n"

    def mock_run(cmd, **kwargs):
        resolved_file = cmd[5]
        with open(resolved_file, "w", encoding="utf-8") as f:
            f.write("# Compiled by uv\n\nrequests==2.31.0\n")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=mock_run) as mock_run:
        resolve_dependencies(content, python_version="3.11")
        assert mock_run.call_count == 1

        # Clear cache, then call again — subprocess should be called again
        clear_cache()
        resolve_dependencies(content, python_version="3.11")
        assert mock_run.call_count == 2
