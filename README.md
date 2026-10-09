# Consolidador de Fontes para LLM

Aplicacao para selecionar fontes de codigo, detectar conteudo sensivel, remover comentarios configurados e gerar um arquivo consolidado com um log de exclusoes.

## Estado atual

- Backend FastAPI implementado em `backend/`.
- Testes unitarios e de integracao em `backend/tests/`.
- Prompts de implementacao e especificacoes tecnicas em `prompt/` e `spec/`.
- A implementacao do frontend Angular descrita nos documentos ainda nao esta incluida.

## Estrutura

```text
backend/   API FastAPI, servicos, schemas e testes
prompt/    Guias e prompts de implementacao
spec/      Especificacoes tecnicas do backend e frontend
AGENTS.md  Diretrizes de arquitetura e seguranca
```

## Backend

Requisitos: Python 3.11+ e `uv`.

```bash
cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload
```

A documentacao interativa fica em <http://localhost:8000/docs>.

Para executar os testes:

```bash
cd backend
uv run pytest
```

## Endpoints

- `POST /api/v1/consolidator/process-local`: processa um diretorio local acessivel pelo servidor.
- `POST /api/v1/consolidator/process-upload`: recebe um ZIP e uma configuracao de perfil em JSON.
- `GET /api/v1/consolidator/download/{job_id}/consolidated`: baixa o consolidado TXT.
- `GET /api/v1/consolidator/download/{job_id}/log`: baixa o log de exclusoes.
- `GET /api/v1/consolidator/profiles`: lista os perfis predefinidos.

Os jobs sao gravados no diretorio temporario do sistema, sob `consolidator_jobs/`. O armazenamento nao possui expiracao automatica nesta etapa; configure uma rotina de retencao antes de hospedar o servico continuamente.

## Seguranca

Arquivos de ambiente, chaves e credenciais locais sao excluidos pelo `.gitignore`. Essa regra protege apenas arquivos ainda nao rastreados pelo Git; revise o conteudo antes de publicar e nunca envie segredos para o repositorio.