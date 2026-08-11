# app/scripts/generate_embeddings_for_chunks.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.services.embedding_service import generate_embedding
import time
import sys
import traceback

def main():
    settings = get_settings()
    db_url = getattr(settings, "DATABASE_URL_SYNC", None)
    if not db_url:
        print("ERRO: DATABASE_URL_SYNC não encontrada nas settings")
        sys.exit(1)

    engine = create_engine(db_url, pool_pre_ping=True)

    with Session(engine) as db:
        # Buscar chunks sem embedding
        rows = db.execute(text("SELECT id, content FROM legal_chunks WHERE embedding IS NULL ORDER BY id")).fetchall()
        total = len(rows)
        print(f"Chunks sem embedding encontrados: {total}")
        if total == 0:
            print("Nada a fazer. Todos os chunks já têm embedding.")
            return

        for idx, row in enumerate(rows, 1):
            chunk_id = row[0]
            content = row[1]
            try:
                print(f"[{idx}/{total}] Gerando embedding para chunk {chunk_id} (len={len(content)})...")
                vec = generate_embedding(content)
                # Atualiza embedding; passamos a lista diretamente e o driver/pgvector deve adaptar
                db.execute(
                    text("UPDATE legal_chunks SET embedding = :embedding WHERE id = :id"),
                    {"embedding": vec, "id": chunk_id},
                )
                # Commit a cada 10 para reduzir perda em caso de falha
                if idx % 10 == 0:
                    db.commit()
                    print(f"Committed {idx} embeddings...")
                # Pequena pausa para evitar bursts
                time.sleep(0.2)
            except Exception as e:
                print(f"Falha ao gerar embedding para chunk {chunk_id}: {e}")
                traceback.print_exc()
                # Não interrompe tudo; continua com o próximo
        db.commit()
        print("Embeddings gerados para todos os chunks sem embedding.")

if __name__ == "__main__":
    main()