import httpx
import pytest
from app.services.pypi_client import PyPIClient
from app.models.schemas import PyPIPackageData

@pytest.mark.asyncio
async def test_get_package_info_success(httpx_mock, mock_http_client, sample_pypi_response):
    client = PyPIClient(mock_http_client)
    httpx_mock.add_response(json=sample_pypi_response)
    
    # First call
    info1 = await client.get_package_info("requests", "2.31.0")
    # Second call to test cache (Line 58)
    info2 = await client.get_package_info("requests", "2.31.0")
    
    assert info1 == info2
    assert info1["version"] == "2.31.0"
    assert info1["summary"] == "Python HTTP for Humans."
    assert info1["license"] == "Apache 2.0"
    assert info1["source_repo"] == "https://github.com/psf/requests"
    assert "requests-2.31.0-py3-none-any.whl" in info1["download_url"] or "pypi.org" in info1["download_url"]

@pytest.mark.asyncio
async def test_get_package_info_api_error(httpx_mock, mock_http_client):
    client = PyPIClient(mock_http_client)
    httpx_mock.add_response(status_code=500)
    info = await client.get_package_info("requests", "2.31.0")
    assert info["version"] == "2.31.0"
    assert info["summary"] == ""
    assert info["license"] == "N/A"
    assert info["source_repo"] is None

def test_version_to_cp_tags():
    client = PyPIClient(None)
    assert client._version_to_cp_tags("3.12") == ["cp312"]
    assert client._version_to_cp_tags("3.8") == ["cp38"]
    assert client._version_to_cp_tags("") == []
    assert client._version_to_cp_tags("3") == []
    assert client._version_to_cp_tags("abc") == []

def test_extract_source_repo():
    client = PyPIClient(None)
    # Test Line 135 (Homepage match)
    info = {"project_urls": {"Homepage": "https://github.com/user/repo-home"}}
    assert client._extract_source_repo(info) == "https://github.com/user/repo-home"
    
    # Test Line 140 (home_page field match)
    info = {"home_page": "https://github.com/user/repo-home-field"}
    assert client._extract_source_repo(info) == "https://github.com/user/repo-home-field"
    
    # Test Line 140 (home_page field but not a repo)
    info = {"home_page": "https://google.com"}
    assert client._extract_source_repo(info) is None

    # Test fallback loop and skipping issues/releases (Line 146-147)
    info = {
        "project_urls": {
            "BadLink": "https://github.com/user/repo/issues",
            "GoodLink": "https://github.com/user/repo"
        }
    }
    assert client._extract_source_repo(info) == "https://github.com/user/repo"
    
    # Test final fallback (Line 141-148)
    info = {
        "project_urls": {
            "random_key": "https://github.com/user/repo-final"
        }
    }
    assert client._extract_source_repo(info) == "https://github.com/user/repo-final"
    
    # Test no repo found (Line 150)
    info = {"project_urls": {"Homepage": "https://google.com"}}
    assert client._extract_source_repo(info) is None
    
    info = {}
    assert client._extract_source_repo(info) is None


    # Test Line 140 (skipping /issues or /releases)
    info = {
        "project_urls": {
            "Issues": "https://github.com/user/repo/issues",
            "Releases": "https://github.com/user/repo/releases",
            "Source": "https://github.com/user/repo"
        }
    }
    assert client._extract_source_repo(info) == "https://github.com/user/repo"
    
    # Test final fallback (Line 141-148)
    # Ensure NO keys from source_keys or homepage_keys are present
    info = {
        "project_urls": {
            "random_key": "https://github.com/user/repo-final"
        }
    }
    assert client._extract_source_repo(info) == "https://github.com/user/repo-final"
    
    # Test no repo found (Line 150)
    info = {"project_urls": {"Homepage": "https://google.com"}}
    assert client._extract_source_repo(info) is None
    
    info = {}
    assert client._extract_source_repo(info) is None

def test_extract_download_url():
    client = PyPIClient(None)
    
    # Test exact win_amd64 match (Line 184)
    data_exact = {
        "urls": [
            {"filename": "pkg-1.0.0-cp312-win_amd64.whl", "url": "http://exact-win"},
        ]
    }
    url, filename = client._extract_download_url(data_exact, "1.0.0", "pkg", "3.12")
    assert filename == "pkg-1.0.0-cp312-win_amd64.whl"
    assert url == "http://exact-win"
    
    # Test any_win_amd64 bucket (Line 186)
    data_win = {
        "urls": [
            {"filename": "pkg-1.0.0-cp37-win_amd64.whl", "url": "http://win-amd64"},
        ]
    }
    url, filename = client._extract_download_url(data_win, "1.0.0", "pkg", "3.12")
    assert filename == "pkg-1.0.0-cp37-win_amd64.whl"
    assert url == "http://win-amd64"
    
    # Test universal_whl bucket (Line 188)
    data_univ = {
        "urls": [
            {"filename": "pkg-1.0.0-py3-none-any.whl", "url": "http://univ"},
        ]
    }
    url, filename = client._extract_download_url(data_univ, "1.0.0", "pkg", "3.12")
    assert filename == "pkg-1.0.0-py3-none-any.whl"
    assert url == "http://univ"
    
    # Test any_whl bucket (Line 190)
    data_any = {
        "urls": [
            {"filename": "pkg-1.0.0-macosx-10.9-x86_64.whl", "url": "http://macosx"},
        ]
    }
    url, filename = client._extract_download_url(data_any, "1.0.0", "pkg", None)
    assert filename == "pkg-1.0.0-macosx-10.9-x86_64.whl"
    assert url == "http://macosx"
    
    # Test sdist fallback (Line 192)
    data_sdist = {
        "urls": [
            {"filename": "pkg-1.0.0.tar.gz", "url": "http://sdist"},
        ]
    }
    url, filename = client._extract_download_url(data_sdist, "1.0.0", "pkg", None)
    assert filename == "pkg-1.0.0.tar.gz"
    assert url == "http://sdist"
    
    # Test total fallback (Line 199-200)
    # Provide urls that don't match any bucket (not .whl, not .tar.gz, etc.)
    data_no_match = {
        "urls": [
            {"filename": "pkg-1.0.0.exe", "url": "http://exe"},
        ]
    }
    url, filename = client._extract_download_url(data_no_match, "1.0.0", "pkg", None)
    assert "pypi.org" in url
    assert filename == ""
