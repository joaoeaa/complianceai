# ComplianceAI: Backend

API FastAPI que faz a análise de conformidade contratual.

> Visão geral do projeto, setup completo e referência da API estão no [README da raiz](../README.md).
> Este documento cobre apenas o que é específico de trabalhar no backend.

---

## Rodando

```bash
cp .env.example .env          # preencha ANTHROPIC_API_KEY e OPENAI_API_KEY
docker compose up -d          # postgres + api
```

API em `:8000`, Swagger em `/docs`.

Fora do Docker, é um processo só:

```bash
uvicorn app.main:app --reload --port 8000
```

A análise roda numa thread da própria API (ver [Análise em background](#análise-em-background)). Não há worker nem Redis.

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
│                 #   analysis_runner.py roda a análise em background;
│                 #   storage.py guarda o arquivo original (disco ou bucket S3)
├── scripts/      # Seeds de legislação e manutenção de embeddings
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

Tudo idempotente. **Em produção nada disso roda**: use `alembic upgrade head` e crie os usuários manualmente. No Railway, o `startCommand` do `railway.toml` já roda as migrations a cada deploy.

Em qualquer ambiente, o startup também marca como `error` as análises interrompidas por um restart (ver abaixo).

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
| `medir_analises` | Compara tempo, tokens e taxas de verificação por prompt ou modelo |
| `seed_rules` | As 29 regras globais, 14 ativas. Idempotente, e alinha as já gravadas |
| `generate_embeddings_for_chunks` | Gera embeddings dos chunks que ainda não têm |
| `repopulate_chunks` | Reconstrói chunks de documentos legais que ficaram sem eles |
| `seed_legal_base`, `seed_all`, `seed_cdc`, ... | Seeds antigos: 53 artigos escolhidos a mão. Substituídos pelo `ingest_planalto` |

---

## Pipeline de análise

`services/analysis_runner.py` orquestra, numa thread do pool da API:

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

O texto é extraído **no upload**, e não aqui: o arquivo pode estar num bucket, e a extração precisa de um caminho local. O upload extrai de uma cópia temporária e grava o texto no banco; a análise não volta a ler o arquivo.

### Análise em background

O upload grava o documento, commita e agenda a análise num `ThreadPoolExecutor` da própria API, e responde na hora. O pool é próprio, e não o threadpool do Starlette, porque uma análise leva minutos e não deve ocupar a vaga que o upload e o PDF usam via `asyncio.to_thread`. O tamanho dele, `ANALYSIS_MAX_CONCURRENT` (padrão 2), é o limite de análises simultâneas.

- **Progresso**: cada etapa grava `documents.analysis_stage` e `analysis_progress`. O `GET /documents/{id}/status` devolve `"Etapa: <stage> (<n>%)"`, formato que o front interpreta.
- **Retry**: até 3 tentativas, com as esperas de `analysis_errors.py` (mais longas para sobrecarga do provedor). Falha que não passa com insistência, como resposta longa demais, para na primeira. O documento só vira `error` quando não há mais tentativa.
- **Análise órfã**: sem fila externa, a análise que morre com o processo não volta. `documents.analysis_updated_at` é o sinal de vida: muda a cada etapa, a cada nova tentativa e, enquanto o documento está na fila ou rodando, a cada 60s, por uma thread de batimento que só existe enquanto há análise em andamento. Órfã é a que está em `uploaded`/`processing` sem sinal de vida há mais de `ORPHAN_TIMEOUT_MINUTES` (padrão 12; sem a coluna, vale `uploaded_at`). Ela vira `error` na varredura do startup e, preguiçosamente, no `GET /documents/{id}/status` daquele documento.
- **Por que o batimento**: a etapa `analyzing` é uma chamada só, e dentro dela o tenacity retenta sem escrever nada, com até 300s por requisição. Só com etapas e tentativas, uma análise viva pareceria órfã. É também o batimento que protege, durante um deploy, a análise que ainda roda na instância antiga.
- **Teto do batimento**: passados `ANALYSIS_MAX_DURATION_MINUTES` (padrão 60) do início da primeira tentativa, o documento deixa de ser renovado e vira órfão no prazo normal, cerca de 72 minutos depois do início com os padrões. É o que impede uma thread travada de segurar o documento em `processing` para sempre. A espera na fila não conta. A thread em si não pode ser interrompida em Python: ela segue ocupando a vaga no pool até terminar, e se não terminar nunca, só um restart libera a vaga.
- **Retries e pior caso**: a requisição à Anthropic tem uma camada só de retry, o tenacity (3 tentativas, esperas de 4s); o cliente sai com `max_retries=0` e 10s de timeout de conexão. A consulta de embedding do RAG tem 30s de timeout e 1 retry. Com os padrões, o pior caso de uma análise viva é 3318s, ~55 min: por tentativa, embedding 2 × (10 + 30) + 8 = 88s e LLM 3 × (10 + 300) + 4 + 4 = 938s; três tentativas e as esperas de 60s e 180s entre elas. A conta está em `analysis_runner.pior_caso_da_analise`, coberta por teste, e o boot avisa se `ANALYSIS_MAX_DURATION_MINUTES` ficar abaixo dela. Ela conta conexão + leitura de cada requisição e deixa de fora o envio do corpo, as consultas ao banco e uma resposta que chegue pingada, que o timeout de leitura do httpx não cobre.
- **A thread não desfaz um `error`**: toda escrita de status dela é condicional a `uploaded`/`processing`. Se o documento foi marcado por fora, ela para na próxima etapa, sem esperar o backoff, e a troca para `analyzed` vai na mesma transação da análise, que é desfeita junto.

### Storage

`services/storage.py`, escolhido por `STORAGE_BACKEND`: `local` grava em `UPLOAD_DIR`; `s3` grava num bucket compatível com S3 (Supabase Storage, Cloudflare R2, AWS), configurado pelas variáveis `S3_*` do `.env.example`. `documents.file_path` guarda a chave `<uuid><ext>`. Upload, download, exclusão e expurgo por retenção passam todos por ali, e o arquivo é apagado antes do registro, para nunca sobrar contrato no storage sem registro que leve a ele.

A verificação não descarta alerta nenhum, apenas rotula. Um trecho não localizado pode ser paráfrase correta, e um artigo fora do top-k recuperado pode estar certo assim mesmo. O objetivo é dizer ao revisor onde confiar e onde ir conferir na fonte.

Ao mexer no prompt, `services/ai_analyzer.py` é o único ponto a tocar. O formato de
resposta esperado está documentado lá, e `PROMPT_VERSION` precisa ser incrementado
junto: o valor fica gravado em `analyses.prompt_version` e é o que permite comparar
análises antes e depois. O histórico das redações está em comentário ao lado da
constante.

---

## Testes

Rodam contra SQLite (`aiosqlite`, arquivo `test.db`), com as chamadas de IA mockadas: a suíte não consome créditos de API nem exige Postgres no ar. O `conftest.py` troca o agendamento da análise por um registro (fixture `analises_agendadas`) e o storage por um diretório temporário por teste; a execução da análise em si é testada em `test_analysis_runner.py`. O rate limiting é desligado via `RATE_LIMIT_ENABLED=false` em `pyproject.toml`.

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
