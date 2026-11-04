"""Storage do arquivo original: disco local ou bucket compatível com S3.

Os testes de rota usam DOCX, que a suíte gera sem dependência nativa. O backend
S3 é testado com um cliente falso, que registra as chamadas: o que importa aqui é
que a chave, o bucket e o tratamento de "não existe" estejam certos, e isso não
precisa de rede.
"""
import io
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import Document
from app.core.config import Settings
from app.services.storage import LocalStorage, S3Storage, build_storage
from tests.conftest import TestSession

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@lru_cache(maxsize=1)
def _docx(texto: str = "Contrato de teste. Cláusula de foro: comarca de Recife.") -> bytes:
    from docx import Document as DocxDocument

    docx = DocxDocument()
    if texto:
        docx.add_paragraph(texto)
    buffer = io.BytesIO()
    docx.save(buffer)
    return buffer.getvalue()


async def _upload(client: AsyncClient, headers: dict, conteudo: bytes = None, data=None):
    return await client.post(
        "/api/v1/documents/upload",
        files={"file": ("contrato.docx", _docx() if conteudo is None else conteudo, DOCX_MIME)},
        data=data,
        headers=headers,
    )


async def _documento(doc_id: str) -> Document:
    async with TestSession() as db:
        return (
            await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
        ).scalar_one()


# ─── LocalStorage ───

