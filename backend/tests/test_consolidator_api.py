import json
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.consolidator import get_consolidator_service
from app.main import app
from app.services.consolidator_service import ConsolidatorService


def make_zip(filename: str, content: str) -> bytes:
	buffer = BytesIO()
	with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
		archive.writestr(filename, content)
	return buffer.getvalue()


@pytest.fixture
def client(tmp_path: Path):
	service = ConsolidatorService(storage_root=tmp_path / "jobs")
	app.dependency_overrides[get_consolidator_service] = lambda: service
	with TestClient(app) as test_client:
		yield test_client
	app.dependency_overrides.clear()


def test_process_local_endpoint_and_download(client: TestClient, tmp_path: Path) -> None:
	project = tmp_path / "project"
	project.mkdir()
	(project / "main.py").write_text("print('api')\n", encoding="utf-8")
	response = client.post(
		"/api/v1/consolidator/process-local",
		json={"root_path": str(project), "profile": "python"},
	)

	assert response.status_code == 200
	job_id = response.json()["job_id"]
	download = client.get(f"/api/v1/consolidator/download/{job_id}/consolidated")
	assert download.status_code == 200
	assert "print('api')" in download.text
	assert download.headers["content-disposition"].endswith('filename="consolidated.txt"')


def test_process_upload_endpoint_accepts_profile_json(client: TestClient) -> None:
	profile_config = {
		"profile": "custom",
		"extensions": ["py"],
		"subfolders": [],
		"excluded_dirs": [],
	}
	response = client.post(
		"/api/v1/consolidator/process-upload",
		files={"file": ("project.zip", make_zip("src/main.py", "print('uploaded')"), "application/zip")},
		data={"config": json.dumps(profile_config)},
	)

	assert response.status_code == 200
	job_id = response.json()["job_id"]
	assert "print('uploaded')" in client.get(
		f"/api/v1/consolidator/download/{job_id}/consolidated"
	).text


def test_upload_rejects_non_zip_filename(client: TestClient) -> None:
	response = client.post(
		"/api/v1/consolidator/process-upload",
		files={"file": ("project.txt", b"not zip", "text/plain")},
		data={"config": "{}"},
	)

	assert response.status_code == 415


def test_profiles_endpoint_returns_expected_profiles(client: TestClient) -> None:
	response = client.get("/api/v1/consolidator/profiles")

	assert response.status_code == 200
	assert set(response.json()) == {"java", "angular", "postgres", "python", "dotnet"}


def test_download_returns_404_for_missing_job(client: TestClient) -> None:
	response = client.get(
		"/api/v1/consolidator/download/00000000000000000000000000000000/log"
	)

	assert response.status_code == 404