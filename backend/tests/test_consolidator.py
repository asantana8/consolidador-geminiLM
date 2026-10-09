from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.consolidator import get_consolidator_service
from app.main import app
from app.services.consolidator_service import ConsolidatorService
from app.services.sanitization_service import SanitizationService


@pytest.mark.parametrize(
	("source", "language", "preserved", "removed"),
	[
		(
			'String url = "https://example.test/a//b"; // remove this\n'
			"int count = 1; /* and this */",
			"java",
			("https://example.test/a//b", "int count = 1;"),
			("remove this", "and this"),
		),
		(
			'const message = "// is text"; /* remove this */\n'
			"const ready: boolean = true; // remove this too",
			"typescript",
			('"// is text"', "const ready: boolean = true;"),
			("remove this",),
		),
		(
			"SELECT '-- not a comment' AS value; -- remove this\n",
			"sql",
			("SELECT '-- not a comment' AS value;",),
			("remove this",),
		),
	],
)
def test_remove_comments_for_java_typescript_and_sql(
	source: str,
	language: str,
	preserved: tuple[str, ...],
	removed: tuple[str, ...],
) -> None:
	result = SanitizationService().remove_comments(source, language)

	assert all(fragment in result for fragment in preserved)
	assert all(fragment not in result for fragment in removed)


def test_sensitive_filename_and_content_are_detected() -> None:
	sanitizer = SanitizationService()

	assert sanitizer.is_sensitive_filename(Path("config/.env"), []) == (
		True,
		"nome de arquivo sensivel: .env",
	)
	assert sanitizer.is_sensitive_content('password = "actual-secret-value"') == (
		True,
		"credential assignment",
	)


@pytest.fixture
def api_client(tmp_path: Path):
	service = ConsolidatorService(storage_root=tmp_path / "jobs")
	app.dependency_overrides[get_consolidator_service] = lambda: service
	try:
		with TestClient(app) as client:
			yield client
	finally:
		app.dependency_overrides.pop(get_consolidator_service, None)


def test_process_local_and_download_endpoints(
	api_client: TestClient,
	tmp_path: Path,
) -> None:
	project = tmp_path / "project"
	project.mkdir()
	(project / "main.py").write_text("print('hello')\n", encoding="utf-8")
	response = api_client.post(
		"/api/v1/consolidator/process-local",
		json={"root_path": str(project), "profile": "python"},
	)

	assert response.status_code == 200
	job_id = response.json()["job_id"]

	consolidated_response = api_client.get(
		f"/api/v1/consolidator/download/{job_id}/consolidated"
	)
	log_response = api_client.get(f"/api/v1/consolidator/download/{job_id}/log")

	assert consolidated_response.status_code == 200
	assert "print('hello')" in consolidated_response.text
	assert log_response.status_code == 200
	assert f"Job ID: {job_id}" in log_response.text