"""Cliente da API Bitrix24 — puxa deals, vendedores e SPA Inventário."""

import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from threading import Semaphore
from typing import Optional

import requests

from src.models import Deal, InventarioMoto, Vendedor

# Pipelines relevantes
PIPELINE_LOCACAO = 48           # Locação APP (fluxo principal)
PIPELINE_LOCACAO_SHOWROOM = 0   # Locação Showroom (presencial)
PIPELINE_VENDA = 40

# ─── SPA Inventário de Motos (entityTypeId 1072) ───────────────────────
INVENTARIO_ENTITY_TYPE_ID = 1072
CADASTRO_ENTITY_TYPE_ID = 1076  # SPA Cadastro das Motos (catálogo)

# Stages do pipeline 28 do Inventário (único pipeline da SPA)
STAGE_INV_DISPONIVEL = "DT1072_28:NEW"
STAGE_INV_ALUGADA = "DT1072_28:UC_S400BR"
STAGE_INV_VENDIDA = "DT1072_28:SUCCESS"
STAGE_INV_CANCELADA = "DT1072_28:FAIL"

# Mapa stageId → label legível (descoberto via crm.status.list)
STAGES_INVENTARIO: dict[str, str] = {
    "DT1072_28:NEW": "Disponíveis",
    "DT1072_28:UC_1BA0K7": "Amostra | Teste | ADM",
    "DT1072_28:UC_WG73L1": "MKT",
    "DT1072_28:UC_S400BR": "Alugada",
    "DT1072_28:UC_CF60AT": "Parceiros",
    "DT1072_28:UC_IK83H1": "Manutenção | Com Cliente",
    "DT1072_28:UC_R2ZTM1": "Manutenção | Sem Cliente",
    "DT1072_28:UC_S503RS": "Manutenção | Desmobilização",
    "DT1072_28:UC_G81GRJ": "Manutenção | Externo",
    "DT1072_28:UC_89PW1I": "Moto c/ Restrição e sem Doc",
    "DT1072_28:UC_YDDGMM": "Sinistro | BO",
    "DT1072_28:UC_JR7O9S": "Preparação da Moto",
    "DT1072_28:UC_XZV1UO": "Aguardando Assinatura Transp.",
    "DT1072_28:UC_Q6V7UW": "Em Trânsito",
    "DT1072_28:SUCCESS": "Vendida",
    "DT1072_28:FAIL": "Cancelada",
}

# Campos custom do Inventário usados pelo app
_INV_PLACA = "ufCrm_68BB19F1AD8FD"
_INV_CADASTRO_ID = "ufCrm16_1749580517"
_INV_MODELO = "ufCrm16_1758898469346"
_INV_COR = "ufCrm16_1758052962637"
_INV_BASE = "ufCrm16_1766577003"
_INV_LOCAL_LOCACAO = "ufCrm16_1762542381071"
_INV_DATA_ULTIMA_LOCACAO = "ufCrm16_1762542410292"

# Mapa enumerated → texto (extraído de crm.item.fields, items[].ID → VALUE)
_BASE_LABELS: dict[str, str] = {
    "11354": "Serra galpão",
    "11356": "Vila Velha APP",
    "11358": "Vila Velha SH",
    "11360": "Serra SH",
    "11362": "Troca ou Destroca",
    # códigos do Cadastro (SPA 1076) — mesmo dicionário lógico
    "11338": "Serra galpão",
    "11340": "Vila Velha APP",
    "11342": "Vila Velha SH",
    "11344": "Serra SH",
    "11346": "Troca ou Destroca",
}


def label_base(raw: str | int | None) -> str:
    if raw in (None, "", 0):
        return ""
    return _BASE_LABELS.get(str(raw), str(raw))


def label_stage_inventario(stage_id: str | None) -> str:
    if not stage_id:
        return ""
    return STAGES_INVENTARIO.get(stage_id, stage_id)

# Catálogo de origens (SOURCE_ID → nome legível) — extraído do Bitrix via
# crm.status.list ENTITY_ID=SOURCE. Mantém em código pra:
#   1. Não fazer 1 chamada extra ao Bitrix por load (catálogo muda raramente)
#   2. Permitir agrupar fontes parecidas (vários WhatsApp viram "WhatsApp")
SOURCES_LABELS: dict[str, str] = {
    "EMAIL": "Formulário Showroom",
    "TRADE_SHOW": "Formulário Parceiros",
    "2|WHATSAPP": "Meta",
    "ADVERTISING": "Google Ads",
    "CALL": "Chamada",
    "WEB": "Site",
    "PARTNER": "Cliente Existente",
    "RECOMMENDATION": "Recomendação",
    "BOOKING": "Agendamento on-line",
    "WEBFORM": "Formulário CRM",
    "CALLBACK": "Retorno de Chamada",
    "RC_GENERATOR": "Canal de Marketing",
    "36|OPENLINE": "Bate-papo ao vivo",
    "42|WHATSAPP": "WhatsApp Disparo MKT",
    "32|BITRIX_WHATCRM_NET_70680444": "WhatsApp",
    "STORE": "Loja on-line",
    "UC_060700": "E-mail",
    "REPEAT_SALE": "Vendas recorrentes",
    "UC_0X6HPK": "Credere",
    "UC_IKCQBG": "Aplicativo",
}


