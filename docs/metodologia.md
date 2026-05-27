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

## Três escolhas metodológicas críticas

A leitura padrão (acumulado no exercício, exceto-intra, liquidada) **subestima sistematicamente** o indicador do art. 167-A. Para alinhar com a interpretação da SEF/SC e da literatura fiscal, fazemos três ajustes:

### 1. Agregamos intra-orçamentárias

Cada conta corrente aparece **duas vezes** no RREO Anexo 01:
- Uma linha na seção **"EXCETO INTRA-ORÇAMENTÁRIAS (I/VIII)"**
- Uma linha na seção **"INTRA-ORÇAMENTÁRIAS (II/IX)"**

O distintivo está no campo `cod_conta`: a versão intra termina com `Intra` (ex.: `ReceitasCorrentes` vs `ReceitasCorrentesIntra`). **Somamos as duas** porque o agregado é o universo natural para análise de um único ente — a segregação intra serve à consolidação federativa para evitar dupla contagem, não à leitura interna do Estado.

Mantemos as parcelas exceto-intra disponíveis em colunas com sufixo `_exc_intra` para auditoria.

### 2. Despesa em estágio de empenho

Para a leitura constitucional do art. 167-A, usamos `DESPESAS EMPENHADAS ATÉ O BIMESTRE (f)` como métrica principal:

- **Empenhada**: compromisso assumido. Estágio canônico para limites de gasto (a LRF usa empenhado para o limite de pessoal, art. 19).
- Liquidada: serviço prestado / mercadoria entregue. Útil mas sub-mede compromissos do exercício.
- Paga: fluxo de caixa. Depende de calendário financeiro, não é a métrica certa para análise estrutural.

As liquidadas ficam disponíveis em colunas `_liq` (e o ratio `dc_rc_liquidada`) para comparação.

### 3. Janela móvel de 12 meses

O art. 167-A fala em "exercício financeiro anterior" — uma janela de 12 meses fechados, **não** acumulado dentro do exercício corrente. Calculamos:

```
DC12m[ano, bim] = DC_anual[ano-1] + DC_acum[ano, bim] − DC_acum[ano-1, bim]
RC12m[ano, bim] = (idem para receita)
dc_rc_12m       = DC12m / RC12m
```

É o equivalente bimestral do "trailing twelve months" usado em análise fiscal corporativa.

Para o **status constitucional** do painel, preferimos `dc_rc_12m` quando disponível; quando não (primeiros bimestres da série, sem ano anterior na base), caímos para a razão acumulada do bimestre como aproximação.

## Coluna de valor utilizada
- **Receitas correntes:** coluna `Até o Bimestre (c)` — acumulado realizado.
- **Despesas correntes (principal):** coluna `DESPESAS EMPENHADAS ATÉ O BIMESTRE (f)` — acumulado empenhado.
- **Despesas correntes (auditoria):** coluna `DESPESAS LIQUIDADAS ATÉ O BIMESTRE (h)`.

## Contas mapeadas
Por correspondência de descrição normalizada (remove acentos, caixa alta, espaços compactados), porque os códigos `cod_conta` variam entre edições anuais do MDF (e ainda servem para distinguir intra vs exceto-intra).

| Nome canônico | Descrição RREO |
|---|---|
| `receitas_correntes` | RECEITAS CORRENTES (agregado exc-intra + intra) |
| `transferencias_correntes` | TRANSFERÊNCIAS CORRENTES (agregado) |
| `despesas_correntes` | DESPESAS CORRENTES (agregado, empenhadas) |
| `pessoal_encargos` | PESSOAL E ENCARGOS SOCIAIS |
| `juros_encargos` | JUROS E ENCARGOS DA DÍVIDA |
| `outras_despesas_correntes` | OUTRAS DESPESAS CORRENTES |

## Indicadores

### Poupança bruta
```
poupanca_bruta = receitas_correntes − despesas_correntes
```
Quando positiva, o Estado tem recursos correntes disponíveis para investimento ou amortização de dívida. Como usamos despesa empenhada, esse indicador captura o compromisso assumido com a operação corrente, não apenas o já liquidado.

### Poupança líquida (proxy)
```
poupanca_liquida_proxy = (receitas_correntes − transferencias_correntes) − despesas_correntes
```
**Proxy** porque a apuração rigorosa da Receita Corrente Líquida (RCL) exige deduzir as transferências constitucionais e legais que o ente repassa a Municípios — esse detalhamento vive no **RREO Anexo 03 (Demonstrativo da RCL)**, fora do escopo do Anexo 01.

### DC ÷ RC
```
dc_rc       = despesas_correntes_acumulado / receitas_correntes_acumulado  (dentro do exercício)
dc_rc_12m   = trailing 12 months (chave do art. 167-A — é a métrica principal)
dc_rc_liquidada = mesma razão, mas com despesa liquidada (auditoria)
```

## Gatilhos do art. 167-A da CF (EC 109/2021)

A Emenda Constitucional 109/2021 introduziu o art. 167-A na Constituição Federal, criando mecanismos automáticos de ajuste fiscal escalonado por gatilhos:

| Zona | DC ÷ RC | Cor | Interpretação |
|---|---|---|---|
| Confortável | < 85% | Verde | Há espaço fiscal para investimento e poupança corrente positiva. |
| Alerta | 85% – 95% | Amarelo | Aproximação das condições de acionamento; vigilância recomendada. |
| Crítica | ≥ 95% | Vermelho | Acima do limiar que justifica as vedações automáticas do art. 167-A. |

**Importante:** o art. 167-A se aplica a todos os entes (CF: "União, Estados, DF e Municípios"). As vedações específicas (concessão de vantagens, contratação de pessoal etc.) têm regimes próprios para Estados na LRF (LC 101/2000).

## Reconciliação com a SEF/SC
A SEF/SC publica o mesmo indicador em base **mensal** (fonte: contabilidade interna). Como o Siconfi público só publica em base **bimestral**, nossas janelas de 12 meses não casam exatamente os mesmos meses, gerando uma diferença residual de até ~2 pontos percentuais entre nosso `dc_rc_12m` e o número publicado pela SEF para o mês mais próximo. Para fechamentos anuais (bimestre 6), os valores **coincidem** (ex.: 2025: SEF 88,65% × nosso 88,64%).

## Atualização do conjunto
Pipeline em GitHub Actions executa no dia 5 de cada mês (cron `0 9 5 * *`). Caso o bimestre mais recente ainda não tenha sido publicado pelo Estado no Siconfi, a chamada retorna 404 e o pipeline registra warning sem falhar.

## Limitações conhecidas
1. **Granularidade bimestral** — Siconfi só publica de 2 em 2 meses; a SEF tem dados mensais.
2. **RCL é proxy**, não oficial — vide acima sobre Anexo 03.
3. **Sem deflator** — valores nominais. Comparações intertemporais devem considerar inflação.
4. **Sem Anexo 02** — Demonstrativo da Execução das Despesas por Função/Subfunção.
5. **Sem comparativo entre UFs** — estrutura suporta, mas v1 é Santa Catarina apenas.
