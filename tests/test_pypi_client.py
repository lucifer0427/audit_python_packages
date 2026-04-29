import httpx
import pytest

from app.services.pypi_client import PyPIClient
from app.models.schemas import PyPIPackageData

@pytest.mark.asyncio
async def test_get_package_info_success(httpx_mock, mock_http_client, sample_pypi_response):
    client = PyPIClient(mock_http_client)
    
    httpx_mock.add_response(json=sample_pypi_response)
    
    info = await client.get_package_info("requests", "2.31.0")
    
    assert info["version"] == "2.31.0"
    assert info["summary"] == "Python HTTP for Humans."
    assert info["license"] == "Apache 2.0"
    assert info["source_repo"] == "https://github.com/psf/requests"
    assert "requests-2.31.0-py3-none-any.whl" in info["download_url"] or "pypi.org" in info["download_url"]

@pytest.mark.asyncio
async def test_get_package_info_api_error(httpx_mock, mock_http_client):
    client = PyPIClient(mock_http_client)
    
    httpx_mock.add_response(status_code=500)
    
    info = await client.get_package_info("requests", "2.31.0")
    
    assert info["version"] == "2.31.0"
    assert info["summary"] == ""
    assert info["license"] == "N/A"
    assert info["source_repo"] is None

def test_extract_source_repo():
    client = PyPIClient(None)
    info = {
        "project_urls": {
            "Source": "https://github.com/user/repo",
            "Homepage": "https://example.com"
        }
    }
    assert client._extract_source_repo(info) == "https://github.com/user/repo"
    
    info = {
        "project_urls": {
            "Homepage": "https://github.com/user/repo2"
        }
    }
    assert client._extract_source_repo(info) == "https://github.com/user/repo2"

def test_extract_download_url():
    client = PyPIClient(None)
    # The test data format in original test was slightly wrong compared to real API
    # The real API returns data = {"info": {...}, "urls": [...]}
    # The original test passed 'releases' which is not what _extract_download_url expects
    # It expects the root data dict.
    data = {
        "urls": [
            {"filename": "pkg-1.0.0.tar.gz", "url": "http://example.com/tar"},
            {"filename": "pkg-1.0.0-py3-none-any.whl", "url": "http://example.com/whl"},
        ]
    }
    url, filename = client._extract_download_url(data, "1.0.0", "pkg", None)
    # With 'py3-none-any', it should match universal_whl
    assert filename == "pkg-1.0.0-py3-none-any.whl"
    assert url == "http://example.com/whl"
