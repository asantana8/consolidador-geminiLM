# AGENTS.md - Contexto e Diretrizes para Agentes de IA

Este repositório contém a evolução da ferramenta **Consolidador de Códigos para LLM/NotebookLM**, transformada de um script CLI legado em uma solução Web Full Stack composta por:
1. **Backend:** Python (FastAPI, Pydantic v2, Asyncio).
2. **Frontend:** Angular 18 (Standalone Components, Signals, Angular Material 18, Tailwind CSS).

Ao atuar neste projeto, siga estritamente as diretrizes de arquitetura, padrões de código e procedimentos operacionais descritos neste documento.

---

## 🎯 Objetivo do Sistema

A finalidade desta aplicação é varrer projetos de código-fonte, aplicar sanitizações rigorosas de segurança (remoção de senhas, tokens, arquivos sensíveis e comentários redundantes) e consolidar os fontes em um único arquivo de texto formatado (`.txt`), além de gerar um log detalhado de exclusões de segurança (`.log`).

---

## 🏗️ Diretrizes do Backend (Python / FastAPI)

### Estrutura de Pastas e Componentes
- Mantenha a organização em `backend/app/`:
  - `api/v1/endpoints/`: Rotas HTTP anotadas com Schemas Pydantic.
  - `core/`: Configurações globais (`config.py`), CORS, variáveis de ambiente.
  - `schemas/`: Modelos Pydantic v2 de entrada e saída.
  - `services/`: Regras de negócio desacopladas (Sanitização, Extração de Arquivos, Processamento de Jobs).

### Convenções e Boas Práticas
1. **Pydantic v2:** Utilize `type_adapters` e sintaxe `model_validator` / `field_validator` da versão v2. Não utilize sintaxe legada do Pydantic v1.
2. **Sanitização Agressiva:** O serviço `SanitizationService` deve ser agnóstico. Qualquer nova regra de segurança deve ser configurável via DTO (`ProfileConfig`).
3. **Assincronismo:** Operações de I/O em disco ou extração de ZIPs extensos devem ser delegadas para `BackgroundTasks` do FastAPI ou executadas de forma assíncrona para evitar o bloqueio do loop de eventos.
4. **Resets e Temporários:** Todos os uploads de arquivos `.zip` devem ser extraídos em diretórios temporários controlados (`tempfile.TemporaryDirectory`) e limpos após a conclusão do Job.

---

## 🅰️ Diretrizes do Frontend (Angular 18)

### Estrutura de Pastas e Componentes
- Mantenha a organização em `frontend/src/app/`:
  - `core/`: Modelos de dados TypeScript e Serviços Singleton (`providedIn: 'root'`).
  - `features/consolidator/`: Módulo funcional contendo componentes Standalone (Wizard, Dashboard, Page).

### Convenções e Boas Práticas
1. **Standalone Only:** Todos os componentes, diretivas e pipes DEVEM ser `standalone: true`. Não crie NgModules.
2. **Estado Reativo com Signals:** Prefira o uso de Angular **Signals** (`signal()`, `computed()`, `effect()`) para gerenciamento de estado e reatividade na UI ao invés de BehaviorSubjects, exceto onde o RxJS for estritamente necessário (operações HTTP complexas).
3. **Injeção de Dependências:** Utilize a função `inject()` ao invés de injeção via construtor:
   ```typescript
   private consolidatorService = inject(ConsolidatorService);
   ```
4. **Formulários Reativos:** Formulários complexos no Wizard de configuração devem ser construídos estritamente com `ReactiveForms` e `FormBuilder`.
5. **Acessibilidade e Layout:** Utilize componentes do Angular Material 18 integrados com utilitários do Tailwind CSS para estilização fluida e responsiva.

---

## 🔒 Princípios Fundamentais de Segurança (Não Negociáveis)

- **Sanitização em Memória/Disco:** Nunca grave strings contendo tokens/chaves expostas nos consolidados de saída (`.txt`). Se uma credencial for detectada por Regex, o arquivo correspondente DEVE ser bloqueado e enviado para o log de exclusões.
- **Path Traversal Prevention:** Ao manipular rotas locais (`root_path`), certifique-se de validar a existência do caminho e impedir ataques de *path traversal* (e.g., bloqueie referências com `..` descontrolados).

---

## 🧪 Estratégia de Testes

Ao implementar novas funcionalidades ou corrigir bugs, certifique-se de manter os testes atualizados:
- **Backend:** Execute suítes de teste com `pytest`.
- **Frontend:** Execute suítes de teste com `ng test`.

---

## 📄 Arquivos de Referência do Projeto
- `prompts_implementacao_backend.md`: Prompts modulares para geração/evolução do backend FastAPI.
- `prompts_implementacao_frontend.md`: Prompts modulares para geração/evolução do frontend Angular 18.
- `Especificacao_Tecnica_Backend_Python_FastAPI.docx`: Documentação técnica do backend.
- `Especificacao_Tecnica_Frontend_Angular_18.docx`: Documentação técnica do frontend.