def label_source(source_id: str) -> str:
    """Retorna nome legível de um SOURCE_ID. Fallback: o próprio ID."""
    if not source_id:
        return "Sem origem"
    return SOURCES_LABELS.get(source_id, source_id)

# Limite global de conexões simultâneas ao Bitrix.
# 6 = sweet spot pra dashboard (3 pipelines × 2 meses cabem em 1 wave).
# Mais que ~10 começa a estourar 503.
_BITRIX_GATE = Semaphore(6)

# Status HTTP que justificam retry (rate limit + indisponibilidade transiente)
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _webhook_url() -> str:
    url = os.getenv("BITRIX_WEBHOOK_URL")
    if not url:
        raise RuntimeError("Variável BITRIX_WEBHOOK_URL não configurada")
    return url.rstrip("/")


def _webhook_item_url() -> str:
    """Webhook usado para SPAs (crm.item.*).

    Cai pro `BITRIX_WEBHOOK_URL` se a variável dedicada não estiver setada —
    o scope `crm` cobre os endpoints `crm.item.*` em ambos os webhooks.
    """
    return (os.getenv("BITRIX_WEBHOOK_ITEM_URL") or _webhook_url()).rstrip("/")


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
            "CLOSEDATE", "SOURCE_ID",
            "UF_CRM_1730135950688",   # CPF/CNPJ no deal
            "UF_CRM_1749815964662",   # Placa
            "UF_CRM_1743092456783",   # Data locação/venda
            "UF_CRM_WEEKLY_SUBSCRIPTION",  # Plano semanal
            "UF_CRM_1744638028",      # Cidade do cliente (replicado no deal)
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
                source_id=(d.get("SOURCE_ID") or "").strip(),
                cidade=(d.get("UF_CRM_1744638028") or "").strip(),
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


# Bitrix limita o tamanho da URL/payload, então quebramos as placas em
# lotes. 50 por lote é seguro e mantém a contagem de chamadas baixa.
_DEVOLUCAO_BATCH = 50


def _devolucoes_lote(placas_lote: list[str]) -> list[dict]:
    """Busca devoluções (P22) para um lote de placas via filter array OR."""
    params: dict = {
        "filter[CATEGORY_ID]": PIPELINE_DEVOLUCAO,
        "select[]": [
            "ID", "TITLE", "CONTACT_ID",
            "UF_CRM_1749815964662",   # Placa
            "UF_CRM_1758565735272",   # Data devolução
        ],
    }
    # filter[UF_CRM_1749815964662][0]=PLACA1, filter[...][1]=PLACA2, ...
    # Bitrix interpreta como OR dentro do mesmo campo.
    for i, placa in enumerate(placas_lote):
        params[f"filter[UF_CRM_1749815964662][{i}]"] = placa
    return _call_list("crm.deal.list", params)


def buscar_devolucoes_por_placas(placas: list[str]) -> dict[str, list[dict]]:
    """Busca deals de devolução no Pipeline 22 para as placas informadas.

    Retorna dict[placa, lista de devoluções] com data_devolucao e titulo.
    Lotes de até `_DEVOLUCAO_BATCH` placas via filter OR — 1 chamada por
    lote em vez de 1 por placa. Para 200 placas: 4 chamadas paralelas
    em vez de 200. Reduz drasticamente carga no Bitrix e tempo total.
    """
    if not placas:
        return {}

    placas_unicas = [p for p in set(placas) if p]
    if not placas_unicas:
        return {}

    lotes = [
        placas_unicas[i : i + _DEVOLUCAO_BATCH]
        for i in range(0, len(placas_unicas), _DEVOLUCAO_BATCH)
    ]

    resultado: dict[str, list[dict]] = {}
    # max_workers = nº de lotes (gated em 6 pelo _BITRIX_GATE).
    with ThreadPoolExecutor(max_workers=max(1, len(lotes))) as ex:
        for raw_deals in ex.map(_devolucoes_lote, lotes):
            for d in raw_deals:
                placa = (d.get("UF_CRM_1749815964662") or "").strip()
                if not placa:
                    continue
                data_dev = _parse_date(d.get("UF_CRM_1758565735272"))
                if not data_dev:
                    continue
                resultado.setdefault(placa, []).append({
                    "id": int(d["ID"]),
                    "titulo": d.get("TITLE", ""),
                    "placa": placa,
                    "data_devolucao": data_dev,
                    "contact_id": int(d["CONTACT_ID"]) if d.get("CONTACT_ID") else None,
                })

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


# ─── SPA Inventário (crm.item.*) ───────────────────────────────────────
def _call_item(method: str, params: dict | None = None) -> dict:
    """Versão de `_call` que usa o webhook de SPA (BITRIX_WEBHOOK_ITEM_URL)."""
    url = f"{_webhook_item_url()}/{method}.json"
    last_exc: Exception | None = None
    delay = 0.5

    with _BITRIX_GATE:
        for tentativa in range(4):
            try:
                resp = requests.post(url, data=params or {}, timeout=30)
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


