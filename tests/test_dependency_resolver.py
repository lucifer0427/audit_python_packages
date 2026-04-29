import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.services.dependency_resolver import resolve_dependencies


def test_resolve_dependencies_success():
    def mock_run(cmd, **kwargs):
        report_file = cmd[4]
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump({
                "install": [
                    {"metadata": {"name": "urllib3", "version": "2.0.0"}},
                    {"metadata": {"name": "requests", "version": "2.31.0"}},
                ]
            }, f)
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=mock_run):
        new_content, pkgs = resolve_dependencies(b"requests\n")
        assert len(pkgs) == 2
        assert pkgs[0] == ("requests", "2.31.0")
        assert pkgs[1] == ("urllib3", "2.0.0")
        assert b"requests==2.31.0\nurllib3==2.0.0" == new_content


def test_resolve_dependencies_subprocess_error():
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, [])):
        new_content, pkgs = resolve_dependencies(b"requests\n")
        assert pkgs == []
        assert new_content == b"requests\n"


def test_resolve_dependencies_no_report():
    with patch("subprocess.run"):
        # subprocess.run succeeds but does not write report file
        new_content, pkgs = resolve_dependencies(b"requests\n")
        assert pkgs == []
        assert new_content == b"requests\n"


def test_resolve_dependencies_missing_metadata():
    def mock_run(cmd, **kwargs):
        report_file = cmd[4]
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump({
                "install": [
                    {"metadata": {"name": "requests"}}, # missing version
                    {"metadata": {}}, # missing both
                ]
            }, f)
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=mock_run):
        new_content, pkgs = resolve_dependencies(b"requests\n")
        assert len(pkgs) == 0
        assert new_content == b""
