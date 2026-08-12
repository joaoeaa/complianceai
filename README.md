# ComplianceAI

**Plataforma de IA para análise de conformidade de contratos sob a legislação brasileira.**

Faça upload de um contrato em PDF ou DOCX e receba um relatório de conformidade apontando cláusulas problemáticas, riscos e recomendações, com fundamentação nos artigos de lei aplicáveis. A base cobre dez leis brasileiras na íntegra: Código Civil, CLT, CDC, LGPD, Marco Civil, Lei Anticorrupção, Lei de Licitações, Lei do Inquilinato, Lei das S.A. e Lei de Propriedade Industrial.

A análise combina **Claude AI** com **RAG** (busca semântica sobre uma base de legislação vetorizada), de modo que cada alerta cita o dispositivo legal em que se apoia em vez de depender apenas do conhecimento paramétrico do modelo.

---

## Índice

- [Como funciona](#como-funciona)
- [Escopo de trabalho](#escopo-de-trabalho)
- [Camada de escritório](#camada-de-escritório)
- [Stack](#stack)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Começando](#começando)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [API](#api)
- [Testes](#testes)
- [Migrations](#migrations)
- [Deploy](#deploy)
- [Segurança](#segurança)
- [O que ainda não tem interface](#o-que-ainda-não-tem-interface)

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
       ├─▶ Confere cada alerta contra as fontes (trecho no contrato, artigo na base)
       └─▶ Persiste análise (status: analyzed)
       │
       ▼
Relatório: JSON · HTML · PDF (WeasyPrint)
```

### Principais capacidades

| Recurso | Descrição |
|---|---|
| **Escopo de trabalho** | Alterna entre pessoal e equipe; documentos, regras, clientes, histórico e dashboard seguem a escolha |
| **Verificação dos alertas** | Cada alerta é conferido contra as fontes: se o trecho citado existe mesmo no contrato, em que página está, e se o artigo citado existe na base legal |
| **Regras por área do direito** | 29 regras padrão em 10 áreas, ligadas e desligadas por área inteira conforme o tipo de contrato |
| **Sigilo por cliente** | Documentos amarrados a um cliente só são lidos por quem foi designado a ele |
| **Log de acesso** | Quem leu, baixou, exportou ou excluiu o quê, e quando |
| **Política de retenção** | Prazo de guarda por cliente, com fila de expurgo sob confirmação |
| **RAG jurídico** | Base legal fatiada por artigo, com embeddings e busca por similaridade em pgvector |
| **Organizações** | Multi-tenant com membros e papéis (`owner` / `admin` / `member`) |
| **Fluxo do revisor** | Marcação de cada alerta como a corrigir, não se aplica ou resolvido, por revisor |
| **Feedback e aprendizado** | Feedback por alerta realimenta o prompt, restrito ao escopo do documento |
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

As regras vivem em três escopos. As **globais** são as 29 padrão do sistema, 14 ativas: todos as veem e ninguém as edita, mas cada escopo pode desativá-las para si, o que grava um registro em `rule_overrides` em vez de alterar a regra compartilhada. As demais pertencem a um usuário ou a uma organização.

Cada regra pertence a uma **área do direito**. As de estrutura do contrato, proteção de dados, civil, trabalhista e anticorrupção vêm ativas, porque valem para praticamente qualquer contrato. As de locação, societário, propriedade industrial, consumidor e internet vêm desligadas, porque regra de locação num contrato de TI só gera falso positivo. A tela agrupa por área e liga a área inteira de uma vez.

Na análise, o escopo sai do próprio documento: se ele pertence a uma organização, valem as regras da equipe; senão, as pessoais de quem enviou. O mesmo vale para o aprendizado por feedback, que é agregado dentro do escopo do documento e nunca cruza contas.

---

## Camada de escritório

Um escritório de advocacia não organiza o trabalho por arquivo, e sim por cliente. É o cliente que define quem pode ler o material, por quanto tempo ele fica guardado e o que a auditoria precisa reconstruir depois.

### Sigilo por cliente

Um documento pode ser amarrado a um cliente no momento do upload. A partir daí, só enxerga esse documento quem estiver **designado** ao cliente. Quem não está designado recebe `404`, e não `403`: a existência do cliente já é informação sob sigilo.

`owner` e `admin` da organização enxergam a carteira inteira, como sócio de escritório.

Documento **sem cliente** continua visível a toda a equipe. Isso é deliberado: quem ainda não organizou a carteira não perde acesso ao próprio acervo.

A restrição existe em duas camadas independentes, o filtro da listagem e a checagem na leitura individual, cada uma com teste próprio.

### Log de acesso

Num escritório o dano de sigilo está na leitura, não na alteração. Entram no registro a leitura do relatório, o download do original, a exportação e a exclusão.

O log guarda UUIDs e o nome do arquivo, nunca email ou nome, e sobrevive ao expurgo do documento (`ON DELETE SET NULL`): saber que alguém leu um documento hoje apagado é justamente o que a auditoria quer. É restrito a `owner` e `admin`, porque abri-lo a todos criaria uma segunda via de vazamento do que ele existe para proteger.

O registro entra na mesma transação da ação que o originou. Se a leitura falha, o registro cai junto: o log diz quem viu, não quem tentou.

### Política de retenção

Cada cliente tem um prazo de guarda opcional, em meses. Prazo nulo guarda por tempo indeterminado, que é o padrão, porque apagar por engano é pior do que guardar demais.

Nada é apagado sozinho. Os documentos vencidos entram numa fila que alguém revisa e confirma, e o endpoint de expurgo reconfere o vencimento de cada id recebido, para não virar um caminho paralelo de exclusão. Um contrato pode estar vencido para a política de guarda e ainda ser prova em processo em curso.

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
│   │   │   ├── clients.py        # Clientes, designações, retenção e auditoria
│   │   │   ├── templates.py      # Templates de contrato (sem interface)
│   │   │   ├── workflows.py      # Workflows de aprovação (sem interface)
│   │   │   ├── webhooks.py       # Configuração de webhooks (sem interface)
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
│   │   │   ├── verification.py       # Confere trecho e artigo citados contra as fontes
│   │   │   ├── scope.py              # Escopo e sigilo: quem lê qual documento
│   │   │   ├── rule_scope.py         # Escopo das regras + overrides das globais
│   │   │   ├── audit.py              # Registro de acesso
│   │   │   ├── feedback_learning.py  # Agregado de feedback, restrito ao escopo
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
| `POST` | `/documents/upload` | Upload e enfileiramento. Aceita `organization_id` e `client_id` |
| `GET` | `/documents` | Listar do escopo. Aceita `organization_id`, `client_id`, `status`, `search`, paginação |
| `GET` | `/documents/{id}` | Detalhes do documento |
| `GET` | `/documents/{id}/status` | Status da análise |
| `GET` | `/documents/{id}/report` | Relatório em JSON |
| `GET` | `/documents/{id}/report/html` | Relatório em HTML |
| `GET` | `/documents/{id}/report/pdf` | Relatório em PDF |
| `GET` | `/documents/{id}/download` | Baixar o arquivo original |
| `PATCH` | `/documents/{id}/alerts/{i}` | Marcar o alerta como a corrigir, não se aplica ou resolvido |
| `DELETE` | `/documents/{id}` | Excluir. Em equipe, só quem enviou ou os responsáveis |

### Regras de conformidade

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/rules` | Globais + as do escopo. Aceita `organization_id` e `active_only` |
| `GET` | `/rules/{id}` | Detalhar uma regra visível |
| `POST` | `/rules` | Criar. Sem `organization_id` cria pessoal; com ele, da equipe |
| `PATCH` | `/rules/{id}` | Editar. Só regras próprias ou da equipe que administra |
| `PATCH` | `/rules/{id}/toggle` | Ativar/desativar. Em regra global, grava um override do escopo |
| `PATCH` | `/rules/categoria/{area}` | Ligar ou desligar uma área do direito inteira |
| `DELETE` | `/rules/{id}` | Excluir. Regras globais não podem ser removidas |

### Legislação (RAG)

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/legislation/ingest` | Ingerir lei: faz chunking por artigo e gera embeddings |
| `GET` | `/legislation` · `/legislation/{id}` | Listar / detalhar |
| `POST` | `/legislation/search` | Busca semântica por similaridade |

### Clientes, sigilo e auditoria

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/clients` | Clientes visíveis no escopo. Sem designação, o cliente não aparece |
| `POST` | `/clients` | Criar. Na equipe, só `owner` e `admin` |
| `PATCH` `DELETE` | `/clients/{id}` | Editar e excluir. Excluir o cliente não apaga os documentos |
| `GET` `POST` | `/clients/{id}/assignees` | Quem tem acesso ao cliente, e conceder acesso |
| `DELETE` | `/clients/{id}/assignees/{user_id}` | Retirar o acesso |
| `GET` | `/clients/retencao/vencidos` | Fila dos documentos que passaram do prazo de guarda |
| `POST` | `/clients/retencao/expurgar` | Excluir os escolhidos, reconferindo o vencimento |
| `GET` | `/clients/auditoria/acessos` | Log de acesso. Na equipe, restrito a `owner` e `admin` |

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

São **286 testes**, rodando contra um SQLite local (`aiosqlite`, arquivo `test.db`, ignorado pelo Git), com as foreign keys ativadas para que `CASCADE` e `SET NULL` valham também no teste.

Cobrem autenticação, documentos, regras e seu escopo, organizações, templates, workflows, webhooks, dashboard, extração de documentos, o analisador de IA, a geração de relatórios e, com atenção especial, os limites que sustentam a confiança na ferramenta: o sigilo por cliente, o isolamento do feedback entre contas e a recusa do expurgo fora do prazo.

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
python -m app.scripts.seed_rules                # as 29 regras globais, 14 ativas
```

O `seed_rules` é idempotente e **alinha** as regras globais já gravadas ao conjunto
do arquivo, não só insere as que faltam. Rodá-lo de novo depois de uma migration
que acrescente coluna às regras é o que evita que as antigas fiquem presas no
valor padrão enquanto as novas nascem certas.

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

- **A plataforma não roda as migrations no build.** O container novo sobe com o modelo pedindo colunas que ainda não existem, e a aplicação responde `500` com `UndefinedTable` ou `UndefinedColumn`. Rode `alembic upgrade head` logo depois do push, por dentro do container: `railway ssh --service api`. O `railway run` executa na sua máquina e não resolve o hostname interno do banco.
- O Postgres padrão não traz a extensão `vector`. Sem ela, o RAG não existe.
- `CORS_ORIGINS` precisa ser JSON válido. Uma variável definida e **vazia** derruba a API no boot.
- O `VITE_API_URL` entra no build, não na execução. Alterá-lo exige um novo deploy.
- `storage/uploads` é efêmero em plataformas de container. As análises persistem no banco, mas o arquivo original some a cada redeploy.

---

## Segurança

- **Autenticação**: JWT (access 1h, refresh 7d) com senhas em bcrypt
- **Autorização**: por escopo. No pessoal, cada usuário só enxerga os próprios documentos e regras; na equipe, só membros acessam, e apenas `owner` e `admin` alteram as regras
- **Sigilo profissional**: documento amarrado a um cliente só é lido por quem foi designado a ele, verificado em duas camadas independentes. Quem não tem acesso recebe `404`
- **Log de acesso**: leitura, download, exportação e exclusão ficam registrados, sem PII, e o registro sobrevive à exclusão do documento
- **Isolamento do aprendizado**: o feedback que realimenta o prompt é agregado dentro do escopo do documento. Os comentários dos revisores entram no prompt em texto literal, então cruzá-los entre contas seria vazamento de informação de cliente
- **Exclusão de documento**: no escopo de equipe, restrita a quem enviou e aos responsáveis
- **Rate limiting**: SlowAPI nos endpoints sensíveis
- **Uploads**: validação de tipo e tamanho máximo configurável
- **LGPD**: `DELETE /documents/{id}` remove documento e análises associadas
- **Segredos**: carregados exclusivamente do `.env`, que está no `.gitignore`

> **Antes de expor em produção:** troque o `SECRET_KEY`, remova o usuário admin de seed, restrinja `CORS_ORIGINS` e defina `APP_ENV=production`.

---

## O que ainda não tem interface

Três módulos existem no backend, com testes e rotas em `/docs`, mas nenhuma tela os chama. Ficam documentados aqui para que a lista de capacidades não prometa o que o produto não entrega:

| Módulo | Estado |
|---|---|
| `templates` | CRUD de modelos de contrato. Funciona pela API, sem tela |
| `workflows` | Máquina de estados de aprovação. Funciona pela API, sem tela |
| `webhooks` | Notificação de eventos externos. Funciona pela API, sem tela |

Além deles, a avaliação geral da análise (1 a 5 estrelas) é gravada e relida na própria tela, mas não alimenta o prompt nem vira métrica no dashboard. Diferente do feedback **por alerta**, que realimenta a análise de verdade.

### Limitações conhecidas

- **Arquivo original é efêmero** em plataformas de container. A análise persiste no banco; o PDF some a cada redeploy, e o download responde `410`.
- **Comparação entre versões** de um mesmo contrato ainda não existe.
- **Sem muralha absoluta**: `owner` e `admin` enxergam todos os clientes por desenho. Não há hoje a figura do cliente restrito, em que nem o sócio entra sem designação.

---

## Custo estimado

Documento médio (~8.000 tokens de entrada, ~1.500 de saída): cerca de **US$ 0,04 por análise**, aproximadamente US$ 40 para 1.000 análises/mês, sem contar o custo (marginal) dos embeddings.
