import json
import subprocess
from unittest.mock import MagicMock, patch
import pytest
from app.services.dependency_resolver import resolve_dependencies

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
            f.write("requests\n") # Invalid format, no ==
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=mock_run):
        new_content, pkgs = resolve_dependencies(b"requests\n")
        assert len(pkgs) == 0
        assert new_content == b"requests\n"
