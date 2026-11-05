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
python -m app.scripts.ingest_planalto --lei licitacoes --reprocessar --dry-run  # o que mudaria
python -m app.scripts.ingest_planalto --lei licitacoes --reprocessar            # refaz os chunks
```

`--reprocessar` refaz os chunks de uma lei já ingerida a partir do texto gravado em `legal_documents.full_text`, sem baixar do Planalto. Normaliza o texto, fatia, gera os embeddings e só então troca os chunks antigos pelos novos, numa transação: se o embedding falhar, a lei fica como estava. Com `--dry-run` mostra chunks, artigos e referências quebradas, antes e depois, sem gerar embedding.

Leis cobertas, na íntegra: Código Civil, CLT, CDC, LGPD, Marco Civil da Internet, Lei Anticorrupção, Lei de Licitações, Lei do Inquilinato, Lei das S.A. e Lei de Propriedade Industrial.

Duas decisões desse script que parecem estranhas e não são:

- **A extração é por expressão regular, não por parser de árvore.** O HTML do Planalto vem do FrontPage, com tags mal fechadas que fazem o lxml abandonar o documento no meio: no Código Civil ele parava no artigo 57 de 2.046.
- **Trechos em `<strike>` e `<del>` são descartados.** É a marcação que o Planalto usa para redação revogada, que apareceria duplicada ao lado da vigente.
- **A quebra de linha do código-fonte HTML vira espaço.** O editor do Planalto quebra linha no meio da frase, e o texto saía com `"Art. \r\n 92"` e `"III \r\n - locação"`. A referência ia para o `article_ref` com a quebra, e a verificação não casava a citação. A mesma quebra jogava citações como `"art. 20 da Lei 11.033"` para o começo da linha, onde viravam um falso início de artigo. Toda ingestão passa ainda por `normalizar_referencias`, que junta artigo, parágrafo, inciso, alínea e ordinal partidos. Leis ingeridas antes disso precisam de `--reprocessar`.

Sem embeddings, os chunks existem mas a busca semântica não retorna nada, e a análise cai de volta no conhecimento paramétrico do Claude, sem citar artigos.

Outros scripts:

| Script | Função |
|---|---|
| `ingest_planalto` | Ingestão a partir da fonte oficial, com embeddings. É o caminho atual |
| `medir_analises` | Compara tempo, tokens e taxas de verificação por prompt ou modelo |
| `seed_rules` | As 29 regras globais, 14 ativas. Idempotente, alinha as já gravadas, `--dry-run` para conferir |
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
build_legal_context()   services/rag_service          uma consulta por cláusula e por regra
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

### Recuperação da base legal

Uma consulta só, feita com o começo do contrato, recuperava a lei do cabeçalho: num contrato com cláusula inteira de tratamento de dados, o contexto saía com Marco Civil, CLT e CDC e nenhum artigo da LGPD. A recuperação agora é assim:

- **Consultas**: uma por cláusula (`CLÁUSULA` no início da linha, seguida de ordinal) e uma por regra ativa do escopo (nome + critério). O preâmbulo, antes da primeira cláusula, também é consultado. Sem ao menos duas cláusulas, o texto é dividido em parágrafos, juntando os curtos até ~800 caracteres. Até 120 consultas de até 6.000 caracteres cada, para caber numa requisição de embedding.
- **Embedding**: todas as consultas numa requisição em lote. Se ela falhar, a análise segue sem contexto legal.
- **Seleção**: 3 trechos por consulta; o mesmo trecho trazido por mais de uma consulta entra uma vez, com a maior similaridade. Por similaridade, até `RAG_MAX_TRECHOS` (padrão 12) no total e 5 por lei, para uma lei longa não ocupar o contexto inteiro.

### Análise em background

O upload grava o documento, commita e agenda a análise num `ThreadPoolExecutor` da própria API, e responde na hora. O pool é próprio, e não o threadpool do Starlette, porque uma análise leva minutos e não deve ocupar a vaga que o upload e o PDF usam via `asyncio.to_thread`. O tamanho dele, `ANALYSIS_MAX_CONCURRENT` (padrão 2), é o limite de análises simultâneas.

- **Progresso**: cada etapa grava `documents.analysis_stage` e `analysis_progress`. O `GET /documents/{id}/status` devolve `"Etapa: <stage> (<n>%)"`, formato que o front interpreta.
- **Retry**: até 3 tentativas, com as esperas de `analysis_errors.py` (mais longas para sobrecarga do provedor). Falha que não passa com insistência, como resposta longa demais, para na primeira. O documento só vira `error` quando não há mais tentativa.
- **Análise órfã**: sem fila externa, a análise que morre com o processo não volta. `documents.analysis_updated_at` é o sinal de vida: muda a cada etapa, a cada nova tentativa e, enquanto o documento está na fila ou rodando, a cada 60s, por uma thread de batimento que só existe enquanto há análise em andamento. Órfã é a que está em `uploaded`/`processing` sem sinal de vida há mais de `ORPHAN_TIMEOUT_MINUTES` (padrão 12; sem a coluna, vale `uploaded_at`). Ela vira `error` na varredura do startup e, preguiçosamente, no `GET /documents/{id}/status` daquele documento.
- **Por que o batimento**: a etapa `analyzing` é uma chamada só, e dentro dela o tenacity retenta sem escrever nada, com até 300s por requisição. Só com etapas e tentativas, uma análise viva pareceria órfã. É também o batimento que protege, durante um deploy, a análise que ainda roda na instância antiga.
- **Teto do batimento**: passados `ANALYSIS_MAX_DURATION_MINUTES` (padrão 60) do início da primeira tentativa, o documento deixa de ser renovado e vira órfão no prazo normal, cerca de 72 minutos depois do início com os padrões. É o que impede uma thread travada de segurar o documento em `processing` para sempre. A espera na fila não conta. A thread em si não pode ser interrompida em Python: ela segue ocupando a vaga no pool até terminar, e se não terminar nunca, só um restart libera a vaga.
- **Retries e pior caso**: a requisição à Anthropic tem uma camada só de retry, o tenacity (3 tentativas, esperas de 4s); o cliente sai com `max_retries=0` e 10s de timeout de conexão. As consultas de embedding do RAG vão todas numa requisição em lote, com 30s de timeout e 1 retry. Com os padrões, o pior caso de uma análise viva é 3318s, ~55 min: por tentativa, embedding 2 × (10 + 30) + 8 = 88s e LLM 3 × (10 + 300) + 4 + 4 = 938s; três tentativas e as esperas de 60s e 180s entre elas. A conta está em `analysis_runner.pior_caso_da_analise`, coberta por teste, e o boot avisa se `ANALYSIS_MAX_DURATION_MINUTES` ficar abaixo dela. Ela conta conexão + leitura de cada requisição e deixa de fora o envio do corpo, as consultas ao banco e uma resposta que chegue pingada, que o timeout de leitura do httpx não cobre.
- **A thread não desfaz um `error`**: toda escrita de status dela é condicional a `uploaded`/`processing`. Se o documento foi marcado por fora, ela para na próxima etapa, sem esperar o backoff, e a troca para `analyzed` vai na mesma transação da análise, que é desfeita junto.

### Storage

`services/storage.py`, escolhido por `STORAGE_BACKEND`: `local` grava em `UPLOAD_DIR`; `s3` grava num bucket compatível com S3 (Supabase Storage, Cloudflare R2, AWS), configurado pelas variáveis `S3_*` do `.env.example`. `documents.file_path` guarda a chave `<uuid><ext>`. Upload, download, exclusão e expurgo por retenção passam todos por ali, e o arquivo é apagado antes do registro, para nunca sobrar contrato no storage sem registro que leve a ele.

A verificação não descarta alerta nenhum, apenas rotula. Um trecho não localizado pode ser paráfrase correta, e um artigo fora do top-k recuperado pode estar certo assim mesmo. O objetivo é dizer ao revisor onde confiar e onde ir conferir na fonte.

**Origem do alerta** (prompt v4): o modelo aponta as regras reprovadas e também os problemas relevantes fora do checklist, até 10 por análise. Cada alerta sai com `origin`: `rule` para regra do checklist, `finding` para achado livre. A origem é conferida em código contra os nomes das regras enviadas, porque o checklist conta como reprovada a regra que tem alerta com o nome dela: um nome de regra com caixa ou espaço diferente volta ao nome configurado, e um `rule` sem regra correspondente vira `finding`. A tela e o PDF mostram a origem em selo; análises anteriores ao v4 não têm o campo e ficam sem selo.

Ao mexer no prompt, `services/ai_analyzer.py` é o único ponto a tocar. O formato de
resposta esperado está documentado lá. Uma redação nova entra como versão nova em
`PROMPT_VERSIONS`, sem alterar o texto das anteriores: a versão usada fica gravada
em `analyses.prompt_version` e é o que permite comparar análises antes e depois. O
histórico das redações está em comentário ao lado da constante.

**Versões disponíveis**: `ANALYSIS_PROMPT_VERSION` escolhe a redação (padrão `4`).
O v4 lista exemplos de problema relevante. O v5 troca a lista por um método de
revisão (cada cláusula por equilíbrio, valores e encargos, responsabilidade,
dados, saída do contrato e ausências; cada trecho de lei como item de
verificação; revisão final das cláusulas sem alerta). Valor fora da lista é erro
de boot.

### Avaliação do prompt

`tests/eval/contracts/` tem cinco contratos fictícios com gabarito em YAML:
problemas esperados, com gravidade e base legal, e o que **não** deve aparecer,
com o porquê. Os gabaritos não foram revisados por profissional e dizem isso no
topo; são legíveis para que alguém da área jurídica os revise.

```bash
python -m app.scripts.eval_prompt --estimar                                  # só o custo
python -m app.scripts.eval_prompt --versoes 4,5 --rodadas 3 --max-tokens 16384
python -m app.scripts.eval_prompt --comparar tests/eval/resultados/<arquivo>.json
```

O script roda a análise de verdade, sem gravar no banco (o RAG lê a base numa
transação `READ ONLY`), com e sem as regras ativas do seed. Um segundo modelo, o
juiz, decide a que item do gabarito cada alerta corresponde e registra a
justificativa. Saem cobertura, cobertura dos graves, falsos positivos, alertas
fora do gabarito (listados para revisão manual), citações confirmadas, artigo
esperado, tempo, tokens de saída e quantas respostas chegaram perto do teto ou o
passaram, por contrato e na média das rodadas, com o desvio entre elas. Antes de
rodar, mostra o custo estimado e pede confirmação; a execução completa (v4 e v5,
com e sem regras, 3 rodadas) fica em torno de US$ 9. Não faz parte da suíte:
`tests/test_eval_prompt.py` testa só a lógica do script e a validade dos
gabaritos, sem API. O resultado completo vai para `tests/eval/resultados/`,
fora do Git.

Com regras, um alerta que só a regra pede (por exemplo, ausência de cláusula
anticorrupção) cai em "fora do gabarito", e não em falso positivo: o gabarito
descreve problemas jurídicos, e quem decide o que a regra exige é quem a
configurou.

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
