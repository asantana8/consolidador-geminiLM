from pathlib import Path

import pytest

from app.services.sanitization_service import SanitizationService


@pytest.fixture
def sanitizer() -> SanitizationService:
    return SanitizationService()


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
            'ratio = left // right  # remove this\n'
            'label = "/* literal */"',
            "python",
            ("left // right", '"/* literal */"'),
            ("remove this",),
        ),
        (
            "-- remove this\nSELECT '-- still text';",
            "sql",
            ("SELECT '-- still text';",),
            ("remove this",),
        ),
        (
            "<p><!-- remove this --></p>",
            "html",
            ("<p>", "</p>"),
            ("remove this",),
        ),
        (
            'var text = @"// keep this"; // remove this\n',
            "csharp",
            ('@"// keep this"',),
            ("remove this",),
        ),
        (
            "a { color: #fff; --custom-property: 1; /* remove this */ }",
            "css",
            ("#fff", "--custom-property: 1"),
            ("remove this",),
        ),
        (
            "#app { background: url(https://cdn.example.test/image.png); }\n"
            "/* remove this */",
            "css",
            ("#app {", "https://cdn.example.test/image.png"),
            ("remove this",),
        ),
        (
            "<a href=https://example.test/page>open</a><!-- remove this -->",
            "html",
            ("href=https://example.test/page",),
            ("remove this",),
        ),
    ],
)
def test_remove_comments_preserves_literals_and_code(
    sanitizer: SanitizationService,
    source: str,
    language: str,
    preserved: tuple[str, ...],
    removed: tuple[str, ...],
) -> None:
    result = sanitizer.remove_comments(source, language)

    assert all(fragment in result for fragment in preserved)
    assert all(fragment not in result for fragment in removed)


def test_is_sensitive_filename_detects_sensitive_names_and_directories(
    sanitizer: SanitizationService,
) -> None:
    assert sanitizer.is_sensitive_filename(Path("config/.env.production"), []) == (
        True,
        "nome de arquivo sensivel: .env.production",
    )
    assert sanitizer.is_sensitive_filename(Path(".ssh/config"), []) == (
        True,
        "diretorio sensivel: .ssh",
    )
    assert sanitizer.is_sensitive_filename(Path("secrets.production/data.json"), []) == (
        True,
        "diretorio sensivel: secrets.production",
    )


def test_is_sensitive_filename_matches_gitignore_patterns(
    sanitizer: SanitizationService,
) -> None:
    assert sanitizer.is_sensitive_filename(
        Path("C:/work/project/build/output.txt"), ["/build/"]
    ) == (True, "ignorado por regra do .gitignore")


@pytest.mark.parametrize(
    "content",
    [
        'password = "actual-secret-value"',
        "DATABASE_URL=postgresql://app:actual-secret@db.example.test/app",
        "token = eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature123",
        "-----BEGIN PRIVATE KEY-----\n"
        "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n"
        "-----END PRIVATE KEY-----",
    ],
)
def test_is_sensitive_content_detects_credentials(
    sanitizer: SanitizationService,
    content: str,
) -> None:
    is_sensitive, reason = sanitizer.is_sensitive_content(content)

    assert is_sensitive is True
    assert reason is not None


def test_is_sensitive_content_ignores_placeholders(
    sanitizer: SanitizationService,
) -> None:
    assert sanitizer.is_sensitive_content('password = "your_password"') == (False, None)


def test_custom_sensitive_patterns_are_applied() -> None:
    sanitizer = SanitizationService([r"internal-[A-Z]{8}"])

    assert sanitizer.is_sensitive_content("key=internal-ABCDEFGH") == (
        True,
        "padrao sensivel personalizado",
    )