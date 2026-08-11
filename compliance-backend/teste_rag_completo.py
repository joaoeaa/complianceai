import asyncio
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

# Imports do seu projeto
from app.core.config import get_settings
from app.services.rag_service import build_legal_context_sync
from app.services.ai_analyzer import analyze_document

settings = get_settings()
sync_engine = create_engine(settings.DATABASE_URL_SYNC)

def test_flow():
    print("🚀 Iniciando teste de IA Vertical (RAG + Claude)...")
    
    # Simulação de um texto de contrato com problema de LGPD
    texto_contrato = """
    CLÁUSULA DÉCIMA - DOS DADOS: A contratada poderá coletar e utilizar todos os dados 
    dos funcionários da contratante para qualquer finalidade comercial, inclusive 
    compartilhamento com parceiros internacionais, sem necessidade de aviso prévio.
    """
    
    # Regra de teste
    regras = [{
        "name": "Conformidade LGPD",
        "severity": "high",
        "criteria": "Verificar se há base legal para tratamento de dados e se respeita a LGPD."
    }]

    with Session(sync_engine) as db:
        # 1. Testando o RAG
        print("\n🔍 1. Buscando contexto legal no banco (RAG)...")
        contexto = build_legal_context_sync(texto_contrato, regras, db, top_k=3)
        
        if not contexto:
            print("⚠️  AVISO: Nenhum contexto legal encontrado. Verifique se o seed_lgpd foi rodado.")
        else:
            print(f"✅ Sucesso! Encontrados {len(contexto)} trechos da lei.")
            for i, c in enumerate(contexto, 1):
                print(f"   - [{i}] {c['source']} {c['article_ref']}")

        # 2. Testando a IA com o contexto
        print("\n🧠 2. Enviando para o Claude (IA Vertical)...")
        try:
            resultado = analyze_document(texto_contrato, regras, legal_context=contexto)
            
            print("\n--- RESULTADO DA ANÁLISE ---")
            print(f"Score de Risco: {resultado.risk_score}")
            print(f"Resumo: {resultado.summary}")
            
            for alert in resultado.alerts:
                print(f"\n🚨 ALERTA: {alert['rule_name']}")
                print(f"   Problema: {alert['issue']}")
                print(f"   Base Legal Citada: {alert.get('legal_basis')}")
                print(f"   Sugestão: {alert['suggestion']}")
                
        except Exception as e:
            print(f"❌ Erro na chamada da IA: {e}")

if __name__ == "__main__":
    test_flow()