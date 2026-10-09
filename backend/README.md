# Consolidador de Fontes para LLM

Backend inicial da API REST em FastAPI.

## Executar localmente

Com `uv` instalado:

```bash
uv sync --extra dev
uv run uvicorn app.main:app --reload
```

A documentacao interativa fica disponivel em <http://localhost:8000/docs>.

As origens CORS podem ser configuradas pela variavel `CORS_ORIGINS`, como uma
lista JSON, por exemplo: `["http://localhost:4200"]`.