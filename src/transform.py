"""Consolidação e cálculo de indicadores fiscais.

Lê todos os JSONs de `data/raw/`, extrai as contas relevantes do RREO Anexo 01
e produz CSV (auditoria) e Parquet (análise) em `data/processed/`.

### Decisões metodológicas (alinhadas com a SEF/SC para o art. 167-A)

1. **Inclusão de intra-orçamentárias.** Cada conta corrente aparece duas
   vezes no RREO: na seção "EXCETO INTRA-ORÇAMENTÁRIAS" e na seção
   "INTRA-ORÇAMENTÁRIAS". Somamos ambas — o agregado é o universo natural
   para análise de um único ente. As parcelas exceto-intra ficam disponíveis
   em colunas com sufixo `_exc_intra` para auditoria.
2. **Despesa em estágio de empenho.** Para a leitura constitucional do
   art. 167-A, usamos `DESPESAS EMPENHADAS ATÉ O BIMESTRE (f)` como métrica
   principal. As liquidadas ficam em colunas com sufixo `_liq`.
3. **DC/RC rolling 12 meses.** O texto constitucional fala em "exercício
   financeiro anterior" → janela de 12 meses fechados, não acumulado dentro
   do exercício. Calculamos:
        DC12m[ano, bim] = DC_acum[ano-1, 6] + DC_acum[ano, bim] − DC_acum[ano-1, bim]
   (idem RC). Para bimestres sem o ano anterior completo na base, fica NaN.

Indicadores derivados:
- poupanca_bruta              = rc_total − dc_total_empenhada
- poupanca_liquida_proxy      = (rc_total − transf_correntes) − dc_total_emp
- dc_rc                       = dc_total_emp / rc_total (acumulado no exercício)
- dc_rc_12m                   = rolling 12m (chave do art. 167-A)
- status_constitucional       = classificação pelo dc_rc_12m quando disponível,
                                senão pelo dc_rc do bimestre
- crescimento_yoy_*           = variação % ano-contra-ano do mesmo bimestre
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pandas as pd

from .config import (
    COLUNA_DESPESA_EMPENHADA,
    COLUNA_DESPESA_LIQUIDADA,
    COLUNA_RECEITA_ACUMULADA,
    CONTAS_DESPESA,
    CONTAS_RECEITA,
    classificar_dc_rc,
    conta_canonica,
    normalizar,
)

RAIZ = Path(__file__).resolve().parents[1]
DIR_RAW = RAIZ / "data" / "raw"
DIR_OUT = RAIZ / "data" / "processed"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("transform")


def _para_float(valor) -> float | None:
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _eh_intra(cod_conta: str | None) -> bool:
    """True quando o cod_conta indica a linha intra-orçamentária."""
    return "Intra" in (cod_conta or "")


def _extrair_valores_arquivo(caminho: Path) -> dict | None:
    """Lê um JSON RREO e devolve um dict com as contas-alvo agregadas.

    Para cada conta canônica (ex.: receitas_correntes), produz:
      - `<chave>`           : soma exceto-intra + intra
      - `<chave>_exc_intra` : apenas exceto-intra (auditoria)
    Para despesas, há ainda variantes em estágio empenhado (padrão) e
    liquidado (sufixo `_liq`).
    """
    try:
        payload = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.error("falha ao ler %s → %s", caminho.name, e)
        return None

    itens = payload.get("items") or []
    if not itens:
        return None

    primeiro = itens[0]
    ano = int(primeiro.get("exercicio"))
    bimestre = int(primeiro.get("periodo"))
    linha: dict = {"ano": ano, "bimestre": bimestre}

    col_rc = normalizar(COLUNA_RECEITA_ACUMULADA)
    col_dc_emp = normalizar(COLUNA_DESPESA_EMPENHADA)
    col_dc_liq = normalizar(COLUNA_DESPESA_LIQUIDADA)

    # Acumuladores temporários: {chave_canonica: {exc, intra}}
    rc_acum: dict[str, dict[str, float]] = {}
    dc_emp_acum: dict[str, dict[str, float]] = {}
    dc_liq_acum: dict[str, dict[str, float]] = {}

    for item in itens:
        coluna_n = normalizar(item.get("coluna"))
        valor = _para_float(item.get("valor"))
        cod = item.get("cod_conta")
        bucket = "intra" if _eh_intra(cod) else "exc"

        canon_r = conta_canonica(item.get("conta"), "receita")
        canon_d = conta_canonica(item.get("conta"), "despesa")

        if canon_r and coluna_n == col_rc and valor is not None:
            rc_acum.setdefault(canon_r, {}).setdefault(bucket, 0.0)
            rc_acum[canon_r][bucket] += valor

        if canon_d and valor is not None:
            if coluna_n == col_dc_emp:
                dc_emp_acum.setdefault(canon_d, {}).setdefault(bucket, 0.0)
                dc_emp_acum[canon_d][bucket] += valor
            elif coluna_n == col_dc_liq:
                dc_liq_acum.setdefault(canon_d, {}).setdefault(bucket, 0.0)
                dc_liq_acum[canon_d][bucket] += valor

    # Materializa colunas finais
    for chave in CONTAS_RECEITA:
        vals = rc_acum.get(chave, {})
        exc = vals.get("exc")
        intra = vals.get("intra", 0.0) if "intra" in vals else None
        total = (exc or 0.0) + (intra or 0.0) if (exc is not None or intra is not None) else None
        linha[chave] = total
        linha[f"{chave}_exc_intra"] = exc

    for chave in CONTAS_DESPESA:
        # Empenhada (métrica principal)
        vals_e = dc_emp_acum.get(chave, {})
        exc_e = vals_e.get("exc")
        intra_e = vals_e.get("intra", 0.0) if "intra" in vals_e else None
        tot_e = (exc_e or 0.0) + (intra_e or 0.0) if (exc_e is not None or intra_e is not None) else None
        linha[chave] = tot_e
        linha[f"{chave}_exc_intra"] = exc_e

        # Liquidada (auditoria)
        vals_l = dc_liq_acum.get(chave, {})
        exc_l = vals_l.get("exc")
        intra_l = vals_l.get("intra", 0.0) if "intra" in vals_l else None
        tot_l = (exc_l or 0.0) + (intra_l or 0.0) if (exc_l is not None or intra_l is not None) else None
        linha[f"{chave}_liq"] = tot_l

    return linha


def _rolling_12m(df: pd.DataFrame, coluna_acum: str) -> pd.Series:
    """Calcula janela móvel de 12 meses sobre coluna acumulada-no-exercício.

    Fórmula: 12m[ano, bim] = anual[ano-1] + acum[ano, bim] − acum[ano-1, bim].
    Equivale a "trailing 12 months" para dados bimestrais cumulativos.
    """
    # Mapas auxiliares (ano, bim) → valor acumulado
    acum = df.set_index(["ano", "bimestre"])[coluna_acum]
    # Anual = acumulado no bimestre 6
    anual = df[df["bimestre"] == 6].set_index("ano")[coluna_acum]

    valores = []
    for _, row in df.iterrows():
        a, b = int(row["ano"]), int(row["bimestre"])
        try:
            anual_anterior = anual.loc[a - 1]
            acum_anterior = acum.loc[(a - 1, b)]
            atual = row[coluna_acum]
            if pd.isna(anual_anterior) or pd.isna(acum_anterior) or pd.isna(atual):
                valores.append(float("nan"))
            else:
                valores.append(anual_anterior + atual - acum_anterior)
        except KeyError:
            valores.append(float("nan"))
    return pd.Series(valores, index=df.index)


def _calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["ano", "bimestre"]).reset_index(drop=True)

    # Identificadores temporais (data_ref = primeiro dia do mês posterior ao bimestre)
    df["data_ref"] = pd.to_datetime(
        df["ano"].astype(str) + "-" + (df["bimestre"] * 2).astype(str) + "-01",
        errors="coerce",
    )
    df["rotulo_periodo"] = df["ano"].astype(str) + "-B" + df["bimestre"].astype(str)

    # Indicadores principais (sobre o agregado total: exc-intra + intra,
    # com despesa em estágio empenhado).
    df["poupanca_bruta"] = df["receitas_correntes"] - df["despesas_correntes"]
    df["poupanca_liquida_proxy"] = (
        df["receitas_correntes"] - df["transferencias_correntes"]
    ) - df["despesas_correntes"]
    df["dc_rc"] = df["despesas_correntes"] / df["receitas_correntes"]

    # Variante com despesa liquidada (para comparação/auditoria)
    df["dc_rc_liquidada"] = df["despesas_correntes_liq"] / df["receitas_correntes"]

    # Rolling 12 meses — métrica do art. 167-A
    rc_12m = _rolling_12m(df, "receitas_correntes")
    dc_12m = _rolling_12m(df, "despesas_correntes")
    df["receitas_correntes_12m"] = rc_12m
    df["despesas_correntes_12m"] = dc_12m
    df["dc_rc_12m"] = dc_12m / rc_12m

    # Status constitucional: prefere a métrica rolling 12m (correta);
    # quando indisponível (primeiros anos da série), cai para o bimestre.
    def classificar(row):
        ratio = row["dc_rc_12m"] if pd.notna(row["dc_rc_12m"]) else row["dc_rc"]
        return classificar_dc_rc(ratio) if pd.notna(ratio) else ""

    df["status_constitucional"] = df.apply(classificar, axis=1)

    # Composição de despesa (participação relativa, sobre o total empenhado)
    for chave in ["pessoal_encargos", "juros_encargos", "outras_despesas_correntes"]:
        df[f"part_{chave}"] = df[chave] / df["despesas_correntes"]

    # Crescimento YoY (mesmo bimestre, ano anterior) — sobre o agregado
    for campo in ["receitas_correntes", "despesas_correntes", "poupanca_bruta"]:
        df[f"yoy_{campo}"] = df.groupby("bimestre")[campo].pct_change()

    return df


def consolidar() -> pd.DataFrame:
    if not DIR_RAW.exists():
        raise SystemExit(
            f"diretório de raw não existe: {DIR_RAW}. Rode `python -m src.extract` antes."
        )

    arquivos = sorted(DIR_RAW.glob("rreo_*.json"))
    if not arquivos:
        raise SystemExit("nenhum JSON em data/raw. Rode `python -m src.extract`.")

    linhas: list[dict] = []
    for caminho in arquivos:
        linha = _extrair_valores_arquivo(caminho)
        if linha:
            linhas.append(linha)

    df = pd.DataFrame(linhas)
    log.info("consolidado: %d bimestres", len(df))

    df = _calcular_indicadores(df)

    DIR_OUT.mkdir(parents=True, exist_ok=True)
    csv_path = DIR_OUT / "poupanca_sc.csv"
    pq_path = DIR_OUT / "poupanca_sc.parquet"
    df.to_csv(csv_path, index=False, encoding="utf-8")
    df.to_parquet(pq_path, index=False)
    log.info("escrito: %s", csv_path.relative_to(RAIZ))
    log.info("escrito: %s", pq_path.relative_to(RAIZ))

    return df


def _resumo(df: pd.DataFrame) -> None:
    if df.empty:
        log.warning("sem dados a resumir.")
        return
    ult = df.iloc[-1]
    ratio_principal = ult["dc_rc_12m"] if pd.notna(ult["dc_rc_12m"]) else ult["dc_rc"]
    log.info(
        "último bimestre: %s | DC/RC (bim)=%.2f%% | DC/RC (12m)=%s | status=%s | poup. bruta=R$ %.2f bi",
        ult["rotulo_periodo"],
        (ult["dc_rc"] or 0) * 100,
        f"{ult['dc_rc_12m']*100:.2f}%" if pd.notna(ult["dc_rc_12m"]) else "n/d",
        ult["status_constitucional"],
        (ult["poupanca_bruta"] or 0) / 1e9,
    )


def main() -> int:
    df = consolidar()
    _resumo(df)
    return 0


if __name__ == "__main__":
    sys.exit(main())
