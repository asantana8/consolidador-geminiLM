"""Detecta e remove conteudo que nao deve entrar em uma consolidacao."""

from __future__ import annotations

import re
from fnmatch import fnmatchcase
from pathlib import Path

from pathspec import PathSpec


SENSITIVE_FILE_PATTERNS = (
	".env",
	".env.*",
	"*.env",
	"*.key",
	"*.pem",
	"*.p12",
	"*.pfx",
	"*.p8",
	"*.ppk",
	"*.jks",
	"*.keystore",
	"id_rsa*",
	"id_ed25519*",
	"id_ecdsa*",
	"id_dsa*",
	"secrets",
	"secrets.*",
	"secret.*",
	"credentials",
	"credentials.*",
	"credential.*",
	"service-account*.json",
	"terraform.tfstate",
	"terraform.tfstate.*",
	".npmrc",
	".pypirc",
	".netrc",
)

SENSITIVE_DIRS = frozenset(
	{
		".aws",
		".azure",
		".docker",
		".gnupg",
		".kube",
		".ssh",
		"secrets",
	}
)

SENSITIVE_CONTENT_PATTERNS = (
	(
		"private key",
		re.compile(
			r"-----BEGIN (?P<key_type>(?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY)-----"
			r"\s*[A-Za-z0-9+/=\r\n]{32,}?\s*"
			r"-----END (?P=key_type)-----",
			re.IGNORECASE,
		),
	),
	(
		"JWT token",
		re.compile(
			r"\beyJ[A-Za-z0-9_-]{3,}\.[A-Za-z0-9_-]{3,}\.[A-Za-z0-9_-]{3,}\b"
		),
	),
	(
		"provider token",
		re.compile(
			r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
			r"xox[baprs]-[A-Za-z0-9-]{10,})\b"
		),
	),
	(
		"cloud access key",
		re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
	),
	(
		"connection string credentials",
		re.compile(
			r"\b(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis|amqps?|jdbc)"
			r"://[^\s:/@]+:[^\s/@]+@",
			re.IGNORECASE,
		),
	),
	(
		"credential assignment",
		re.compile(
			r"[\"']?\b(?:password|passwd|pwd|secret|client_secret|"
			r"api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token)"
			r"\b[\"']?\s*(?:=|:)\s*(?:"
			r"(?P<quote>[\"'])(?P<quoted>(?:\\.|(?! (?P=quote)).){4,})(?P=quote)"
			r"|(?P<bare>[^,\s;\"'`]{4,}))",
			re.IGNORECASE | re.VERBOSE,
		),
	),
)

_PLACEHOLDER_VALUES = frozenset(
	{
		"changeme",
		"change-me",
		"change_me",
		"example",
		"dummy",
		"none",
		"null",
		"placeholder",
		"redacted",
		"test",
		"your_password",
		"your_secret",
		"your_token",
	}
)
_PYTHON_DIRECTIVES = frozenset({"define", "elif", "else", "endif", "if", "ifdef", "ifndef", "include", "pragma", "region", "undef"})