_PAGE_SIZE = 50  # default do crm.item.list


def _call_item_list(
    entity_type_id: int,
    filtros: dict | None = None,
    select: list[str] | None = None,
) -> list[dict]:
    """Paginação para `crm.item.list` — shape do response é `result.items`.

    Faz a primeira chamada sync pra descobrir `total`, depois despacha as
    páginas restantes em paralelo (gated em 6 conexões pelo `_BITRIX_GATE`).
    Para 1400+ itens, derruba o tempo de ~22s (sequencial) pra ~4s.

    `select` limita os campos retornados (ex: ["id", "stageId"]) — derruba
    payload de cada item de ~3KB pra ~50 bytes.
    """
    base_params: dict = {"entityTypeId": entity_type_id, **(filtros or {})}
    if select:
        for i, field in enumerate(select):
            base_params[f"select[{i}]"] = field

    # Página 1 (sync): aprende total e já traz o primeiro lote.
    first = _call_item("crm.item.list", {**base_params, "start": 0})
    items: list[dict] = list(first.get("result", {}).get("items", []))
    total = first.get("total")
    if not items or total is None or len(items) >= total:
        return items

    # Páginas 2..N (paralelo, gated pelo _BITRIX_GATE no _call_item).
    starts = list(range(_PAGE_SIZE, int(total), _PAGE_SIZE))

    def _fetch(start: int) -> list[dict]:
        data = _call_item("crm.item.list", {**base_params, "start": start})
        return list(data.get("result", {}).get("items", []))

    with ThreadPoolExecutor(max_workers=6) as ex:
        for page in ex.map(_fetch, starts):
            items.extend(page)

    return items


def _parse_dt(raw: str | None) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _build_inventario(raw: dict) -> InventarioMoto:
    return InventarioMoto(
        id=int(raw["id"]),
        placa=(raw.get(_INV_PLACA) or raw.get("title") or "").strip().upper(),
        modelo=(raw.get(_INV_MODELO) or "").strip(),
        cor=(raw.get(_INV_COR) or "").strip(),
        base=label_base(raw.get(_INV_BASE)),
        stage_id=raw.get("stageId") or "",
        stage_label=label_stage_inventario(raw.get("stageId")),
        deal_id=int(raw["parentId2"]) if raw.get("parentId2") else None,
        cadastro_id=int(raw[_INV_CADASTRO_ID]) if raw.get(_INV_CADASTRO_ID) else None,
        moved_at=_parse_dt(raw.get("movedTime")),
        updated_at=_parse_dt(raw.get("updatedTime")),
        local_locacao=(raw.get(_INV_LOCAL_LOCACAO) or "").strip(),
    )


def listar_inventario(stage_ids: list[str] | None = None) -> list[InventarioMoto]:
    """Lista todas as motos do Inventário, opcionalmente filtrando por stages."""
    if stage_ids:
        # Bitrix aceita array em filtro: filter[stageId][]=... — mas via POST
        # urlencoded precisa de key repetida. Mais simples: 1 chamada por stage.
        out: list[InventarioMoto] = []
        for sid in stage_ids:
            raws = _call_item_list(
                INVENTARIO_ENTITY_TYPE_ID, {"filter[stageId]": sid}
            )
            out.extend(_build_inventario(r) for r in raws)
        return out
    raws = _call_item_list(INVENTARIO_ENTITY_TYPE_ID)
    return [_build_inventario(r) for r in raws]


def contar_motos_por_estado() -> dict[str, int]:
    """Retorna dict[stage_label, count] com a distribuição atual da frota.

    Versão lightweight: usa `select=[id, stageId]` pra reduzir o payload
    de cada item de ~3KB para ~50 bytes. A paginação paralela em
    `_call_item_list` derruba o tempo de ~22s (sequencial) pra ~4s.

    SPA items não têm `stageSemanticId` — pra excluir terminais, filtra
    client-side pelo label (Vendida/Cancelada).
    """
    raws = _call_item_list(
        INVENTARIO_ENTITY_TYPE_ID,
        select=["id", "stageId"],
    )
    contagem: dict[str, int] = {}
    for raw in raws:
        label = label_stage_inventario(raw.get("stageId")) or "Sem estado"
        contagem[label] = contagem.get(label, 0) + 1
    return contagem


def contar_motos_alugadas() -> int:
    """KPI rápido: quantas motos estão no estado Alugada agora."""
    return len(listar_inventario([STAGE_INV_ALUGADA]))


def buscar_placas_por_deals(deal_ids: list[int]) -> dict[int, str]:
    """Resolve placas a partir de deal_ids via Inventário (parentId2 → deal).

    Cobertura observada: ~99.5% das motos Alugadas têm parentId2 preenchido.
    Para deals sem item no Inventário, o caller deve fazer fallback para
    `Deal.placa` ou `buscar_placa_contato`.
    """
    if not deal_ids:
        return {}
    motos = listar_inventario()
    return {
        m.deal_id: m.placa
        for m in motos
        if m.deal_id in set(deal_ids) and m.placa
    }
