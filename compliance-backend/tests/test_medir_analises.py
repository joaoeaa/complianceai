"""Cálculo das taxas usadas na medição.

A tabela existe para decidir se uma mudança de prompt ou de modelo valeu a pena.
Se a conta estiver errada, a decisão vai junto.
"""
from app.scripts.medir_analises import _pct, _taxas


def test_alerta_sem_trecho_nao_entra_no_denominador():
    """Cláusula ausente não tem trecho para conferir, e contaria como falha."""
    alertas = [
        {"excerpt_check": "exact", "legal_basis_check": "grounded"},
        {"excerpt_check": "empty", "legal_basis_check": "empty"},
    ]
    conferidos, com_trecho, apoiadas, com_citacao = _taxas(alertas)
    assert (conferidos, com_trecho) == (1, 1)
    assert (apoiadas, com_citacao) == (1, 1)


def test_aproximado_conta_como_nao_conferido():
    """Só a localização exata sustenta o selo verde."""
    conferidos, com_trecho, _, _ = _taxas([{"excerpt_check": "approximate"}])
    assert (conferidos, com_trecho) == (0, 1)


def test_artigo_na_base_conta_como_apoiado():
    """`in_base` é dispositivo real, só não recuperado nesta análise."""
    _, _, apoiadas, com_citacao = _taxas([{"legal_basis_check": "in_base"}])
    assert (apoiadas, com_citacao) == (1, 1)


def test_citacao_sem_respaldo_nao_conta():
    _, _, apoiadas, com_citacao = _taxas([{"legal_basis_check": "ungrounded"}])
    assert (apoiadas, com_citacao) == (0, 1)


def test_lista_vazia_nao_quebra():
    assert _taxas([]) == (0, 0, 0, 0)
    assert _taxas(None) == (0, 0, 0, 0)


def test_percentual_sem_denominador_nao_divide_por_zero():
    assert _pct(0, 0).strip() == "."
    assert _pct(1, 2).strip() == "50.0%"
