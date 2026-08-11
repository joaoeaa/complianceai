"""Seed the default compliance rules.

The rules used to live inline in `main.py`, which only seeds in development. In
production the table starts empty and every analysis runs with zero rules, so this
is the canonical list — `main.py` imports it, and it can be run standalone:

    python -m app.scripts.seed_rules

Idempotent: skips rules whose name already exists.
"""
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

DEFAULT_RULES: list[dict] = [
    # ── Regras Gerais de Contratos ──
    {
        "name": "Foro Competente",
        "description": "Verificar se o foro está adequado à jurisdição contratual",
        "severity": "high",
        "criteria": "Verificar se a cláusula de foro/jurisdição está presente e se é compatível com a sede das partes ou local de execução do contrato. Gerar alerta se o foro for em jurisdição incompatível ou ausente.",
        "is_active": True,
    },
    {
        "name": "Prazo de Pagamento",
        "description": "Prazo de pagamento não pode exceder 60 dias",
        "severity": "medium",
        "criteria": "Verificar todos os prazos de pagamento mencionados. Se algum prazo exceder 60 dias corridos ou úteis, gerar alerta. Prazos entre 45-60 dias devem gerar observação.",
        "is_active": True,
    },
    {
        "name": "Confidencialidade",
        "description": "Deve conter cláusula de confidencialidade/NDA",
        "severity": "high",
        "criteria": "Verificar presença de cláusula de confidencialidade, sigilo, NDA ou non-disclosure. Ausência completa gera alerta de alta severidade.",
        "is_active": True,
    },
    {
        "name": "Multa de Rescisão",
        "description": "Multa de rescisão não pode exceder 10% do valor total",
        "severity": "medium",
        "criteria": "Verificar se há cláusula de multa rescisória. Se o percentual exceder 10% do valor total do contrato, gerar alerta.",
        "is_active": True,
    },
    {
        "name": "Vigência Definida",
        "description": "O contrato deve ter prazo de vigência claramente definido",
        "severity": "low",
        "criteria": "Verificar se há cláusula de vigência com datas claras (início e fim) ou período definido. Contratos por prazo indeterminado sem justificativa geram alerta.",
        "is_active": True,
    },
    # ── LGPD (Lei 13.709/2018) ──
    {
        "name": "Conformidade LGPD",
        "description": "Contratos com tratamento de dados pessoais devem referenciar a LGPD",
        "severity": "high",
        "criteria": "Se o contrato envolve coleta, armazenamento, compartilhamento ou tratamento de dados pessoais, verificar menção à LGPD (Lei 13.709/2018), bases legais (Art. 7º), direitos do titular (Art. 18) e medidas de segurança (Art. 46). Ausência gera alerta.",
        "is_active": True,
    },
    # ── Código de Defesa do Consumidor (Lei 8.078/1990) ──
    {
        "name": "Conformidade CDC",
        "description": "Contratos com consumidores devem respeitar o CDC",
        "severity": "high",
        "criteria": "Se o contrato é de consumo (B2C), verificar: cláusulas abusivas (Art. 51 do CDC), direito de arrependimento em compras fora do estabelecimento (Art. 49), transparência nas informações (Art. 6º), garantia legal (Art. 26). Cláusulas que limitem direitos do consumidor geram alerta.",
        "is_active": True,
    },
    # ── Código Civil (Lei 10.406/2002) ──
    {
        "name": "Conformidade Código Civil",
        "description": "Verificar aderência às normas gerais de contratos do Código Civil",
        "severity": "medium",
        "criteria": "Verificar: função social do contrato (Art. 421), boa-fé objetiva (Art. 422), vícios de consentimento, onerosidade excessiva (Art. 478-480), e se as cláusulas respeitam os requisitos de validade do negócio jurídico (Art. 104). Cláusulas leoninas ou que violem equilíbrio contratual geram alerta.",
        "is_active": True,
    },
    # ── CLT / Legislação Trabalhista ──
    {
        "name": "Conformidade Trabalhista",
        "description": "Contratos de trabalho/prestação de serviço devem observar a legislação trabalhista",
        "severity": "high",
        "criteria": "Se o contrato envolve prestação de serviço ou relação de trabalho, verificar: descaracterização de vínculo empregatício (Art. 3º CLT), observância de direitos irrenunciáveis, conformidade com reforma trabalhista (Lei 13.467/2017), e se terceirização segue a Lei 13.429/2017. Indícios de pejotização geram alerta.",
        "is_active": False,
    },
    # ── Marco Civil da Internet (Lei 12.965/2014) ──
    {
        "name": "Conformidade Marco Civil",
        "description": "Contratos digitais devem observar o Marco Civil da Internet",
        "severity": "medium",
        "criteria": "Se o contrato envolve serviços digitais, aplicações de internet ou armazenamento de dados online, verificar menção ao Marco Civil (Lei 12.965/2014): neutralidade de rede (Art. 9º), proteção de registros e dados pessoais (Art. 10-12), responsabilidade de provedores (Art. 18-21). Ausência gera alerta.",
        "is_active": False,
    },
    # ── Lei Anticorrupção (Lei 12.846/2013) ──
    {
        "name": "Cláusula Anticorrupção",
        "description": "Contratos corporativos devem conter cláusula anticorrupção",
        "severity": "medium",
        "criteria": "Verificar presença de cláusula anticorrupção referenciando a Lei 12.846/2013 e/ou FCPA/UK Bribery Act. Deve incluir compromisso das partes com práticas éticas, vedação a suborno e corrupção, e previsão de rescisão em caso de violação. Ausência em contratos B2B gera alerta.",
        "is_active": True,
    },
]


def seed_rules(db) -> int:
    """Insert any default rule that isn't in the database yet. Returns how many were added."""
    from app.models import Rule

    existing_names = set(db.execute(select(Rule.name)).scalars().all())
    added = 0
    for spec in DEFAULT_RULES:
        if spec["name"] in existing_names:
            continue
        db.add(Rule(**spec))
        added += 1
    return added


def main() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL_SYNC)
    try:
        with Session(engine) as db:
            added = seed_rules(db)
            db.commit()
            total = len(DEFAULT_RULES)
        if added:
            print(f"OK — {added} regra(s) inserida(s) de um total de {total}.")
        else:
            print(f"Nada a fazer — as {total} regras padrão já existem.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
