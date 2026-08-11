"""Regras de conformidade padrão do sistema.

Estas são as regras globais: visíveis a todos, editáveis por ninguém. Cada conta
pode desativá-las para si e criar as suas próprias por cima.

Duas famílias convivem aqui, e a distinção importa para quem lê o relatório:

    Estruturais   verificações de boas práticas contratuais. Algumas carregam um
                  limite numérico que é POLÍTICA, não exigência legal. O limite
                  aparece na descrição para ninguém confundir com lei.

    Legais        uma regra por dispositivo, não por legislação inteira. "LGPD"
                  como regra única produzia vários alertas homônimos e um
                  dashboard que dizia apenas "LGPD: 4", sem informar o que foi
                  violado.

`is_active` reflete o caso mais comum, contrato B2B de fornecimento ou prestação
de serviço. Regras de consumo e de serviços digitais vêm desligadas porque em B2B
geram falso positivo; quem trabalha com B2C liga em um clique.

Uso:
    python -m app.scripts.seed_rules            # insere o que falta
    python -m app.scripts.seed_rules --prune    # remove globais fora deste conjunto
"""
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# Limites que são política interna, não previsão legal. Ficam aqui em cima para
# quem quiser mudar o padrão da instalação saber onde mexer.
PRAZO_PAGAMENTO_DIAS = 60
MULTA_RESCISORIA_PCT = 10

