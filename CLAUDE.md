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
- **Nível atingido**: calculado automaticamente:
  - **Bronze**: atingiu pelo menos 75% da meta (X - 25%)
  - **Prata**: atingiu 100% da meta (= X)
  - **Ouro**: atingiu 125% da meta (X + 25%)

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

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.

## Architecture

Architecture not yet mapped. Will be defined after escolha da tecnologia.
