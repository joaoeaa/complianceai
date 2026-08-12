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
│                 #   scope.py e rule_scope.py concentram as checagens de acesso;
│                 #   se uma autorização não passa por ali, ela vai divergir
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

A forma atual de popular é o `ingest_planalto`, que baixa o texto oficial, fatia por artigo e gera os embeddings num passo só:

```bash
python -m app.scripts.ingest_planalto --listar     # catálogo
python -m app.scripts.ingest_planalto --lei lgpd   # uma lei
python -m app.scripts.ingest_planalto --todas      # o catálogo inteiro
python -m app.scripts.ingest_planalto --todas --dry-run   # conta artigos sem gravar
```

Leis cobertas, na íntegra: Código Civil, CLT, CDC, LGPD, Marco Civil da Internet, Lei Anticorrupção, Lei de Licitações, Lei do Inquilinato, Lei das S.A. e Lei de Propriedade Industrial.

Duas decisões desse script que parecem estranhas e não são:

- **A extração é por expressão regular, não por parser de árvore.** O HTML do Planalto vem do FrontPage, com tags mal fechadas que fazem o lxml abandonar o documento no meio: no Código Civil ele parava no artigo 57 de 2.046.
- **Trechos em `<strike>` e `<del>` são descartados.** É a marcação que o Planalto usa para redação revogada, que apareceria duplicada ao lado da vigente.

Sem embeddings, os chunks existem mas a busca semântica não retorna nada, e a análise cai de volta no conhecimento paramétrico do Claude, sem citar artigos.

Outros scripts:

| Script | Função |
|---|---|
| `ingest_planalto` | Ingestão a partir da fonte oficial, com embeddings. É o caminho atual |
| `seed_rules` | As 29 regras globais, 14 ativas. Idempotente, e alinha as já gravadas |
| `generate_embeddings_for_chunks` | Gera embeddings dos chunks que ainda não têm |
| `repopulate_chunks` | Reconstrói chunks de documentos legais que ficaram sem eles |
| `seed_legal_base`, `seed_all`, `seed_cdc`, ... | Seeds antigos: 53 artigos escolhidos a mão. Substituídos pelo `ingest_planalto` |

---

## Pipeline de análise

`workers/tasks.py` orquestra:

```
texto do documento      já extraído no upload, em documents.extracted_text
    ↓
regras ativas           services/rule_scope           escopo do documento + overrides
    ↓
search_similar()        services/rag_service          busca vetorial em legal_chunks
    ↓
aprendizado             services/feedback_learning    agregado do feedback, mesmo escopo
    ↓
analyze()               services/ai_analyzer          monta prompt, chama Claude, valida JSON
    ↓
annotate_alerts()       services/verification         confere trecho e artigo contra as fontes
    ↓
persiste Analysis       status: analyzed
```

O texto é extraído **no upload**, e não aqui: API e worker são containers separados em produção e não compartilham disco, então o texto viaja pelo banco em vez de pelo arquivo.

A verificação não descarta alerta nenhum, apenas rotula. Um trecho não localizado pode ser paráfrase correta, e um artigo fora do top-k recuperado pode estar certo assim mesmo. O objetivo é dizer ao revisor onde confiar e onde ir conferir na fonte.

Ao mexer no prompt, `services/ai_analyzer.py` é o único ponto a tocar. O formato de resposta esperado está documentado lá.

---

## Testes

Rodam contra SQLite (`aiosqlite`, arquivo `test.db`), com as chamadas de IA mockadas: a suíte não consome créditos de API nem exige Postgres ou Redis no ar. O rate limiting é desligado via `RATE_LIMIT_ENABLED=false` em `pyproject.toml`.

As foreign keys do SQLite são ativadas no `conftest.py`. Sem isso, `CASCADE` e `SET NULL` não valem no teste e a suíte passa a aprovar exclusão que deixa órfão.

Ao adicionar um endpoint, cubra pelo menos o happy path e um caso de erro. Fixtures compartilhadas ficam em `tests/conftest.py`.

Ao mexer numa checagem de acesso, o teste que vale é o que falha quando a checagem cai. A forma de verificar isso é remover a checagem de propósito, rodar, ver o teste ficar vermelho e restaurar. Teste de autorização que passa sozinho e também passa com o bug reintroduzido não protege nada.

---

## Notas

- **Async em todo o caminho**: SQLAlchemy async + asyncpg. Nada de I/O bloqueante nos handlers; para código síncrono inevitável, use `asyncio.to_thread` (ver `_seed_legal_database` em `main.py`).
- **Config**: todas as settings passam por `core/config.py`. Nenhum segredo tem default preenchido; tudo vem do `.env`.
- **Rate limiting**: SlowAPI. Login em 5/min, upload em 10/min.
- **Logging**: structlog via `core/logging.py`. Não logue conteúdo de contrato nem PII.
- **Escopo**: nenhuma consulta que devolva documento, regra ou cliente deve rodar sem passar por `services/scope.py` ou `services/rule_scope.py`. Já houve vazamento entre contas por consulta escrita direto no endpoint.
- **Prompt**: tudo que entra no prompt precisa vir do escopo do documento em análise. Isso inclui os comentários de feedback, que entram em texto literal e falam sobre contratos de clientes reais.
