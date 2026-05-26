"""Consolidação e cálculo de indicadores fiscais.

Lê todos os JSONs de `data/raw/`, extrai as contas relevantes (Receitas e
Despesas Correntes e seus subitens), e produz:

- `data/processed/poupanca_sc.csv`     — auditoria humana
- `data/processed/poupanca_sc.parquet` — eficiência analítica

Indicadores calculados por bimestre acumulado:
- poupanca_bruta            = receitas_correntes - despesas_correntes
- poupanca_liquida_proxy    = (receitas_correntes - transferencias_correntes) - despesas_correntes
- dc_rc                     = despesas_correntes / receitas_correntes
- dc_rc_12m                 = média móvel de 12 meses da DC/RC (4 bimestres)
- status_constitucional     = classificação pelo art. 167-A da CF (EC 109/2021)
- crescimento_yoy_*         = variação % ano-contra-ano do mesmo bimestre

Uso:
    python -m src.transform
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pandas as pd

from .config import (
    COLUNA_DESPESA_ACUMULADA,
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


def _coluna_alvo(tipo: str) -> set[str]:
    """Aceita pequenas variações de pontuação na descrição da coluna."""
    alvo = COLUNA_RECEITA_ACUMULADA if tipo == "receita" else COLUNA_DESPESA_ACUMULADA
    return {normalizar(alvo)}


def _extrair_valores_arquivo(caminho: Path) -> dict | None:
    """Lê um JSON RREO e devolve um dict com as contas-alvo."""
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

    colunas_receita = _coluna_alvo("receita")
    colunas_despesa = _coluna_alvo("despesa")

    encontradas_receita = set()
    encontradas_despesa = set()

    for item in itens:
        coluna_norm = normalizar(item.get("coluna"))
        desc = item.get("conta")
        valor = item.get("valor")

        # Caminho de receita
        if coluna_norm in colunas_receita:
            canonica = conta_canonica(desc, "receita")
            if canonica and canonica not in encontradas_receita:
                linha[canonica] = _para_float(valor)
                encontradas_receita.add(canonica)

        # Caminho de despesa
        if coluna_norm in colunas_despesa:
            canonica = conta_canonica(desc, "despesa")
            if canonica and canonica not in encontradas_despesa:
                linha[canonica] = _para_float(valor)
                encontradas_despesa.add(canonica)

    # Garante presença das chaves esperadas (NaN se ausentes)
    for chave in CONTAS_RECEITA:
        linha.setdefault(chave, None)
    for chave in CONTAS_DESPESA:
        linha.setdefault(chave, None)

    return linha


def _para_float(valor) -> float | None:
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["ano", "bimestre"]).reset_index(drop=True)

    # Identificadores temporais
    df["data_ref"] = pd.to_datetime(
        df["ano"].astype(str) + "-" + (df["bimestre"] * 2).astype(str) + "-01",
        errors="coerce",
    )
    df["rotulo_periodo"] = df["ano"].astype(str) + "-B" + df["bimestre"].astype(str)

    # Indicadores principais
    df["poupanca_bruta"] = df["receitas_correntes"] - df["despesas_correntes"]
    df["poupanca_liquida_proxy"] = (
        df["receitas_correntes"] - df["transferencias_correntes"]
    ) - df["despesas_correntes"]
    df["dc_rc"] = df["despesas_correntes"] / df["receitas_correntes"]

    # Média móvel de 4 bimestres (~12 meses) da DC/RC
    df["dc_rc_12m"] = df["dc_rc"].rolling(window=4, min_periods=1).mean()

    # Status constitucional (faixa do art. 167-A) — pelo DC/RC do bimestre
    df["status_constitucional"] = df["dc_rc"].apply(
        lambda x: classificar_dc_rc(x) if pd.notna(x) else ""
    )

    # Composição de despesa (participação relativa)
    for chave in ["pessoal_encargos", "juros_encargos", "outras_despesas_correntes"]:
        df[f"part_{chave}"] = df[chave] / df["despesas_correntes"]

    # Crescimento YoY (mesmo bimestre, ano anterior)
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
    log.info(
        "último bimestre: %s | DC/RC=%.2f%% | status=%s | poupança bruta=R$ %.2f bi",
        ult["rotulo_periodo"],
        (ult["dc_rc"] or 0) * 100,
        ult["status_constitucional"],
        (ult["poupanca_bruta"] or 0) / 1e9,
    )


def main() -> int:
    df = consolidar()
    _resumo(df)
    return 0


if __name__ == "__main__":
    sys.exit(main())
