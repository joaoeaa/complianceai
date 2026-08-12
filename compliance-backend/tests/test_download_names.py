"""Nome do arquivo nos downloads.

O relatório sai do sistema e vai para a pasta do caso, ao lado do contrato. Um
nome como `relatorio_Contrato_Loca__o.pdf` obriga a renomear à mão toda vez, e
depois de dez contratos ninguém sabe qual relatório é de qual.
"""
from urllib.parse import unquote

import pytest

from app.api.documents import _cabecalho_download, _nome_do_relatorio


def _partes(nome_visivel: str) -> tuple[str, str]:
    """Devolve (nome legível, substituto ascii) do cabeçalho gerado."""
    cabecalho = _cabecalho_download(nome_visivel)["Content-Disposition"]
    ascii_nome = cabecalho.split('"')[1]
    legivel = unquote(cabecalho.split("UTF-8''")[1])
    return legivel, ascii_nome


def test_relatorio_herda_o_nome_do_contrato():
    assert _nome_do_relatorio("Contrato Locação Comercial.pdf") == (
        "Relatório - Contrato Locação Comercial.pdf"
    )


def test_extensao_do_contrato_nao_sobra_no_relatorio():
    """DOCX vira relatório PDF, e o nome não pode terminar em .docx.pdf."""
    assert _nome_do_relatorio("aditivo.docx") == "Relatório - aditivo.pdf"


def test_contrato_sem_nome_nao_gera_arquivo_sem_nome():
    assert _nome_do_relatorio(".pdf") == "Relatório - documento.pdf"


def test_acento_sobrevive_no_nome_legivel():
    legivel, _ = _partes("Relatório - Contrato Locação.pdf")
    assert legivel == "Relatório - Contrato Locação.pdf"


def test_substituto_ascii_translitera_em_vez_de_apagar():
    """"Locação" precisa virar "Locacao", e não "Loca__o"."""
    _, ascii_nome = _partes("Relatório - Contrato Locação.pdf")
    assert ascii_nome == "Relatorio - Contrato Locacao.pdf"
    assert "_" not in ascii_nome


@pytest.mark.parametrize("proibido", ["/", "\\", ":", "*", "?", '"', "<", ">", "|"])
def test_caracteres_recusados_pelo_sistema_de_arquivos_saem(proibido):
    legivel, ascii_nome = _partes(f"Contrato{proibido}final.pdf")
    assert proibido not in legivel
    assert proibido not in ascii_nome


def test_cabecalho_e_enviavel_pelo_servidor():
    """Header HTTP é latin-1. Um nome com caractere fora disso derrubaria a resposta."""
    cabecalho = _cabecalho_download("Relatório - Contrato ☂ chuva.pdf")["Content-Disposition"]
    cabecalho.encode("latin-1")  # não deve levantar


def test_aspas_no_nome_nao_quebram_o_cabecalho():
    """Aspas dentro de filename="..." encerrariam o campo antes da hora."""
    cabecalho = _cabecalho_download('Contrato "final".pdf')["Content-Disposition"]
    assert cabecalho.count('"') == 2


def test_cors_expoe_o_cabecalho_do_nome():
    """Sem expose_headers, o navegador esconde o nome do arquivo do JavaScript.

    O front roda em domínio próprio e a API em outro, então todo download é
    cross-origin. Sem esta configuração o `Content-Disposition` existe na resposta
    mas o `fetch` não consegue lê-lo, e o arquivo é salvo com um nome fixo, que o
    navegador vai numerando: relatorio (1).pdf, relatorio (2).pdf.
    """
    from app.main import app

    cors = [
        m for m in app.user_middleware
        if "CORSMiddleware" in str(m.cls)
    ]
    assert cors, "CORSMiddleware não está registrado"

    expostos = cors[0].kwargs.get("expose_headers") or []
    assert "Content-Disposition" in expostos
