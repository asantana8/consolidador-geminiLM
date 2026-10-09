# Prompts para Implementação do Frontend (Angular 18) - Consolidador de Fontes para LLM

Este documento contém uma sequência modular de prompts projetados para serem executados por um assistente de código baseado em IA (Cursor, Claude, Copilot, ChatGPT). A abordagem é incremental para garantir testes adequados, arquitetura limpa e utilização dos recursos mais recentes do Angular 18 (Standalone Components e Signals).

---

## 🚀 Prompt 1: Configuração Inicial e Estrutura do Projeto Angular 18

```
Atue como um Desenvolvedor Senior Frontend especialista em Angular 18.
Siga as boas práticas de arquitetura limpa e modulada para criar a estrutura inicial da aplicação Web.

Tecnologias:
- Angular 18 (com Standalone Components habilitados)
- Angular Material 18 (MatStepper, MatCard, MatProgressBar, MatTable, MatIcon, MatButton)
- Angular Signals e RxJS
- Tailwind CSS / SCSS
- HttpClient para consumo de API REST

Por favor, crie/configure a seguinte estrutura de pastas e arquivos base:

src/app/
├── core/
│   ├── models/
│   │   └── consolidator.model.ts
│   ├── services/
│   │   └── consolidator.service.ts
│   └── interceptors/
│       └── error-handler.interceptor.ts
├── features/
│   └── consolidator/
│       ├── pages/
│       │   └── consolidator-page/
│       │       ├── consolidator-page.component.ts
│       │       ├── consolidator-page.component.html
│       │       └── consolidator-page.component.scss
│       └── components/
│           ├── wizard/
│           │   ├── consolidator-wizard.component.ts
│           │   ├── consolidator-wizard.component.html
│           │   └── consolidator-wizard.component.scss
│           └── dashboard/
│               ├── results-dashboard.component.ts
│               ├── results-dashboard.component.html
│               └── results-dashboard.component.scss
├── app.component.ts
├── app.config.ts
└── app.routes.ts

Gere os arquivos de modelo `consolidator.model.ts`, as configurações de provedores no `app.config.ts` (incluindo `provideHttpClient` e `provideAnimationsAsync`), e o estilo global Tailwind/SCSS.
```

---

## 📐 Prompt 2: Interfaces, Modelos e Serviço Angular (`ConsolidatorService`)

```
Com base na especificação da API FastAPI, crie as interfaces TypeScript em `core/models/consolidator.model.ts` e o serviço HTTP em `core/services/consolidator.service.ts`.

1. **Modelos TypeScript**:
   - `ProfileConfig` (extensions, subfolders, excluded_dirs, custom_sensitive_patterns)
   - `ConsolidateLocalRequest` (root_path, project_prefix, profile, custom_rules, strip_comments, security_scan)
   - `ExclusionDetail` (file_path, reason)
   - `ConsolidationJobResponse` (job_id, status, processed_files_count, added_files_count, excluded_files_count, download_consolidated_url, download_log_url, exclusions)
   - `PresetProfile` (id, name, extensions, subfolders)

2. **Serviço HTTP (`ConsolidatorService`)**:
   - Utilize `HttpClient` e gerencie estados reativos usando **Angular Signals** (`signal`, `computed`).
   - `getProfiles(): Observable<PresetProfile[]>`
   - `processLocal(payload: ConsolidateLocalRequest): Observable<ConsolidationJobResponse>`
   - `processUpload(file: File, config: ConsolidateLocalRequest): Observable<ConsolidationJobResponse>`
   - `downloadFile(url: str): void` (método auxiliar para acionar o download dos arquivos .txt e .log)

Adicione tratamento de erros resiliente e garanta que o serviço seja injetável no nível raiz (`providedIn: 'root'`).
```

---

## 🧙‍♂️ Prompt 3: Componente Assistente em Passos (`ConsolidatorWizardComponent`)

