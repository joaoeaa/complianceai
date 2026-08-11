from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.services.embedding_service import generate_embedding
import uuid

def main():
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL_SYNC)
    
    print("🔍 Buscando documentos legais sem chunks...")
    
    with Session(engine) as db:
        docs = db.execute(text("""
            SELECT id, title, full_text, source, category 
            FROM legal_documents 
            WHERE id NOT IN (SELECT DISTINCT document_id FROM legal_chunks)
        """)).fetchall()
        
        print(f"Encontrados {len(docs)} documentos para processar.")
        
        for doc in docs:
            doc_id, title, full_text, source, category = doc
            print(f"🚀 Processando: {title}...")
            
            try:
                print(f"   - Gerando embedding...")
                embedding = generate_embedding(full_text)
                
                chunk_id = str(uuid.uuid4())
                db.execute(text("""
                    INSERT INTO legal_chunks (id, document_id, content, embedding, article_ref, metadata, chunk_index)
                    VALUES (:id, :doc_id, :content, :embedding, :ref, :meta, :chunk_index)
                """), {
                    "id": chunk_id,
                    "doc_id": doc_id,
                    "content": full_text,
                    "embedding": embedding,
                    "ref": category or title,
                    "meta": "{}",
                    "chunk_index": 0
                })
                db.commit()
                print(f"   ✅ Chunk criado com sucesso!")
            except Exception as e:
                print(f"   ❌ Erro no documento {title}: {e}")
                db.rollback()

    print("\n✨ Processo concluído!")

if __name__ == "__main__":
    main()