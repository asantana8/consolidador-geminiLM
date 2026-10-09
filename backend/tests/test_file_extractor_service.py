from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.services.file_extractor_service import FileExtractionError, FileExtractorService


def make_zip(entries: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_get_files_from_local_dir_applies_filters_and_exclusions(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "src" / "module").mkdir(parents=True)
    (root / "src" / "node_modules").mkdir()
    (root / "docs").mkdir()
    (root / "src" / "module" / "main.py").write_text("print('ok')", encoding="utf-8")
    (root / "src" / "node_modules" / "vendor.py").write_text("vendor", encoding="utf-8")
    (root / "docs" / "readme.md").write_text("docs", encoding="utf-8")

    files = FileExtractorService().get_files_from_local_dir(
        root,
        subfolders=["src"],
        extensions=["py"],
        excluded_dirs=["node_modules"],
    )

    assert files == [root / "src" / "module" / "main.py"]


def test_get_files_from_local_dir_rejects_relative_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absoluto"):
        FileExtractorService().get_files_from_local_dir(
            Path("relative"), [], [], []
        )

    with pytest.raises(ValueError, match="relativos seguros"):
        FileExtractorService().get_files_from_local_dir(
            tmp_path, ["../outside"], [], []
        )


def test_extract_and_get_files_from_zip_filters_and_cleans_up(tmp_path: Path) -> None:
    archive_bytes = make_zip(
        {
            "project/src/main.py": "print('ok')",
            "project/src/node_modules/vendor.py": "vendor",
            "project/docs/readme.md": "docs",
        }
    )
    temporary_root = tmp_path / "temporary"
    service = FileExtractorService(temporary_root=temporary_root)

    with service:
        extracted_root, files = service.extract_and_get_files_from_zip(
            archive_bytes,
            subfolders=["project/src"],
            extensions=[".py"],
            excluded_dirs=["node_modules"],
        )
        assert files == [extracted_root / "project" / "src" / "main.py"]
        assert files[0].read_text(encoding="utf-8") == "print('ok')"
        assert extracted_root.exists()

    assert not extracted_root.exists()


def test_extract_and_get_files_from_zip_rejects_zip_slip(tmp_path: Path) -> None:
    archive_bytes = make_zip({"../outside.txt": "unsafe"})
    service = FileExtractorService(temporary_root=tmp_path / "temporary")

    with pytest.raises(FileExtractionError, match="Caminho inseguro"):
        service.extract_and_get_files_from_zip(archive_bytes, [], [], [])

    assert list((tmp_path / "temporary").iterdir()) == []


def test_extract_and_get_files_from_zip_rejects_invalid_archive() -> None:
    with pytest.raises(FileExtractionError, match="ZIP"):
        FileExtractorService().extract_and_get_files_from_zip(b"not a zip", [], [], [])


def test_extract_and_get_files_from_zip_enforces_size_limit() -> None:
    archive_bytes = make_zip({"src/main.py": "12345"})
    service = FileExtractorService(max_uncompressed_size_bytes=4)

    with pytest.raises(FileExtractionError, match="limite"):
        service.extract_and_get_files_from_zip(archive_bytes, [], [], [])


def test_read_gitignore_rules_returns_lines_and_handles_missing_file(tmp_path: Path) -> None:
    service = FileExtractorService()
    (tmp_path / ".gitignore").write_text("# generated\n*.pyc\n!keep.py\n", encoding="utf-8")

    assert service.read_gitignore_rules(tmp_path) == ["# generated", "*.pyc", "!keep.py"]

    (tmp_path / ".gitignore").unlink()
    assert service.read_gitignore_rules(tmp_path) == []