# Contexto para o assistente — Poupança Corrente SC

Este arquivo orienta sessões futuras de assistente neste projeto. Leia inteiro antes de propor mudanças relevantes.

## O que é este projeto

Painel público de transparência fiscal sobre o Estado de Santa Catarina. O fluxo é:

1. `src/extract.py` baixa JSONs do RREO Anexo 01 via API Siconfi/STN.
2. `src/transform.py` consolida em CSV/Parquet e calcula indicadores derivados.
3. `site/` é um painel HTML estático servido pelo GitHub Pages.
4. Workflows automatizam a atualização mensal.

## Domínio fiscal — conceitos-chave

### Poupança corrente
Diferença entre receitas correntes e despesas correntes. Mede quanto sobra da atividade rotineira do Estado para investimento e amortização de dívida. Forma rigorosa usa Receita Corrente Líquida (RCL); aqui usamos proxy do Anexo 01 (vide [metodologia](docs/metodologia.md)).

### RCL — Receita Corrente Líquida
Definida no art. 2º, §1º da Lei de Responsabilidade Fiscal (LC 101/2000). Para Estados:
- **Soma das receitas correntes**
- **Menos:**
  - Contribuições dos servidores ao próprio RPPS
  - Compensação financeira entre regimes previdenciários (CF art. 201, §9º)
  - Transferências constitucionais e legais a Municípios (no caso de Estados)
- Apurada com base nos **12 meses** terminados no mês de referência.

Vive no **RREO Anexo 03** (Demonstrativo da RCL). **Esta v1 do painel não consome o Anexo 03** — incorporá-lo é o principal próximo passo evolutivo.

### Art. 167-A da CF (EC 109/2021)
Gatilho fiscal: se DC ÷ RC ≥ 95% no exercício anterior, vedações automáticas no exercício seguinte (contratação, reajustes, novos benefícios tributários, etc.). Texto integral em [docs/ec-109.md](docs/ec-109.md).

**Três escolhas críticas** que fazemos no cálculo (alinhadas com a SEF/SC — vide `docs/metodologia.md`):
1. **Agregamos intra-orçamentárias.** Cada conta corrente aparece duas vezes no RREO Anexo 01 (seção I/VIII = exceto-intra, seção II/IX = intra). Distintivo via `cod_conta` (sufixo `Intra`). Somamos.
2. **Despesa empenhada**, não liquidada — estágio canônico para limites de gasto (LRF art. 19). Mantemos liquidada em colunas `_liq` para auditoria.
3. **Rolling 12 meses** (`dc_rc_12m`), não acumulado dentro do exercício. Fórmula: `12m[a,b] = anual[a-1] + acum[a,b] - acum[a-1,b]`. É a chave do art. 167-A ("exercício financeiro anterior").

Faixas adotadas no painel:
- < 85% → confortável (verde)
- 85-95% → alerta (amarelo) — convenção do painel, *não* constitucional
- ≥ 95% → crítico (vermelho) — limite real do art. 167-A

## API Siconfi — pontos críticos

- **Base:** `https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo`
- **Sem autenticação.** Rate limit informal — usar retry exponencial.
- **404** é esperado para bimestres ainda não publicados → log warning, segue.
- **id_ente=42** é Santa Catarina (código IBGE da UF).
- **Caixa baixa nos parâmetros:** `an_exercicio`, `nr_periodo`, `co_tipo_demonstrativo`, `no_anexo`, `id_ente`.
- **Encoding:** JSON retornado é UTF-8 mas pode mostrar mojibake em terminal Windows (cosmético).
- **Estrutura instável entre MDFs:** códigos de conta (`cod_conta`) variam entre edições anuais; **sempre** casar por descrição normalizada (vide `src/config.py:normalizar`).

## Convenções de código

- **Português** em comentários e nomes (exceto convenções universais).
- **Imports absolutos** dentro do pacote `src` (use `from .config import ...`).
- **Datas/períodos:** sempre tratar como `(ano, bimestre)`, não data calendário.
- **Valores monetários:** floats em reais nominais. Formatar no front-end, não no pipeline.
- **Logs:** módulo `logging`, nunca `print`. Formato unificado em `extract.py` / `transform.py`.
- **Testes:** se for adicionar, prefira `pytest` em `tests/`.

## Como adicionar um novo indicador

1. Em `src/config.py`, mapeie a conta nova em `CONTAS_RECEITA` ou `CONTAS_DESPESA` se ainda não estiver.
2. Em `src/transform.py`, dentro de `_calcular_indicadores()`, derive a nova coluna do DataFrame.
3. Em `site/app.js`, leia a coluna e adicione KPI/gráfico.
4. Documente em `docs/metodologia.md`.

Se o indicador exigir conta de outro anexo (RREO 03, 06 etc.), primeiro estenda `extract.py` para baixar esse anexo, depois replique o padrão de extração em `transform.py`.

## Princípios

- **Transparência total**: todo cálculo é auditável a partir do CSV. Sem cálculos "no front-end" que não estejam no CSV.
- **Dados imutáveis em raw/**: `data/raw/*.json` é a fonte de verdade. Nunca edite manualmente.
- **Mudanças interpretativas**: se ajustar interpretação de gatilho ou definição de indicador, marque com comentário citando a base legal (artigo, lei, MDF) e atualize a metodologia.
- **Falhas graciosas**: o pipeline e o site devem degradar quando faltam dados — nunca quebrar o painel inteiro por um campo nulo.

## Limitações conhecidas

- RCL é proxy (precisa Anexo 03).
- Valores nominais, sem deflator.
- Sem comparativo entre UFs (estrutura permite, falta UI).
- Sem alerta/notificação quando muda de zona (extensão útil).

## Próximos passos sugeridos

1. **Incorporar RREO Anexo 03** para RCL oficial.
2. **Adicionar outros Estados** para benchmarking horizontal.
3. **Deflator IPCA** para análise real.
4. **Análise por função** (RREO Anexo 02) para detalhar onde a despesa cresce.
