"""Cliente da API MicroWork Cloud — puxa recebimentos por período."""

import os
from datetime import date
from decimal import Decimal

import requests

from src.models import Pagamento


def _env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Variável de ambiente {key} não configurada")
    return val


def _parse_date(raw: str | None) -> date:
    if not raw:
        return date.min
    return date.fromisoformat(raw[:10])


def _dec(val) -> Decimal:
    if val is None:
        return Decimal("0")
    return Decimal(str(val))


def _normalize_cpf(raw: str) -> str:
    """Remove pontos, traços e barras para comparação uniforme."""
    return "".join(c for c in raw if c.isdigit())


def buscar_recebimentos(inicio: date, fim: date) -> list[Pagamento]:
    """Busca recebimentos no MicroWork Cloud para o período informado."""

    url = _env("MICROWORK_API_URL")
    token = _env("MICROWORK_TOKEN")
    empresas_raw = _env("MICROWORK_EMPRESAS")
    empresas = [int(e.strip()) for e in empresas_raw.split(",")]

    body = {
        "idrelatorioconfiguracao": int(_env("MICROWORK_REPORT_CONFIG")),
        "idrelatorioconsulta": int(_env("MICROWORK_REPORT_CONSULTA")),
        "idrelatorioconfiguracaoleiaute": int(_env("MICROWORK_REPORT_LAYOUT")),
        "idrelatoriousuarioleiaute": int(_env("MICROWORK_REPORT_USER_LAYOUT")),
        "ididioma": 1,
        "listaempresas": empresas,
        "filtros": (
            f"Portador=null;"
            f"Datademovimentacaoinicial={inicio.isoformat()};"
            f"SomenteComProvisao=True;"
            f"Especie=null;"
            f"Departamento=null;"
            f"Operador=null;"
            f"Datademovimentacaofinal={fim.isoformat()};"
            f"Modalidadedecobranca=null;"
            f"Municipio=null;"
            f"Receita=null;"
            f"Vendedor=null;"
            f"ContaFinanceira=null;"
            f"Origem=null;"
            f"ComDocumentoFiscal=True;"
            f"DocumentoCancelado=False;"
            f"Pessoa=null;"
            f"RelacaoComercial=null;"
            f"LancamentosEstornados=False;"
            f"SomenteSemProvisao=True;"
            f"LancamentoTipoSistema=1"
        ),
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    resp = requests.post(url, json=body, headers=headers, timeout=60)
    resp.raise_for_status()
    dados = resp.json()

    if not isinstance(dados, list):
        return []

    resultado = []
    for r in dados:
        resultado.append(
            Pagamento(
                cpf_cnpj=_normalize_cpf(r.get("cpfoucnpj", "")),
                empresa=r.get("empresa", ""),
                documento=r.get("documento", ""),
                especie=r.get("especiedodocumento", ""),
                emissao=_parse_date(r.get("emissao")),
                vencimento=_parse_date(r.get("vencimento")),
                movimento=_parse_date(r.get("movimento")),
                pessoa=r.get("pessoa", ""),
                valor_parcela=_dec(r.get("valorparcela")),
                valor_lancamento=_dec(r.get("valorlancamento")),
                juros=_dec(r.get("juros")),
                multa=_dec(r.get("multa")),
                desconto=_dec(r.get("desconto")),
                valor_total=_dec(r.get("valortotal")),
                nota_fiscal=r.get("notafiscal") or "",
                rg=r.get("rgouinscricaoestadual") or "",
            )
        )

    return resultado
