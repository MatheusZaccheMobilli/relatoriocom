"""Cálculo de dias úteis ponderados — Serra/ES.

Regra (mesma do dashboard de referência):
    Segunda a Sexta = 1.0
    Sábado         = 0.5
    Domingo        = 0.0
    Feriado        = 0.0  (sobrescreve Seg–Sex e Sábado)

Feriados: nacionais + estaduais ES + municipais Serra.
"""

from __future__ import annotations

from datetime import date, timedelta
from dateutil.relativedelta import relativedelta


# Feriados Serra/ES 2026 — atualizar anualmente.
# Inclui nacionais + ES + Serra (Aniversário 26/12) + religiosos móveis.
FERIADOS_2026: set[date] = {
    date(2026, 1, 1),    # Confraternização Universal
    date(2026, 2, 16),   # Carnaval (segunda)
    date(2026, 2, 17),   # Carnaval (terça)
    date(2026, 4, 3),    # Sexta-feira Santa
    date(2026, 4, 21),   # Tiradentes
    date(2026, 5, 1),    # Dia do Trabalho
    date(2026, 6, 4),    # Corpus Christi
    date(2026, 9, 7),    # Independência
    date(2026, 10, 12),  # N. Sra. Aparecida
    date(2026, 11, 2),   # Finados
    date(2026, 11, 15),  # Proclamação da República
    date(2026, 11, 20),  # Consciência Negra (federal a partir de 2024)
    date(2026, 12, 25),  # Natal
    date(2026, 12, 26),  # Aniversário de Serra
}


def _peso_dia(d: date) -> float:
    if d in FERIADOS_2026:
        return 0.0
    wd = d.weekday()  # 0=seg ... 6=dom
    if wd <= 4:
        return 1.0
    if wd == 5:
        return 0.5
    return 0.0


def _primeiro_dia(mes: date) -> date:
    return mes.replace(day=1)


def _ultimo_dia(mes: date) -> date:
    proximo = mes.replace(day=1) + relativedelta(months=1)
    return proximo - timedelta(days=1)


def du_mes(mes: date) -> float:
    """Dias úteis ponderados do mês inteiro (1.0 + 0.5 + 0.0)."""
    inicio = _primeiro_dia(mes)
    fim = _ultimo_dia(mes)
    total = 0.0
    d = inicio
    while d <= fim:
        total += _peso_dia(d)
        d += timedelta(days=1)
    return total


def du_ate_hoje(mes: date, hoje: date | None = None) -> float:
    """Dias úteis ponderados decorridos do dia 1 até `hoje` (inclusive).

    Se `hoje` está fora do mês, retorna `du_mes(mes)` (cheio) ou 0 (mês futuro).
    """
    if hoje is None:
        hoje = date.today()
    inicio = _primeiro_dia(mes)
    fim_mes = _ultimo_dia(mes)
    if hoje < inicio:
        return 0.0
    fim = min(hoje, fim_mes)
    total = 0.0
    d = inicio
    while d <= fim:
        total += _peso_dia(d)
        d += timedelta(days=1)
    return total
