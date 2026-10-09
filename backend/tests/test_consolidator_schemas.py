from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.consolidator import (
    ConsolidateLocalRequest,
    ConsolidationJobResponse,
    ExclusionDetail,
    ProfileConfig,
)


def test_profile_config_normalizes_extensions_and_paths() -> None:
    profile = ProfileConfig(
        extensions=["PY", ".TS"],
        subfolders=[r"src\app", "."],
        excluded_dirs=["node_modules/"],
    )

    assert profile.extensions == [".py", ".ts"]
    assert profile.subfolders == ["src/app", "."]
    assert profile.excluded_dirs == ["node_modules"]
    assert profile.custom_sensitive_patterns is None


@pytest.mark.parametrize("extensions", [[], [""], ["../py"], ["src/py"]])
def test_profile_config_rejects_invalid_extensions(extensions: list[str]) -> None:
    with pytest.raises(ValidationError):
        ProfileConfig(extensions=extensions, subfolders=[], excluded_dirs=[])


@pytest.mark.parametrize("folder", ["../outside", "/etc", r"C:\secrets", "src/../../outside"])
def test_profile_config_rejects_unsafe_filter_paths(folder: str) -> None:
    with pytest.raises(ValidationError):
        ProfileConfig(extensions=["py"], subfolders=[folder], excluded_dirs=[])


def test_profile_config_rejects_invalid_custom_regex() -> None:
    with pytest.raises(ValidationError, match="Expressao regular invalida"):
        ProfileConfig(
            extensions=["py"],
            subfolders=[],
            excluded_dirs=[],
            custom_sensitive_patterns=["["],
        )


def test_consolidate_local_request_sanitizes_existing_absolute_root(tmp_path: Path) -> None:
    request = ConsolidateLocalRequest(
        root_path=f"  {tmp_path}  ",
        profile="JAVA",
    )

    assert request.root_path == str(tmp_path.resolve())
    assert request.profile == "java"
    assert request.project_prefix == "consolidado"
    assert request.strip_comments is True
    assert request.security_scan is True


@pytest.mark.parametrize("root_path", ["relative/path", "", "../outside"])
def test_consolidate_local_request_rejects_unsafe_root(root_path: str) -> None:
    with pytest.raises(ValidationError):
        ConsolidateLocalRequest(root_path=root_path, profile="java")


def test_consolidate_local_request_rejects_non_directory_root(tmp_path: Path) -> None:
    file_path = tmp_path / "source.py"
    file_path.write_text("pass", encoding="utf-8")

    with pytest.raises(ValidationError, match="diretorio"):
        ConsolidateLocalRequest(root_path=str(file_path), profile="python")


def test_consolidate_local_request_rejects_unsafe_project_prefix(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="project_prefix"):
        ConsolidateLocalRequest(
            root_path=str(tmp_path),
            profile="custom",
            project_prefix="../output",
        )


def test_response_models_validate_counts_and_exclusions() -> None:
    response = ConsolidationJobResponse(
        job_id="job-123",
        status="completed",
        processed_files_count=3,
        added_files_count=2,
        excluded_files_count=1,
        download_consolidated_url="/download/job-123/consolidated",
        download_log_url="/download/job-123/log",
        exclusions=[ExclusionDetail(file_path=".env", reason="sensitive file")],
    )

    assert response.exclusions[0].file_path == ".env"
    with pytest.raises(ValidationError):
        ConsolidationJobResponse(
            job_id="job-123",
            status="completed",
            processed_files_count=-1,
            added_files_count=0,
            excluded_files_count=0,
            download_consolidated_url="/download/file",
            download_log_url="/download/log",
            exclusions=[],
        )