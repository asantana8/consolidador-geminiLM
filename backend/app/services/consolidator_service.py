"""Consolida fontes, aplica bloqueios de seguranca e persiste resultados de jobs."""

from __future__ import annotations

import shutil
import tempfile
import uuid
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Callable, Literal

from app.schemas.consolidator import (
	ConsolidateLocalRequest,
	ConsolidateUploadRequest,
	ConsolidationJobResponse,
	ExclusionDetail,
	ProfileConfig,
)
from app.services.file_extractor_service import FileExtractorService
from app.services.sanitization_service import SanitizationService


class ConsolidatorServiceError(RuntimeError):
	"""Indica erro de configuracao, processamento ou armazenamento de um job."""


class ConsolidatorService:
	"""Orquestra selecao de fontes, sanitizacao e armazenamento de jobs.

	Os resultados ficam em ``<tempdir>/consolidator_jobs/<job_id>/`` por padrao;
	em sistemas POSIX, o diretorio temporario normalmente e ``/tmp``. Os artefatos
	continuam disponiveis para download ate serem removidos por uma politica de
	retencao externa.
	"""

	SEPARATOR = "=" * 80
	DEFAULT_EXCLUDED_DIRS = [
		".git",
		".venv",
		"__pycache__",
		"build",
		"dist",
		"node_modules",
		"target",
		"venv",
	]
	DEFAULT_PROFILES = {
		"java": ProfileConfig(extensions=["java"], subfolders=[], excluded_dirs=DEFAULT_EXCLUDED_DIRS),
		"angular": ProfileConfig(
			extensions=["ts", "html", "scss", "css", "json"],
			subfolders=[],
			excluded_dirs=DEFAULT_EXCLUDED_DIRS,
		),
		"postgres": ProfileConfig(extensions=["sql"], subfolders=[], excluded_dirs=DEFAULT_EXCLUDED_DIRS),
		"python": ProfileConfig(extensions=["py"], subfolders=[], excluded_dirs=DEFAULT_EXCLUDED_DIRS),
		"dotnet": ProfileConfig(
			extensions=["cs", "csproj", "sln", "json", "config", "xml"],
			subfolders=[],
			excluded_dirs=DEFAULT_EXCLUDED_DIRS,
		),
	}

	def __init__(
		self,
		storage_root: Path | None = None,
		extractor_factory: Callable[[], FileExtractorService] | None = None,
		sanitizer: SanitizationService | None = None,
	) -> None:
		"""Configura o diretorio dos jobs e as dependencias do servico."""
		self.storage_root = (
			Path(storage_root)
			if storage_root is not None
			else Path(tempfile.gettempdir()) / "consolidator_jobs"
		)
		self._extractor_factory = extractor_factory or FileExtractorService
		self._sanitizer = sanitizer or SanitizationService()

	def process_local(self, request: ConsolidateLocalRequest) -> ConsolidationJobResponse:
		"""Consolida um diretorio local conforme o request validado."""
		root = Path(request.root_path).resolve(strict=True)
		config = self._resolve_profile(request.profile, request.custom_rules)
		extractor = self._extractor_factory()
		try:
			files = extractor.get_files_from_local_dir(
				root, config.subfolders, config.extensions, config.excluded_dirs
			)
			gitignore_patterns = extractor.read_gitignore_rules(root)
		except (OSError, ValueError, RuntimeError) as error:
			raise ConsolidatorServiceError(f"Falha ao selecionar arquivos locais: {error}") from error

		return self._create_job(
			files,
			root,
			request.profile,
			request.project_prefix,
			config,
			request.strip_comments,
			request.security_scan,
			gitignore_patterns,
		)

	def process_upload(self, zip_bytes: bytes, request: ConsolidateUploadRequest) -> ConsolidationJobResponse:
		"""Consolida um ZIP e limpa os arquivos extraidos apos gerar o job."""
		config = self._resolve_profile(request.profile, request.custom_rules)
		extractor = self._extractor_factory()
		try:
			with extractor:
				root, files = extractor.extract_and_get_files_from_zip(
					zip_bytes,
					config.subfolders,
					config.extensions,
					config.excluded_dirs,
				)
				return self._create_job(
					files,
					root,
					request.profile,
					request.project_prefix,
					config,
				request.strip_comments,
					request.security_scan,
					self._read_zip_gitignore_rules(zip_bytes),
				)
		except ConsolidatorServiceError:
			raise
		except Exception as error:
			raise ConsolidatorServiceError(f"Falha ao processar o arquivo ZIP: {error}") from error

	def get_job_file(self, job_id: str, file_type: Literal["consolidated", "log"]) -> Path:
		"""Retorna o caminho do consolidado ou do log para um UUID valido."""
		if file_type not in {"consolidated", "log"}:
			raise ValueError("file_type deve ser 'consolidated' ou 'log'")
		try:
			normalized_job_id = uuid.UUID(job_id).hex
		except (AttributeError, ValueError) as error:
			raise ValueError("job_id deve ser um UUID valido") from error

		try:
			storage_root = self.storage_root.resolve(strict=True)
			job_directory = (storage_root / normalized_job_id).resolve(strict=True)
		except OSError as error:
			raise FileNotFoundError("Job nao encontrado") from error
		if not job_directory.is_relative_to(storage_root):
			raise FileNotFoundError("Job nao encontrado")

		filename = "consolidated.txt" if file_type == "consolidated" else "exclusions.log"
		job_file = job_directory / filename
		if not job_file.is_file():
			raise FileNotFoundError(f"Arquivo do job nao encontrado: {filename}")
		return job_file

	@classmethod
	def list_profiles(cls) -> dict[str, dict[str, list[str] | None]]:
		"""Retorna os filtros padrao publicados pelo endpoint de perfis."""
		return {name: config.model_dump() for name, config in cls.DEFAULT_PROFILES.items()}

	def _create_job(
		self,
		files: list[Path],
		source_root: Path,
		profile: str,
		project_prefix: str,
		config: ProfileConfig,
		strip_comments: bool,
		security_scan: bool,
		gitignore_patterns: list[str],
	) -> ConsolidationJobResponse:
		self._validate_project_prefix(project_prefix)
		sanitizer = (
			SanitizationService(config.custom_sensitive_patterns)
			if security_scan and config.custom_sensitive_patterns
				else self._sanitizer
		)
		sections: list[str] = []
		exclusions: list[ExclusionDetail] = []
		processed_count = 0

		for file_path in files:
			processed_count += 1
			try:
				relative_path = file_path.relative_to(source_root).as_posix()
			except ValueError:
				exclusions.append(ExclusionDetail(file_path=str(file_path), reason="caminho fora da raiz"))
				continue

			is_sensitive, reason = sanitizer.is_sensitive_filename(file_path, gitignore_patterns)
			if is_sensitive:
				exclusions.append(ExclusionDetail(file_path=relative_path, reason=reason or "arquivo excluido"))
				continue

			try:
				content = file_path.read_text(encoding="utf-8-sig")
			except UnicodeDecodeError:
				exclusions.append(
					ExclusionDetail(file_path=relative_path, reason="arquivo nao esta codificado em UTF-8")
				)
				continue
			except OSError as error:
				exclusions.append(
					ExclusionDetail(file_path=relative_path, reason=f"falha de leitura: {type(error).__name__}")
				)
				continue

			is_sensitive, reason = sanitizer.is_sensitive_content(content)
			if is_sensitive:
				exclusions.append(
					ExclusionDetail(file_path=relative_path, reason=reason or "conteudo sensivel detectado")
				)
				continue

			if strip_comments:
				content = sanitizer.remove_comments(content, file_path.suffix)
			sections.append(self._format_file_section(relative_path, file_path.name, content))

		job_id = uuid.uuid4().hex
		job_directory = self.storage_root / job_id
		try:
			self.storage_root.mkdir(parents=True, exist_ok=True)
			job_directory.mkdir(mode=0o700)
			(job_directory / "consolidated.txt").write_text(
				self._format_consolidated_file(project_prefix, profile, sections),
				encoding="utf-8",
				newline="\n",
			)
			(job_directory / "exclusions.log").write_text(
				self._format_exclusion_log(job_id, processed_count, len(sections), exclusions),
				encoding="utf-8",
				newline="\n",
			)
		except OSError as error:
			shutil.rmtree(job_directory, ignore_errors=True)
			raise ConsolidatorServiceError(f"Falha ao armazenar o job: {error}") from error

		return ConsolidationJobResponse(
			job_id=job_id,
			status="completed",
			processed_files_count=processed_count,
			added_files_count=len(sections),
			excluded_files_count=len(exclusions),
			download_consolidated_url=f"/api/v1/consolidator/download/{job_id}/consolidated",
			download_log_url=f"/api/v1/consolidator/download/{job_id}/log",
			exclusions=exclusions,
		)

	@classmethod
	def _resolve_profile(cls, profile: str, custom_rules: ProfileConfig | None) -> ProfileConfig:
		if custom_rules is not None:
			return custom_rules.model_copy(deep=True)
		if profile == "custom":
			raise ConsolidatorServiceError("O perfil custom exige custom_rules")
		try:
			return cls.DEFAULT_PROFILES[profile].model_copy(deep=True)
		except KeyError as error:
			raise ConsolidatorServiceError(f"Perfil nao suportado: {profile}") from error

	@staticmethod
	def _validate_project_prefix(project_prefix: str) -> None:
		forbidden = set('/\\\0:*?"<>|')
		if (
			not project_prefix.strip()
			or project_prefix in {".", ".."}
			or any(character in forbidden for character in project_prefix)
			or project_prefix.endswith((".", " "))
		):
			raise ConsolidatorServiceError("project_prefix deve ser um nome seguro")

	@classmethod
	def _format_file_section(cls, relative_path: str, filename: str, content: str) -> str:
		return "\n".join(
			[
				cls.SEPARATOR,
				f"Path do arquivo: {relative_path}",
				f"Nome do arquivo: {filename}",
				cls.SEPARATOR,
				content.rstrip("\r\n"),
			]
		)

	@classmethod
	def _format_consolidated_file(cls, project_prefix: str, profile: str, sections: list[str]) -> str:
		header = "\n".join(
			[
				cls.SEPARATOR,
				"Consolidador de Fontes para LLM",
				f"Projeto: {project_prefix}",
				f"Perfil: {profile}",
				cls.SEPARATOR,
			]
		)
		return header + "\n\n" + "\n\n".join(sections) + "\n"

	@classmethod
	def _format_exclusion_log(
		cls,
		job_id: str,
		processed_count: int,
		added_count: int,
		exclusions: list[ExclusionDetail],
	) -> str:
		lines = [
			f"Job ID: {job_id}",
			f"Arquivos processados: {processed_count}",
			f"Arquivos adicionados: {added_count}",
			f"Arquivos excluidos: {len(exclusions)}",
		]
		if exclusions:
			lines.extend(["", "Exclusoes:"])
			lines.extend(f"{item.file_path} | {item.reason}" for item in exclusions)
		return "\n".join(lines) + "\n"

	@staticmethod
	def _read_zip_gitignore_rules(zip_bytes: bytes) -> list[str]:
		try:
			with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
				members = [info for info in archive.infolist() if not info.is_dir()]
				root_ignore = next(
					(
						info
						for info in members
						if PurePosixPath(info.filename.replace("\\", "/")).parts == (".gitignore",)
					),
					None,
				)
				if root_ignore is None:
					paths = [PurePosixPath(info.filename.replace("\\", "/")) for info in members]
					top_levels = {path.parts[0] for path in paths if path.parts}
					if len(top_levels) == 1 and all(len(path.parts) > 1 for path in paths):
						prefix = next(iter(top_levels))
						root_ignore = next(
							(
								info
								for info in members
								if PurePosixPath(info.filename.replace("\\", "/")).parts
								== (prefix, ".gitignore")
							),
							None,
						)
				if root_ignore is None:
					return []
				return archive.read(root_ignore).decode("utf-8-sig").splitlines()
		except (OSError, UnicodeError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
			raise ConsolidatorServiceError(f"Falha ao ler .gitignore do ZIP: {error}") from error