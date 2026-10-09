# Prompts para Implementação do Backend (FastAPI) - Consolidador de Fontes para LLM

Este documento contém uma sequência modular de prompts projetados para serem executados por um assistente de código baseado em IA (Cursor, Claude, Copilot, ChatGPT). A abordagem é incremental para garantir testes adequados e arquitetura limpa.

---

## 🚀 Prompt 1: Configuração Inicial e Estrutura do Projeto

```text
Atue como um Desenvolvedor Senior Python especialista em FastAPI.
Siga as boas práticas de Clean Architecture para criar a estrutura inicial do projeto de consolidação de código fonte.

Tecnologias:
- Python 3.11+
- FastAPI
- Uvicorn
- Pydantic v2
- uv ou poetry (gerenciamento de dependências)

Por favor, crie a seguinte estrutura de pastas e arquivos base:

backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── endpoints/
│   │           └── consolidator.py
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── consolidator.py
│   └── services/
│       ├── __init__.py
│       ├── consolidator_service.py
│       ├── sanitization_service.py
│       └── file_extractor_service.py
├── tests/
│   └── __init__.py
├── pyproject.toml
└── README.md

Gere o código inicial de `pyproject.toml`, `app/main.py` com suporte a CORS habilitado, e `app/core/config.py`.
```

---

## 🔒 Prompt 2: Serviços de Sanitização e Segurança (Core Logic)

```text
Com base na lógica de segurança do script legado, precisamos implementar o `SanitizationService` em `app/services/sanitization_service.py`.

Requisitos do Serviço:
1. `remove_comments(content: str) -> str`: Função capaz de remover comentários mantendo a integridade de strings (suporte a Java, TS/JS, SQL, HTML, CSS, C# e Python).
2. `is_sensitive_filename(file_path: Path, gitignore_patterns: list[str]) -> tuple[bool, str | None]`: Valida se o nome do arquivo ou pasta bate com padrões sensíveis (*.env, *.key, secrets.*, etc.) ou se é ignorado pelo .gitignore.
3. `is_sensitive_content(content: str) -> tuple[bool, str | None]`: Aplica validação Regex para identificar senhas, connection strings, tokens JWT e chaves privadas ativas.

Reaproveite e aprimore os padrões de Regex do script original:
- SENSITIVE_FILE_PATTERNS
- SENSITIVE_DIRS
- SENSITIVE_CONTENT_PATTERNS

Crie a classe `SanitizationService` com esses métodos e inclua docstrings completas.
```

---

## 📂 Prompt 3: Serviço Extrator e Leitor de Arquivos (Agnóstico)

```text
Crie o serviço `FileExtractorService` em `app/services/file_extractor_service.py`.

Este serviço deve ser 100% agnóstico e lidar com duas fontes de entrada:
1. **Diretório Local no Servidor**: Dado um `Path` absoluto, lê a estrutura do diretório respeitando subpastas configuradas.
2. **Arquivo Compactado (.ZIP)**: Dado um upload de arquivo ZIP em memória/disco temporário, extrai os arquivos temporariamente para processamento seguro.

Métodos necessários:
- `get_files_from_local_dir(root_path: Path, subfolders: list[str], extensions: list[str], excluded_dirs: list[str]) -> list[Path]`
- `extract_and_get_files_from_zip(zip_bytes: bytes, subfolders: list[str], extensions: list[str], excluded_dirs: list[str]) -> tuple[Path, list[Path]]`
- `read_gitignore_rules(root_path: Path) -> list[str]`

Certifique-se de tratar exceções de I/O e garantir a limpeza de arquivos temporários após extração de ZIPs.
```

---

## 📋 Prompt 4: Schemas Pydantic (DTOs da API)

```text
Defina os Schemas Pydantic v2 em `app/schemas/consolidator.py` para representar os contratos da API.

Crie as seguintes estruturas:
1. `ProfileConfig`:
   - `extensions`: list[str]
   - `subfolders`: list[str]
   - `excluded_dirs`: list[str]
   - `custom_sensitive_patterns`: Optional[list[str]]

2. `ConsolidateLocalRequest`:
   - `root_path`: str
   - `project_prefix`: str = "consolidado"
   - `profile`: str (ex: "java", "angular", "postgres", "custom")
   - `custom_rules`: Optional[ProfileConfig]
   - `strip_comments`: bool = True
   - `security_scan`: bool = True

3. `ExclusionDetail`:
   - `file_path`: str
   - `reason`: str

4. `ConsolidationJobResponse`:
   - `job_id`: str
   - `status`: str
   - `processed_files_count`: int
   - `added_files_count`: int
   - `excluded_files_count`: int
   - `download_consolidated_url`: str
   - `download_log_url`: str
   - `exclusions`: list[ExclusionDetail]

Adicione validações do Pydantic para garantir que `extensions` não sejam vazias e que `root_path` seja sanitizado.
```

---

## ⚙️ Prompt 5: Serviço Principal de Consolidação e Jobs

```text
Implemente o `ConsolidatorService` em `app/services/consolidator_service.py`.

Requisitos:
1. Gerenciar a consolidação completa unindo o `FileExtractorService` e o `SanitizationService`.
2. Armazenar os arquivos gerados (.txt consolidado e .log de exclusões) em um diretório de storage temporário (`/tmp/consolidator_jobs/{job_id}/`).
3. Formatar o cabeçalho do arquivo consolidado e os separadores por arquivo exatamente como no script original:
   - Divisores: `=` * 80
   - Metadados do arquivo: Path do arquivo, Nome do arquivo.
4. Retornar um objeto do tipo `ConsolidationJobResponse`.

Crie também um mecanismo para buscar e servir esses arquivos para download posterior dado um `job_id`.
```

---

## 🌐 Prompt 6: Endpoints REST FastAPI

```text
Implemente as rotas do FastAPI em `app/api/v1/endpoints/consolidator.py`.

Endpoints obrigatórios:
1. `POST /api/v1/consolidator/process-local`
   - Recebe `ConsolidateLocalRequest` em JSON.
   - Executa a consolidação de diretório local no servidor.

2. `POST /api/v1/consolidator/process-upload`
   - Recebe um arquivo `.zip` via `UploadFile` (Multipart Form Data) e uma string JSON com a configuração do perfil.
   - Extrai e consolida.

3. `GET /api/v1/consolidator/download/{job_id}/{file_type}`
   - `file_type`: "consolidated" (.txt) ou "log" (.log).
   - Retorna o arquivo usando `FileResponse` para download direto no navegador.

4. `GET /api/v1/consolidator/profiles`
   - Retorna os perfis pré-definidos padrão (Java, Angular, Postgres, Python, .NET).

Registre as rotas em `app/main.py`.
```

---

## 🧪 Prompt 7: Testes Unitários e de Integração

```text
Escreva os testes com `pytest` e `httpx` para a aplicação.

No arquivo `tests/test_consolidator.py`:
1. Teste unitário para `SanitizationService.remove_comments` com trechos de código Java, TypeScript e SQL.
2. Teste unitário para `SanitizationService.is_sensitive_filename` e `is_sensitive_content`.
3. Teste de integração para a rota `POST /api/v1/consolidator/process-local` usando um diretório temporário criado pelo `tmp_path` do pytest.
4. Teste de integração para a rota `GET /api/v1/consolidator/download/{job_id}/{file_type}`.
```