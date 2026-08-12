"""Isolamento do aprendizado por feedback.

O agregado de feedback vira texto dentro do prompt, incluindo comentários
literais que o revisor escreveu. Se ele juntar contas diferentes, o que alguém
escreveu sobre o contrato do próprio cliente entra na análise de outro
escritório. É vazamento de informação sob sigilo, não só ruído estatístico.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import AlertFeedback, Analysis, Document, Organization, OrgMember, User
from app.services.feedback_learning import load_feedback_learnings


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _usuario(db, email: str) -> User:
    u = User(email=email, password_hash="x", full_name=email)
    db.add(u)
    db.flush()
    return u


def _documento(db, dono: User, org_id=None) -> Document:
    doc = Document(
        user_id=dono.id,
        filename=f"{email_slug(dono)}.pdf",
        file_path="/tmp/x.pdf",
        status="analyzed",
        organization_id=org_id,
    )
    db.add(doc)
    db.flush()
    return doc


def email_slug(u: User) -> str:
    return u.email.split("@")[0]


def _feedback(db, doc: Document, autor: User, regra: str, correto: bool, comentario: str):
    analise = Analysis(
        document_id=doc.id, risk_score=50, summary="s", alerts=[], missing_clauses=[]
    )
    db.add(analise)
    db.flush()
    db.add(AlertFeedback(
        analysis_id=analise.id,
        user_id=autor.id,
        alert_index=0,
        rule_name=regra,
        is_correct=correto,
        comment=comentario,
    ))
    db.flush()


def test_feedback_de_outra_conta_nao_entra_no_prompt(db):
    """O bug: o agregado somava todas as contas do sistema."""
    ana = _usuario(db, "ana@escritorio-a.com")
    bruno = _usuario(db, "bruno@escritorio-b.com")

    doc_de_bruno = _documento(db, bruno)
    _feedback(db, doc_de_bruno, bruno, "Foro competente", False,
              "nao se aplica, a Construtora Aurora ja trata isso no contrato-mae")

    doc_de_ana = _documento(db, ana)
    aprendizado = load_feedback_learnings(db, doc_de_ana)

    assert aprendizado == []


def test_comentario_alheio_nao_vaza_nem_quando_a_regra_coincide(db):
    """A regra ser a mesma nos dois escritórios não autoriza cruzar o comentário."""
    ana = _usuario(db, "ana@escritorio-a.com")
    bruno = _usuario(db, "bruno@escritorio-b.com")

    doc_de_bruno = _documento(db, bruno)
    _feedback(db, doc_de_bruno, bruno, "Foro competente", False, "segredo do cliente dele")

    doc_ana_antigo = _documento(db, ana)
    _feedback(db, doc_ana_antigo, ana, "Foro competente", False, "meu proprio comentario")

    doc_novo = _documento(db, ana)
    aprendizado = load_feedback_learnings(db, doc_novo)

    assert len(aprendizado) == 1
    entrada = aprendizado[0]
    assert entrada["total"] == 1
    assert entrada["sample_comments"] == ["meu proprio comentario"]


def test_documento_pessoal_aprende_com_o_proprio_historico(db):
    ana = _usuario(db, "ana@escritorio-a.com")

    antigo = _documento(db, ana)
    _feedback(db, antigo, ana, "Multa abusiva", False, "clausula negociada, era esperado")

    novo = _documento(db, ana)
    aprendizado = load_feedback_learnings(db, novo)

    assert [e["rule_name"] for e in aprendizado] == ["Multa abusiva"]
    assert aprendizado[0]["false_positive_rate"] == 100.0


def test_equipe_aprende_com_o_feedback_da_equipe(db):
    """Dentro do escritório o aprendizado é compartilhado, que é o ponto dele."""
    ana = _usuario(db, "ana@escritorio-a.com")
    carla = _usuario(db, "carla@escritorio-a.com")

    org = Organization(name="Escritório A", slug="escritorio-a")
    db.add(org)
    db.flush()
    db.add_all([
        OrgMember(organization_id=org.id, user_id=ana.id, role="owner"),
        OrgMember(organization_id=org.id, user_id=carla.id, role="member"),
    ])
    db.flush()

    doc_da_carla = _documento(db, carla, org_id=org.id)
    _feedback(db, doc_da_carla, carla, "Foro competente", False, "padrao da casa")

    doc_da_ana = _documento(db, ana, org_id=org.id)
    aprendizado = load_feedback_learnings(db, doc_da_ana)

    assert [e["rule_name"] for e in aprendizado] == ["Foro competente"]
    assert aprendizado[0]["sample_comments"] == ["padrao da casa"]


def test_documento_pessoal_nao_aprende_com_o_da_equipe(db):
    """Escopos separados nos dois sentidos, como no resto do sistema."""
    ana = _usuario(db, "ana@escritorio-a.com")
    org = Organization(name="Escritório A", slug="escritorio-a")
    db.add(org)
    db.flush()
    db.add(OrgMember(organization_id=org.id, user_id=ana.id, role="owner"))
    db.flush()

    da_equipe = _documento(db, ana, org_id=org.id)
    _feedback(db, da_equipe, ana, "Foro competente", False, "contexto da equipe")

    pessoal = _documento(db, ana)
    assert load_feedback_learnings(db, pessoal) == []


def test_taxa_de_falso_positivo_conta_certo(db):
    ana = _usuario(db, "ana@escritorio-a.com")
    for correto in (True, True, True, False):
        doc = _documento(db, ana)
        _feedback(db, doc, ana, "Foro competente", correto, "c")

    novo = _documento(db, ana)
    entrada = load_feedback_learnings(db, novo)[0]

    assert entrada["total"] == 4
    assert entrada["correct"] == 3
    assert entrada["incorrect"] == 1
    assert entrada["false_positive_rate"] == 25.0
