from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import PackageInfo
from app.services.audit_service import AuditService


@pytest.fixture
def mock_osv_client():
    client = MagicMock()
    client.query_vulnerabilities = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_pypi_client():
    client = MagicMock()
    client.get_package_info = AsyncMock(
        return_value={
            "version": "1.0.0",
            "summary": "Test summary",
            "license": "MIT",
            "source_repo": "https://github.com/test/test",
            "download_url": "http://test.com/dl",
            "download_filename": "test.whl",
        }
    )
    return client


@pytest.fixture
def mock_translator():
    service = MagicMock()
    service.translate_summaries = AsyncMock(return_value={"test-pkg": "測試摘要"})
    return service


@pytest.fixture
def audit_service(mock_osv_client, mock_pypi_client, mock_translator):
    return AuditService(mock_osv_client, mock_pypi_client, mock_translator)


@pytest.mark.asyncio
async def test_run_audit_flow_success(audit_service, mock_osv_client, mock_pypi_client, mock_translator):
    with (
        patch("app.services.parser.parse_requirements") as mock_parse,
        patch("app.services.dependency_resolver.resolve_dependencies") as mock_resolve,
        patch("app.services.dependency_resolver.get_offline_download_urls") as mock_get_urls,
        patch("app.services.pip_audit_runner.run_pip_audit") as mock_pip_audit,
        patch("app.services.report_generator.generate_report") as mock_gen_report,
    ):
        mock_parse.return_value = [PackageInfo(name="test-pkg", version="1.0.0")]
        mock_resolve.return_value = (b"test-pkg==1.0.0", [("test-pkg", "1.0.0")])
        mock_get_urls.return_value = {"test-pkg": "http://pip.com/dl"}
        mock_pip_audit.return_value = {}
        mock_gen_report.return_value = (
            MagicMock(name="md"),
            MagicMock(name="html"),
            MagicMock(name="pdf"),
            MagicMock(name="res"),
        )

        result = await audit_service.run_audit_flow(b"test-pkg==1.0.0", "requirements.txt")

        assert result["message"] == "稽核完成"
        assert result["total_packages"] == 1
        assert "report_file" in result


@pytest.mark.asyncio
async def test_run_audit_flow_parse_error(audit_service):
    with (
        patch("app.services.parser.parse_requirements", side_effect=Exception("Parse Error")),
        pytest.raises(ValueError, match="檔案解析失敗"),
    ):
        await audit_service.run_audit_flow(b"invalid", "reqs.txt")


@pytest.mark.asyncio
async def test_run_audit_flow_no_packages(audit_service):
    with (
        patch("app.services.parser.parse_requirements", return_value=[]),
        pytest.raises(ValueError, match="未解析到任何套件"),
    ):
        await audit_service.run_audit_flow(b"", "reqs.txt")


@pytest.mark.asyncio
async def test_run_audit_flow_with_vulns(audit_service, mock_osv_client, mock_pypi_client, mock_translator):
    from app.models.schemas import VulnerabilityInfo

    with (
        patch("app.services.parser.parse_requirements") as mock_parse,
        patch("app.services.dependency_resolver.resolve_dependencies") as mock_resolve,
        patch("app.services.dependency_resolver.get_offline_download_urls") as mock_get_urls,
        patch("app.services.pip_audit_runner.run_pip_audit") as mock_pip_audit,
        patch("app.services.report_generator.generate_report") as mock_gen_report,
    ):
        mock_parse.return_value = [PackageInfo(name="test-pkg", version="1.0.0")]
        mock_resolve.return_value = (b"test-pkg==1.0.0", [("test-pkg", "1.0.0")])
        mock_get_urls.return_value = {}

        # Mock OSV vuln
        mock_osv_client.query_vulnerabilities.return_value = [
            VulnerabilityInfo(vuln_id="OSV-1", summary="OSV Vuln", severity="High", snyk_url="url")
        ]
        # Mock pip-audit vuln
        mock_pip_audit.return_value = {
            "test-pkg": [VulnerabilityInfo(vuln_id="PIP-1", summary="Pip Vuln", severity=None, snyk_url=None)]
        }

        mock_gen_report.return_value = (
            MagicMock(name="md"),
            MagicMock(name="html"),
            MagicMock(name="pdf"),
            MagicMock(name="res"),
        )

        result = await audit_service.run_audit_flow(b"test-pkg==1.0.0", "requirements.txt")

        assert result["vuln_packages"] == 1
        # Check if both vulns were merged
        # This requires checking the generated report or internal state if we could,
        # but we can check the mock call to report_generator
        args, _ = mock_gen_report.call_args
        report = args[0]
        assert report.vuln_count == 1
        assert len(report.packages[0].vulnerabilities) == 2


def test_resolve_versions():
    # Need a real AuditService instance but we can call private methods
    service = AuditService(MagicMock(), MagicMock(), MagicMock())
    pkgs = [PackageInfo(name="p1", version="1.0"), PackageInfo(name="p2", version=None)]
    pypi_data = {"p2": {"version": "2.0"}}

    resolved = service._resolve_versions(pkgs, pypi_data)
    assert resolved["p1"] == "1.0"
    assert resolved["p2"] == "2.0"


def test_merge_vulnerabilities():
    service = AuditService(MagicMock(), MagicMock(), MagicMock())
    from app.models.schemas import VulnerabilityInfo

    osv = {"pkg1": [VulnerabilityInfo(vuln_id="V1", summary="S1", severity="H", snyk_url="U1")]}
    pip = {
        "pkg1": [
            VulnerabilityInfo(vuln_id="V1", summary="S1", severity=None, snyk_url=None),  # Duplicate
            VulnerabilityInfo(vuln_id="V2", summary="S2", severity=None, snyk_url=None),  # New
        ],
        "pkg2": [VulnerabilityInfo(vuln_id="V3", summary="S3", severity=None, snyk_url=None)],
    }

    merged = service._merge_vulnerabilities(osv, pip)
    assert len(merged["pkg1"]) == 2
    assert len(merged["pkg2"]) == 1
    assert {v.vuln_id for v in merged["pkg1"]} == {"V1", "V2"}
