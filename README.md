# ComplianceAI

**Plataforma de IA para análise de conformidade de contratos sob a legislação brasileira.**

Faça upload de um contrato em PDF ou DOCX e receba um relatório de conformidade apontando cláusulas problemáticas, riscos e recomendações, com fundamentação nos artigos de lei aplicáveis. A base cobre dez leis brasileiras na íntegra: Código Civil, CLT, CDC, LGPD, Marco Civil, Lei Anticorrupção, Lei de Licitações, Lei do Inquilinato, Lei das S.A. e Lei de Propriedade Industrial.

A análise combina **Claude AI** com **RAG** (busca semântica sobre uma base de legislação vetorizada), de modo que cada alerta cita o dispositivo legal em que se apoia em vez de depender apenas do conhecimento paramétrico do modelo.

---

## Índice

- [Como funciona](#como-funciona)
- [Escopo de trabalho](#escopo-de-trabalho)
- [Stack](#stack)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Começando](#começando)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [API](#api)
- [Testes](#testes)
- [Migrations](#migrations)
- [Deploy](#deploy)
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
| **Escopo de trabalho** | Alterna entre pessoal e equipe; documentos, regras, histórico e dashboard seguem a escolha |
| **Análise multi-legislação** | Regras configuráveis por severidade (`low` / `medium` / `high`), próprias ou da equipe |
| **RAG jurídico** | Base legal fatiada por artigo, com embeddings e busca por similaridade em pgvector |
| **Organizações** | Multi-tenant com membros e papéis (`owner` / `admin` / `member`) |
| **Templates de contrato** | Modelos reutilizáveis por tipo de contrato |
| **Workflows de aprovação** | Máquina de estados para revisão e aprovação de documentos |
| **Webhooks** | Notificações de eventos para sistemas externos |
| **Feedback e aprendizado** | Registro de feedback por alerta, agregado em "learnings" |
| **Dashboard** | Métricas consolidadas de conformidade |
| **Relatórios em PDF** | Geração server-side via WeasyPrint |

---

## Escopo de trabalho

Tudo no app acontece dentro de um escopo, escolhido no seletor do topo:

| | Pessoal | Equipe |
|---|---|---|
| Documentos | só os seus | de todos os membros |
| Regras aplicadas | globais + suas | globais + da equipe |
| Dashboard e histórico | seus dados | dados da equipe |
| Quem edita as regras | você | `owner` e `admin` |
| Quem exclui um documento | você | quem enviou, `owner` e `admin` |

As regras vivem em três escopos. As **globais** são as 11 padrão do sistema: todos as veem e ninguém as edita, mas cada escopo pode desativá-las para si, o que grava um registro em `rule_overrides` em vez de alterar a regra compartilhada. As demais pertencem a um usuário ou a uma organização.

Na análise, o escopo sai do próprio documento: se ele pertence a uma organização, valem as regras da equipe; senão, as pessoais de quem enviou.

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
│   │   │   ├── scope.py              # Escopo pessoal/equipe: acesso a documentos
│   │   │   ├── rule_scope.py         # Escopo das regras + overrides das globais
│   │   │   └── webhook_service.py
│   │   ├── scripts/          # Seeds de legislação e das regras padrão
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

Disponível em http://localhost:5173. Por padrão aponta para `http://localhost:8000`;
para usar outra API, defina `VITE_API_URL` (veja `compliance-frontend/.env.example`).

### 5. Entre

Em modo `development`, o boot cria um administrador de conveniência:

```
email:    admin@complianceai.com.br
senha:    senha123
```

> Vale **apenas em desenvolvimento**. Com `APP_ENV=production` esse usuário não é
> criado; cadastre o seu pela tela de registro ou por `POST /api/v1/auth/register`.

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
| `POST` | `/auth/login` | Login: retorna access + refresh token |
| `POST` | `/auth/refresh` | Renovar access token |
| `GET` | `/auth/me` | Dados do usuário autenticado |

### Documentos

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/documents/upload` | Upload e enfileiramento. Aceita `organization_id` para enviar à equipe |
| `GET` | `/documents` | Listar do escopo. Aceita `organization_id`, `status`, `search`, paginação |
| `GET` | `/documents/{id}` | Detalhes do documento |
| `GET` | `/documents/{id}/status` | Status da análise |
| `GET` | `/documents/{id}/report` | Relatório em JSON |
| `GET` | `/documents/{id}/report/html` | Relatório em HTML |
| `GET` | `/documents/{id}/report/pdf` | Relatório em PDF |
| `DELETE` | `/documents/{id}` | Excluir. Em equipe, só quem enviou ou os responsáveis |

### Regras de conformidade

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/rules` | Globais + as do escopo. Aceita `organization_id` e `active_only` |
| `GET` | `/rules/{id}` | Detalhar uma regra visível |
| `POST` | `/rules` | Criar. Sem `organization_id` cria pessoal; com ele, da equipe |
| `PATCH` | `/rules/{id}` | Editar. Só regras próprias ou da equipe que administra |
| `PATCH` | `/rules/{id}/toggle` | Ativar/desativar. Em regra global, grava um override do escopo |
| `DELETE` | `/rules/{id}` | Excluir. Regras globais não podem ser removidas |

### Legislação (RAG)

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/legislation/ingest` | Ingerir lei: faz chunking por artigo e gera embeddings |
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

A suíte roda contra um SQLite local (`aiosqlite`, arquivo `test.db`, ignorado pelo Git) e cobre autenticação, documentos, regras, organizações, templates, workflows, webhooks, dashboard, extração de documentos, o analisador de IA e a geração de relatórios.

---

## Migrations

```bash
# Aplicar migrations
docker compose exec api alembic upgrade head

# Criar nova migration
docker compose exec api alembic revision --autogenerate -m "descricao"
```

Em `APP_ENV=development` as tabelas são criadas automaticamente no startup. **Em produção, use Alembic**. O auto-create é desativado fora de `development`.

Em um banco novo de produção, depois das migrations, popule a base:

```bash
python -m app.scripts.ingest_planalto --todas   # baixa as 10 leis e gera embeddings
python -m app.scripts.seed_rules                # as 18 regras globais
```

O `ingest_planalto` busca o texto oficial no Planalto, fatia por artigo e gera os
embeddings, tudo num passo. Leva alguns minutos e custa poucos centavos de API.
Use `--listar` para ver o catálogo, `--lei <slug>` para uma só e `--dry-run` para
conferir a contagem de artigos sem gravar nada.

O `seed_legal_base` antigo continua no repositório, mas cobria 53 artigos escolhidos
a mão e foi substituído por este.

---

## Deploy

O projeto vai para o ar em dois lugares, porque o Vercel não roda containers de longa duração e o worker Celery precisa de um processo vivo:

| Parte | Onde | Como |
|---|---|---|
| Frontend | Vercel | Root Directory `compliance-frontend`, preset Vite, variável `VITE_API_URL` |
| API + worker | Railway (ou similar) | Dois serviços do mesmo `Dockerfile`, mudando o comando de início |
| Postgres | Railway | Imagem `pgvector/pgvector:pg15`, com volume em `/var/lib/postgresql/data` |
| Redis | Railway | Serviço gerenciado |

A ordem importa, porque cada lado precisa da URL do outro: publique a API, use a URL dela em `VITE_API_URL`, publique o frontend e então preencha `CORS_ORIGINS` no backend com o domínio gerado.

Pontos que costumam morder:

- O Postgres padrão não traz a extensão `vector`. Sem ela, o RAG não existe.
- `CORS_ORIGINS` precisa ser JSON válido. Uma variável definida e **vazia** derruba a API no boot.
- O `VITE_API_URL` entra no build, não na execução. Alterá-lo exige um novo deploy.
- `storage/uploads` é efêmero em plataformas de container. As análises persistem no banco, mas o arquivo original some a cada redeploy.

---

## Segurança

- **Autenticação**: JWT (access 1h, refresh 7d) com senhas em bcrypt
- **Autorização**: por escopo. No pessoal, cada usuário só enxerga os próprios documentos e regras; na equipe, só membros acessam, e apenas `owner` e `admin` alteram as regras
- **Exclusão de documento**: no escopo de equipe, restrita a quem enviou e aos responsáveis
- **Rate limiting**: SlowAPI nos endpoints sensíveis
- **Uploads**: validação de tipo e tamanho máximo configurável
- **LGPD**: `DELETE /documents/{id}` remove documento e análises associadas
- **Segredos**: carregados exclusivamente do `.env`, que está no `.gitignore`

> **Antes de expor em produção:** troque o `SECRET_KEY`, remova o usuário admin de seed, restrinja `CORS_ORIGINS` e defina `APP_ENV=production`.

---

## Custo estimado

Documento médio (~8.000 tokens de entrada, ~1.500 de saída): cerca de **US$ 0,04 por análise**, aproximadamente US$ 40 para 1.000 análises/mês, sem contar o custo (marginal) dos embeddings.
