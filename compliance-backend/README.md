# ComplianceAI: Backend

API FastAPI que faz a análise de conformidade contratual.

> Visão geral do projeto, setup completo e referência da API estão no [README da raiz](../README.md).
> Este documento cobre apenas o que é específico de trabalhar no backend.

---

## Rodando

```bash
cp .env.example .env          # preencha ANTHROPIC_API_KEY e OPENAI_API_KEY
docker compose up -d          # postgres + redis + api + worker
```

API em `:8000`, Swagger em `/docs`.

Fora do Docker, são dois processos, a API e o worker Celery:

```bash
uvicorn app.main:app --reload --port 8000
celery -A app.workers.tasks.celery_app worker --loglevel=info
```

O worker é obrigatório: o upload apenas enfileira a análise. Sem worker rodando, o documento fica travado em `processing`.

---

## Comandos

```bash
pytest                                              # suíte completa
pytest tests/test_documents.py -v                   # um arquivo
pytest -k rag                                       # por nome

alembic upgrade head                                # aplicar migrations
alembic revision --autogenerate -m "descricao"      # nova migration
```

Com Docker, prefixe com `docker compose exec api`.

---

## Organização do código

```
app/
├── api/          # Routers FastAPI: um por domínio, todos sob /api/v1
├── core/         # config (pydantic-settings), database, security, logging, limiter
├── models/       # Re-export dos modelos SQLAlchemy definidos em app/__init__.py
├── schemas/      # Schemas Pydantic de request/response
├── services/     # Regra de negócio: sem dependência de FastAPI
├── scripts/      # Seeds de legislação e manutenção de embeddings
├── workers/      # Tasks Celery
└── main.py       # Wiring: rotas, middleware, lifespan
```

Os endpoints ficam finos: validam entrada, chamam um serviço, devolvem o schema. A lógica pesada mora em `services/`.

---

## Comportamento do startup

O `lifespan` em `main.py` só executa em `APP_ENV=development`:

1. `CREATE EXTENSION IF NOT EXISTS vector` (ignorado no SQLite)
2. `Base.metadata.create_all`: cria as tabelas
3. Seed do usuário admin e das regras de conformidade padrão
4. Seed da base legal

Tudo idempotente. **Em produção nada disso roda**: use `alembic upgrade head` e crie os usuários manualmente.

---

## Base legal e embeddings

A base legal vive em duas tabelas: `legal_documents` (uma linha por lei) e `legal_chunks` (uma linha por artigo).

O seed automático do startup popula os artigos, mas **não gera embeddings**: isso exige chamadas à API da OpenAI e é feito em passo separado:

```bash
python -m app.scripts.generate_embeddings_for_chunks
```

Sem esse passo os chunks existem, mas a busca semântica não retorna nada, e a análise cai de volta no conhecimento paramétrico do Claude, sem citar artigos.

Outros scripts:

| Script | Função |
|---|---|
| `seed_legal_base` | Seed consolidado: 93 artigos de 7 leis. Idempotente, sem embeddings |
| `seed_all` | Roda os seeds individuais por lei em sequência |
| `seed_lgpd`, `seed_cdc`, `seed_clt`, ... | Seed de uma lei específica |
| `generate_embeddings_for_chunks` | Gera embeddings dos chunks que ainda não têm |
| `repopulate_chunks` | Reconstrói chunks de documentos legais que ficaram sem eles |

Leis cobertas: LGPD (13.709/2018), CDC (8.078/1990), Código Civil (10.406/2002), CLT, Marco Civil da Internet (12.965/2014), Lei Anticorrupção (12.846/2013) e Lei de Licitações (14.133/2021).

---

## Pipeline de análise

`workers/tasks.py` orquestra:

```
extract_text()          services/document_extractor   pdfplumber · python-docx · OCR
    ↓
regras ativas           SELECT em rules WHERE is_active
    ↓
search_similar()        services/rag_service          busca vetorial em legal_chunks
    ↓
analyze()               services/ai_analyzer          monta prompt, chama Claude, valida JSON
    ↓
persiste Analysis       status: analyzed
```

Ao mexer no prompt, `services/ai_analyzer.py` é o único ponto a tocar. O formato de resposta esperado está documentado lá.

---

## Testes

Rodam contra SQLite (`aiosqlite`, arquivo `test.db`), com as chamadas de IA mockadas: a suíte não consome créditos de API nem exige Postgres ou Redis no ar. O rate limiting é desligado via `RATE_LIMIT_ENABLED=false` em `pyproject.toml`.

Ao adicionar um endpoint, cubra pelo menos o happy path e um caso de erro. Fixtures compartilhadas ficam em `tests/conftest.py`.

---

## Notas

- **Async em todo o caminho**: SQLAlchemy async + asyncpg. Nada de I/O bloqueante nos handlers; para código síncrono inevitável, use `asyncio.to_thread` (ver `_seed_legal_database` em `main.py`).
- **Config**: todas as settings passam por `core/config.py`. Nenhum segredo tem default preenchido; tudo vem do `.env`.
- **Rate limiting**: SlowAPI. Login em 5/min, upload em 10/min.
- **Logging**: structlog via `core/logging.py`. Não logue conteúdo de contrato nem PII.
