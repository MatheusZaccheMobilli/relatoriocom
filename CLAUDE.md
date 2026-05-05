## Project

**Mobílli — Relatório de Comissão de Vendedores**

Relatório mensal de comissão que puxa dados do Bitrix24 CRM para o RH gerar, imprimir e coletar assinatura dos vendedores. Cobre operações de Locação (pipeline 48) e Venda de Motos GW12 (pipeline 40).

**Core Value:** RH consegue gerar o relatório de comissão de cada vendedor com dados reais do CRM, sem preencher manualmente, e o vendedor assina confirmando ciência.

### Quem usa

- **RH** gera o relatório (seleciona vendedor, mês, tipo de operação)
- **Vendedor** recebe, confere e assina

### Constraints

- **Fonte de dados:** API REST Bitrix24 via webhook (mesmo do projeto BI)
- **Webhook:** Mesmo webhook usado no projeto Power BI (ver `.env` em `../Construção Power BI/.env`)
- **Tecnologia:** A DEFINIR na primeira sessão de trabalho
- **Cálculo de comissão:** PENDENTE — estrutura será montada com placeholder

### Referência visual

- `relatorio 1.jpeg` — rascunho manual do layout do relatório

---

## Especificação do Relatório

### Cabeçalho (filtros selecionáveis)

- **Tipo de operação**: seletor entre "Locação" e "Venda" (não altera campos, apenas filtra dados)
- **Mês de referência**: seletor de mês/ano
- **Vendedor**: seletor de vendedor

Todos os filtros são selecionáveis. Ao mudar qualquer um, o relatório inteiro se atualiza.

### Dados do Vendedor

- **Nome do vendedor** (preenchido automaticamente pelo filtro)
- **CPF do vendedor**

### Bloco de Meta

- **Competência**: mês/ano de referência (mesmo do filtro)
- **Valor da meta mensal**: campo configurável (valor base X)
- **Nível atingido**: calculado automaticamente (proporção 32%):
  - **Bronze**: < 100% da meta (padrão, sem floor)
  - **Prata**: ≥ 100% da meta (= X)
  - **Ouro**: ≥ 132% da meta (X + 32%)

### Indicadores

- **Negócios fechados no período**: quantidade no mês de referência
- **Negócios encerrados (devolvidos)**: fechados em M-1 e M-2 que foram devolvidos no mês atual

### Lista de Verificação de Pagamento

| Parcela | Nome do Cliente | Placa | Data Locação | Data Retorno |
|---------|-----------------|-------|--------------|--------------|

**Regra de parcelas (M-1 e M-2):**
- Comissão dividida em 2 parcelas
- Negócio fechado em mês X → parcela 1/2 em X+1, parcela 2/2 em X+2
- Relatório do mês M mostra:
  - Negócios de M-1 como parcela 1/2
  - Negócios de M-2 como parcela 2/2
- Negócios devolvidos/encerrados: sinalizados ou descontados

### Rodapé

- **Termo de ciência**: "Eu, [nome do vendedor], declaro que li e concordo com os dados apresentados acima."
- **Espaço para assinatura**: linha/campo em branco
- **Total a receber (R$)**: valor total da comissão (cálculo PENDENTE)

---

## Dados do Bitrix24

### Pipelines relevantes
- **Pipeline 48**: Locação APP
- **Pipeline 40**: Venda de Motos GW12

### Campos necessários do CRM
- Deals: ID, título, vendedor (ASSIGNED_BY_ID), data fechamento, status, pipeline
- Clientes: nome
- Veículos: placa (campo custom a identificar)
- Vendedores: nome, CPF (campo custom a identificar)

### Webhook
Mesmo endpoint do projeto BI. Base URL no `.env` do projeto irmão (`../Construção Power BI/.env`).

---

## Pendências

- [ ] Definir tecnologia de implementação
- [ ] Definir racional de cálculo do valor da comissão (R$)
- [ ] Identificar campo de CPF do vendedor no Bitrix24
- [ ] Identificar campo de placa do veículo no Bitrix24
- [ ] Definir valor base da meta mensal (ou se vem de alguma fonte)

## Estrutura de pastas

```
/
├── app.py                     # Streamlit (entrypoint)
├── logo-mobilli.png           # Logo usada no PDF
├── requirements.txt
├── CLAUDE.md                  # Este arquivo
├── .env                       # Webhook/API keys (gitignored)
│
├── src/                       # Código de produção
│   ├── models.py              # Dataclasses (Deal, Pagamento, etc.)
│   ├── business/
│   │   ├── orchestrator.py    # Monta o RelatorioData cruzando Bitrix+MicroWork
│   │   └── comissao.py        # Tabela TM-018 e cálculo de nível
│   ├── data/
│   │   ├── bitrix.py          # Cliente API Bitrix24
│   │   └── microwork.py       # Cliente API MicroWork Cloud
│   ├── export/
│   │   ├── pdf.py             # Geração do PDF do relatório
│   │   └── fonts/             # Fontes DejaVu
│   └── ui/
│
├── scripts/
│   ├── gerar_manual_rh.py     # Gera o manual de comissão para o RH
│   ├── validacao/             # Scripts ad-hoc de investigação (gitignored)
│   └── arquivados/            # One-offs históricos (gitignored)
│
├── docs/                      # Docs de referência (PDF/DOCX)
│   ├── doc_apiMicrowork.pdf
│   ├── TM - 018 - ...docx
│   └── relatorio 1.jpeg       # Rascunho visual original
│
└── output/                    # PDFs gerados (gitignored)
```

## Regras de cálculo (resumo)

**Locação (Pipeline 48):**
1. Filtro: `especie=OUTROS` + documento casa `^\d{4,}-\d+P?\s*-\s*\d+$`
2. Soma pagamentos no mês-base; qtd efetiva = `round(soma / valor_card)`
3. Base = `qtd × valor_card` (descarta juros, protege parciais)
4. **Semanal:** 1/2 = mês do fechamento, 2/2 = mês seguinte
5. **Mensal:** ambas parcelas usam mês do fechamento, comissão total ÷ 2

**Venda (Pipeline 40):**
- Base = `deal.valor` direto (card Bitrix, não consulta MicroWork)
- Parcela única 1/1 paga em M+1

**Níveis de meta (TM-018):**
- Bronze: < 100% da meta (padrão)
- Prata: ≥ 100% da meta
- Ouro: ≥ 132% da meta (proporção 32% sobre a meta)

**Devolução:** Deal no Pipeline 22 com mesma placa + mesmo contato zera a comissão daquele ciclo.

## Conventions

- Dataclasses frozen em `src/models.py` — nenhum dict cru atravessa camadas
- Fontes customizadas em `src/export/fonts/` (DejaVu, já empacotadas)
- Scripts em `scripts/` rodam do **project root**: `python scripts/gerar_manual_rh.py`
- Output vai pra `output/` (gitignored)
