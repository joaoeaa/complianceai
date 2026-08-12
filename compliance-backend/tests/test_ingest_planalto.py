"""Identidade da lei na reingestão.

A limpeza antes de reingerir comparava o texto da fonte, então "Lei 8.078/1990"
não reconhecia "Lei 8.078/1990 (CDC)" gravada por um seed antigo como sendo a
mesma lei. As duas versões ficavam na base, e os oito trechos velhos, de artigos
escolhidos a mão, competiam na busca vetorial com o CDC íntegro.
"""
import pytest

from app.scripts.ingest_planalto import CATALOGO, chave_da_lei


@pytest.mark.parametrize(
    "escrita_antiga,escrita_nova",
    [
        ("Lei 8.078/1990 (CDC)", "Lei 8.078/1990"),
        ("Decreto-Lei 5.452/1943 (CLT)", "Decreto-Lei 5.452/1943"),
        ("Lei 13.709/2018 - LGPD", "Lei 13.709/2018"),
        ("lei 10.406 / 2002", "Lei 10.406/2002"),
    ],
)
def test_mesma_lei_escrita_de_formas_diferentes(escrita_antiga, escrita_nova):
    assert chave_da_lei(escrita_antiga) == chave_da_lei(escrita_nova)


def test_leis_diferentes_nao_se_confundem():
    assert chave_da_lei("Lei 8.078/1990") != chave_da_lei("Lei 8.245/1991")
    # Mesmo número, anos diferentes: leis distintas.
    assert chave_da_lei("Lei 9.279/1996") != chave_da_lei("Lei 9.279/1997")


def test_fonte_sem_numero_ao_menos_casa_consigo_mesma():
    assert chave_da_lei("Constituição Federal") == chave_da_lei("  constituição federal  ")


def test_catalogo_nao_tem_duas_entradas_para_a_mesma_lei():
    """Duas entradas com a mesma chave se apagariam na ingestão em sequência."""
    chaves = [chave_da_lei(lei.fonte) for lei in CATALOGO]
    assert len(chaves) == len(set(chaves))
