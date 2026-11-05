"""Lógica do script de avaliação do prompt, sem chamar a API.

A execução em si (app/scripts/eval_prompt.py) é manual, porque chama a Anthropic
e custa dinheiro. Aqui só o que pode quebrar sem custo: gabaritos válidos,
casamento de citação, métricas e agregação.
"""
from unittest.mock import patch

import pytest

from app.scripts import eval_prompt as ev


def _contrato(esperados=None, nao_devem=None):
    return ev.Contrato(nome="x", texto="t", gabarito={
        "contrato": "x.txt", "tipo": "teste", "revisado_por_profissional": False,
        "problemas_esperados": esperados if esperados is not None else [
            {"id": "juros", "clausula": "2", "problema": "p", "gravidade": "alta",
             "base_legal": ["Art. 406, Código Civil"]},
            {"id": "sigilo", "clausula": "-", "problema": "p", "gravidade": "média", "base_legal": []},
        ],
        "nao_devem_aparecer": nao_devem if nao_devem is not None else [
            {"id": "foro", "clausula": "9", "o_que_seria_errado": "o", "por_que": "p"},
        ],
    })


# ─── Gabaritos ───────────────────────────────────────────────────────────────

def test_os_cinco_gabaritos_carregam_e_avisam_que_nao_foram_revisados():
    contratos = ev.carregar_contratos()
    assert len(contratos) == 5
    for c in contratos:
        assert c.gabarito["revisado_por_profissional"] is False
        topo = (ev.PASTA_CONTRATOS / f"{c.nome}.yaml").read_text(encoding="utf-8")[:400]
        assert "GABARITO NÃO REVISADO POR PROFISSIONAL" in topo
        assert c.esperados and len(c.texto) > 1000


def test_contrato_equilibrado_tem_poucos_problemas_e_muitos_nao_devem():
    equilibrado = next(c for c in ev.carregar_contratos() if "equilibrado" in c.nome)
    assert len(equilibrado.esperados) <= 2
    assert len(equilibrado.nao_devem) >= 5


@pytest.mark.parametrize("estrago, mensagem", [
    (lambda g: g.pop("tipo"), "falta 'tipo'"),
    (lambda g: g["problemas_esperados"][0].update(gravidade="gravíssima"), "gravidade"),
    (lambda g: g["problemas_esperados"][0].update(base_legal="Art. 1"), "lista"),
    (lambda g: g["nao_devem_aparecer"][0].update(id="juros"), "repetidos"),
])
def test_gabarito_malformado_falha_com_o_nome_do_arquivo(estrago, mensagem):
    g = _contrato().gabarito
    estrago(g)
    with pytest.raises(ValueError, match=mensagem):
        ev.validar_gabarito(g, "teste.yaml")


# ─── Citação do artigo esperado ──────────────────────────────────────────────

@pytest.mark.parametrize("citado, esperado, casa", [
    ("Art. 406, CC", ["Art. 406, Código Civil"], True),
    ("Art. 406 da Lei 10.406/2002", ["Art. 406, Código Civil"], True),
    ("Art. 16, Lei 13.709/2018", ["Art. 16, LGPD"], True),
    ("Art. 4º, Lei do Inquilinato", ["Art. 4º, Lei 8.245/1991"], True),
    ("Art. 25, Lei 8.078/1990; Art. 51, Lei 8.078/1990", ["Art. 51, CDC"], True),
    ("Art. 406, LGPD", ["Art. 406, Código Civil"], False),     # artigo certo, lei errada
    ("Art. 407, Código Civil", ["Art. 406, Código Civil"], False),
    ("Código Civil", ["Art. 406, Código Civil"], False),        # sem artigo
    (None, ["Art. 406, Código Civil"], False),
    ("Art. 406, CC", [], False),
])
def test_cita_o_esperado(citado, esperado, casa):
    assert ev.cita_o_esperado(citado, esperado) is casa


# ─── Julgamento e métricas ───────────────────────────────────────────────────

def test_julgamento_descarta_id_inventado_e_preenche_alerta_pulado():
    j = ev.normalizar_julgamento(
        {"alertas": [{"indice": 0, "esperados": ["juros", "inventado"], "nao_devem": [],
                      "justificativa": "ok"},
                     {"indice": 9, "esperados": ["juros"]}]},
        _contrato(), 2,
    )
    assert j[0]["esperados"] == ["juros"] and j[0]["ids_invalidos"] == ["inventado"]
    assert j[1]["esperados"] == [] and "não avaliou" in j[1]["justificativa"]


