"""Classificação das falhas da análise.

Mora fora de `app/workers/tasks.py` por um motivo prático: aquele módulo carrega
o Celery junto e por isso é substituído por mock em boa parte da suíte. Uma
função de classificação que vive lá não pode ser testada de verdade, e um teste
que importa o mock passa sozinho e falha acompanhado.

A mensagem devolvida aqui é a que chega à tela, então sai em português e sem
jargão: o usuário via "RetryError[<Future at 0x7f02 state=finished raised
InternalServerError>]", que não diz nem que o problema passa sozinho.
"""
from __future__ import annotations

# Sobrecarga do provedor de IA (HTTP 529) passa sozinha, mas leva minutos, e não
# os segundos que o backoff anterior esperava. Vale mais tentativa e espera maior
# nesse caso do que num erro que não vai se resolver por insistência.
ESPERA_SOBRECARGA = (60, 180, 420)  # segundos
ESPERA_PADRAO = (10, 20)


def classificar_falha(exc: Exception) -> tuple[str, str, bool]:
    """Devolve (categoria, mensagem para o usuário, vale retentar).

    A mensagem sai daqui em português e sem jargão porque é ela que chega à tela.
    Antes o usuário via "RetryError[<Future at 0x7f02 state=finished raised
    InternalServerError>]", que não diz nem que o problema é temporário.
    """
    texto = str(exc)
    causa = getattr(exc, "last_attempt", None)
    if causa is not None and causa.failed:
        texto = f"{texto} {causa.exception()}"

    if "529" in texto or "overloaded" in texto.lower():
        return (
            "sobrecarga",
            "O serviço de IA está sobrecarregado no momento. "
            "A análise será refeita automaticamente em alguns minutos.",
            True,
        )
    if "limite de resposta" in texto:
        return (
            "resposta_longa",
            "O documento gerou uma resposta maior do que o limite do modelo. "
            "Divida o documento ou reduza o número de regras ativas.",
            False,
        )
    if "não é JSON válido" in texto or "JSON" in texto:
        return (
            "resposta_invalida",
            "A IA devolveu uma resposta fora do formato esperado. "
            "Tente novamente; se persistir, avise o suporte.",
            True,
        )
    if "rate_limit" in texto.lower() or "429" in texto:
        return (
            "limite_de_uso",
            "Limite de uso da IA atingido. A análise será refeita em instantes.",
            True,
        )
    return (
        "desconhecida",
        "Tivemos um problema técnico ao analisar este documento. "
        "Tente novamente em alguns minutos.",
        True,
    )
