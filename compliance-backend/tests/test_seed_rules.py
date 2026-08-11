"""Testes da sincronizacao das regras globais."""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import Rule
from app.scripts.seed_rules import DEFAULT_RULES, seed_rules


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_conjunto_canonico_tem_nomes_unicos():
    """Nome duplicado geraria alertas homonimos, que e o que esta revisao corrige."""
    nomes = [r["name"] for r in DEFAULT_RULES]
    assert len(nomes) == len(set(nomes))


def test_regras_legais_citam_o_dispositivo():
    """Cada regra legal deve apontar um artigo, para o alerta poder ser conferido."""
    legais = [r for r in DEFAULT_RULES if ":" in r["name"] or "LGPD" in r["description"]]
    assert legais, "esperava regras legais no conjunto"
    for regra in legais:
        texto = regra["description"] + regra["criteria"]
        assert "Art" in texto, f"{regra['name']} nao cita dispositivo"


def test_limites_numericos_sao_declarados_como_politica():
    """Os numeros de 60 dias e 10% nao vem da lei; a descricao precisa dizer isso."""
    com_numero = [r for r in DEFAULT_RULES if "60 dias" in r["name"] or "10%" in r["name"]]
    assert len(com_numero) == 2
    for regra in com_numero:
        assert "Política interna" in regra["description"]


def test_vinculo_empregaticio_vem_ativo():
    """Era a lacuna mais cara do conjunto anterior."""
    regra = next(r for r in DEFAULT_RULES if "vínculo empregatício" in r["name"])
    assert regra["is_active"] is True
    assert regra["severity"] == "high"


def test_regras_de_consumo_vem_desativadas():
    """Em contrato B2B, CDC gera falso positivo."""
    for regra in DEFAULT_RULES:
        if regra["name"].startswith("CDC:"):
            assert regra["is_active"] is False


def test_seed_insere_tudo_em_banco_vazio(db):
    inseridas, removidas = seed_rules(db)
    db.commit()
    assert inseridas == len(DEFAULT_RULES)
    assert removidas == 0
    assert db.execute(select(Rule)).scalars().all().__len__() == len(DEFAULT_RULES)


def test_seed_e_idempotente(db):
    seed_rules(db)
    db.commit()
    inseridas, _ = seed_rules(db)
    db.commit()
    assert inseridas == 0


def test_prune_remove_regras_globais_antigas(db):
    """Aposenta nomes que sairam do conjunto, como 'Conformidade LGPD'."""
    db.add(Rule(name="Conformidade LGPD", severity="high", criteria="antiga", is_active=True))
    db.commit()

    inseridas, removidas = seed_rules(db, prune=True)
    db.commit()

    assert removidas == 1
    nomes = {r.name for r in db.execute(select(Rule)).scalars().all()}
    assert "Conformidade LGPD" not in nomes
    assert "LGPD: base legal para tratamento" in nomes


def test_prune_nao_toca_regras_de_usuario_ou_equipe(db):
    """Regra propria com nome fora do conjunto nao pode ser removida pelo seed."""
    import uuid

    minha = Rule(name="Regra minha", severity="low", criteria="x", user_id=uuid.uuid4())
    db.add(minha)
    db.commit()

    seed_rules(db, prune=True)
    db.commit()

    nomes = {r.name for r in db.execute(select(Rule)).scalars().all()}
    assert "Regra minha" in nomes
