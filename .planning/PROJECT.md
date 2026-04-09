# Relatório de Comissão de Vendedores — Mobílli

## What This Is

Aplicação Streamlit que gera relatórios de comissão de vendedores em PDF, puxando dados do Bitrix24 CRM. O RH acessa via link, seleciona filtros (vendedor, mês, tipo de operação), e baixa o PDF estilizado no padrão Mobílli para coleta de assinatura do vendedor.

## Core Value

RH consegue gerar o relatório de comissão de cada vendedor com dados reais do CRM, sem preenchimento manual, e exportar como PDF pronto para assinatura.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Filtros: vendedor, mês/ano de referência, tipo de operação (Locação/Venda)
- [ ] Conexão com Bitrix24 via webhook (pipelines 48=Locação, 40=Venda de Motos GW12)
- [ ] Cálculo automático de nível (Bronze 75%, Prata 100%, Ouro 125% da meta)
- [ ] Cálculo de comissão B2C conforme tabela TM-018:
  - Venda 0km: Bronze 1,00% / Prata 1,20% / Ouro 1,30% sobre preço de venda
  - Venda Usado: Bronze 3,40% / Prata 4,00% / Ouro 4,80% sobre preço de venda
  - Locação: Bronze 8,00% / Prata 9,00% / Ouro 10,00% sobre primeira mensalidade
- [ ] Parcelas de locação: 3 meses, cessa se houver churn
- [ ] Lista de verificação de pagamento (parcela, cliente, placa, data locação, data retorno)
- [ ] Indicadores: negócios fechados no período, negócios encerrados (devolvidos)
- [ ] Bloco de meta: competência, valor meta mensal, nível atingido
- [ ] Dados do vendedor: nome, CPF
- [ ] Termo de ciência com espaço para assinatura
- [ ] Total a receber (R$)
- [ ] Geração de PDF individual estilizado no padrão Mobílli
- [ ] Geração de ZIP com PDF de todos os vendedores de uma vez
- [ ] Deploy no Streamlit Cloud (gratuito, link compartilhável)

### Out of Scope

- B2B (>=5 motos/cliente) — será adicionado depois do v1
- Consórcio — não entra nesta versão
- Assinatura digital (DocuSign, Clicksign) — processo de assinatura é externo
- App mobile — acesso via navegador é suficiente
- Cálculo de passivos de comissões de regras anteriores (item 3.4 do TM-018)

## Context

- **Fonte de dados:** API REST Bitrix24 via webhook (mesmo do projeto Power BI)
- **Webhook:** Mesmo endpoint usado no projeto BI (ver `.env` em `../Construção Power BI/.env`)
- **Documento base:** TM-018 - Termo de Comissão de Vendas (regras formais de comissão)
- **Referência visual:** `relatorio 1.jpeg` (rascunho manual do layout)
- **Marca:** Extrair padrão visual do site mobillirentals.com.br
- **Pipelines Bitrix24:**
  - Pipeline 48: Locação APP
  - Pipeline 40: Venda de Motos GW12
- **Campos CRM necessários:**
  - Deals: ID, título, vendedor (ASSIGNED_BY_ID), data fechamento, status, pipeline, valor
  - Clientes: nome
  - Veículos: placa (campo custom a identificar)
  - Vendedores: nome, CPF (campo custom a identificar)
- **Regra de parcelas (Locação):**
  - Comissão dividida em 3 parcelas mensais
  - Negócio fechado em mês X → parcela 1/3 em X+1, parcela 2/3 em X+2, parcela 3/3 em X+3
  - Se churn (cliente cancela), pagamento cessa no mês subsequente ao cancelamento
- **Metas:** Definidas mensalmente pela empresa, valor base configurável no relatório

## Constraints

- **Tech stack**: Python + Streamlit — simplicidade de manutenção e deploy
- **Deploy**: Streamlit Cloud (gratuito) — compartilha link com RH
- **Dados**: Webhook Bitrix24 — mesmo do projeto BI existente
- **Escopo B2C**: Apenas operações B2C no v1 (1-4 motos/cliente)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Streamlit como framework | Fácil manutenção, deploy gratuito, filtros nativos, sem frontend separado | — Pending |
| Streamlit Cloud como hosting | Gratuito, basta compartilhar link | — Pending |
| Apenas B2C no v1 | Simplificar escopo inicial, B2B adicionado depois | — Pending |
| Consórcio fora do v1 | Não está nos pipelines atuais do Bitrix | — Pending |
| Parcelas em 3 meses (não 2) | Conforme TM-018, regra formal da empresa | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-09 after initialization*
