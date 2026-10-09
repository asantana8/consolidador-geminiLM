"""Modelos Pydantic v2 usados nos contratos da API de consolidacao."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class APIModel(BaseModel):
	"""Configuracao comum para os modelos expostos pela API."""

	model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProfileConfig(APIModel):
	"""Filtros de arquivos e regras de seguranca para um perfil."""

	extensions: list[str]
	subfolders: list[str]
	excluded_dirs: list[str]
	custom_sensitive_patterns: list[str] | None = None

	@field_validator("extensions")
	@classmethod
	def validate_extensions(cls, extensions: list[str]) -> list[str]:
		"""Normaliza extensoes e rejeita listas vazias ou valores invalidos."""
		normalized = [extension.strip().lower() for extension in extensions]
		if not normalized:
			raise ValueError("Informe ao menos uma extensao")

		for extension in normalized:
			if extension == "*":
				continue
			if not re.fullmatch(r"\.[a-z0-9][a-z0-9._+-]*", extension if extension.startswith(".") else f".{extension}"):
				raise ValueError(f"Extensao invalida: {extension}")

		return [extension if extension == "*" or extension.startswith(".") else f".{extension}" for extension in normalized]

	@field_validator("subfolders", "excluded_dirs")
	@classmethod
	def validate_relative_paths(cls, paths: list[str]) -> list[str]:
		"""Normaliza caminhos de filtro e impede caminhos absolutos ou traversal."""
		normalized_paths: list[str] = []
		for value in paths:
			normalized = value.replace("\\", "/")
			parts = PurePosixPath(normalized).parts
			if (
				not normalized
				or normalized.startswith("/")
				or re.match(r"^[A-Za-z]:", normalized)
				or ".." in parts
				or "\0" in normalized
			):
				raise ValueError("Os filtros devem conter somente caminhos relativos seguros")

			cleaned = "/".join(part for part in parts if part not in {"", "."})
			normalized_paths.append(cleaned or ".")
		return normalized_paths

	@field_validator("custom_sensitive_patterns")
	@classmethod
	def validate_custom_sensitive_patterns(
		cls,
		patterns: list[str] | None,
	) -> list[str] | None:
		"""Confirma que cada regra personalizada e uma expressao regular valida."""
		if patterns is None:
			return None
		if any(not pattern.strip() for pattern in patterns):
			raise ValueError("Padroes sensiveis personalizados nao podem ser vazios")
		for pattern in patterns:
			try:
				re.compile(pattern)
			except re.error as error:
				raise ValueError(f"Expressao regular invalida: {error}") from error
		return patterns


class ConsolidateLocalRequest(APIModel):
	"""Configuracao de uma solicitacao de consolidacao de diretorio local."""

	root_path: str
	project_prefix: str = "consolidado"
	profile: str
	custom_rules: ProfileConfig | None = None
	strip_comments: bool = True
	security_scan: bool = True

	@field_validator("root_path")
	@classmethod
	def sanitize_root_path(cls, root_path: str) -> str:
		"""Canonicaliza uma raiz existente e rejeita caminhos relativos/traversal.

		O caminho e interpretado no sistema operacional do servidor. A validacao
		exige que a raiz exista e seja um diretorio antes de aceitar a requisicao.
		"""
		value = root_path.strip()
		if not value or "\0" in value:
			raise ValueError("root_path deve ser um caminho valido")

		path = Path(value).expanduser()
		if not path.is_absolute():
			raise ValueError("root_path deve ser absoluto")
		if ".." in path.parts:
			raise ValueError("root_path nao pode conter segmentos '..'")

		try:
			resolved_path = path.resolve(strict=True)
		except (OSError, RuntimeError) as error:
			raise ValueError("root_path nao existe ou nao pode ser acessado") from error

		if not resolved_path.is_dir():
			raise ValueError("root_path deve apontar para um diretorio")
		return str(resolved_path)

	@field_validator("project_prefix")
	@classmethod
	def validate_project_prefix(cls, project_prefix: str) -> str:
		"""Impede separadores e caracteres que possam escapar do nome de saida."""
		value = project_prefix.strip()
		forbidden_characters = set('/\\\0:*?"<>|')
		if (
			not value
			or value in {".", ".."}
			or any(character in forbidden_characters for character in value)
			or value.endswith((".", " "))
		):
			raise ValueError("project_prefix deve ser um nome de arquivo seguro")
		return value

	@field_validator("profile")
	@classmethod
	def normalize_profile(cls, profile: str) -> str:
		"""Normaliza o identificador do perfil e rejeita valores vazios."""
		value = profile.strip().lower()
		if not value or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}", value):
			raise ValueError("profile deve ser um identificador valido")
		return value


class ConsolidateUploadRequest(APIModel):
	"""Configuracao enviada junto com o ZIP, sem caminho local de origem."""

	project_prefix: str = "consolidado"
	profile: str = "custom"
	custom_rules: ProfileConfig | None = None
	strip_comments: bool = True
	security_scan: bool = True

	@field_validator("project_prefix")
	@classmethod
	def validate_project_prefix(cls, project_prefix: str) -> str:
		"""Rejeita prefixos que possam escapar do nome do arquivo gerado."""
		value = project_prefix.strip()
		forbidden_characters = set('/\\\0:*?"<>|')
		if (
			not value
			or value in {".", ".."}
			or any(character in forbidden_characters for character in value)
			or value.endswith((".", " "))
		):
			raise ValueError("project_prefix deve ser um nome de arquivo seguro")
		return value

	@field_validator("profile")
	@classmethod
	def normalize_profile(cls, profile: str) -> str:
		"""Normaliza o identificador de perfil."""
		value = profile.strip().lower()
		if not value or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}", value):
			raise ValueError("profile deve ser um identificador valido")
		return value

	@model_validator(mode="after")
	def require_custom_rules(self) -> ConsolidateUploadRequest:
		"""Exige regras explicitas para o perfil customizado."""
		if self.profile == "custom" and self.custom_rules is None:
			raise ValueError("O perfil custom exige custom_rules")
		return self


class ExclusionDetail(APIModel):
	"""Descricao de um arquivo removido do processo de consolidacao."""

	file_path: str = Field(min_length=1)
	reason: str = Field(min_length=1)


class ConsolidationJobResponse(APIModel):
	"""Resultado de um job e URLs para baixar os arquivos gerados."""

	job_id: str = Field(min_length=1)
	status: str = Field(min_length=1)
	processed_files_count: int = Field(ge=0)
	added_files_count: int = Field(ge=0)
	excluded_files_count: int = Field(ge=0)
	download_consolidated_url: str = Field(min_length=1)
	download_log_url: str = Field(min_length=1)
	exclusions: list[ExclusionDetail]