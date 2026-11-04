"""
Armazenamento do arquivo original enviado.

O arquivo só é lido de novo para o download do original: a análise trabalha
sobre o texto, que a api extrai no upload e grava em documents.extracted_text.
Por isso o storage pode ficar fora do container, num bucket, sem que a análise
dependa dele.

Duas implementações, escolhidas por STORAGE_BACKEND:

- local: disco do container, em UPLOAD_DIR. Some a cada redeploy se UPLOAD_DIR
  não estiver num volume persistente.
- s3: qualquer serviço compatível com a API do S3. Para Supabase Storage e
  Cloudflare R2, muda só o endpoint e a região:

    Supabase  S3_ENDPOINT_URL=https://<projeto>.supabase.co/storage/v1/s3
              S3_REGION=<região do projeto, ex.: sa-east-1>
    R2        S3_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com
              S3_REGION=auto

A chave gravada em documents.file_path é só o nome do arquivo, "<uuid><ext>".
Registros antigos guardam o caminho local inteiro ("storage/uploads/<uuid>.pdf");
as duas implementações usam apenas o nome final, o que atende aos dois formatos e
impede que uma chave saia do diretório ou do prefixo.
"""
from __future__ import annotations

import logging
import os
import tempfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Optional, Protocol

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class Storage(Protocol):
    def save(self, key: str, data: bytes, content_type: Optional[str] = None) -> None: ...

    def read(self, key: str) -> Optional[bytes]:
        """Conteúdo do arquivo, ou None se ele não existe."""
        ...

    def delete(self, key: str) -> None:
        """Apaga o arquivo. Apagar o que não existe não é erro."""
        ...


def _nome(key: str) -> str:
    nome = os.path.basename(key.replace("\\", "/"))
    if nome in ("", ".", ".."):
        raise ValueError(f"Chave de arquivo inválida: {key!r}")
    return nome


class LocalStorage:
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)

    def _caminho(self, key: str) -> Path:
        return self.base_dir / _nome(key)

    def save(self, key: str, data: bytes, content_type: Optional[str] = None) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._caminho(key).write_bytes(data)

    def read(self, key: str) -> Optional[bytes]:
        caminho = self._caminho(key)
        return caminho.read_bytes() if caminho.is_file() else None

    def delete(self, key: str) -> None:
        try:
            self._caminho(key).unlink()
        except FileNotFoundError:
            pass


class S3Storage:
    """Bucket compatível com S3. Recebe o cliente pronto, o que permite testar sem rede."""

    def __init__(self, client: Any, bucket: str, prefix: str = ""):
        self.client = client
        self.bucket = bucket
        self.prefix = prefix

    def _chave(self, key: str) -> str:
        return f"{self.prefix}{_nome(key)}"

    def save(self, key: str, data: bytes, content_type: Optional[str] = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        self.client.put_object(Bucket=self.bucket, Key=self._chave(key), Body=data, **extra)

    def read(self, key: str) -> Optional[bytes]:
        try:
            resposta = self.client.get_object(Bucket=self.bucket, Key=self._chave(key))
        except Exception as e:
            if _nao_existe(e):
                return None
            raise
        return resposta["Body"].read()

    def delete(self, key: str) -> None:
        # O S3 responde 204 também para chave inexistente.
        self.client.delete_object(Bucket=self.bucket, Key=self._chave(key))


def _nao_existe(exc: Exception) -> bool:
    codigo = (getattr(exc, "response", None) or {}).get("Error", {}).get("Code")
    return codigo in {"NoSuchKey", "404", "NotFound"}


def build_storage(settings: Settings) -> Storage:
    backend = settings.STORAGE_BACKEND.strip().lower()
    if backend == "local":
        return LocalStorage(settings.UPLOAD_DIR)
    if backend == "s3":
        faltando = [
            nome
            for nome in ("S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")
            if not getattr(settings, nome)
        ]
        if faltando:
            raise RuntimeError(
                "STORAGE_BACKEND=s3 exige " + ", ".join(faltando) + " no ambiente."
            )
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL or None,
            region_name=settings.S3_REGION or None,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            config=Config(
                signature_version="s3v4",
                # Supabase só aceita path-style, e R2 e S3 aceitam os dois.
                s3={"addressing_style": "path"},
                # Desde a 1.36, o boto3 manda checksum CRC em todo upload, e nem
                # todo serviço compatível aceita. "when_required" volta ao
                # comportamento que todos entendem.
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        return S3Storage(client, settings.S3_BUCKET, settings.S3_PREFIX)
    raise RuntimeError(f"STORAGE_BACKEND inválido: {backend!r}. Use 'local' ou 's3'.")


@lru_cache()
def get_storage() -> Storage:
    return build_storage(get_settings())


@contextmanager
def arquivo_temporario(data: bytes, suffix: str = "") -> Iterator[str]:
    """Grava `data` num arquivo temporário e devolve o caminho; apaga ao sair.

    A extração de texto (pdfplumber, python-docx, OCR) trabalha sobre um caminho
    local, e com o storage num bucket o arquivo não está mais no disco.
    """
    fd, caminho = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        yield caminho
    finally:
        try:
            os.unlink(caminho)
        except FileNotFoundError:
            pass
