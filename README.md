# ComplianceAI

**Plataforma de IA para análise de conformidade de contratos sob a legislação brasileira.**

Faça upload de um contrato em PDF ou DOCX e receba um relatório de conformidade apontando cláusulas problemáticas, riscos e recomendações — com fundamentação nos artigos de lei aplicáveis (LGPD, CDC, Código Civil, CLT, Marco Civil da Internet, Lei Anticorrupção e Lei de Licitações).

A análise combina **Claude AI** com **RAG** (busca semântica sobre uma base de legislação vetorizada), de modo que cada alerta cita o dispositivo legal em que se apoia em vez de depender apenas do conhecimento paramétrico do modelo.

---

## Índice

- [Como funciona](#como-funciona)
- [Stack](#stack)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Começando](#começando)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [API](#api)
- [Testes](#testes)
- [Migrations](#migrations)
- [Segurança](#segurança)

---

## Como funciona

```
Upload (PDF/DOCX)
       │
       ▼
Extração de texto ──── pdfplumber · python-docx · Tesseract OCR
       │
       ▼
Enfileiramento Celery (status: processing)
       │
       ├─▶ Carrega regras de conformidade ativas do banco
       ├─▶ RAG: busca semântica na base legal (pgvector + embeddings OpenAI)
       ├─▶ Monta prompt com contrato + regras + artigos de lei recuperados
       ├─▶ Claude AI analisa e retorna JSON estruturado
       ├─▶ Valida o schema da resposta
       └─▶ Persiste análise (status: analyzed)
       │
       ▼
Relatório: JSON · HTML · PDF (WeasyPrint)
```

### Principais capacidades

| Recurso | Descrição |
|---|---|
| **Análise multi-legislação** | Regras configuráveis por severidade (`low` / `medium` / `high`), ativáveis individualmente |
| **RAG jurídico** | Base legal fatiada por artigo, com embeddings e busca por similaridade em pgvector |
| **Organizações** | Multi-tenant com membros e papéis |
| **Templates de contrato** | Modelos reutilizáveis por tipo de contrato |
| **Workflows de aprovação** | Máquina de estados para revisão e aprovação de documentos |
| **Webhooks** | Notificações de eventos para sistemas externos |
| **Feedback e aprendizado** | Registro de feedback por alerta, agregado em "learnings" |
| **Dashboard** | Métricas consolidadas de conformidade |
| **Relatórios em PDF** | Geração server-side via WeasyPrint |

---

## Stack

**Backend**
- FastAPI · Python 3.11+
- PostgreSQL 15 + [pgvector](https://github.com/pgvector/pgvector)
- SQLAlchemy 2 (async) + Alembic
- Celery + Redis (processamento assíncrono)
- Anthropic Claude (análise) · OpenAI `text-embedding-3-small` (embeddings)
- JWT + bcrypt · SlowAPI (rate limiting) · structlog

**Frontend**
- React 19 + Vite 7
- lucide-react

---

## Estrutura do repositório

```
compliance-project/
├── compliance-backend/
│   ├── app/
│   │   ├── api/              # Rotas REST por domínio
│   │   │   ├── auth.py           # Registro, login, refresh, /me
│   │   │   ├── documents.py      # Upload, listagem, relatórios (JSON/HTML/PDF)
│   │   │   ├── rules.py          # CRUD de regras de conformidade
│   │   │   ├── legislation.py    # Ingestão e busca semântica na base legal
│   │   │   ├── organizations.py  # Organizações e membros
│   │   │   ├── templates.py      # Templates de contrato
│   │   │   ├── workflows.py      # Workflows de aprovação
│   │   │   ├── webhooks.py       # Configuração de webhooks
│   │   │   └── dashboard.py      # Métricas e feedback
│   │   ├── core/             # Config, database, security, logging, limiter
│   │   ├── models/           # Modelos SQLAlchemy
│   │   ├── schemas/          # Schemas Pydantic
│   │   ├── services/
│   │   │   ├── ai_analyzer.py        # Prompt engineering + chamada ao Claude
│   │   │   ├── rag_service.py        # Chunking por artigo + busca vetorial
│   │   │   ├── embedding_service.py  # Geração de embeddings
│   │   │   ├── document_extractor.py # PDF/DOCX/OCR
│   │   │   ├── report_generator.py   # HTML → PDF
│   │   │   └── webhook_service.py
│   │   ├── scripts/          # Seeds de legislação (LGPD, CDC, CLT, ...)
│   │   ├── workers/          # Tasks Celery
│   │   └── main.py
│   ├── alembic/              # Migrations
│   ├── tests/                # Pytest
│   ├── docker-compose.yml
│   └── Dockerfile
└── compliance-frontend/
    ├── src/
    └── vite.config.js
```

---

## Começando

### Pré-requisitos

- Docker + Docker Compose
- Node.js 20+ (para o frontend)
- Chaves de API: [Anthropic](https://console.anthropic.com/) e [OpenAI](https://platform.openai.com/api-keys)

### 1. Clone o repositório

```bash
git clone https://github.com/joaoeaa/complianceai.git
cd complianceai
```

### 2. Configure o backend

```bash
cd compliance-backend
cp .env.example .env
```

Edite o `.env` e preencha `ANTHROPIC_API_KEY` e `OPENAI_API_KEY`.

> O `.env` está no `.gitignore` e **nunca** deve ser commitado.

### 3. Suba os serviços

```bash
docker compose up -d
```

Isso sobe quatro containers: PostgreSQL (com pgvector), Redis, a API na porta `8000` e o worker Celery.

No primeiro boot em modo `development`, a aplicação cria as tabelas, popula as regras padrão e faz o seed da base legal automaticamente (idempotente).

Verifique:

- Swagger: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### 4. Suba o frontend

```bash
cd ../compliance-frontend
npm install
npm run dev
```

Disponível em http://localhost:5173. O frontend aponta para `http://localhost:8000/api/v1`.

### 5. Entre

Um usuário administrador é criado no seed:

```
email:    admin@complianceai.com.br
senha:    senha123
```

> Credenciais de desenvolvimento. Troque antes de qualquer uso real.

### Rodando o backend sem Docker

<details>
<summary>Passo a passo</summary>

Requer PostgreSQL 15+ com a extensão `vector`, Redis 7+ e, opcionalmente, Tesseract OCR para PDFs escaneados.

```bash
cd compliance-backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # configure DB, Redis e as chaves de API
createdb compliance_db

uvicorn app.main:app --reload --port 8000
```

Em outro terminal:

```bash
celery -A app.workers.tasks.celery_app worker --loglevel=info
```

</details>

---

## Variáveis de ambiente

| Variável | Descrição | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Chave da API Anthropic | **obrigatório** |
| `ANTHROPIC_MODEL` | Modelo usado na análise | `claude-sonnet-5` |
| `ANTHROPIC_MAX_TOKENS` | Teto de thinking + resposta | `8192` |
| `OPENAI_API_KEY` | Chave da API OpenAI (embeddings) | **obrigatório** |
| `OPENAI_EMBEDDING_MODEL` | Modelo de embedding | `text-embedding-3-small` |
| `DATABASE_URL` | Conexão PostgreSQL (async) | `localhost:5432` |
| `REDIS_URL` | Conexão Redis | `localhost:6379/0` |
| `SECRET_KEY` | Assinatura dos JWTs | **trocar em produção** |
| `APP_ENV` | `development` habilita auto-create e seeds | `development` |
| `MAX_FILE_SIZE_MB` | Tamanho máximo de upload | `10` |
| `CORS_ORIGINS` | Origens permitidas | `localhost:5173`, ... |

Lista completa em [`compliance-backend/.env.example`](compliance-backend/.env.example).

---

## API

Todas as rotas ficam sob o prefixo `/api/v1`. Documentação interativa em `/docs` (Swagger) e `/redoc`.

### Autenticação

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/auth/register` | Criar conta |
| `POST` | `/auth/login` | Login — retorna access + refresh token |
| `POST` | `/auth/refresh` | Renovar access token |
| `GET` | `/auth/me` | Dados do usuário autenticado |

### Documentos

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/documents/upload` | Upload e enfileiramento da análise |
| `GET` | `/documents` | Listar documentos do usuário |
| `GET` | `/documents/{id}` | Detalhes do documento |
| `GET` | `/documents/{id}/status` | Status da análise |
| `GET` | `/documents/{id}/report` | Relatório em JSON |
| `GET` | `/documents/{id}/report/html` | Relatório em HTML |
| `GET` | `/documents/{id}/report/pdf` | Relatório em PDF |
| `DELETE` | `/documents/{id}` | Excluir documento e análises |

### Regras de conformidade

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/rules` · `/rules/{id}` | Listar / detalhar |
| `POST` | `/rules` | Criar regra *(admin)* |
| `PATCH` | `/rules/{id}` | Editar regra *(admin)* |
| `PATCH` | `/rules/{id}/toggle` | Ativar/desativar *(admin)* |
| `DELETE` | `/rules/{id}` | Excluir regra *(admin)* |

### Legislação (RAG)

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/legislation/ingest` | Ingerir lei — faz chunking por artigo e gera embeddings |
| `GET` | `/legislation` · `/legislation/{id}` | Listar / detalhar |
| `POST` | `/legislation/search` | Busca semântica por similaridade |

### Organizações, templates, workflows e webhooks

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` `GET` `PATCH` `DELETE` | `/organizations[/{id}]` | CRUD de organizações |
| `POST` `PATCH` `DELETE` | `/organizations/{id}/members[/{user_id}]` | Gestão de membros |
| `POST` `GET` `PATCH` `DELETE` | `/templates[/{id}]` | CRUD de templates de contrato |
| `POST` `GET` | `/workflows[/{id}]` | Criar e consultar workflows |
| `POST` | `/workflows/{id}/transition` | Transicionar estado do workflow |
| `POST` `GET` `PATCH` `DELETE` | `/webhooks[/{id}]` | CRUD de webhooks |

### Dashboard e feedback

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/dashboard` | Métricas consolidadas |
| `POST` | `/dashboard/feedback` · `/feedback/batch` | Registrar feedback de análise |
| `GET` | `/dashboard/feedback/{analysis_id}` | Feedback de uma análise |
| `GET` | `/dashboard/feedback/alerts/{analysis_id}` | Feedback por alerta |
| `GET` | `/dashboard/feedback/learnings` | Aprendizados agregados |

### Exemplo

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@complianceai.com.br","password":"senha123"}' \
  | jq -r .access_token)

# Upload
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@contrato.pdf"

# Relatório
curl http://localhost:8000/api/v1/documents/1/report \
  -H "Authorization: Bearer $TOKEN"
```

---

## Testes

```bash
# Com Docker
docker compose exec api pytest

# Local
cd compliance-backend && pytest
```

A suíte roda contra um SQLite local (`aiosqlite`, arquivo `test.db` — ignorado pelo Git) e cobre autenticação, documentos, regras, organizações, templates, workflows, webhooks, dashboard, extração de documentos, o analisador de IA e a geração de relatórios.

---

## Migrations

```bash
# Aplicar migrations
docker compose exec api alembic upgrade head

# Criar nova migration
docker compose exec api alembic revision --autogenerate -m "descricao"
```

Em `APP_ENV=development` as tabelas são criadas automaticamente no startup. **Em produção, use Alembic** — o auto-create é desativado fora de `development`.

---

## Segurança

- **Autenticação** — JWT (access 1h, refresh 7d) com senhas em bcrypt
- **Autorização** — RBAC (`admin` / `user`); cada usuário só enxerga os próprios documentos
- **Rate limiting** — SlowAPI nos endpoints sensíveis
- **Uploads** — validação de tipo e tamanho máximo configurável
- **LGPD** — `DELETE /documents/{id}` remove documento e análises associadas
- **Segredos** — carregados exclusivamente do `.env`, que está no `.gitignore`

> **Antes de expor em produção:** troque o `SECRET_KEY`, remova o usuário admin de seed, restrinja `CORS_ORIGINS` e defina `APP_ENV=production`.

---

## Custo estimado

Documento médio (~8.000 tokens de entrada, ~1.500 de saída): cerca de **US$ 0,04 por análise** — aproximadamente US$ 40 para 1.000 análises/mês, sem contar o custo (marginal) dos embeddings.
