import httpx
import pytest

from app.services.osv_client import OSVClient
from app.models.schemas import VulnerabilityInfo

@pytest.mark.asyncio
async def test_query_vulnerabilities_found(httpx_mock, mock_http_client, sample_osv_response):
    client = OSVClient(mock_http_client)
    
    httpx_mock.add_response(json=sample_osv_response)
    
    vulns = await client.query_vulnerabilities("requests", "2.31.0")
    
    assert len(vulns) == 1
    assert vulns[0].vuln_id == "GHSA-j8r2-6x86-q33q"
    assert vulns[0].summary == "Potential denial of service in Requests"
    assert vulns[0].severity == "MODERATE"
    assert "snyk.io" in vulns[0].snyk_url

@pytest.mark.asyncio
async def test_query_vulnerabilities_not_found(httpx_mock, mock_http_client):
    client = OSVClient(mock_http_client)
    
    httpx_mock.add_response(json={})
    
    vulns = await client.query_vulnerabilities("safe-package", "1.0.0")
    assert len(vulns) == 0

@pytest.mark.asyncio
async def test_query_vulnerabilities_api_error(httpx_mock, mock_http_client):
    client = OSVClient(mock_http_client)
    
    httpx_mock.add_response(status_code=500)
    
    vulns = await client.query_vulnerabilities("requests", "2.31.0")
    assert len(vulns) == 0

def test_extract_severity():
    # Use a dummy client for helper methods
    client = OSVClient(None)
    
    # CVSS V3
    vuln = {"severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}]}
    assert "CVSS:" in client._extract_severity(vuln)
    
    # Database specific
    vuln = {"database_specific": {"severity": "HIGH"}}
    assert client._extract_severity(vuln) == "HIGH"
    
    # Missing
    assert client._extract_severity({}) == "未知"

def test_cvss_to_level():
    client = OSVClient(None)
    assert client._cvss_to_level("9.5") == "嚴重"
    assert client._cvss_to_level("7.5") == "高"
    assert client._cvss_to_level("5.0") == "中"
    assert client._cvss_to_level("2.0") == "低"
    assert "CVSS:" in client._cvss_to_level("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H")
    assert client._cvss_to_level("invalid") == "invalid"
