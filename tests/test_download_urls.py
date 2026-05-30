import json
import subprocess
from unittest.mock import MagicMock, patch

from app.services.dependency_resolver import get_offline_download_urls


def test_get_offline_download_urls_success():
    def mock_run(cmd, **kwargs):
        # Extract report file path from cmd
        # cmd is like ['pip', 'install', '--dry-run', '--report', '/tmp/report.json', ...]
        report_idx = cmd.index("--report") + 1
        report_file = cmd[report_idx]

        mock_data = {
            "install": [
                {"metadata": {"name": "requests"}, "download_info": {"url": "https://test.com/requests.whl"}},
                {"metadata": {"name": "urllib3"}, "download_info": {"url": "https://test.com/urllib3.whl"}},
            ]
        }
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(mock_data, f)
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=mock_run):
        urls = get_offline_download_urls(b"requests\n", python_version="3.12", platform="win_amd64")
        assert len(urls) == 2
        assert urls["requests"] == "https://test.com/requests.whl"
        assert urls["urllib3"] == "https://test.com/urllib3.whl"


def test_get_offline_download_urls_failure():
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, [], stderr="pip error")):
        urls = get_offline_download_urls(b"requests\n")
        assert urls == {}


def test_get_offline_download_urls_invalid_json():
    def mock_run(cmd, **kwargs):
        report_idx = cmd.index("--report") + 1
        report_file = cmd[report_idx]
        with open(report_file, "w", encoding="utf-8") as f:
            f.write("invalid json")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=mock_run):
        urls = get_offline_download_urls(b"requests\n")
        assert urls == {}
