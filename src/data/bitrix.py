"""Cliente da API Bitrix24 — puxa deals e vendedores."""

import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Semaphore
from typing import Optional

import requests

from src.models import Deal, Vendedor

# Pipelines relevantes
PIPELINE_LOCACAO = 48           # Locação APP (fluxo principal)
PIPELINE_LOCACAO_SHOWROOM = 0   # Locação Showroom (presencial)
PIPELINE_VENDA = 40

# Limite global de conexões simultâneas ao Bitrix.
# Mais que isso = 503 Service Temporarily Unavailable.
_BITRIX_GATE = Semaphore(4)

# Status HTTP que justificam retry (rate limit + indisponibilidade transiente)
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _webhook_url() -> str:
    url = os.getenv("BITRIX_WEBHOOK_URL")
    if not url:
        raise RuntimeError("Variável BITRIX_WEBHOOK_URL não configurada")
    return url.rstrip("/")


def _call(method: str, params: dict | None = None) -> dict:
    """Chamada Bitrix com semáforo + retry exponencial.

    O semáforo limita concorrência global a 4. Retry tenta até 4 vezes em
    erros transientes (429/500/502/503/504, timeout, ConnectionError) com
    backoff exponencial (0.5s, 1s, 2s, 4s) + jitter.
    """
    url = f"{_webhook_url()}/{method}.json"
    last_exc: Exception | None = None
    delay = 0.5

    with _BITRIX_GATE:
        for tentativa in range(4):
            try:
                resp = requests.get(url, params=params or {}, timeout=30)
                if resp.status_code in _RETRY_STATUS:
                    last_exc = requests.HTTPError(
                        f"{resp.status_code} {resp.reason} (Bitrix {method})"
                    )
                else:
                    resp.raise_for_status()
                    return resp.json()
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_exc = exc

            if tentativa < 3:
                time.sleep(delay + random.uniform(0, 0.25))
                delay *= 2

    raise last_exc or RuntimeError(f"Bitrix {method} falhou sem causa identificada")


def _call_list(method: str, params: dict | None = None) -> list[dict]:
    """Busca paginada — itera até trazer todos os registros."""
    params = dict(params or {})
    resultado = []
    start = 0

    while True:
        params["start"] = start
        data = _call(method, params)
        items = data.get("result", [])
        if not items:
            break
        resultado.extend(items)
        next_val = data.get("next")
        if next_val is None:
            break
        start = int(next_val)

    return resultado


def _parse_date(raw: str | None) -> Optional[date]:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except (ValueError, TypeError):
        return None


def _dec(val) -> Decimal:
    if not val:
        return Decimal("0")
    return Decimal(str(val))


def _normalize_cpf(raw: str | None) -> str:
    if not raw:
        return ""
    return "".join(c for c in raw if c.isdigit())


def buscar_deals(pipeline_id: int, fecha_inicio: date, fecha_fim: date) -> list[Deal]:
    """Busca deals WON em um pipeline para o período (data de locação/venda)."""

    # Pipeline 0 (categoria default) usa stages sem prefixo: "WON"
    # Pipelines >0 usam stages com prefixo: "C48:WON", "C40:WON", etc.
    stage_won = "WON" if pipeline_id == 0 else f"C{pipeline_id}:WON"

    params = {
        "filter[CATEGORY_ID]": pipeline_id,
        "filter[STAGE_ID]": stage_won,
        "filter[>=UF_CRM_1743092456783]": fecha_inicio.isoformat(),
        "filter[<=UF_CRM_1743092456783]": fecha_fim.isoformat(),
        "select[]": [
            "ID", "TITLE", "CATEGORY_ID", "STAGE_ID",
            "ASSIGNED_BY_ID", "CONTACT_ID", "OPPORTUNITY",
            "CLOSEDATE",
            "UF_CRM_1730135950688",   # CPF/CNPJ no deal
            "UF_CRM_1749815964662",   # Placa
            "UF_CRM_1743092456783",   # Data locação/venda
            "UF_CRM_WEEKLY_SUBSCRIPTION",  # Plano semanal
        ],
    }

    raw_deals = _call_list("crm.deal.list", params)
    resultado = []

    for d in raw_deals:
        # UF_CRM_WEEKLY_SUBSCRIPTION é boolean do Bitrix: "1" = semanal, "0" = mensal
        semanal_raw = (d.get("UF_CRM_WEEKLY_SUBSCRIPTION") or "").strip()
        is_semanal = semanal_raw == "1"

        resultado.append(
            Deal(
                id=int(d["ID"]),
                titulo=d.get("TITLE", ""),
                pipeline_id=int(d.get("CATEGORY_ID", 0)),
                stage_id=d.get("STAGE_ID", ""),
                assigned_by_id=int(d.get("ASSIGNED_BY_ID", 0)),
                contact_id=int(d["CONTACT_ID"]) if d.get("CONTACT_ID") else None,
                cpf_cnpj_deal=_normalize_cpf(d.get("UF_CRM_1730135950688")),
                valor=_dec(d.get("OPPORTUNITY")),
                data_locacao=_parse_date(d.get("UF_CRM_1743092456783")),
                placa=d.get("UF_CRM_1749815964662") or "",
                plano_semanal=is_semanal,
                data_fechamento=_parse_date(d.get("CLOSEDATE")),
            )
        )

    return resultado


