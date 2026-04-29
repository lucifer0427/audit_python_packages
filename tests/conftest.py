import json
from pathlib import Path

import httpx
import pytest

@pytest.fixture
def mock_http_client():
    """Mock httpx.AsyncClient for testing"""
    # Since we use pytest-httpx, the actual httpx.AsyncClient will be intercepted by httpx_mock.
    # We just need to return a real client and let pytest-httpx do its magic.
    client = httpx.AsyncClient()
    yield client
    # No need to aclose since it's intercepted, but it's good practice
    # Though in async fixture we'd need pytest-asyncio and async def.
    # We'll just provide a sync fixture that returns the client.
    
@pytest.fixture
def sample_requirements():
    return b"""
requests==2.31.0
Django>=4.2.0
"""

@pytest.fixture
def sample_pypi_response():
    return {
        "info": {
            "version": "2.31.0",
            "summary": "Python HTTP for Humans.",
            "license": "Apache 2.0",
            "project_urls": {
                "Homepage": "https://requests.readthedocs.io",
                "Source": "https://github.com/psf/requests"
            }
        },
        "releases": {
            "2.31.0": [
                {
                    "filename": "requests-2.31.0-py3-none-any.whl",
                    "packagetype": "bdist_wheel",
                    "url": "https://files.pythonhosted.org/packages/.../requests-2.31.0-py3-none-any.whl"
                },
                {
                    "filename": "requests-2.31.0.tar.gz",
                    "packagetype": "sdist",
                    "url": "https://files.pythonhosted.org/packages/.../requests-2.31.0.tar.gz"
                }
            ]
        }
    }

@pytest.fixture
def sample_osv_response():
    return {
        "vulns": [
            {
                "id": "GHSA-j8r2-6x86-q33q",
                "summary": "Potential denial of service in Requests",
                "database_specific": {
                    "severity": "MODERATE"
                }
            }
        ]
    }
