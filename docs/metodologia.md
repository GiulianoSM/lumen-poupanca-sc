# Metodologia

## Fonte primária
Os dados deste painel vêm exclusivamente da **API pública do Siconfi** (Sistema de Informações Contábeis e Fiscais do Setor Público Brasileiro), mantida pela Secretaria do Tesouro Nacional (STN).

- **Endpoint:** `https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo`
- **Demonstrativo:** RREO — Relatório Resumido de Execução Orçamentária
- **Anexo:** RREO-Anexo 01 — Balanço Orçamentário
- **Ente:** Estado de Santa Catarina (`id_ente=42`)
- **Periodicidade:** bimestral (6 bimestres por exercício)

## Janela temporal
Cobertura de **2015 até o ano corrente**. Antes de 2015, o MDF (Manual dos Demonstrativos Fiscais) sofreu reorganizações relevantes; estabilizá-las exigiria mapeamentos específicos fora do escopo desta v1.

## Coluna de valor utilizada
- **Receitas correntes:** coluna `Até o Bimestre (c)` — acumulado realizado no exercício.
- **Despesas correntes:** coluna `DESPESAS LIQUIDADAS ATÉ O BIMESTRE (h)` — acumulado liquidado no exercício.

Liquidada é o estágio mais comumente adotado para análises de execução corrente — empenhado superestima (inclui restos a pagar não processados) e pago subestima (depende de fluxo de caixa).

## Contas mapeadas
Por correspondência de descrição normalizada (remove acentos, caixa alta, espaços compactados), porque os códigos `cod_conta` variam entre edições anuais do MDF.

| Nome canônico | Descrição RREO |
|---|---|
| `receitas_correntes` | RECEITAS CORRENTES |
| `transferencias_correntes` | TRANSFERÊNCIAS CORRENTES |
| `despesas_correntes` | DESPESAS CORRENTES |
| `pessoal_encargos` | PESSOAL E ENCARGOS SOCIAIS |
| `juros_encargos` | JUROS E ENCARGOS DA DÍVIDA |
| `outras_despesas_correntes` | OUTRAS DESPESAS CORRENTES |

## Indicadores

### Poupança bruta
```
poupanca_bruta = receitas_correntes − despesas_correntes
```
Mede o quanto, do que entrou em receita corrente, sobra após cobrir as despesas correntes. Quando positiva, o Estado tem recursos correntes próprios disponíveis para investimento ou amortização de dívida.

### Poupança líquida (proxy)
```
poupanca_liquida_proxy = (receitas_correntes − transferencias_correntes) − despesas_correntes
```
**Proxy** porque a apuração rigorosa da Receita Corrente Líquida (RCL) exige deduzir, da receita corrente bruta, as transferências constitucionais e legais que o ente é obrigado a repassar (no caso dos Estados, principalmente para Municípios). Esse detalhamento vive no **RREO Anexo 03 (Demonstrativo da RCL)**, fora do escopo do Anexo 01.

Como aproximação, subtraímos o total de **transferências correntes recebidas** — note que isso é *qualitativamente diferente* da dedução exigida pela LRF (art. 2º, §1º). É um indicador exploratório, útil para comparação relativa, e deve ser substituído por RCL oficial em uma futura versão que incorpore o Anexo 03.

### DC ÷ RC (despesa corrente sobre receita corrente)
```
dc_rc = despesas_correntes / receitas_correntes
dc_rc_12m = média móvel de 4 bimestres (~12 meses) de dc_rc
```

## Gatilhos do art. 167-A da CF (EC 109/2021)

A Emenda Constitucional 109/2021 introduziu o art. 167-A na Constituição Federal, criando mecanismos automáticos de ajuste fiscal escalonado por gatilhos:

| Zona | DC ÷ RC | Cor | Interpretação |
|---|---|---|---|
| Confortável | < 85% | Verde | Há espaço fiscal para investimento e poupança corrente positiva. |
| Alerta | 85% – 95% | Amarelo | Aproximação das condições de acionamento; vigilância recomendada. |
| Crítica | ≥ 95% | Vermelho | Acima do limiar que justifica as vedações automáticas do art. 167-A. |

**Importante:** o art. 167-A originalmente trata da **União**, embora seus parâmetros sirvam de referência analítica para entes subnacionais. As vedações específicas (concessão de vantagens, contratação de pessoal etc.) têm regimes próprios para Estados e Municípios na LRF (Lei Complementar 101/2000). Esta classificação é, portanto, **interpretativa**.

## Atualização do conjunto
Pipeline em GitHub Actions executa no dia 5 de cada mês (cron `0 9 5 * *`). Caso o bimestre mais recente ainda não tenha sido publicado pelo Estado no Siconfi, a chamada retorna 404 e o pipeline registra warning sem falhar.

## Limitações conhecidas
1. **RCL é proxy**, não oficial — vide acima.
2. **Sem deflator** — os valores são nominais. Comparações intertemporais devem considerar inflação.
3. **Sem Anexo 02** — Demonstrativo da Execução das Despesas por Função/Subfunção. Pode ser incorporado em futuras versões.
4. **Sem comparativo entre UFs** — a estrutura suporta, mas a v1 é Santa Catarina apenas.
