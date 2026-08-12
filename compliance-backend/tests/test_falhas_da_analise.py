"""Classificação das falhas da análise.

O que quebrou em produção foi um HTTP 529 da API da Anthropic, sobrecarga
temporária do provedor. O usuário via "Erro na análise" e, no retorno da tarefa,
"RetryError[<Future at 0x7f02 state=finished raised InternalServerError>]", que
não diz sequer que o problema passa sozinho.
"""
import pytest

from app.services.analysis_errors import (
    ESPERA_PADRAO,
    ESPERA_SOBRECARGA,
    classificar_falha,
)


class _Tentativa:
    """Imita o last_attempt do tenacity, que embrulha a causa real."""

    failed = True

    def __init__(self, erro):
        self._erro = erro

    def exception(self):
        return self._erro


class _RetryError(Exception):
    def __init__(self, causa):
        super().__init__("RetryError[<Future at 0x7f02 state=finished>]")
        self.last_attempt = _Tentativa(causa)


def test_sobrecarga_do_provedor_e_reconhecida_dentro_do_retryerror():
    """A causa real vem embrulhada; sem desembrulhar, cai em desconhecida."""
    causa = Exception("Error code: 529 - {'type': 'overloaded_error'}")
    categoria, mensagem, retentavel = classificar_falha(_RetryError(causa))

    assert categoria == "sobrecarga"
    assert retentavel is True
    assert "sobrecarregado" in mensagem
    assert "RetryError" not in mensagem and "Future" not in mensagem


def test_resposta_longa_nao_adianta_retentar():
    """Insistir num documento que estoura o teto só repete a falha."""
    categoria, mensagem, retentavel = classificar_falha(
        ValueError("A análise excedeu o limite de resposta do modelo (16384 tokens).")
    )
    assert categoria == "resposta_longa"
    assert retentavel is False
    assert "Divida o documento" in mensagem


def test_limite_de_uso_e_retentavel():
    categoria, _, retentavel = classificar_falha(Exception("Error code: 429 rate_limit"))
    assert categoria == "limite_de_uso"
    assert retentavel is True


def test_falha_desconhecida_nao_vaza_detalhe_tecnico():
    _, mensagem, retentavel = classificar_falha(
        RuntimeError("psycopg2.OperationalError: FATAL: sorry, too many clients")
    )
    assert retentavel is True
    assert "psycopg2" not in mensagem
    assert "problema técnico" in mensagem


@pytest.mark.parametrize("exc", [
    Exception("Error code: 529"),
    Exception("overloaded_error"),
    Exception("OVERLOADED"),
])
def test_variacoes_de_sobrecarga(exc):
    assert classificar_falha(exc)[0] == "sobrecarga"


def test_espera_da_sobrecarga_e_maior_que_a_padrao():
    """529 leva minutos para passar; o backoff antigo desistia em menos de um."""
    assert min(ESPERA_SOBRECARGA) > max(ESPERA_PADRAO)
    assert sum(ESPERA_SOBRECARGA) >= 600


def test_mensagens_sao_em_portugues_e_sem_jargao():
    for exc in (Exception("529"), Exception("429"), RuntimeError("boom")):
        _, mensagem, _ = classificar_falha(exc)
        assert mensagem[0].isupper()
        for proibido in ("Traceback", "Exception", "Error code", "0x"):
            assert proibido not in mensagem
