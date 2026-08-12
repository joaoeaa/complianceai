"""Compara as análises já feitas, agrupadas por modelo e versão do prompt.

Serve para responder com número, e não com impressão, a duas perguntas que
aparecem sempre que algo muda no prompt ou no modelo: ficou mais rápido, e a
qualidade caiu junto.

Velocidade e volume saem direto do banco. Qualidade não tem medida automática
perfeita, mas as taxas de verificação são um bom substituto: elas dizem quanto
do que o modelo afirmou pôde ser confirmado contra o documento e contra a base
legal. Se elas caem, o modelo passou a citar trecho que não existe ou artigo que
não confere, e isso aparece antes de alguém reclamar.

O que este script NÃO mede é falso negativo, o alerta que deveria existir e não
existe. Para isso não há atalho: rode os contratos de `contratos-teste` e
confira contra o gabarito.

Uso:
    python -m app.scripts.medir_analises
    python -m app.scripts.medir_analises --por modelo
    python -m app.scripts.medir_analises --dias 7
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def _taxas(alertas: list) -> tuple[int, int, int, int]:
    """(trechos conferidos, com trecho, citações apoiadas, com citação)."""
    conferidos = com_trecho = apoiadas = com_citacao = 0
    for alerta in alertas or []:
        checagem = alerta.get("excerpt_check")
        if checagem and checagem != "empty":
            com_trecho += 1
            if checagem == "exact":
                conferidos += 1
        legal = alerta.get("legal_basis_check")
        if legal and legal != "empty":
            com_citacao += 1
            if legal in ("grounded", "in_base"):
                apoiadas += 1
    return conferidos, com_trecho, apoiadas, com_citacao


def _pct(parte: int, total: int) -> str:
    return f"{parte / total * 100:5.1f}%" if total else "    ."


def main() -> None:
    parser = argparse.ArgumentParser(description="Mede as análises já realizadas.")
    parser.add_argument(
        "--por", default="prompt", choices=["prompt", "modelo", "ambos"],
        help="como agrupar (padrão: versão do prompt)",
    )
    parser.add_argument("--dias", type=int, help="considerar apenas os últimos N dias")
    args = parser.parse_args()

    from app.core.config import get_settings
    from app.models import Analysis

    engine = create_engine(get_settings().DATABASE_URL_SYNC)
    try:
        with Session(engine) as db:
            consulta = select(Analysis)
            if args.dias:
                corte = datetime.now(timezone.utc) - timedelta(days=args.dias)
                consulta = consulta.where(Analysis.analyzed_at >= corte)
            analises = db.execute(consulta).scalars().all()
    finally:
        engine.dispose()

    if not analises:
        print("Nenhuma análise encontrada.")
        return

    grupos: dict[str, list] = {}
    for a in analises:
        if args.por == "prompt":
            chave = f"prompt v{a.prompt_version or '?'}"
        elif args.por == "modelo":
            chave = a.model or "?"
        else:
            chave = f"{a.model or '?'} / v{a.prompt_version or '?'}"
        grupos.setdefault(chave, []).append(a)

    cabecalho = (
        f"{'grupo':24s} {'n':>3s} {'seg':>6s} {'saída':>6s} "
        f"{'alertas':>7s} {'tk/alerta':>9s} {'trecho ok':>10s} {'citação ok':>11s}"
    )
    print(cabecalho)
    print("-" * len(cabecalho))

    for chave in sorted(grupos):
        lote = grupos[chave]
        # Duração só existe a partir da migration 012: análises antigas ficam de
        # fora da média em vez de entrar como zero e puxá-la para baixo.
        duracoes = [a.duration_ms for a in lote if a.duration_ms]
        saidas = [a.completion_tokens for a in lote if a.completion_tokens]

        total_alertas = 0
        conferidos = com_trecho = apoiadas = com_citacao = 0
        for a in lote:
            alertas = a.alerts or []
            total_alertas += len(alertas)
            c, ct, ap, cc = _taxas(alertas)
            conferidos += c
            com_trecho += ct
            apoiadas += ap
            com_citacao += cc

        segundos = f"{sum(duracoes) / len(duracoes) / 1000:6.1f}" if duracoes else "     ."
        saida = f"{sum(saidas) / len(saidas):6.0f}" if saidas else "     ."

        # A medida comparavel entre grupos. Saida total depende de quantos alertas
        # o contrato rende, e contratos diferentes rendem numeros muito diferentes:
        # dividir pelo numero de alertas isola o quanto o modelo escreve por
        # apontamento, que e o que uma mudanca de prompt de fato altera.
        por_alerta = (
            f"{sum(saidas) / total_alertas:9.0f}" if saidas and total_alertas else "        ."
        )

        print(
            f"{chave:24s} {len(lote):3d} {segundos} {saida} "
            f"{total_alertas / len(lote):7.1f} {por_alerta} "
            f"{_pct(conferidos, com_trecho):>10s} {_pct(apoiadas, com_citacao):>11s}"
        )

    print()
    print("seg        média da chamada ao modelo, onde está quase todo o tempo")
    print("saída      média de tokens gerados; é o que determina o tempo")
    print("alertas    média por documento; depende muito mais do contrato do que")
    print("           da versão do prompt")
    print("tk/alerta  tokens gastos por apontamento. É a coluna comparável entre")
    print("           grupos: isola o quanto o modelo escreve de quantos problemas")
    print("           o contrato tem")
    print("trecho ok  alertas cujo trecho citado foi localizado no documento")
    print("citação ok alertas cujo artigo citado foi localizado na base legal")
    print()
    print("Compare sempre os mesmos contratos entre grupos: o número de alertas")
    print("varia muito mais por contrato do que por versão de prompt.")

    sem_duracao = sum(1 for a in analises if not a.duration_ms)
    if sem_duracao:
        print()
        print(f"{sem_duracao} análise(s) sem duração gravada, anteriores à migration 012.")


if __name__ == "__main__":
    main()
