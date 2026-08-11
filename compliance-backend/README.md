# ComplianceAI — Backend

**Plataforma de IA para Compliance e Auditoria de Documentos Contratuais**

Backend completo com FastAPI, PostgreSQL, Celery/Redis e integração com Claude AI (Anthropic).

---

## 🏗️ Arquitetura

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│   Frontend   │────▶│  FastAPI     │────▶│  PostgreSQL  │
│   (React)    │◀────│  Backend     │◀────│  Database    │
└─────────────┘     └──────┬──────┘     └──────────────┘
                           │
                    ┌──────▼──────┐     ┌──────────────┐
                    │   Celery     │────▶│  Claude AI   │
                    │   Worker     │◀────│  (Anthropic) │
                    └──────┬──────┘     └──────────────┘
                           │
                    ┌──────▼──────┐
                    │    Redis     │
                    │   (Broker)   │
                    └─────────────┘
```

## 📁 Estrutura do Projeto

```
compliance-backend/
├── app/
│   ├── api/                  # Rotas da API REST
│   │   ├── auth.py           # Login, registro, JWT
│   │   ├── documents.py      # Upload, listagem, relatórios
│   │   └── rules.py          # CRUD de regras de conformidade
│   ├── core/
│   │   ├── config.py         # Settings (pydantic-settings)
│   │   ├── database.py       # SQLAlchemy async engine
│   │   └── security.py       # JWT + bcrypt
│   ├── models/
│   │   └── __init__.py       # User, Document, Rule, Analysis
│   ├── schemas/
│   │   └── __init__.py       # Pydantic schemas (request/response)
│   ├── services/
│   │   ├── ai_analyzer.py    # Integração Claude AI + prompt engineering
│   │   └── document_extractor.py  # Extração PDF/DOCX
│   ├── workers/
│   │   └── tasks.py          # Celery tasks (processamento async)
│   └── main.py               # FastAPI app entry point
├── docker-compose.yml        # PostgreSQL + Redis + API + Worker
├── Dockerfile
├── requirements.txt
├── alembic.ini
└── .env.example
```

## 🚀 Setup Rápido (Docker)

### 1. Clone e configure

```bash
cp .env.example .env
# Edite .env e adicione sua ANTHROPIC_API_KEY
```

### 2. Suba tudo com Docker Compose

```bash
docker compose up -d
```

Isso sobe: PostgreSQL, Redis, API (porta 8000) e Celery Worker.

### 3. Acesse

- **API Docs (Swagger):** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

---

## 🚀 Setup Manual (sem Docker)

### 1. Pré-requisitos

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Tesseract OCR (opcional, para PDFs escaneados)

### 2. Instale dependências

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 3. Configure ambiente

```bash
cp .env.example .env
# Edite .env com suas credenciais de DB, Redis e Anthropic
```

### 4. Crie o banco

```bash
createdb compliance_db
# Ou via psql: CREATE DATABASE compliance_db;
```

### 5. Inicie a API

```bash
uvicorn app.main:app --reload --port 8000
```

### 6. Inicie o Celery Worker (em outro terminal)

```bash
celery -A app.workers.tasks.celery_app worker --loglevel=info
```

---

## 📡 API Endpoints

### Autenticação

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/v1/auth/register` | Criar conta |
| POST | `/api/v1/auth/login` | Login (retorna JWT) |
| POST | `/api/v1/auth/refresh` | Renovar token |
| GET | `/api/v1/auth/me` | Dados do usuário logado |

### Documentos

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/v1/documents/upload` | Upload + iniciar análise |
| GET | `/api/v1/documents` | Listar documentos |
| GET | `/api/v1/documents/{id}` | Detalhes do documento |
| GET | `/api/v1/documents/{id}/report` | Relatório completo |
| GET | `/api/v1/documents/{id}/status` | Status da análise |
| DELETE | `/api/v1/documents/{id}` | Excluir (LGPD) |

### Regras

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/v1/rules` | Listar regras |
| POST | `/api/v1/rules` | Criar regra (admin) |
| PATCH | `/api/v1/rules/{id}` | Editar regra (admin) |
| DELETE | `/api/v1/rules/{id}` | Excluir regra (admin) |
| PATCH | `/api/v1/rules/{id}/toggle` | Ativar/desativar (admin) |

---

## 🔒 Segurança

- **Autenticação:** JWT com bcrypt (custo 12) para senhas
- **Tokens:** Access token (1h) + Refresh token (7d)
- **RBAC:** Admin vs User (admin para gerenciar regras)
- **Isolamento:** Cada usuário só acessa seus documentos
- **LGPD:** Endpoint de exclusão (direito ao esquecimento)

---

## 🧠 Fluxo de Análise com IA

```
Upload PDF/DOCX
       │
       ▼
Salva no disco + DB (status: "uploaded")
       │
       ▼
Celery Task inicia (status: "processing")
       │
       ├──▶ 1. Extrair texto (pdfplumber / python-docx)
       ├──▶ 2. Buscar regras ativas do banco
       ├──▶ 3. Montar prompt dinâmico
       ├──▶ 4. Enviar para Claude AI
       ├──▶ 5. Validar JSON de resposta
       └──▶ 6. Salvar análise no banco (status: "analyzed")
               │
               ▼
       Frontend exibe relatório
```

---

## 💰 Custo Estimado por Análise

- Documento médio: ~8.000 tokens entrada + ~1.500 tokens saída
- **Custo por análise: ~$0.04 USD**
- 1.000 análises/mês: ~$40 USD

---

## 🔧 Variáveis de Ambiente

| Variável | Descrição | Default |
|----------|-----------|---------|
| `ANTHROPIC_API_KEY` | Chave da API Anthropic | (obrigatório) |
| `ANTHROPIC_MODEL` | Modelo do Claude | claude-sonnet-4-20250514 |
| `DATABASE_URL` | String de conexão PostgreSQL | localhost |
| `REDIS_URL` | URL do Redis | localhost:6379 |
| `SECRET_KEY` | Chave para JWT | (trocar em prod!) |
| `MAX_FILE_SIZE_MB` | Tamanho máximo de upload | 10 |

---

## 🧪 Testando

```bash
# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@complianceai.com.br","password":"senha123"}'

# Upload (use o token retornado)
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer SEU_TOKEN" \
  -F "file=@contrato.pdf"

# Verificar status
curl http://localhost:8000/api/v1/documents/{id}/status?task_id=TASK_ID \
  -H "Authorization: Bearer SEU_TOKEN"

# Ver relatório
curl http://localhost:8000/api/v1/documents/{id}/report \
  -H "Authorization: Bearer SEU_TOKEN"
```