DEFAULT_RULES: list[dict] = [
    # ─── Estruturais ────────────────────────────────────────────────────────
    {
        "name": "Foro competente",
        "description": "O foro eleito deve ser compatível com as partes ou com a execução",
        "severity": "high",
        "criteria": (
            "Verificar se há cláusula de eleição de foro. Gerar alerta se estiver ausente, "
            "ou se o foro eleito não tiver relação com a sede de nenhuma das partes nem com "
            "o local de execução do contrato. Citar o foro eleito e as sedes no trecho."
        ),
        "is_active": True,
    },
    {
        "name": f"Prazo de pagamento acima de {PRAZO_PAGAMENTO_DIAS} dias",
        "description": (
            f"Política interna: prazo máximo de {PRAZO_PAGAMENTO_DIAS} dias. "
            "Não é exigência legal; ajuste conforme a sua realidade"
        ),
        "severity": "medium",
        "criteria": (
            f"Identificar todos os prazos de pagamento do contrato. Gerar alerta para qualquer "
            f"prazo superior a {PRAZO_PAGAMENTO_DIAS} dias, corridos ou úteis. Sinalizar também "
            "condições que tornem o prazo indeterminado na prática, como aceite sem prazo definido."
        ),
        "is_active": True,
    },
    {
        "name": "Ausência de cláusula de confidencialidade",
        "description": "Contratos com troca de informação sensível devem prever sigilo",
        "severity": "high",
        "criteria": (
            "Verificar se há cláusula de confidencialidade, sigilo ou NDA. Gerar alerta se "
            "ausente em contrato que envolva dados de clientes, informação comercial ou acesso "
            "a sistemas. Não alertar em contratos sem troca de informação sensível."
        ),
        "is_active": True,
    },
    {
        "name": f"Multa rescisória acima de {MULTA_RESCISORIA_PCT}%",
        "description": (
            f"Política interna: teto de {MULTA_RESCISORIA_PCT}% do valor do contrato. "
            "O Código Civil (Art. 412) admite até o valor da obrigação principal"
        ),
        "severity": "medium",
        "criteria": (
            f"Localizar cláusulas de multa por rescisão. Gerar alerta se o percentual exceder "
            f"{MULTA_RESCISORIA_PCT}% do valor total, ou se a base de cálculo for artificialmente "
            "inflada, como projeção de anos futuros em contrato sem prazo definido."
        ),
        "is_active": True,
    },
    {
        "name": "Vigência indeterminada",
        "description": "O contrato deve ter prazo de vigência claro",
        "severity": "low",
        "criteria": (
            "Verificar se há prazo de vigência com início e fim, ou período definido. Gerar "
            "alerta para prazo indeterminado sem justificativa, ou quando o cronograma ficar "
            "a critério exclusivo de uma das partes."
        ),
        "is_active": True,
    },

    # ─── LGPD, Lei 13.709/2018 ──────────────────────────────────────────────
    {
        "name": "LGPD: base legal para tratamento",
        "description": "Todo tratamento de dados precisa de uma das hipóteses do Art. 7º",
        "severity": "high",
        "criteria": (
            "Se o contrato envolve tratamento de dados pessoais, verificar se há indicação da "
            "base legal (Art. 7º da LGPD): consentimento, execução de contrato, obrigação legal, "
            "legítimo interesse ou outra hipótese. Gerar alerta se o tratamento for autorizado "
            "de forma genérica, como 'para qualquer finalidade', sem base legal e sem finalidade "
            "determinada."
        ),
        "is_active": True,
    },
    {
        "name": "LGPD: direitos do titular",
        "description": "O titular deve ser informado e poder exercer os direitos do Art. 18",
        "severity": "high",
        "criteria": (
            "Verificar se o contrato preserva os direitos do titular (Art. 18 da LGPD): "
            "confirmação, acesso, correção, portabilidade e eliminação. Gerar alerta se houver "
            "dispensa de aviso ao titular, ausência de canal de atendimento, ou renúncia a esses "
            "direitos."
        ),
        "is_active": True,
    },
    {
        "name": "LGPD: transferência internacional",
        "description": "Envio de dados ao exterior exige garantias (Art. 33)",
        "severity": "medium",
        "criteria": (
            "Verificar se há compartilhamento de dados pessoais com partes no exterior. Gerar "
            "alerta se a transferência for autorizada sem indicar país de destino, nível de "
            "proteção adequado ou salvaguardas como cláusulas contratuais padrão."
        ),
        "is_active": True,
    },
    {
        "name": "LGPD: medidas de segurança",
        "description": "O tratamento exige medidas técnicas e administrativas (Art. 46)",
        "severity": "medium",
        "criteria": (
            "Verificar se o contrato atribui a alguma parte a obrigação de adotar medidas de "
            "segurança sobre os dados tratados. Gerar alerta se a obrigação for expressamente "
            "afastada, ou se a responsabilidade por incidentes for integralmente transferida a "
            "quem não controla o tratamento."
        ),
        "is_active": True,
    },
    {
        "name": "LGPD: dados sensíveis",
        "description": "Dados sensíveis têm hipóteses próprias e mais restritas (Art. 11)",
        "severity": "medium",
        "criteria": (
            "Verificar se o contrato pode abranger dados sensíveis: saúde, biometria, origem "
            "racial, convicção religiosa, opinião política, dados de menores. Gerar alerta se o "
            "tratamento for autorizado de forma indistinta, sem prever hipótese específica nem "
            "consentimento destacado."
        ),
        "is_active": True,
    },

    # ─── Código Civil, Lei 10.406/2002 ──────────────────────────────────────
    {
        "name": "Exclusão abusiva de responsabilidade",
        "description": "Cláusula que afasta responsabilidade por dolo ou culpa grave é nula",
        "severity": "high",
        "criteria": (
            "Localizar cláusulas de limitação ou exclusão de responsabilidade. Gerar alerta "
            "quando excluírem responsabilidade por dolo ou culpa grave, quando afastarem toda e "
            "qualquer indenização, ou quando forem unilaterais em favor de uma só parte."
        ),
        "is_active": True,
    },
    {
        "name": "Desequilíbrio contratual",
        "description": "Boa-fé objetiva e função social do contrato (Arts. 421 e 422)",
        "severity": "medium",
        "criteria": (
            "Verificar se há assimetria relevante entre as partes: obrigações apenas de um lado, "
            "poderes discricionários sem contrapartida, ou onerosidade excessiva. Gerar alerta "
            "descrevendo a assimetria concreta encontrada, não a mera existência de vantagem."
        ),
        "is_active": True,
    },

    # ─── Trabalhista, CLT e Lei 13.429/2017 ─────────────────────────────────
    {
        "name": "Indícios de vínculo empregatício",
        "description": "Subordinação, pessoalidade e habitualidade caracterizam vínculo (Art. 3º CLT)",
        "severity": "high",
        "criteria": (
            "Se o contrato envolve prestação de serviço por pessoa física ou PJ individual, "
            "procurar os elementos do vínculo: subordinação hierárquica, controle de jornada, "
            "pessoalidade na execução, exclusividade e habitualidade. Gerar alerta ao encontrar "
            "combinação desses elementos, especialmente junto de exigência de constituir PJ ou "
            "de renúncia a verbas trabalhistas."
        ),
        "is_active": True,
    },
    {
        "name": "Terceirização fora dos requisitos legais",
        "description": "Requisitos da Lei 13.429/2017 para terceirização de serviços",
        "severity": "medium",
        "criteria": (
            "Se há terceirização, verificar previsão de responsabilidade subsidiária da "
            "contratante, capacidade econômica da prestadora e delimitação dos serviços. Gerar "
            "alerta se a responsabilidade subsidiária for afastada por cláusula."
        ),
        "is_active": False,
    },

    # ─── Anticorrupção, Lei 12.846/2013 ─────────────────────────────────────
    {
        "name": "Ausência de cláusula anticorrupção",
        "description": "Contratos corporativos devem prever compromisso anticorrupção",
        "severity": "medium",
        "criteria": (
            "Verificar se há cláusula anticorrupção referenciando a Lei 12.846/2013, FCPA ou UK "
            "Bribery Act, com vedação a suborno e previsão de rescisão em caso de violação. "
            "Gerar alerta se ausente em contrato entre empresas."
        ),
        "is_active": True,
    },

    # ─── CDC, Lei 8.078/1990. Desativadas: só se aplicam a contrato de consumo ──
    {
        "name": "CDC: cláusulas abusivas",
        "description": "Nulidade das cláusulas do Art. 51. Ative em contratos de consumo",
        "severity": "high",
        "criteria": (
            "Aplicar apenas se houver relação de consumo. Verificar cláusulas do Art. 51 do CDC: "
            "exoneração de responsabilidade do fornecedor, renúncia a direitos, inversão do ônus "
            "da prova em prejuízo do consumidor, alteração unilateral do preço."
        ),
        "is_active": False,
    },
    {
        "name": "CDC: direito de arrependimento",
        "description": "Prazo de 7 dias em contratação fora do estabelecimento (Art. 49)",
        "severity": "medium",
        "criteria": (
            "Aplicar apenas se houver relação de consumo com contratação a distância ou fora do "
            "estabelecimento. Gerar alerta se o direito de arrependimento em 7 dias for afastado "
            "ou condicionado."
        ),
        "is_active": False,
    },

    # ─── Marco Civil, Lei 12.965/2014. Desativada: só serviços digitais ─────
    {
        "name": "Marco Civil: guarda e proteção de registros",
        "description": "Obrigações dos Arts. 10 a 15. Ative em contratos de serviço digital",
        "severity": "medium",
        "criteria": (
            "Aplicar apenas a contratos de aplicação de internet ou hospedagem. Verificar "
            "previsão sobre guarda de registros de acesso, sigilo das comunicações e hipóteses "
            "de fornecimento a terceiros."
        ),
        "is_active": False,
    },
]


