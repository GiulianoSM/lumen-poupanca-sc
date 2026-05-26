"""Extração de dados do RREO Anexo 01 — Estado de SC — via API Siconfi.

Faz download incremental dos JSONs de cada (ano, bimestre) e salva em
`data/raw/rreo_<ano>_<bimestre>.json`. Re-execuções não re-baixam arquivos
já presentes, salvo se `--forcar` for usado.

Uso:
    python -m src.extract                  # série completa
    python -m src.extract --ano 2024       # só 2024 (todos os bimestres)
    python -m src.extract --ano 2024 --bimestre 6
    python -m src.extract --forcar         # ignora cache
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import (
    ANEXO,
    ANO_INICIAL,
    BASE_URL,
    COD_IBGE_SC,
    PERIODOS,
    TIPO_DEMONSTRATIVO,
)

# Diretório raiz do projeto (assume execução com `python -m src.extract`).
RAIZ = Path(__file__).resolve().parents[1]
DIR_RAW = RAIZ / "data" / "raw"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("extract")


class BimestreNaoPublicado(Exception):
    """API retornou 404 — bimestre ainda não foi publicado pelo ente."""


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1.5, min=2, max=15),
    retry=retry_if_exception_type((requests.RequestException,)),
)
def _baixar(ano: int, bimestre: int) -> dict:
    """Faz a chamada HTTP à API Siconfi com retry exponencial."""
    params = {
        "an_exercicio": ano,
        "nr_periodo": bimestre,
        "co_tipo_demonstrativo": TIPO_DEMONSTRATIVO,
        "no_anexo": ANEXO,
        "id_ente": COD_IBGE_SC,
    }
    resp = requests.get(BASE_URL, params=params, timeout=60)
    if resp.status_code == 404:
        raise BimestreNaoPublicado(f"{ano}/{bimestre}")
    resp.raise_for_status()
    return resp.json()


def caminho_json(ano: int, bimestre: int) -> Path:
    return DIR_RAW / f"rreo_{ano}_{bimestre}.json"


def extrair(ano: int, bimestre: int, forcar: bool = False) -> Path | None:
    """Baixa um (ano, bimestre) e salva em data/raw. Retorna o path ou None."""
    destino = caminho_json(ano, bimestre)
    if destino.exists() and not forcar:
        log.info("cache  %d/%d → %s", ano, bimestre, destino.name)
        return destino

    try:
        payload = _baixar(ano, bimestre)
    except BimestreNaoPublicado:
        log.warning("vazio  %d/%d (não publicado ainda)", ano, bimestre)
        return None
    except requests.RequestException as e:
        log.error("falha  %d/%d → %s", ano, bimestre, e)
        return None

    itens = payload.get("items", [])
    if not itens:
        log.warning("vazio  %d/%d (sem 'items' no payload)", ano, bimestre)
        return None

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("salvo  %d/%d → %s (%d itens)", ano, bimestre, destino.name, len(itens))
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extrai RREO Anexo 01 de SC.")
    parser.add_argument("--ano", type=int, help="Ano específico (default: todos)")
    parser.add_argument("--bimestre", type=int, help="Bimestre específico 1-6")
    parser.add_argument("--forcar", action="store_true", help="Ignora cache")
    args = parser.parse_args(argv)

    ano_atual = dt.date.today().year
    anos = [args.ano] if args.ano else list(range(ANO_INICIAL, ano_atual + 1))
    bimestres = [args.bimestre] if args.bimestre else PERIODOS

    total_ok = 0
    total_pulado = 0
    falhas_consecutivas_ano = 0
    ultimo_ano_falhado = None

    for ano in anos:
        ok_ano = 0
        for bim in bimestres:
            if extrair(ano, bim, forcar=args.forcar):
                total_ok += 1
                ok_ano += 1
            else:
                total_pulado += 1

        # Heurística de circuit-breaker — se um ano inteiro falhar, pode ser
        # mudança de estrutura na API. Aborto após 2 anos consecutivos vazios.
        if ok_ano == 0:
            if ultimo_ano_falhado == ano - 1:
                falhas_consecutivas_ano += 1
            else:
                falhas_consecutivas_ano = 1
            ultimo_ano_falhado = ano
            if falhas_consecutivas_ano >= 2:
                log.error(
                    "dois anos seguidos sem dados (%d, %d) — interrompendo.",
                    ano - 1, ano,
                )
                return 2
        else:
            falhas_consecutivas_ano = 0

    log.info("concluído: %d salvos / %d pulados", total_ok, total_pulado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