class SanitizationService:
	"""Aplica regras de exclusao de arquivos e deteccao de credenciais.

	Os padroes definidos neste modulo sao um ponto de partida para seguranca;
	nao substituem um gerenciador de segredos nem validacao especifica do projeto.
	Padroes adicionais podem ser fornecidos na inicializacao para integrar regras
	configuradas pelo perfil de consolidacao.
	"""

	def __init__(self, custom_sensitive_patterns: list[str] | None = None) -> None:
		"""Inicializa o servico e compila expressoes regulares adicionais.

		Args:
			custom_sensitive_patterns: Expressoes regulares opcionais que, quando
				encontradas no conteudo, indicam dado sensivel. Expressoes invalidas
				geram ``re.error`` para que uma regra incorreta nao seja ignorada.
		"""
		self._custom_sensitive_patterns = [
			re.compile(pattern, re.IGNORECASE)
			for pattern in (custom_sensitive_patterns or [])
		]

	def remove_comments(self, content: str, language: str | None = None) -> str:
		"""Remove comentarios sem interpretar marcadores dentro de literais.

		Sao reconhecidos comentarios de linha Java/JavaScript/TypeScript/C#/SQL/
		Python, comentarios em bloco ``/* ... */`` e comentarios HTML ``<!-- ... -->``.
		Literais entre aspas simples, duplas, crases e aspas triplas sao copiados
		integralmente, incluindo URLs e marcadores de comentario. Comentarios
		multilinha conservam as quebras de linha e deixam um espaco para impedir
		que tokens adjacentes sejam unidos.

		Como a assinatura nao recebe extensao de arquivo, os casos ambiguos podem
		ser desambiguados pelo argumento opcional ``language`` (por exemplo,
		``"python"`` para preservar o operador ``//`` ou ``"css"`` para preservar
		propriedades iniciadas por ``--``). Sem ele, sao aplicadas heuristicas
		conservadoras para os usos comuns dessas sintaxes.

		Args:
			content: Texto-fonte a processar.
			language: Linguagem opcional, com ou sem ponto inicial na extensao.

		Returns:
			O texto com comentarios removidos e literais preservados.
		"""
		normalized_language = (language or "").lower().lstrip(".")
		python_mode = normalized_language in {"py", "python"}
		css_mode = normalized_language == "css"
		sql_mode = normalized_language in {"sql", "pgsql", "postgres"}
		output: list[str] = []
		index = 0
		length = len(content)

		while index < length:
			if content[index] in "'\"`":
				end = self._quoted_literal_end(content, index)
				output.append(content[index:end])
				index = end
				continue

			if content.startswith("<!--", index):
				end = content.find("-->", index + 4)
				end = length if end == -1 else end + 3
				output.append(self._comment_replacement(content[index:end]))
				index = end
				continue

			if content.startswith("/*", index):
				end = content.find("*/", index + 2)
				end = length if end == -1 else end + 2
				output.append(self._comment_replacement(content[index:end]))
				index = end
				continue

			if content.startswith("//", index) and normalized_language not in {
				"py",
				"python",
				"css",
				"html",
				"sql",
				"pgsql",
				"postgres",
			}:
				if self._is_slash_comment(content, index):
					end = self._line_comment_end(content, index + 2)
					output.append(self._comment_replacement(content[index:end]))
					index = end
					continue

			if content.startswith("--", index) and (
				sql_mode or (not normalized_language and self._is_sql_comment(content, index))
			):
				if sql_mode or self._is_sql_comment(content, index):
					end = self._line_comment_end(content, index + 2)
					output.append(self._comment_replacement(content[index:end]))
					index = end
					continue

			if content[index] == "#" and (
				python_mode
				or (not normalized_language and self._is_hash_comment(content, index))
			):
				directive = content[index + 1 :].lstrip().split(None, 1)[0].lower() if content[index + 1 :].strip() else ""
				if directive not in _PYTHON_DIRECTIVES:
					end = self._line_comment_end(content, index + 1)
					output.append(self._comment_replacement(content[index:end]))
					index = end
					continue

			output.append(content[index])
			index += 1

		return "".join(output)

	def is_sensitive_filename(
		self,
		file_path: Path,
		gitignore_patterns: list[str],
	) -> tuple[bool, str | None]:
		"""Informa se o caminho aponta para um arquivo que deve ser excluido.

		O nome do arquivo e os componentes de diretório sao comparados, sem
		diferenciar maiusculas de minusculas, com ``SENSITIVE_FILE_PATTERNS`` e
		``SENSITIVE_DIRS``. As regras Gitignore sao avaliadas com a sintaxe
		``gitwildmatch``; como o metodo nao recebe a raiz do repositorio, tambem
		sao testados os sufixos do caminho para caminhos absolutos.

		Args:
			file_path: Caminho do arquivo a verificar.
			gitignore_patterns: Linhas lidas de arquivos ``.gitignore``.

		Returns:
			Um par ``(sensivel, motivo)``. O motivo e ``None`` quando o caminho
			pode ser processado.
		"""
		parts = self._normalized_path_parts(file_path)
		if not parts:
			return False, None

		for directory in parts[:-1]:
			if directory.casefold() in SENSITIVE_DIRS:
				return True, f"diretorio sensivel: {directory}"
			if any(
				fnmatchcase(directory.casefold(), pattern.casefold())
				for pattern in SENSITIVE_FILE_PATTERNS
			):
				return True, f"diretorio sensivel: {directory}"

		filename = parts[-1].casefold()
		if any(fnmatchcase(filename, pattern.casefold()) for pattern in SENSITIVE_FILE_PATTERNS):
			return True, f"nome de arquivo sensivel: {parts[-1]}"

		if self._matches_gitignore(parts, gitignore_patterns):
			return True, "ignorado por regra do .gitignore"

		return False, None

	def is_sensitive_content(self, content: str) -> tuple[bool, str | None]:
		"""Detecta credenciais, tokens e chaves privadas no conteudo.

		Verifica atribuicoes de credenciais, credenciais embutidas em URLs,
		formatos comuns de JWT e tokens de provedores, IDs de chave AWS e blocos
		PEM de chave privada. Valores claramente usados como placeholders nao
		acionam a regra de atribuicao. Padroes adicionais configurados na
		inicializacao sao verificados depois dos padroes integrados.

		Args:
			content: Texto integral do arquivo.

		Returns:
			Um par ``(sensivel, motivo)`` com a primeira regra correspondente;
			retorna ``(False, None)`` quando nenhum padrao e encontrado.
		"""
		for reason, pattern in SENSITIVE_CONTENT_PATTERNS:
			match = pattern.search(content)
			if match is None:
				continue

			if reason == "credential assignment":
				value = match.group("quoted") or match.group("bare") or ""
				if self._is_placeholder(value):
					continue

			return True, reason

		for pattern in self._custom_sensitive_patterns:
			if pattern.search(content):
				return True, "padrao sensivel personalizado"

		return False, None

	@staticmethod
	def _quoted_literal_end(content: str, start: int) -> int:
		quote = content[start]
		delimiter = quote * 3 if quote in "'\"" and content.startswith(quote * 3, start) else quote
		is_verbatim = quote == '"' and start > 0 and content[start - 1] == "@"
		index = start + len(delimiter)

		while index < len(content):
			if is_verbatim and content.startswith('""', index):
				index += 2
				continue
			if not is_verbatim and content[index] == "\\":
				index += 2
				continue
			if content.startswith(delimiter, index):
				return index + len(delimiter)
			index += 1

		return len(content)

	@staticmethod
	def _line_comment_end(content: str, start: int) -> int:
		newline = content.find("\n", start)
		return len(content) if newline == -1 else newline

	@staticmethod
	def _comment_replacement(comment: str) -> str:
		return " " + "".join(character for character in comment if character in "\r\n")

	@staticmethod
	def _is_slash_comment(content: str, start: int) -> bool:
		line_start = max(content.rfind("\n", 0, start), content.rfind("\r", 0, start)) + 1
		prefix = content[line_start:start]
		following = content[start + 2 :]
		if not prefix.strip() or not following or following[0].isspace():
			return True

		previous = prefix.rstrip()[-1:]
		return previous in {";", "{", "}"}

	@staticmethod
	def _is_sql_comment(content: str, start: int) -> bool:
		following = content[start + 2 : start + 3]
		return not following or following.isspace()

	@staticmethod
	def _is_hash_comment(content: str, start: int) -> bool:
		line_start = max(content.rfind("\n", 0, start), content.rfind("\r", 0, start)) + 1
		prefix = content[line_start:start]
		following = content[start + 1 :]
		line = following.splitlines()[0] if following else ""

		if re.match(r"[0-9a-fA-F]{3,8}(?![\w-])", line):
			return False
		if re.match(r"[A-Za-z_][\w-]*\s*\{", line):
			return False
		if following.startswith("!"):
			return True
		if not prefix.strip():
			return not line or line[0].isspace()
		return prefix[-1:].isspace() and (not line or line[0].isspace())

	@staticmethod
	def _normalized_path_parts(file_path: Path) -> list[str]:
		normalized = str(file_path).replace("\\", "/")
		parts = [part for part in normalized.split("/") if part not in {"", "."}]
		if parts and re.fullmatch(r"[A-Za-z]:", parts[0]):
			parts.pop(0)
		return parts

	@staticmethod
	def _matches_gitignore(parts: list[str], patterns: list[str]) -> bool:
		usable_patterns = [pattern.rstrip("\r\n") for pattern in patterns if pattern.strip()]
		if not usable_patterns:
			return False

		spec = PathSpec.from_lines("gitwildmatch", usable_patterns)
		candidates = ["/".join(parts[index:]) for index in range(len(parts))]
		return any(spec.match_file(candidate) for candidate in candidates)

	@staticmethod
	def _is_placeholder(value: str) -> bool:
		normalized = value.strip().strip("\"'`{}<> ").casefold()
		if normalized in _PLACEHOLDER_VALUES:
			return True
		return normalized.startswith(("your_", "replace_me", "${", "$env:", "process.env."))