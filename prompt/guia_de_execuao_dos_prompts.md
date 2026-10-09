# Guia de Execução dos Prompts - Consolidador de Fontes para LLM

Este documento fornece o passo a passo detalhado sobre como utilizar a sequência de prompts e o arquivo de contexto (`AGENTS.md`) em assistentes de código baseados em IA (como Cursor, Claude Code, GitHub Copilot Workspace, ChatGPT ou Windsurf) para construir o projeto do início ao fim.

---

## 🛠️ 1. Preparação do Ambiente e Contexto

Antes de iniciar a execução dos prompts com a IA:

1. **Crie a pasta raiz do projeto no seu computador:**
   ```bash
   mkdir consolidador-lm-web
   cd consolidador-lm-web
   ```

2. **Adicione o arquivo de contexto:**
   * Crie um arquivo chamado `AGENTS.md` na raiz do projeto e cole o conteúdo das diretrizes do projeto nele.
   * Se estiver usando a IDE **Cursor** ou ferramentas similares, o assistente lerá automaticamente o `AGENTS.md` para entender as regras do projeto.

---

## ⚙️ 2. Sequência de Execução dos Prompts

> **IMPORTANTE:** Não envie todos os prompts de uma só vez para a IA. Execute **um prompt por vez**, aguarde a IA gerar o código e valide a execução antes de prosseguir para o próximo passo.

### Fase 1: Backend em Python (FastAPI)

1. **Execute o Prompt 1 (Setup Inicial Backend):**
   * A IA criará a estrutura de pastas do FastAPI, `pyproject.toml`, `app/main.py` e arquivos de configuração.
   * *Validação:* Execute `uvicorn app.main:app --reload` e acesse `http://localhost:8000/docs`.

2. **Execute o Prompt 2 (Serviços de Sanitização e Segurança):**
   * A IA criará o `SanitizationService` com as expressões regulares e funções de remoção de comentários.
   * *Validação:* Garanta que o serviço purgue comentários de Java, JS/TS, SQL e Python sem apagar trechos válidos.

3. **Execute o Prompt 3 (Serviço Extrator Agnóstico):**
   * A IA criará o `FileExtractorService` com suporte a diretórios locais e leitura de arquivos `.zip`.

4. **Execute o Prompt 4 (Schemas Pydantic v2):**
   * A IA criará os DTOs em `app/schemas/consolidator.py` com suporte a Pydantic v2.

5. **Execute o Prompt 5 (Serviço de Consolidação e Jobs):**
   * A IA criará o fluxo que une varredura + sanitização + gravação de arquivos temporários (`.txt` e `.log`).

6. **Execute o Prompt 6 (Endpoints REST FastAPI):**
   * A IA criará as rotas POST `/process-local`, POST `/process-upload` e GET `/download/{job_id}/{file_type}`.
   * *Validação:* Teste os endpoints interativos através do Swagger UI em `/docs`.

7. **Execute o Prompt 7 (Testes com Pytest):**
   * A IA gerará os testes unitários.
   * *Validação:* Execute `pytest` no terminal para garantir que todos os testes passem.

---

### Fase 2: Frontend em Angular 18

1. **Execute o Prompt 1 (Setup Inicial Frontend Angular 18):**
   * A IA inicializará a estrutura do Angular 18 Standalone com Tailwind CSS e Angular Material.
   * *Validação:* Execute `ng serve` e acesse `http://localhost:4200`.

2. **Execute o Prompt 2 (Modelos e Serviço Reativo com Signals):**
   * A IA criará as interfaces TypeScript e o `ConsolidatorService` para consumo das APIs do backend.

3. **Execute o Prompt 3 (Componente Wizard / Stepper):**
   * A IA criará o formulário em passos (`MatStepper`) para seleção de origem (Local vs ZIP), perfil e filtros de segurança.

4. **Execute o Prompt 4 (Componente Dashboard e Downloads):**
   * A IA criará a tela de resultados com os cards de métricas (KPIS), a tabela de exclusões e os botões de download.

5. **Execute o Prompt 5 (Página Principal e Roteamento):**
   * A IA conectará o Wizard e o Dashboard na página principal usando Signals para troca de telas.

6. **Execute o Prompt 6 (Testes Unitários no Frontend):**
   * A IA gerará os testes do Jasmine/Karma.
   * *Validação:* Execute `ng test` no terminal.

---

## 🔍 3. Dicas de Otimização no Uso da IA

* **Referência Cruzada:** Ao enviar um prompt para a IA, você pode citar os arquivos relevantes para a etapa (por exemplo: *"Com base no schema Pydantic criado no passo anterior..."*).
* **Correção Incremental:** Se a IA gerar algum código com erro, cole a mensagem de erro do console no chat do assistente pedindo a correção antes de avançar para o próximo prompt.
* **Segurança:** Caso precise adicionar novos padrões de exclusão de senhas ou chaves, edite diretamente o `SanitizationService` no backend ou atualize a lista no `AGENTS.md`.