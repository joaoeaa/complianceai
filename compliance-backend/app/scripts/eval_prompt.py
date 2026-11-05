"""Avaliação do prompt de análise contra um conjunto de contratos com gabarito.

Roda a análise de verdade (Anthropic + RAG) nos contratos de tests/eval/contracts,
sem gravar nada no banco, e compara cada alerta com o gabarito do contrato. A
comparação é feita por um segundo modelo (o "juiz"), que decide se o alerta
corresponde a um item e registra por quê: o gabarito descreve problemas em
linguagem jurídica, e casar por palavra-chave erraria nos dois sentidos.

Não faz parte da suíte de testes: chama a API e custa dinheiro. Antes de rodar,
mostra a estimativa de custo e pede confirmação (--sim pula a pergunta).

Uso, de dentro de compliance-backend/:

    python -m app.scripts.eval_prompt --estimar                     # só o custo
    python -m app.scripts.eval_prompt --versoes 4,5 --rodadas 3     # v4 e v5, com e sem regras
    python -m app.scripts.eval_prompt --versoes 5 --casos com --contratos 02,05
    python -m app.scripts.eval_prompt --comparar resultados/a.json resultados/b.json
    python -m app.scripts.eval_prompt --retomar resultados/a.json   # refaz o que falhou

--retomar reaproveita uma execução salva: refaz só as análises que falharam por
outro motivo que não o teto de tokens (crédito, rede), julga as que ficaram sem
julgamento e regrava o arquivo. O que já foi pago não é pago de novo.

O RAG lê a base legal do banco de DATABASE_URL_SYNC numa transação READ ONLY.
O resultado completo vai para tests/eval/resultados/<data>_v<versões>.json.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

RAIZ = Path(__file__).resolve().parents[2]
PASTA_CONTRATOS = RAIZ / "tests" / "eval" / "contracts"
PASTA_RESULTADOS = RAIZ / "tests" / "eval" / "resultados"

CASOS = ("sem", "com")          # sem regras / com as regras ativas do seed
GRAVIDADES = {"alta": "high", "média": "medium", "media": "medium", "baixa": "low"}

# Preço por milhão de tokens (entrada, saída), da tabela da Anthropic de 2026-10.
# Modelo fora da tabela: a estimativa sai sem valor em dólar.
PRECOS = {
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-4-6": (3.0, 15.0),
}
# Medidos no contrato de teste: a análise gastou de 4,7 mil a 10,7 mil tokens de
# saída, contando o raciocínio do modelo, que entra em output_tokens. A
# estimativa usa um valor perto do alto, para não sair otimista.
SAIDA_ESTIMADA_ANALISE = 9_000
SAIDA_ESTIMADA_JUIZ = 3_000
CARACTERES_POR_TOKEN = 2.6     # português, medido: ~7,1 mil tokens para ~19 mil caracteres
CONTEXTO_RAG_ESTIMADO = 10_000  # caracteres de legislação no prompt (12 trechos)
PERTO_DO_TETO = 0.85            # fração de ANTHROPIC_MAX_TOKENS


# ─── Gabaritos ───────────────────────────────────────────────────────────────

@dataclass
class Contrato:
    nome: str
    texto: str
    gabarito: dict

    @property
    def esperados(self) -> list[dict]:
        return self.gabarito["problemas_esperados"]

    @property
    def nao_devem(self) -> list[dict]:
        return self.gabarito.get("nao_devem_aparecer") or []


def validar_gabarito(g: dict, nome: str) -> None:
    """Falha cedo, com o nome do arquivo, em vez de no meio de uma rodada paga."""
    def erro(msg):
        raise ValueError(f"Gabarito {nome}: {msg}")

    for chave in ("contrato", "tipo", "problemas_esperados", "revisado_por_profissional"):
        if chave not in g:
            erro(f"falta '{chave}'")
    ids = set()
    for item in g["problemas_esperados"]:
        for chave in ("id", "clausula", "problema", "gravidade", "base_legal"):
            if chave not in item:
                erro(f"item esperado sem '{chave}': {item}")
        if item["gravidade"] not in GRAVIDADES:
            erro(f"gravidade desconhecida em {item['id']}: {item['gravidade']}")
        if not isinstance(item["base_legal"], list):
            erro(f"base_legal de {item['id']} precisa ser lista")
        ids.add(item["id"])
    for item in g.get("nao_devem_aparecer") or []:
        for chave in ("id", "clausula", "o_que_seria_errado", "por_que"):
            if chave not in item:
                erro(f"item nao_devem_aparecer sem '{chave}': {item}")
        ids.add(item["id"])
    total = len(g["problemas_esperados"]) + len(g.get("nao_devem_aparecer") or [])
    if len(ids) != total:
        erro("ids repetidos")


def carregar_contratos(pasta: Path = PASTA_CONTRATOS, filtro: Optional[list[str]] = None) -> list[Contrato]:
    import yaml

    contratos = []
    for arquivo in sorted(pasta.glob("*.yaml")):
        if filtro and not any(arquivo.stem.startswith(f) for f in filtro):
            continue
        g = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
        validar_gabarito(g, arquivo.name)
        texto = (pasta / g["contrato"]).read_text(encoding="utf-8")
        contratos.append(Contrato(nome=arquivo.stem, texto=texto, gabarito=g))
    if not contratos:
        raise SystemExit(f"Nenhum contrato encontrado em {pasta} (filtro: {filtro})")
    return contratos


def regras_do_seed() -> list[dict]:
    from app.scripts.seed_rules import DEFAULT_RULES

    return [{"name": r["name"], "severity": r["severity"], "criteria": r["criteria"]}
            for r in DEFAULT_RULES if r["is_active"]]


# ─── Artigo esperado ─────────────────────────────────────────────────────────

# Como cada lei aparece numa citação. O gabarito escreve "Art. 406, Código Civil"
# e o modelo pode escrever "Art. 406, CC" ou "Art. 406 da Lei 10.406/2002".
_LEIS = {
    "cc": ("codigo civil", "cc", "10.406", "10406"),
    "lgpd": ("lgpd", "13.709", "13709", "protecao de dados"),
    "cdc": ("cdc", "8.078", "8078", "defesa do consumidor"),
    "clt": ("clt", "5.452", "5452", "consolidacao das leis do trabalho"),
    "inquilinato": ("8.245", "8245", "inquilinato", "lei de locacoes", "lei das locacoes"),
    "10192": ("10.192", "10192"),
    "usura": ("22.626", "22626", "lei de usura"),
    "direito-autoral": ("9.610", "9610", "direitos autorais", "direito autoral"),
    "marco-civil": ("12.965", "12965", "marco civil"),
}


def _sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def leis_citadas(texto: str) -> set[str]:
    plano = _sem_acento(texto)
    achadas = set()
    for lei, formas in _LEIS.items():
        for forma in formas:
            if re.search(rf"(?<![\w.]){re.escape(forma)}(?![\w])", plano):
                achadas.add(lei)
                break
    return achadas


def cita_o_esperado(legal_basis: Optional[str], base_legal: list[str]) -> bool:
    """O alerta cita um dos dispositivos do gabarito (mesmo artigo e mesma lei)?"""
    from app.services.verification import _article_numbers

    if not legal_basis or not base_legal:
        return False
    artigos, leis = _article_numbers(legal_basis), leis_citadas(legal_basis)
    for esperado in base_legal:
        if _article_numbers(esperado) & artigos and leis_citadas(esperado) & leis:
            return True
    return False


# ─── Juiz ────────────────────────────────────────────────────────────────────

INSTRUCOES_JUIZ = """Você confere a saída de um analisador de contratos contra um gabarito.