```
Implemente o componente Standalone `ConsolidatorWizardComponent` em `features/consolidator/components/wizard/`.

Requisitos do Layout/UX:
Utilize o `MatStepper` de forma responsiva para guiar o usuário em 4 etapas:

- **Etapa 1: Origem dos Dados**
  - Toggle de seleção entre: "Diretório Local do Servidor" e "Upload de Arquivo ZIP".
  - Se "Local": campo `matInput` para digitar o caminho absoluto (`root_path`).
  - Se "ZIP": área de Drag & Drop (`mat-file-upload`) para selecionar o arquivo compactado.

- **Etapa 2: Perfil e Parâmetros Agnósticos**
  - `mat-select` para escolha do perfil (Java, Angular, Postgres, Python, .NET, Custom).
  - Campos dinâmicos (chips do Material ou Inputs delimitados por vírgula) para:
    - Extensões a incluir (ex: `.java, .ts, .py`)
    - Subpastas-alvo (ex: `src, lib`)
    - Pastas a ignorar (ex: `node_modules, target, .git`)

- **Etapa 3: Regras de Segurança e Limpeza**
  - `mat-slide-toggle` para "Remover comentários de código".
  - `mat-slide-toggle` para "Sanitização de credenciais/chaves por Regex".
  - `mat-slide-toggle` para "Respeitar regras do .gitignore".
  - Campo de texto para prefixo personalizado do consolidado.

- **Etapa 4: Processamento**
  - Botão de confirmação e disparo da requisição HTTP.
  - Exibição de `mat-progress-bar` durante a execução.

Garanta validações com `ReactiveForms` (`FormGroup`, `Validators`) em cada passo do Stepper.
```

---

## 📊 Prompt 4: Painel de Resultados e Downloads (`ResultsDashboardComponent`)

```
Implemente o componente Standalone `ResultsDashboardComponent` em `features/consolidator/components/dashboard/`.

Requisitos de Interface e Recursos:
1. **Cards de Métricas Executivas (KPIs)**:
   - Exibir 3 cards com destaque visual (usando Tailwind e ícones Material):
     - Total de Arquivos Analisados
     - Arquivos Adicionados ao Consolidado (Verde)
     - Arquivos Bloqueados/Excluídos por Segurança (Vermelho/Laranja)

2. **Ações Rápidas de Download**:
   - Botão em destaque com ícone para "Baixar Código Consolidado (.TXT)".
   - Botão secundário para "Baixar Log de Exclusões (.LOG)".
   - Botão para "Novo Processamento" (reseta o fluxo).

3. **Tabela de Exclusões de Segurança (`mat-table`)**:
   - Tabela detalhando as exclusões com colunas:
     - Caminho do Arquivo (`file_path`)
     - Motivo do Bloqueio / Padrão Sensível Detectado (`reason`)
   - Suporte a paginação (`mat-paginator`) e campo de busca/filtro rápido na tabela.

Estilize com uma paleta moderna e limpa, compatível com modo claro e escuro.
```

---

## 🖼️ Prompt 5: Integração da Página Principal (`ConsolidatorPageComponent`)

```
Crie a página principal `ConsolidatorPageComponent` em `features/consolidator/pages/consolidator-page/`.

Requisitos:
1. Atuar como container inteligente para alternar o estado da tela entre o Wizard de entrada (`ConsolidatorWizardComponent`) e o Dashboard de resultados (`ResultsDashboardComponent`).
2. Utilizar **Angular Signals** para controlar o estado da view (`wizard` vs `results`).
3. Adicionar um cabeçalho moderno e informativo com o título da aplicação: **"Consolidador de Fontes para LLM / NotebookLM"** e uma breve descrição indicando os recursos de sanitização automática.
4. Integrar o roteamento em `app.routes.ts` definindo esta página como rota padrão (`/`).
```

---

## 🧪 Prompt 6: Testes Unitários de Componentes e Serviços

```
Escreva testes unitários usando `Jasmine` e `Karma` (ou `Jest`) para os componentes criados.

No arquivo `consolidator.service.spec.ts`:
1. Testar chamadas HTTP mockadas usando `HttpTestingController` para os métodos `processLocal` e `processUpload`.

No arquivo `consolidator-wizard.component.spec.ts`:
1. Validar a troca de campos no formulário ao alternar entre "Local" e "Upload ZIP".
2. Validar o bloqueio de avanço no Stepper caso os campos obrigatórios estejam inválidos.
3. Validar a emissão do evento de payload correto ao submeter o formulário.
```