def test_local_grava_le_e_apaga(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.save("abc.pdf", b"conteudo")

    assert storage.read("abc.pdf") == b"conteudo"
    storage.delete("abc.pdf")
    assert storage.read("abc.pdf") is None


def test_local_apagar_o_que_nao_existe_nao_e_erro(tmp_path):
    LocalStorage(tmp_path).delete("nunca-existiu.pdf")


def test_local_le_registro_antigo_que_guarda_o_caminho_inteiro(tmp_path):
    """Antes do storage, file_path guardava "storage/uploads/<uuid>.pdf"."""
    storage = LocalStorage(tmp_path)
    storage.save("abc.pdf", b"x")
    assert storage.read("storage/uploads/abc.pdf") == b"x"
    assert storage.read("storage\\uploads\\abc.pdf") == b"x"


def test_local_chave_nao_sai_do_diretorio(tmp_path):
    base = tmp_path / "uploads"
    LocalStorage(base).save("../../fora.pdf", b"x")
    assert (base / "fora.pdf").is_file()
    assert not (tmp_path / "fora.pdf").exists()


# ─── S3Storage ───

class _ErroS3(Exception):
    def __init__(self, codigo):
        super().__init__(codigo)
        self.response = {"Error": {"Code": codigo}}


class _Corpo:
    def __init__(self, dados):
        self._dados = dados

    def read(self):
        return self._dados


class _ClienteS3Falso:
    def __init__(self):
        self.objetos = {}
        self.chamadas = []

    def put_object(self, **kw):
        self.chamadas.append(("put", kw["Bucket"], kw["Key"], kw.get("ContentType")))
        self.objetos[(kw["Bucket"], kw["Key"])] = kw["Body"]

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objetos:
            raise _ErroS3("NoSuchKey")
        return {"Body": _Corpo(self.objetos[(Bucket, Key)])}

    def delete_object(self, Bucket, Key):
        self.chamadas.append(("delete", Bucket, Key, None))
        self.objetos.pop((Bucket, Key), None)


def test_s3_grava_com_prefixo_e_tipo():
    cliente = _ClienteS3Falso()
    storage = S3Storage(cliente, "contratos", "uploads/")

    storage.save("abc.pdf", b"pdf", "application/pdf")

    assert cliente.chamadas == [("put", "contratos", "uploads/abc.pdf", "application/pdf")]
    assert storage.read("abc.pdf") == b"pdf"


def test_s3_objeto_inexistente_vira_none():
    assert S3Storage(_ClienteS3Falso(), "b").read("nada.pdf") is None


def test_s3_outro_erro_nao_e_engolido():
    """Credencial errada não pode virar "arquivo não existe" (410) em silêncio."""

    class _Negado(_ClienteS3Falso):
        def get_object(self, Bucket, Key):
            raise _ErroS3("AccessDenied")

    with pytest.raises(_ErroS3):
        S3Storage(_Negado(), "b").read("abc.pdf")


def test_s3_apaga_no_prefixo():
    cliente = _ClienteS3Falso()
    storage = S3Storage(cliente, "contratos", "uploads/")
    storage.save("abc.pdf", b"x")
    storage.delete("storage/uploads/abc.pdf")
    assert storage.read("abc.pdf") is None
    assert cliente.chamadas[-1] == ("delete", "contratos", "uploads/abc.pdf", None)


# ─── Seleção por STORAGE_BACKEND ───

def test_backend_local_e_o_padrao(tmp_path):
    storage = build_storage(Settings(STORAGE_BACKEND="local", UPLOAD_DIR=str(tmp_path)))
    assert isinstance(storage, LocalStorage)


def test_backend_s3_sem_credencial_falha_no_boot():
    with pytest.raises(RuntimeError, match="S3_BUCKET"):
        build_storage(Settings(
            STORAGE_BACKEND="s3", S3_BUCKET="", S3_ACCESS_KEY_ID="", S3_SECRET_ACCESS_KEY=""
        ))


def test_backend_desconhecido_falha():
    with pytest.raises(RuntimeError, match="inválido"):
        build_storage(Settings(STORAGE_BACKEND="ftp"))


def test_backend_s3_monta_cliente_path_style():
    pytest.importorskip("boto3")
    storage = build_storage(Settings(
        STORAGE_BACKEND="s3",
        S3_BUCKET="contratos",
        S3_ENDPOINT_URL="https://projeto.supabase.co/storage/v1/s3",
        S3_REGION="sa-east-1",
        S3_ACCESS_KEY_ID="id",
        S3_SECRET_ACCESS_KEY="segredo",
    ))
    assert isinstance(storage, S3Storage)
    assert storage.client.meta.endpoint_url == "https://projeto.supabase.co/storage/v1/s3"
    assert storage.client.meta.config.s3 == {"addressing_style": "path"}
    url = storage.client.generate_presigned_url(
        "get_object", Params={"Bucket": "contratos", "Key": "uploads/abc.pdf"}
    )
    assert url.startswith("https://projeto.supabase.co/storage/v1/s3/contratos/uploads/abc.pdf")


# ─── Rotas: os quatro pontos ───

async def test_upload_grava_no_storage_e_guarda_a_chave(
    client: AsyncClient, auth_headers: dict, storage_de_teste
):
    resp = await _upload(client, auth_headers)
    assert resp.status_code == 201, resp.text

    doc = await _documento(resp.json()["document_id"])
    assert "/" not in doc.file_path and doc.file_path.endswith(".docx")
    assert storage_de_teste.read(doc.file_path) == _docx()
    assert "comarca de Recife" in doc.extracted_text


async def test_upload_recusado_nao_deixa_arquivo(
    client: AsyncClient, auth_headers: dict, storage_de_teste
):
    """Antes, o arquivo era gravado antes da extração e ficava órfão no 400."""
    resp = await _upload(client, auth_headers, conteudo=_docx.__wrapped__(""))
    assert resp.status_code == 400
    assert not storage_de_teste.base_dir.exists() or not any(storage_de_teste.base_dir.iterdir())


async def test_download_le_do_storage(client: AsyncClient, auth_headers: dict):
    doc_id = (await _upload(client, auth_headers)).json()["document_id"]

    resp = await client.get(f"/api/v1/documents/{doc_id}/download", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.content == _docx()


async def test_download_sem_arquivo_responde_410(
    client: AsyncClient, auth_headers: dict, storage_de_teste
):
    doc_id = (await _upload(client, auth_headers)).json()["document_id"]
    storage_de_teste.delete((await _documento(doc_id)).file_path)

    resp = await client.get(f"/api/v1/documents/{doc_id}/download", headers=auth_headers)

    assert resp.status_code == 410


async def test_excluir_documento_apaga_o_arquivo(
    client: AsyncClient, auth_headers: dict, storage_de_teste
):
    doc_id = (await _upload(client, auth_headers)).json()["document_id"]
    chave = (await _documento(doc_id)).file_path

    resp = await client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers)

    assert resp.status_code == 204
    assert storage_de_teste.read(chave) is None


async def test_expurgo_apaga_o_arquivo_do_que_venceu(
    client: AsyncClient, auth_headers: dict, storage_de_teste
):
    """O expurgo apagava o registro e deixava o contrato no disco."""
    cid = (
        await client.post(
            "/api/v1/clients",
            json={"name": "Cliente com guarda", "retention_months": 12},
            headers=auth_headers,
        )
    ).json()["id"]
    velho = (await _upload(client, auth_headers, data={"client_id": cid})).json()["document_id"]
    novo = (await _upload(client, auth_headers, data={"client_id": cid})).json()["document_id"]
    chave_velho = (await _documento(velho)).file_path
    chave_novo = (await _documento(novo)).file_path

    async with TestSession() as db:
        doc = (
            await db.execute(select(Document).where(Document.id == uuid.UUID(velho)))
        ).scalar_one()
        doc.uploaded_at = datetime.now(timezone.utc) - timedelta(days=400)
        await db.commit()

    resp = await client.post(
        "/api/v1/clients/retencao/expurgar",
        json={"document_ids": [velho, novo]},
        headers=auth_headers,
    )

    assert resp.json() == {"deleted": 1, "skipped": 1}
    assert storage_de_teste.read(chave_velho) is None
    # O que está no prazo fica, registro e arquivo.
    assert storage_de_teste.read(chave_novo) == _docx()