Para cada alerta, diga a quais itens do gabarito ele corresponde.

- Corresponde a um item de PROBLEMAS ESPERADOS quando aponta o mesmo problema na
  mesma cláusula (ou a mesma ausência), ainda que com outras palavras, outra
  gravidade ou outra base legal. Um alerta pode cobrir mais de um item.
- Corresponde a um item de NÃO DEVEM APARECER quando afirma como problema
  exatamente o que o item descreve como errado. Mencionar a cláusula de passagem,
  ou apontá-la por um motivo que está entre os problemas esperados, não conta.
- Se não corresponder a nenhum item, deixe as duas listas vazias.
- "justificativa": uma frase dizendo por que corresponde, ou por que não.

Use apenas os ids do gabarito. Todo alerta aparece uma vez, pelo seu índice.
Responda só com JSON, sem markdown:
{"alertas": [{"indice": 0, "esperados": ["id"], "nao_devem": [], "justificativa": "..."}]}
"""


def prompt_do_juiz(contrato: Contrato, alertas: list[dict]) -> str:
    esperados = "\n".join(
        f'- id "{i["id"]}" (cláusula {i["clausula"]}): {i["problema"]}' for i in contrato.esperados
    )
    nao_devem = "\n".join(
        f'- id "{i["id"]}" (cláusula {i["clausula"]}): {i["o_que_seria_errado"]}'
        for i in contrato.nao_devem
    ) or "(nenhum)"
    lista = "\n".join(
        f'[{n}] {a.get("rule_name")} | cláusula citada: "{(a.get("excerpt") or "-")[:300]}" | '
        f'problema: {a.get("issue")}'
        for n, a in enumerate(alertas)
    )
    return (
        f"CONTRATO: {contrato.gabarito['tipo']}\n\n"
        f"PROBLEMAS ESPERADOS:\n{esperados}\n\n"
        f"NÃO DEVEM APARECER:\n{nao_devem}\n\n"
        f"ALERTAS DO ANALISADOR:\n{lista or '(nenhum alerta)'}"
    )


def _json_da_resposta(texto: str) -> dict:
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)
    return json.loads(texto)


def julgar(contrato: Contrato, alertas: list[dict], modelo: str) -> dict:
    """Uma chamada ao juiz. Devolve a correspondência por alerta e o uso de tokens."""
    if not alertas:
        return {"alertas": [], "tokens_entrada": 0, "tokens_saida": 0}

    import anthropic

    from app.core.config import get_settings

    cliente = anthropic.Anthropic(api_key=get_settings().ANTHROPIC_API_KEY, timeout=300.0)
    resposta = cliente.messages.create(
        model=modelo,
        max_tokens=16_000,
        system=INSTRUCOES_JUIZ,
        messages=[{"role": "user", "content": prompt_do_juiz(contrato, alertas)}],
    )
    texto = next(b.text for b in resposta.content if isinstance(getattr(b, "text", None), str))
    dados = _json_da_resposta(texto)
    return {
        "alertas": normalizar_julgamento(dados, contrato, len(alertas)),
        "tokens_entrada": resposta.usage.input_tokens,
        "tokens_saida": resposta.usage.output_tokens,
    }


def normalizar_julgamento(dados: dict, contrato: Contrato, n_alertas: int) -> list[dict]:
    """Um registro por alerta, só com ids que existem no gabarito.

    Id inventado pelo juiz é descartado e anotado, e alerta que o juiz pulou
    entra como fora do gabarito: nenhum dos dois pode virar acerto.
    """
    ids_esp = {i["id"] for i in contrato.esperados}
    ids_nao = {i["id"] for i in contrato.nao_devem}
    por_indice = {}
    for item in dados.get("alertas") or []:
        try:
            n = int(item.get("indice"))
        except (TypeError, ValueError):
            continue
        if 0 <= n < n_alertas and n not in por_indice:
            esp = [i for i in item.get("esperados") or [] if i in ids_esp]
            nao = [i for i in item.get("nao_devem") or [] if i in ids_nao]
            invalidos = [i for i in (item.get("esperados") or []) + (item.get("nao_devem") or [])
                         if i not in ids_esp | ids_nao]
            por_indice[n] = {
                "indice": n, "esperados": esp, "nao_devem": nao,
                "justificativa": str(item.get("justificativa") or ""),
                **({"ids_invalidos": invalidos} if invalidos else {}),
            }
    return [
        por_indice.get(n, {"indice": n, "esperados": [], "nao_devem": [],
                           "justificativa": "(o juiz não avaliou este alerta)"})
        for n in range(n_alertas)
    ]


# ─── Métricas de uma rodada ──────────────────────────────────────────────────

def metricas(contrato: Contrato, alertas: list[dict], julgamento: list[dict]) -> dict:
    cobertos: dict[str, list[int]] = {}
    for j in julgamento:
        for i in j["esperados"]:
            cobertos.setdefault(i, []).append(j["indice"])
    esperados = contrato.esperados
    altos = [i for i in esperados if GRAVIDADES[i["gravidade"]] == "high"]

    falsos = [j for j in julgamento if j["nao_devem"]]
    fora = [j for j in julgamento if not j["esperados"] and not j["nao_devem"]]

    com_base = [i for i in esperados if i["id"] in cobertos and i["base_legal"]]
    artigo_ok = sum(
        1 for i in com_base
        if any(cita_o_esperado(alertas[n].get("legal_basis"), i["base_legal"]) for n in cobertos[i["id"]])
    )
    gravidade_ok = sum(
        1 for i in esperados if i["id"] in cobertos
        and any(alertas[n].get("severity") == GRAVIDADES[i["gravidade"]] for n in cobertos[i["id"]])
    )
    com_citacao = [a for a in alertas if a.get("legal_basis")]
    return {
        "alertas": len(alertas),
        "achados_livres": sum(1 for a in alertas if a.get("origin") == "finding"),
        "cobertura": len(cobertos) / len(esperados) if esperados else None,
        "cobertura_alta": (sum(1 for i in altos if i["id"] in cobertos) / len(altos)) if altos else None,
        "esperados_cobertos": sorted(cobertos),
        "esperados_perdidos": [i["id"] for i in esperados if i["id"] not in cobertos],
        "falsos_positivos": len(falsos),
        "falsos_positivos_ids": sorted({i for j in falsos for i in j["nao_devem"]}),
        "fora_do_gabarito": len(fora),
        "com_citacao": len(com_citacao),
        "citacoes_confirmadas": sum(
            1 for a in com_citacao if a.get("legal_basis_check") in ("grounded", "in_base")
        ),
        "artigo_esperado": (artigo_ok / len(com_base)) if com_base else None,
        "gravidade_igual": (gravidade_ok / len(cobertos)) if cobertos else None,
    }


# ─── Execução ────────────────────────────────────────────────────────────────

@dataclass
class Tarefa:
    versao: str
    caso: str
    contrato: Contrato
    rodada: int
    resultado: dict = field(default_factory=dict)


def _git_commit() -> Optional[str]:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ,
                              capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception:
        return None


def estimar(contratos: list[Contrato], versoes: list[str], casos: list[str], rodadas: int,
            modelo: str, modelo_juiz: str) -> dict:
    from app.services.ai_analyzer import SYSTEM_PROMPT_V5, _build_user_prompt

    regras = regras_do_seed()
    entrada = saida = entrada_juiz = 0
    for c in contratos:
        for v in versoes:
            for caso in casos:
                chars = len(SYSTEM_PROMPT_V5) + len(
                    _build_user_prompt(c.texto, regras if caso == "com" else [], [], None, versao=v)
                ) + CONTEXTO_RAG_ESTIMADO
                entrada += rodadas * chars / CARACTERES_POR_TOKEN
                saida += rodadas * SAIDA_ESTIMADA_ANALISE
                entrada_juiz += rodadas * (2_500 + 1_500 * len(c.esperados)) / CARACTERES_POR_TOKEN
    n = len(contratos) * len(versoes) * len(casos) * rodadas
    saida_juiz = n * SAIDA_ESTIMADA_JUIZ
    custo = None
    if modelo in PRECOS and modelo_juiz in PRECOS:
        (pe, ps), (je, js) = PRECOS[modelo], PRECOS[modelo_juiz]
        custo = (entrada * pe + saida * ps + entrada_juiz * je + saida_juiz * js) / 1e6
    return {"analises": n, "tokens_entrada": int(entrada + entrada_juiz),
            "tokens_saida": int(saida + saida_juiz), "custo_usd": custo}


def custo_real(execucoes: list[dict], modelo: str, modelo_juiz: str) -> Optional[float]:
    if modelo not in PRECOS or modelo_juiz not in PRECOS:
        return None
    (pe, ps), (je, js) = PRECOS[modelo], PRECOS[modelo_juiz]
    total = 0.0
    for e in execucoes:
        total += (e.get("tokens_entrada") or 0) * pe + (e.get("tokens_saida") or 0) * ps
        juiz = e.get("juiz") or {}
        total += (juiz.get("tokens_entrada") or 0) * je + (juiz.get("tokens_saida") or 0) * js
    return total / 1e6


def contextos_legais(contratos: list[Contrato], casos: list[str], usar_rag: bool) -> dict:
    """Contexto legal por contrato e caso. A busca é determinística; faz-se uma vez."""
    if not usar_rag:
        return {(c.nome, caso): [] for c in contratos for caso in casos}
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from app.core.config import get_settings
    from app.services.rag_service import build_legal_context_sync

    regras = regras_do_seed()
    engine = create_engine(get_settings().DATABASE_URL_SYNC)
    saida = {}
    try:
        with Session(engine) as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            for c in contratos:
                for caso in casos:
                    saida[(c.nome, caso)] = build_legal_context_sync(
                        c.texto, regras if caso == "com" else [], db
                    )
            db.rollback()
    finally:
        engine.dispose()
    return saida


def anotar(execucoes: list[Tarefa], contextos: dict, usar_rag: bool) -> None:
    """Verificação de trecho e de citação, como na análise real. Só leitura."""
    from app.services.verification import annotate_alerts

    if not usar_rag:
        for t in execucoes:
            if "alerts" in t.resultado:
                t.resultado["alerts"] = annotate_alerts(t.resultado["alerts"], t.contrato.texto, [])
        return
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from app.core.config import get_settings
    from app.services.rag_service import make_base_lookup

    engine = create_engine(get_settings().DATABASE_URL_SYNC)
    try:
        with Session(engine) as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            busca = make_base_lookup(db)
            for t in execucoes:
                if "alerts" in t.resultado:
                    t.resultado["alerts"] = annotate_alerts(
                        t.resultado["alerts"], t.contrato.texto,
                        contextos[(t.contrato.nome, t.caso)], busca,
                    )
            db.rollback()
    finally:
        engine.dispose()


def rodar_tarefa(t: Tarefa, contexto: list, max_tokens: int) -> Tarefa:
    from app.services.ai_analyzer import analyze_document

    regras = regras_do_seed() if t.caso == "com" else []
    inicio = time.monotonic()
    try:
        r = analyze_document(t.contrato.texto, regras, legal_context=contexto,
                             feedback_learnings=[], prompt_version=t.versao)
    except Exception as e:  # noqa: BLE001 - uma rodada que falha é dado, não motivo para parar
        t.resultado = {"erro": f"{type(e).__name__}: {e}",
                       "estourou_teto": "excedeu o limite de resposta" in str(e),
                       "duracao_s": time.monotonic() - inicio}
        return t
    t.resultado = {
        "alerts": r.alerts, "risk_score": r.risk_score, "summary": r.summary,
        "missing_clauses": r.missing_clauses, "prompt_version": r.prompt_version,
        "tokens_entrada": r.prompt_tokens, "tokens_saida": r.completion_tokens,
        "duracao_s": r.duration_ms / 1000,
        "perto_do_teto": r.completion_tokens >= PERTO_DO_TETO * max_tokens,
        "estourou_teto": False,
    }
    return t


# Erros que valem para todas as chamadas seguintes: insistir só enche o
# resultado de falhas iguais. A execução para e pode ser retomada depois.
_ERROS_FATAIS = ("credit balance is too low", "invalid x-api-key", "authentication_error")


def erro_fatal(mensagem: Optional[str]) -> bool:
    return bool(mensagem) and any(f in mensagem for f in _ERROS_FATAIS)


def precisa_refazer(e: dict) -> bool:
    """Análise que falhou por motivo externo. Estourar o teto é resultado, não falha."""
    return bool(e.get("erro")) and not e.get("estourou_teto")


def julgar_tarefa(t: Tarefa, modelo_juiz: str) -> Tarefa:
    try:
        t.resultado["juiz"] = julgar(t.contrato, t.resultado["alerts"], modelo_juiz)
        t.resultado["metricas"] = metricas(t.contrato, t.resultado["alerts"], t.resultado["juiz"]["alertas"])
    except Exception as e:  # noqa: BLE001
        t.resultado["erro_juiz"] = f"{type(e).__name__}: {e}"
    return t


# ─── Agregação e impressão ───────────────────────────────────────────────────

METRICAS_TABELA = [
    ("cobertura", "cobertura", "pct"),
    ("cobertura_alta", "cobertura graves", "pct"),
    ("falsos_positivos", "falsos positivos", "num"),
    ("fora_do_gabarito", "fora do gabarito", "num"),
    ("alertas", "alertas", "num"),
    ("taxa_citacao_confirmada", "citações confirmadas", "pct"),
    ("artigo_esperado", "artigo esperado", "pct"),
    ("duracao_s", "tempo (s)", "num"),
    ("tokens_saida", "tokens de saída", "int"),
    ("perto_do_teto", "perto do teto", "cont"),
    ("estourou_teto", "estourou o teto", "cont"),
]


def _valores_da_execucao(e: dict) -> dict:
    m = e.get("metricas") or {}
    v = {k: m.get(k) for k in ("cobertura", "cobertura_alta", "falsos_positivos",
                               "fora_do_gabarito", "alertas", "artigo_esperado")}
    v["taxa_citacao_confirmada"] = (
        m["citacoes_confirmadas"] / m["alertas"] if m.get("alertas") else None
    )
    v["duracao_s"] = e.get("duracao_s")
    v["tokens_saida"] = e.get("tokens_saida")
    v["perto_do_teto"] = 1 if e.get("perto_do_teto") else 0
    v["estourou_teto"] = 1 if e.get("estourou_teto") else 0
    return v


def agregar(execucoes: list[dict]) -> dict:
    """Média e desvio entre rodadas, por versão e caso, e por contrato.

    Primeiro a média dos contratos dentro de cada rodada, depois média e desvio
    entre as rodadas: o desvio mede o quanto o resultado varia de uma execução
    para outra, que é a pergunta que importa ao comparar versões.
    """
    grupos: dict[tuple, dict[int, list[dict]]] = {}
    for e in execucoes:
        grupos.setdefault((e["versao"], e["caso"]), {}).setdefault(e["rodada"], []).append(e)

    def resumo(valores: list[Optional[float]], modo: str) -> dict:
        xs = [x for x in valores if x is not None]
        if not xs:
            return {"media": None, "desvio": None, "n": 0}
        if modo == "cont":
            return {"media": sum(xs), "desvio": None, "n": len(xs)}
        return {"media": statistics.fmean(xs),
                "desvio": statistics.stdev(xs) if len(xs) > 1 else 0.0, "n": len(xs)}

    saida = {}
    for (versao, caso), por_rodada in sorted(grupos.items()):
        geral = {}
        for chave, _, modo in METRICAS_TABELA:
            if modo == "cont":
                geral[chave] = resumo([_valores_da_execucao(e)[chave]
                                       for es in por_rodada.values() for e in es], modo)
                continue
            medias_por_rodada = []
            for es in por_rodada.values():
                xs = [_valores_da_execucao(e)[chave] for e in es]
                xs = [x for x in xs if x is not None]
                medias_por_rodada.append(statistics.fmean(xs) if xs else None)
            geral[chave] = resumo(medias_por_rodada, modo)
        por_contrato = {}
        for e in (e for es in por_rodada.values() for e in es):
            por_contrato.setdefault(e["contrato"], []).append(e)
        saida[f"v{versao}/{caso}"] = {
            "geral": geral,
            "contratos": {
                nome: {chave: resumo([_valores_da_execucao(e)[chave] for e in es], modo)
                       for chave, _, modo in METRICAS_TABELA}
                for nome, es in sorted(por_contrato.items())
            },
            "erros": sum(1 for es in por_rodada.values() for e in es if e.get("erro") or e.get("erro_juiz")),
        }
    return saida


def _fmt(r: dict, modo: str) -> str:
    if r["media"] is None:
        return "—"
    if modo == "cont":
        return f"{int(r['media'])}/{r['n']}"
    if modo == "pct":
        return f"{100 * r['media']:.0f}% ±{100 * r['desvio']:.0f}"
    if modo == "int":
        return f"{r['media']:,.0f} ±{r['desvio']:,.0f}".replace(",", ".")
    return f"{r['media']:.1f} ±{r['desvio']:.1f}"


def imprimir_tabela(agregado: dict, detalhado: bool = True) -> None:
    colunas = list(agregado)
    largura = max(22, *(len(c) + 2 for c in colunas))
    print("\n" + "métrica".ljust(24) + "".join(c.rjust(largura) for c in colunas))
    for chave, rotulo, modo in METRICAS_TABELA:
        print(rotulo.ljust(24) + "".join(_fmt(agregado[c]["geral"][chave], modo).rjust(largura)
                                         for c in colunas))
    print("erros".ljust(24) + "".join(str(agregado[c]["erros"]).rjust(largura) for c in colunas))
    if not detalhado:
        return
    contratos = sorted({n for c in colunas for n in agregado[c]["contratos"]})
    for chave, rotulo, modo in METRICAS_TABELA[:4]:
        print(f"\n{rotulo}, por contrato:")
        for nome in contratos:
            print(f"  {nome:<26}" + "".join(
                (_fmt(agregado[c]["contratos"][nome][chave], modo) if nome in agregado[c]["contratos"] else "—").rjust(largura)
                for c in colunas))


def imprimir_fora_do_gabarito(execucoes: list[dict]) -> None:
    print("\nALERTAS FORA DO GABARITO (para revisão manual):")
    for e in execucoes:
        for j in (e.get("juiz") or {}).get("alertas", []):
            if not j["esperados"] and not j["nao_devem"]:
                a = e["alerts"][j["indice"]]
                print(f"  v{e['versao']}/{e['caso']} r{e['rodada']} {e['contrato']}: "
                      f"[{a.get('origin')}] {a.get('rule_name')} — {j['justificativa']}")
    print("\nFALSOS POSITIVOS:")
    for e in execucoes:
        for j in (e.get("juiz") or {}).get("alertas", []):
            if j["nao_devem"]:
                a = e["alerts"][j["indice"]]
                print(f"  v{e['versao']}/{e['caso']} r{e['rodada']} {e['contrato']}: "
                      f"{a.get('rule_name')} -> {', '.join(j['nao_devem'])} — {j['justificativa']}")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def _lista(valor: str) -> list[str]:
    return [v.strip() for v in valor.split(",") if v.strip()]


def main(argv=None) -> int:
    from app.core.config import get_settings
    from app.services import ai_analyzer

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--versoes", type=_lista, default=[ai_analyzer.PROMPT_VERSION_PADRAO],
                   help="versões do prompt, separadas por vírgula (ex.: 4,5)")
    p.add_argument("--casos", type=_lista, default=list(CASOS),
                   help="sem (sem regras), com (regras ativas do seed) ou os dois")
    p.add_argument("--rodadas", type=int, default=3)
    p.add_argument("--contratos", type=_lista, default=None,
                   help="prefixos dos arquivos (ex.: 01,05); padrão: todos")
    p.add_argument("--modelo-juiz", default=None, help="padrão: ANTHROPIC_MODEL")
    p.add_argument("--max-tokens", type=int, default=None,
                   help="teto de saída da análise; padrão: ANTHROPIC_MAX_TOKENS")
    p.add_argument("--paralelo", type=int, default=4, help="análises simultâneas")
    p.add_argument("--sem-rag", action="store_true", help="não consulta a base legal")
    p.add_argument("--saida", type=Path, default=None)
    p.add_argument("--sim", action="store_true", help="não pede confirmação do custo")
    p.add_argument("--estimar", action="store_true", help="só mostra a estimativa de custo")
    p.add_argument("--comparar", nargs="+", type=Path, help="imprime a tabela de resultados já salvos")
    p.add_argument("--retomar", type=Path, help="refaz o que falhou numa execução salva e julga o que faltou")
    args = p.parse_args(argv)

    if args.retomar:
        return retomar(args.retomar, args)

    if args.comparar:
        agregado = {}
        for arquivo in args.comparar:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
            for chave, valor in dados["agregado"].items():
                agregado[f"{arquivo.stem}:{chave}" if len(args.comparar) > 1 else chave] = valor
        imprimir_tabela(agregado)
        return 0

    for v in args.versoes:
        ai_analyzer.versao_do_prompt(v)
    for c in args.casos:
        if c not in CASOS:
            p.error(f"caso desconhecido: {c} (use sem e/ou com)")

    settings = get_settings()
    if args.max_tokens:
        settings.ANTHROPIC_MAX_TOKENS = args.max_tokens
    modelo, modelo_juiz = settings.ANTHROPIC_MODEL, args.modelo_juiz or settings.ANTHROPIC_MODEL
    contratos = carregar_contratos(filtro=args.contratos)

    est = estimar(contratos, args.versoes, args.casos, args.rodadas, modelo, modelo_juiz)
    print(f"Contratos: {', '.join(c.nome for c in contratos)}")
    print(f"Versões {', '.join(args.versoes)} · casos {', '.join(args.casos)} · {args.rodadas} rodadas")
    print(f"Modelo {modelo} · juiz {modelo_juiz} · ANTHROPIC_MAX_TOKENS {settings.ANTHROPIC_MAX_TOKENS}")
    if settings.ANTHROPIC_MAX_TOKENS < 16_384:
        print("  aviso: teto abaixo do padrão de produção (16384); use --max-tokens 16384 para medir como lá")
    milhar = lambda n: f"{n:,}".replace(",", ".")
    print(f"Estimativa: {est['analises']} análises + {est['analises']} julgamentos, "
          f"~{milhar(est['tokens_entrada'])} tokens de entrada e ~{milhar(est['tokens_saida'])} de saída")
    print(f"Custo estimado: " + (f"~US$ {est['custo_usd']:.2f}" if est["custo_usd"] is not None
                                 else "sem preço na tabela para esse modelo"))
    if any(not c.gabarito["revisado_por_profissional"] for c in contratos):
        print("Atenção: há gabaritos não revisados por profissional.")
    if args.estimar:
        return 0
    if not args.sim and input("Continuar? [s/N] ").strip().lower() not in ("s", "sim"):
        print("Cancelado.")
        return 1

    tarefas = [Tarefa(v, caso, c, r) for r in range(1, args.rodadas + 1)
               for v in args.versoes for caso in args.casos for c in contratos]
    meta = {
        "data": datetime.now().isoformat(timespec="seconds"), "commit": _git_commit(),
        "modelo": modelo, "modelo_juiz": modelo_juiz,
        "max_tokens": settings.ANTHROPIC_MAX_TOKENS, "versoes": args.versoes,
        "casos": args.casos, "rodadas": args.rodadas, "rag": not args.sem_rag,
        "contratos": [c.nome for c in contratos],
        "gabaritos_revisados": all(c.gabarito["revisado_por_profissional"] for c in contratos),
    }
    destino = args.saida or PASTA_RESULTADOS / (
        f"{datetime.now():%Y%m%d-%H%M}_v{'-'.join(args.versoes)}.json"
    )
    return _executar_e_salvar(tarefas, [], meta, destino, args, settings.ANTHROPIC_MAX_TOKENS)


def _executar_e_salvar(analisar: list[Tarefa], so_julgar: list[Tarefa], meta: dict,
                       destino: Path, args, max_tokens: int) -> int:
    """Analisa, anota e julga; agrega e grava. Usado pela execução nova e pela retomada."""
    modelo, modelo_juiz = meta["modelo"], meta["modelo_juiz"]
    inicio = time.monotonic()
    contratos = list({t.contrato.nome: t.contrato for t in analisar}.values())
    casos = sorted({t.caso for t in analisar})
    contextos = contextos_legais(contratos, casos, meta["rag"]) if analisar else {}
    feitas, parou = [], None
    with ThreadPoolExecutor(max(1, args.paralelo)) as ex:
        futuros = [ex.submit(rodar_tarefa, t, contextos[(t.contrato.nome, t.caso)], max_tokens)
                   for t in analisar]
        n = 0
        for f in as_completed(futuros):
            if f.cancelled():
                continue
            n += 1
            t = f.result()
            feitas.append(t)
            r = t.resultado
            estado = (f"ERRO {r['erro'][:80]}" if "erro" in r
                      else f"{len(r['alerts'])} alertas, {r['tokens_saida']} tokens, {r['duracao_s']:.0f}s")
            print(f"[{n}/{len(analisar)}] v{t.versao}/{t.caso} r{t.rodada} {t.contrato.nome}: {estado}", flush=True)
            if parou is None and erro_fatal(r.get("erro")):
                parou = r["erro"]
                print("Erro que vale para as próximas chamadas; parando. Retome com --retomar.", flush=True)
                for outro in futuros:
                    outro.cancel()
    # As canceladas não rodaram: ficam registradas como falha a refazer.
    vistas = {id(t) for t in feitas}
    for t in analisar:
        if id(t) not in vistas:
            t.resultado = {"erro": f"não executada: {parou}", "estourou_teto": False}
            feitas.append(t)

    anotar([t for t in feitas if "alerts" in t.resultado], contextos, meta["rag"])
    a_julgar = [t for t in feitas + so_julgar if "alerts" in t.resultado and "metricas" not in t.resultado]
    if parou is None:
        with ThreadPoolExecutor(max(1, args.paralelo)) as ex:
            list(ex.map(lambda t: julgar_tarefa(t, modelo_juiz), a_julgar))
        juizes_fatais = {t.resultado.get("erro_juiz") for t in a_julgar if erro_fatal(t.resultado.get("erro_juiz"))}
        if juizes_fatais:
            print("O juiz falhou por um erro que vale para as próximas chamadas. Retome com --retomar.")

    todas = feitas + [t for t in so_julgar if t not in feitas]
    execucoes = [
        {"versao": t.versao, "caso": t.caso, "contrato": t.contrato.nome, "rodada": t.rodada, **t.resultado}
        for t in sorted(todas, key=lambda t: (t.versao, t.caso, t.contrato.nome, t.rodada))
    ]
    agregado = agregar(execucoes)
    custo = custo_real(execucoes, modelo, modelo_juiz)
    meta = {**meta, "duracao_total_s": round(meta.get("duracao_total_s", 0) + time.monotonic() - inicio),
            "custo_usd": custo,
            "pendentes": sum(1 for e in execucoes if precisa_refazer(e)
                             or ("alerts" in e and "metricas" not in e))}
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({"meta": meta, "agregado": agregado, "execucoes": execucoes},
                                  ensure_ascii=False, indent=1), encoding="utf-8")

    imprimir_tabela(agregado)
    imprimir_fora_do_gabarito(execucoes)
    print(f"\nCusto real acumulado: " + (f"US$ {custo:.2f}" if custo is not None else "sem preço na tabela"))
    if meta["pendentes"]:
        print(f"Pendentes: {meta['pendentes']} execuções sem resultado completo. Retome com --retomar {destino}")
    print(f"Resultado completo: {destino}")
    return 0 if not meta["pendentes"] else 2


def retomar(arquivo: Path, args) -> int:
    from app.core.config import get_settings

    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    meta = dados["meta"]
    por_nome = {c.nome: c for c in carregar_contratos(filtro=None)}
    tarefas = [Tarefa(e["versao"], e["caso"], por_nome[e["contrato"]], e["rodada"],
                      {k: v for k, v in e.items() if k not in ("versao", "caso", "contrato", "rodada")})
               for e in dados["execucoes"]]
    analisar = [t for t in tarefas if precisa_refazer(t.resultado)]
    for t in tarefas:
        t.resultado.pop("erro_juiz", None)
    so_julgar = [t for t in tarefas if t not in analisar]
    n_julgar = sum(1 for t in so_julgar if "alerts" in t.resultado and "metricas" not in t.resultado)

    settings = get_settings()
    settings.ANTHROPIC_MAX_TOKENS = meta["max_tokens"]
    if meta["modelo"] != settings.ANTHROPIC_MODEL:
        print(f"aviso: o arquivo foi gerado com {meta['modelo']}, e ANTHROPIC_MODEL agora é "
              f"{settings.ANTHROPIC_MODEL}; as análises refeitas usam o atual.")
    est_analise = estimar(list({t.contrato.nome: t.contrato for t in analisar}.values()) or [],
                          ["5"], ["com"], 1, meta["modelo"], meta["modelo_juiz"]) if analisar else None
    por_analise = (est_analise["custo_usd"] / est_analise["analises"]) if est_analise and est_analise["custo_usd"] else None
    print(f"Retomando {arquivo.name}: {len(analisar)} análises a refazer e "
          f"{len(analisar) + n_julgar} julgamentos")
    # Um julgamento sai de ~6 mil tokens de entrada e SAIDA_ESTIMADA_JUIZ de saída.
    por_juiz = None
    if meta["modelo_juiz"] in PRECOS:
        je, js = PRECOS[meta["modelo_juiz"]]
        por_juiz = (6_000 * je + SAIDA_ESTIMADA_JUIZ * js) / 1e6
    if por_juiz is not None and (por_analise is not None or not analisar):
        print(f"Custo estimado: ~US$ {(por_analise or 0) * len(analisar) + por_juiz * n_julgar:.2f}")
    else:
        print("Custo estimado: sem preço na tabela para esse modelo")
    if args.estimar:
        return 0
    if not args.sim and input("Continuar? [s/N] ").strip().lower() not in ("s", "sim"):
        print("Cancelado.")
        return 1
    return _executar_e_salvar(analisar, so_julgar, meta, args.saida or arquivo, args, meta["max_tokens"])


if __name__ == "__main__":
    sys.exit(main())