def test_metricas_de_uma_rodada():
    alertas = [
        {"rule_name": "Juros", "origin": "finding", "severity": "high",
         "legal_basis": "Art. 406, CC", "legal_basis_check": "in_base"},
        {"rule_name": "Foro", "origin": "rule", "severity": "high",
         "legal_basis": None, "legal_basis_check": "empty"},
        {"rule_name": "Outro", "origin": "finding", "severity": "low",
         "legal_basis": "Art. 1, X", "legal_basis_check": "ungrounded"},
    ]
    julgamento = [
        {"indice": 0, "esperados": ["juros"], "nao_devem": [], "justificativa": ""},
        {"indice": 1, "esperados": [], "nao_devem": ["foro"], "justificativa": ""},
        {"indice": 2, "esperados": [], "nao_devem": [], "justificativa": ""},
    ]
    m = ev.metricas(_contrato(), alertas, julgamento)
    assert m["cobertura"] == 0.5 and m["cobertura_alta"] == 1.0
    assert m["esperados_perdidos"] == ["sigilo"]
    assert m["falsos_positivos"] == 1 and m["falsos_positivos_ids"] == ["foro"]
    assert m["fora_do_gabarito"] == 1
    assert m["com_citacao"] == 2 and m["citacoes_confirmadas"] == 1
    assert m["artigo_esperado"] == 1.0 and m["gravidade_igual"] == 1.0
    assert m["achados_livres"] == 2


def test_agrega_media_entre_contratos_e_desvio_entre_rodadas():
    def execucao(rodada, contrato, cobertura, perto=False):
        return {"versao": "5", "caso": "sem", "rodada": rodada, "contrato": contrato,
                "duracao_s": 10, "tokens_saida": 1000, "perto_do_teto": perto,
                "metricas": {"cobertura": cobertura, "cobertura_alta": None, "falsos_positivos": 0,
                             "fora_do_gabarito": 0, "alertas": 2, "artigo_esperado": None,
                             "citacoes_confirmadas": 1}}
    execucoes = [execucao(1, "a", 1.0), execucao(1, "b", 0.0),
                 execucao(2, "a", 1.0, perto=True), execucao(2, "b", 1.0)]
    g = ev.agregar(execucoes)["v5/sem"]
    assert g["geral"]["cobertura"]["media"] == pytest.approx(0.75)   # rodadas 0,5 e 1,0
    assert g["geral"]["cobertura"]["desvio"] == pytest.approx(0.3536, abs=1e-3)
    assert g["geral"]["perto_do_teto"]["media"] == 1 and g["geral"]["perto_do_teto"]["n"] == 4
    assert g["contratos"]["b"]["cobertura"]["media"] == 0.5
    assert g["geral"]["taxa_citacao_confirmada"]["media"] == 0.5


def test_execucao_com_erro_conta_no_teto_e_nos_erros():
    g = ev.agregar([{"versao": "4", "caso": "com", "rodada": 1, "contrato": "a",
                     "erro": "ValueError: excedeu o limite de resposta", "estourou_teto": True}])["v4/com"]
    assert g["erros"] == 1 and g["geral"]["estourou_teto"]["media"] == 1
    assert g["geral"]["cobertura"]["media"] is None


# ─── Custo e CLI ─────────────────────────────────────────────────────────────

def test_estimativa_de_custo():
    contratos = ev.carregar_contratos(filtro=["05"])
    est = ev.estimar(contratos, ["4", "5"], ["sem", "com"], 3, "claude-sonnet-5", "claude-sonnet-5")
    assert est["analises"] == 12
    assert 0.5 < est["custo_usd"] < 5
    assert ev.estimar(contratos, ["4"], ["sem"], 1, "modelo-x", "claude-sonnet-5")["custo_usd"] is None


def test_estimar_nao_chama_a_api(capsys):
    with patch.object(ev, "rodar_tarefa", side_effect=AssertionError("chamou")), \
         patch.object(ev, "julgar", side_effect=AssertionError("chamou")), \
         patch.object(ev, "contextos_legais", side_effect=AssertionError("chamou")):
        assert ev.main(["--versoes", "4,5", "--estimar"]) == 0
    saida = capsys.readouterr().out
    assert "Custo estimado" in saida and "não revisados" in saida


CREDITO = "BadRequestError: Error code: 400 - Your credit balance is too low to access the Anthropic API"