def seed_rules(db, prune: bool = False) -> tuple[int, int]:
    """Sincroniza as regras globais. Devolve (inseridas, removidas).

    Insere o que falta, comparando por nome. Com `prune`, remove as regras globais
    que não pertencem mais a este conjunto, o que serve para aposentar as antigas
    após uma revisão como esta. Regras pessoais e de equipe nunca são tocadas.
    """
    from app.models import Rule

    canonical = {spec["name"] for spec in DEFAULT_RULES}

    globais = db.execute(
        select(Rule).where(Rule.organization_id.is_(None), Rule.user_id.is_(None))
    ).scalars().all()
    existentes = {r.name for r in globais}

    inseridas = 0
    for spec in DEFAULT_RULES:
        if spec["name"] not in existentes:
            db.add(Rule(**spec))
            inseridas += 1

    removidas = 0
    if prune:
        for regra in globais:
            if regra.name not in canonical:
                db.delete(regra)
                removidas += 1

    return inseridas, removidas


def main() -> None:
    from app.core.config import get_settings

    prune = "--prune" in sys.argv
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL_SYNC)
    try:
        with Session(engine) as db:
            inseridas, removidas = seed_rules(db, prune=prune)
            db.commit()

        ativas = sum(1 for r in DEFAULT_RULES if r["is_active"])
        print(f"Conjunto canônico: {len(DEFAULT_RULES)} regras ({ativas} ativas por padrão).")
        print(f"Inseridas: {inseridas}")
        if prune:
            print(f"Removidas (fora do conjunto): {removidas}")
        elif not inseridas:
            print("Nada a fazer. Use --prune para aposentar regras antigas.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
