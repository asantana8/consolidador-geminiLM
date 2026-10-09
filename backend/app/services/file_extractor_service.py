"""Le arquivos locais e arquivos ZIP sem permitir que membros escapem da raiz."""

from __future__ import annotations

import os
import re
import shutil
import stat
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from types import TracebackType
from typing import Self


class FileExtractionError(RuntimeError):
	"""Indica falha ao enumerar, ler ou extrair arquivos do projeto."""


class FileExtractorService:
	"""Seleciona fontes por subpasta e extensao em diretorios ou arquivos ZIP.

	Caminhos locais devem ser absolutos. Caminhos relativos em configuracoes de
	subpastas e diretorios excluidos sao sempre interpretados em relacao a raiz
	da fonte, e caminhos com ``..`` ou raiz absoluta sao rejeitados.

	Arquivos ZIP sao copiados manualmente para um diretorio temporario, sem usar
	``extractall``. Isso permite validar cada membro antes de gravar seus bytes.
	Os diretorios temporarios permanecem disponiveis ate ``cleanup()`` ou ate a
	saida de um bloco ``with`` envolvendo esta instancia.
	"""

	def __init__(
		self,
		temporary_root: Path | None = None,
		max_uncompressed_size_bytes: int | None = 1_000_000_000,
	) -> None:
		"""Inicializa as opcoes de armazenamento e limite de extracao.

		Args:
			temporary_root: Pasta opcional na qual criar os diretorios temporarios.
				Se omitida, e usado o local padrao do sistema operacional.
			max_uncompressed_size_bytes: Limite agregado dos arquivos selecionados
				em cada ZIP. Use ``None`` para desabilitar o limite.

		Raises:
			ValueError: Se o limite informado for zero ou negativo.
		"""
		if max_uncompressed_size_bytes is not None and max_uncompressed_size_bytes <= 0:
			raise ValueError("max_uncompressed_size_bytes deve ser positivo ou None")

		self._temporary_root = temporary_root
		self._max_uncompressed_size_bytes = max_uncompressed_size_bytes
		self._temporary_directories: list[TemporaryDirectory] = []

	def __enter__(self) -> Self:
		"""Retorna o servico para uso em um bloco ``with``."""
		return self

	def __exit__(
		self,
		exception_type: type[BaseException] | None,
		exception: BaseException | None,
		traceback: TracebackType | None,
	) -> bool:
		"""Remove todos os diretorios temporarios ao sair do bloco ``with``."""
		try:
			self.cleanup()
		except FileExtractionError:
			if exception is None:
				raise
		return False

	def get_files_from_local_dir(
		self,
		root_path: Path,
		subfolders: list[str],
		extensions: list[str],
		excluded_dirs: list[str],
	) -> list[Path]:
		"""Lista arquivos regulares de uma raiz local que correspondam aos filtros.

		Uma lista vazia de ``subfolders`` inclui toda a arvore; quando preenchida,
		somente arquivos dentro dessas pastas sao selecionados. Uma lista vazia
		de extensoes nao restringe o tipo de arquivo. Pastas excluidas sao
		removidas da busca antes que suas subarvores sejam percorridas.

		Links simbolicos para diretorios nao sao seguidos. Links para arquivos
		so sao retornados quando seu destino resolvido continua dentro da raiz.

		Args:
			root_path: Caminho absoluto do diretorio raiz a percorrer.
			subfolders: Pastas relativas permitidas, como ``["src", "tests"]``.
			extensions: Extensoes permitidas, com ou sem ponto inicial.
			excluded_dirs: Nomes ou caminhos relativos de diretorios excluidos.

		Returns:
			Lista ordenada de caminhos absolutos dos arquivos selecionados.

		Raises:
			ValueError: Se a raiz nao for absoluta ou algum filtro escapar dela.
			FileExtractionError: Se a raiz nao puder ser lida.
		"""
		root = self._resolve_root(root_path)
		selected_subfolders = self._normalize_configured_paths(subfolders, "subfolders")
		excluded_paths = self._normalize_configured_paths(excluded_dirs, "excluded_dirs")
		normalized_extensions = self._normalize_extensions(extensions)
		discovered: list[Path] = []

		def raise_walk_error(error: OSError) -> None:
			raise FileExtractionError(f"Falha ao percorrer {root}: {error}") from error

		try:
			for current_root, directory_names, filenames in os.walk(
				root,
				topdown=True,
				onerror=raise_walk_error,
				followlinks=False,
			):
				current_path = Path(current_root)
				relative_directory = current_path.relative_to(root).parts
				directory_names[:] = sorted(
					directory
					for directory in directory_names
					if not (current_path / directory).is_symlink()
					and not self._is_excluded_directory(
						(*relative_directory, directory), excluded_paths
					)
				)

				for filename in sorted(filenames):
					file_path = current_path / filename
					relative_parts = (*relative_directory, filename)
					if not self._matches_filters(
						relative_parts,
						selected_subfolders,
						normalized_extensions,
						excluded_paths,
					):
						continue

					try:
						if not file_path.is_file():
							continue
						resolved_file = file_path.resolve(strict=True)
					except OSError as error:
						raise FileExtractionError(
							f"Falha ao inspecionar {file_path}: {error}"
						) from error

					if resolved_file.is_relative_to(root):
						discovered.append(file_path)
		except FileExtractionError:
			raise
		except OSError as error:
			raise FileExtractionError(f"Falha ao percorrer {root}: {error}") from error

		return discovered

	def extract_and_get_files_from_zip(
		self,
		zip_bytes: bytes,
		subfolders: list[str],
		extensions: list[str],
		excluded_dirs: list[str],
	) -> tuple[Path, list[Path]]:
		"""Extrai membros selecionados de um ZIP para armazenamento temporario.

		Cada nome do arquivo e validado para rejeitar caminhos absolutos, letras
		de unidade e segmentos ``..``. Links simbolicos e membros especiais sao
		ignorados. Os bytes sao copiados em blocos e respeitam o limite agregado
		configurado no construtor.

		O diretorio retornado e mantido vivo pelo servico. Chame ``cleanup()`` ao
		terminar o processamento ou use o servico em um bloco ``with`` para
		garantir a remocao mesmo quando ocorrer uma excecao.

		Args:
			zip_bytes: Conteudo binario completo do arquivo ZIP.
			subfolders: Pastas relativas permitidas dentro do arquivo.
			extensions: Extensoes permitidas, com ou sem ponto inicial.
			excluded_dirs: Nomes ou caminhos relativos de diretorios excluidos.

		Returns:
			Tupla com a raiz temporaria e os caminhos dos arquivos extraidos.

		Raises:
			ValueError: Se algum filtro escapar da raiz.
			FileExtractionError: Se o ZIP for invalido, inseguro, grande demais ou
				nao puder ser lido/escrito.
		"""
		selected_subfolders = self._normalize_configured_paths(subfolders, "subfolders")
		excluded_paths = self._normalize_configured_paths(excluded_dirs, "excluded_dirs")
		normalized_extensions = self._normalize_extensions(extensions)

		try:
			if self._temporary_root is not None:
				self._temporary_root.mkdir(parents=True, exist_ok=True)
			temporary_directory = tempfile.TemporaryDirectory(
				prefix="consolidador-zip-",
				dir=str(self._temporary_root) if self._temporary_root else None,
			)
		except OSError as error:
			raise FileExtractionError(f"Nao foi possivel criar diretorio temporario: {error}") from error

		extraction_root = Path(temporary_directory.name).resolve()
		extracted_files: list[Path] = []
		extracted_names: set[str] = set()
		total_bytes_written = 0

		try:
			with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
				for member in archive.infolist():
					parts = self._safe_archive_parts(member.filename)
					if not parts or member.is_dir():
						continue

					member_type = stat.S_IFMT(member.external_attr >> 16)
					if member_type not in {0, stat.S_IFREG}:
						continue

					if not self._matches_filters(
						parts,
						selected_subfolders,
						normalized_extensions,
						excluded_paths,
					):
						continue

					if (
						self._max_uncompressed_size_bytes is not None
						and total_bytes_written + member.file_size
						> self._max_uncompressed_size_bytes
					):
						raise FileExtractionError(
							"O ZIP excede o limite de bytes descompactados selecionados"
						)

					normalized_name = "/".join(parts).casefold()
					if normalized_name in extracted_names:
						raise FileExtractionError(
							f"O ZIP contem caminhos duplicados: {member.filename}"
						)

					destination = extraction_root.joinpath(*parts)
					if not destination.resolve(strict=False).is_relative_to(extraction_root):
						raise FileExtractionError(
							f"O caminho do ZIP escapa da raiz: {member.filename}"
						)
					destination.parent.mkdir(parents=True, exist_ok=True)

					member_bytes_written = 0
					with archive.open(member, "r") as source, destination.open("xb") as target:
						while chunk := source.read(1024 * 1024):
							member_bytes_written += len(chunk)
							if (
								self._max_uncompressed_size_bytes is not None
								and total_bytes_written + member_bytes_written
								> self._max_uncompressed_size_bytes
							):
								raise FileExtractionError(
									"O ZIP excede o limite de bytes descompactados selecionados"
								)
							target.write(chunk)

					total_bytes_written += member_bytes_written
					extracted_names.add(normalized_name)
					extracted_files.append(destination)

			self._temporary_directories.append(temporary_directory)
			return extraction_root, extracted_files
		except Exception as error:
			temporary_directory.cleanup()
			if isinstance(error, FileExtractionError):
				raise
			if isinstance(error, (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError, ValueError)):
				raise FileExtractionError(f"Falha ao extrair arquivo ZIP: {error}") from error
			raise

	def read_gitignore_rules(self, root_path: Path) -> list[str]:
		"""Le as regras do arquivo ``.gitignore`` diretamente na raiz do projeto.

		Linhas vazias e comentarios sao mantidos para que o consumidor possa
		delegar a interpretacao integral da sintaxe Gitignore a uma biblioteca
		compativel, como ``pathspec``.

		Args:
			root_path: Caminho absoluto do diretorio raiz do projeto.

		Returns:
			Linhas do arquivo ``.gitignore`` ou uma lista vazia se ele nao existir.

		Raises:
			ValueError: Se a raiz nao for absoluta.
			FileExtractionError: Se a raiz ou o arquivo nao puder ser lido.
		"""
		root = self._resolve_root(root_path)
		gitignore_path = root / ".gitignore"
		try:
			return gitignore_path.read_text(encoding="utf-8-sig").splitlines()
		except FileNotFoundError:
			return []
		except (OSError, UnicodeError) as error:
			raise FileExtractionError(f"Falha ao ler {gitignore_path}: {error}") from error

	def cleanup(self) -> None:
		"""Remove todos os diretorios temporarios criados por esta instancia.

		A operacao e segura para ser chamada mais de uma vez. Tenta limpar todos
		os diretorios mesmo se um deles falhar e, ao final, informa os erros.

		Raises:
			FileExtractionError: Se algum diretorio temporario nao puder ser removido.
		"""
		errors: list[OSError] = []
		temporary_directories, self._temporary_directories = (
			self._temporary_directories,
			[],
		)
		for temporary_directory in reversed(temporary_directories):
			try:
				temporary_directory.cleanup()
			except OSError as error:
				errors.append(error)

		if errors:
			raise FileExtractionError(
				f"Falha ao remover {len(errors)} diretorio(s) temporario(s): {errors[0]}"
			) from errors[0]

	@staticmethod
	def _resolve_root(root_path: Path) -> Path:
		if not root_path.is_absolute():
			raise ValueError("root_path deve ser um caminho absoluto")
		try:
			root = root_path.resolve(strict=True)
			if not root.is_dir():
				raise NotADirectoryError(f"Nao e um diretorio: {root}")
			return root
		except (OSError, RuntimeError) as error:
			raise FileExtractionError(f"Raiz do projeto invalida: {root_path}: {error}") from error

	@staticmethod
	def _normalize_configured_paths(paths: list[str], setting_name: str) -> list[str]:
		normalized_paths: list[str] = []
		for path in paths:
			normalized = path.replace("\\", "/")
			components = normalized.split("/")
			if (
				normalized.startswith("/")
				or re.match(r"^[A-Za-z]:", normalized)
				or ".." in components
				or "\0" in normalized
			):
				raise ValueError(f"{setting_name} deve conter somente caminhos relativos seguros")

			cleaned = "/".join(component for component in components if component not in {"", "."})
			normalized_paths.append(cleaned.casefold())
		return normalized_paths

	@staticmethod
	def _normalize_extensions(extensions: list[str]) -> tuple[str, ...]:
		normalized: list[str] = []
		for extension in extensions:
			value = extension.strip().casefold()
			if value in {"", "*", ".*"}:
				if value in {"*", ".*"}:
					return ()
				continue
			normalized.append(value if value.startswith(".") else f".{value}")
		return tuple(normalized)

	@staticmethod
	def _safe_archive_parts(member_name: str) -> tuple[str, ...]:
		normalized = member_name.replace("\\", "/")
		path = PurePosixPath(normalized)
		parts = tuple(part for part in path.parts if part not in {"", "."})
		if (
			not parts
			or path.is_absolute()
			or re.match(r"^[A-Za-z]:", parts[0])
			or ".." in parts
			or "\0" in normalized
		):
			raise FileExtractionError(f"Caminho inseguro no arquivo ZIP: {member_name}")
		return parts

	@classmethod
	def _matches_filters(
		cls,
		relative_parts: tuple[str, ...],
		subfolders: list[str],
		extensions: tuple[str, ...],
		excluded_dirs: list[str],
	) -> bool:
		if cls._is_excluded_directory(relative_parts[:-1], excluded_dirs):
			return False

		relative_parent = "/".join(relative_parts[:-1]).casefold()
		if subfolders and not any(
			folder == ""
			or relative_parent == folder
			or relative_parent.startswith(f"{folder}/")
			for folder in subfolders
		):
			return False

		filename = relative_parts[-1].casefold()
		return not extensions or any(filename.endswith(extension) for extension in extensions)

	@staticmethod
	def _is_excluded_directory(
		relative_directory_parts: tuple[str, ...],
		excluded_dirs: list[str],
	) -> bool:
		if not relative_directory_parts or not excluded_dirs:
			return False

		normalized_parts = tuple(part.casefold() for part in relative_directory_parts)
		relative_directory = "/".join(normalized_parts)
		return any(
			excluded in normalized_parts
			or relative_directory == excluded
			or relative_directory.startswith(f"{excluded}/")
			for excluded in excluded_dirs
		)