def test_falha_externa_se_refaz_e_estouro_do_teto_nao():
    assert ev.precisa_refazer({"erro": CREDITO, "estourou_teto": False})
    assert not ev.precisa_refazer({"erro": "ValueError: excedeu", "estourou_teto": True})
    assert not ev.precisa_refazer({"alerts": []})
    assert ev.erro_fatal(CREDITO) and not ev.erro_fatal("APIConnectionError: timeout")


def _sem_api(monkeypatch, analisar):
    chamadas = {"analise": [], "juiz": []}

    def rodar(t, _ctx, _max):
        chamadas["analise"].append((t.versao, t.contrato.nome, t.rodada))
        t.resultado = analisar(t)
        return t

    def julgar(contrato, alertas, _modelo):
        chamadas["juiz"].append(contrato.nome)
        return {"alertas": [{"indice": 0, "esperados": [contrato.esperados[0]["id"]], "nao_devem": [],
                             "justificativa": "j"}], "tokens_entrada": 10, "tokens_saida": 10}

    monkeypatch.setattr(ev, "rodar_tarefa", rodar)
    monkeypatch.setattr(ev, "julgar", julgar)
    monkeypatch.setattr(ev, "contextos_legais", lambda cs, casos, _rag: {(c.nome, k): [] for c in cs for k in casos})
    monkeypatch.setattr(ev, "anotar", lambda *a: None)
    return chamadas


def _ok(_t):
    return {"alerts": [{"rule_name": "r", "severity": "high", "legal_basis": None}],
            "tokens_entrada": 100, "tokens_saida": 100, "duracao_s": 1.0,
            "perto_do_teto": False, "estourou_teto": False}


def test_erro_de_credito_para_a_execucao_e_retomar_completa(monkeypatch, tmp_path, capsys):
    """Sem crédito, as chamadas seguintes falham iguais: para, grava e retoma depois."""
    sem_credito = _sem_api(monkeypatch, lambda t: {"erro": CREDITO, "estourou_teto": False})
    destino = tmp_path / "r.json"
    codigo = ev.main(["--versoes", "5", "--casos", "sem", "--rodadas", "2", "--contratos", "05",
                      "--paralelo", "1", "--sim", "--sem-rag", "--saida", str(destino)])
    assert codigo == 2
    assert len(sem_credito["analise"]) == 1          # a segunda foi cancelada
    assert sem_credito["juiz"] == []
    import json
    salvo = json.loads(destino.read_text(encoding="utf-8"))
    assert salvo["meta"]["pendentes"] == 2

    com_credito = _sem_api(monkeypatch, _ok)
    assert ev.main(["--retomar", str(destino), "--sim", "--paralelo", "1"]) == 0
    assert sorted(r for *_, r in com_credito["analise"]) == [1, 2]
    salvo = json.loads(destino.read_text(encoding="utf-8"))
    assert salvo["meta"]["pendentes"] == 0
    assert all(e["metricas"]["cobertura"] == 1.0 for e in salvo["execucoes"])


def test_retomar_nao_refaz_o_que_ja_foi_analisado_nem_o_que_estourou(monkeypatch, tmp_path):
    import json
    destino = tmp_path / "r.json"
    base = {"versao": "4", "caso": "sem", "contrato": "05_manutencao_equilibrado"}
    destino.write_text(json.dumps({
        "meta": {"modelo": "claude-sonnet-5", "modelo_juiz": "claude-sonnet-5", "max_tokens": 16384,
                 "rag": False},
        "agregado": {},
        "execucoes": [
            {**base, "rodada": 1, **_ok(None), "erro_juiz": CREDITO},   # só falta julgar
            {**base, "rodada": 2, "erro": "ValueError: excedeu o limite de resposta",
             "estourou_teto": True},                                    # resultado, não falha
            {**base, "rodada": 3, "erro": CREDITO, "estourou_teto": False},
        ],
    }), encoding="utf-8")
    chamadas = _sem_api(monkeypatch, _ok)

    assert ev.main(["--retomar", str(destino), "--sim"]) == 0

    assert [r for *_, r in chamadas["analise"]] == [3]
    assert len(chamadas["juiz"]) == 2
    salvo = json.loads(destino.read_text(encoding="utf-8"))
    assert [("metricas" in e, e.get("estourou_teto")) for e in salvo["execucoes"]] == [
        (True, False), (False, True), (True, False)]
    assert salvo["agregado"]["v4/sem"]["geral"]["estourou_teto"]["media"] == 1


def test_versao_desconhecida_falha_antes_de_gastar():
    with pytest.raises(ValueError, match="desconhecida"):
        ev.main(["--versoes", "7", "--estimar"])
