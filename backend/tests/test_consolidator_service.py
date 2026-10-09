from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.schemas.consolidator import (
	ConsolidateLocalRequest,
	ConsolidateUploadRequest,
	ProfileConfig,
)
from app.services.consolidator_service import ConsolidatorService, ConsolidatorServiceError


def make_zip(entries: dict[str, str]) -> bytes:
	buffer = BytesIO()
	with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
		for name, content in entries.items():
			archive.writestr(name, content)
	return buffer.getvalue()


def test_process_local_writes_consolidated_file_and_exclusions(tmp_path: Path) -> None:
	project = tmp_path / "project"
	source = project / "src"
	source.mkdir(parents=True)
	(source / "main.py").write_text('value = "https://example.test"  # remove me\n', encoding="utf-8")
	(source / "credentials.py").write_text('password = "super-secret-value"\n', encoding="utf-8")
	(source / ".env").write_text("API_KEY=secret", encoding="utf-8")
	(source / "ignored.py").write_text("print('ignored')", encoding="utf-8")
	(project / ".gitignore").write_text("src/ignored.py\n", encoding="utf-8")
	request = ConsolidateLocalRequest(
		root_path=str(project),
		project_prefix="example",
		profile="custom",
		custom_rules=ProfileConfig(extensions=["py", "env"], subfolders=["src"], excluded_dirs=[]),
	)
	service = ConsolidatorService(storage_root=tmp_path / "jobs")

	result = service.process_local(request)
	consolidated = service.get_job_file(result.job_id, "consolidated").read_text(encoding="utf-8")
	log = service.get_job_file(result.job_id, "log").read_text(encoding="utf-8")

	assert result.processed_files_count == 4
	assert result.added_files_count == 1
	assert result.excluded_files_count == 3
	assert "=" * 80 in consolidated
	assert "Path do arquivo: src/main.py" in consolidated
	assert "Nome do arquivo: main.py" in consolidated
	assert "https://example.test" in consolidated
	assert "remove me" not in consolidated
	assert "super-secret-value" not in consolidated
	assert "ignorado por regra do .gitignore" in log


def test_process_upload_cleans_extraction_and_keeps_downloadable_job(tmp_path: Path) -> None:
	service = ConsolidatorService(storage_root=tmp_path / "jobs")
	request = ConsolidateUploadRequest(
		profile="custom",
		custom_rules=ProfileConfig(extensions=["py"], subfolders=[], excluded_dirs=[]),
	)

	result = service.process_upload(make_zip({"src/app.py": "print('zip source')\n"}), request)
	download = ConsolidatorService(storage_root=tmp_path / "jobs").get_job_file(
		result.job_id, "consolidated"
	)
	assert "zip source" in download.read_text(encoding="utf-8")


def test_profile_lookup_returns_builtin_profiles() -> None:
	assert set(ConsolidatorService.list_profiles()) == {
		"java",
		"angular",
		"postgres",
		"python",
		"dotnet",
	}


def test_invalid_download_job_id_is_rejected(tmp_path: Path) -> None:
	with pytest.raises(ValueError, match="UUID"):
		ConsolidatorService(storage_root=tmp_path).get_job_file("../outside", "log")


def test_custom_profile_requires_rules(tmp_path: Path) -> None:
	request = ConsolidateLocalRequest(root_path=str(tmp_path), profile="custom")
	with pytest.raises(ConsolidatorServiceError, match="custom_rules"):
		ConsolidatorService(storage_root=tmp_path / "jobs").process_local(request)