def buscar_vendedores(user_ids: list[int]) -> dict[int, Vendedor]:
    """Busca dados dos vendedores por IDs. Retorna dict[user_id, Vendedor]."""

    vendedores = {}
    for uid in set(user_ids):
        try:
            data = _call("crm.deal.list", {
                "filter[ASSIGNED_BY_ID]": uid,
                "select[]": ["ASSIGNED_BY_ID"],
                "limit": 1,
            })
            # Não conseguimos pegar nome/CPF do user sem scope user
            # Usamos o user.get se disponível, senão placeholder
            try:
                user_data = _call("user.get", {"ID": uid})
                users = user_data.get("result", [])
                if users:
                    u = users[0]
                    nome = f"{u.get('NAME', '')} {u.get('LAST_NAME', '')}".strip()
                    vendedores[uid] = Vendedor(id=uid, nome=nome)
                    continue
            except Exception:
                pass

            vendedores[uid] = Vendedor(id=uid, nome=f"Vendedor #{uid}")
        except Exception:
            vendedores[uid] = Vendedor(id=uid, nome=f"Vendedor #{uid}")

    return vendedores


PIPELINE_DEVOLUCAO = 22


def _devolucoes_de_placa(placa: str) -> tuple[str, list[dict]]:
    """Busca devoluções (P22) de UMA placa. Retorna (placa, lista)."""
    params = {
        "filter[UF_CRM_1749815964662]": placa,
        "filter[CATEGORY_ID]": PIPELINE_DEVOLUCAO,
        "select[]": [
            "ID", "TITLE", "CONTACT_ID",
            "UF_CRM_1749815964662",   # Placa
            "UF_CRM_1758565735272",   # Data devolução
        ],
    }
    deals = _call_list("crm.deal.list", params)
    devs = []
    for d in deals:
        data_dev = _parse_date(d.get("UF_CRM_1758565735272"))
        if data_dev:
            devs.append({
                "id": int(d["ID"]),
                "titulo": d.get("TITLE", ""),
                "placa": placa,
                "data_devolucao": data_dev,
                "contact_id": int(d["CONTACT_ID"]) if d.get("CONTACT_ID") else None,
            })
    return placa, devs


def buscar_devolucoes_por_placas(placas: list[str]) -> dict[str, list[dict]]:
    """Busca deals de devolução no Pipeline 22 para as placas informadas.

    Retorna dict[placa, lista de devoluções] com data_devolucao e titulo.
    Faz N chamadas paralelas (uma por placa única) — ordens de magnitude
    mais rápido que o loop sequencial original.
    """
    if not placas:
        return {}

    placas_unicas = [p for p in set(placas) if p]
    if not placas_unicas:
        return {}

    resultado: dict[str, list[dict]] = {}
    # 6 workers — o semáforo global de 4 conexões serializa o excedente,
    # mas mantemos um pequeno pool pra esconder latência de DNS/TCP.
    with ThreadPoolExecutor(max_workers=6) as ex:
        for placa, devs in ex.map(_devolucoes_de_placa, placas_unicas):
            if devs:
                resultado[placa] = devs

    return resultado


def buscar_cpf_contato(contact_id: int) -> str:
    """Busca CPF/CNPJ de um contato do Bitrix."""

    try:
        data = _call("crm.contact.get", {"ID": contact_id})
        result = data.get("result", {})
        return _normalize_cpf(result.get("UF_CRM_1721609323"))
    except Exception:
        return ""


def buscar_placa_contato(contact_id: int) -> str:
    """Busca placa(s) associada(s) a um contato (campo array)."""

    try:
        data = _call("crm.contact.get", {"ID": contact_id})
        result = data.get("result", {})
        placas = result.get("UF_CRM_1723028259246")
        if isinstance(placas, list) and placas:
            return placas[0]
        if isinstance(placas, str):
            return placas
        return ""
    except Exception:
        return ""
