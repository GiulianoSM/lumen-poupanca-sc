"""Constantes do pipeline.

Centraliza identificadores do ente, da API Siconfi e as descrições
normalizadas das contas do RREO Anexo 01 (Balanço Orçamentário).

Referências:
- MDF/STN — Manual de Demonstrativos Fiscais (RREO Anexo 01)
- API Siconfi: https://apidatalake.tesouro.gov.br/docs/siconfi/
- Art. 167-A da Constituição Federal (EC 109/2021)
"""
from __future__ import annotations

import unicodedata

# --- Ente federativo ---------------------------------------------------------
COD_IBGE_SC = 42           # id_ente do Estado de Santa Catarina
UF_SC = "SC"

# --- API Siconfi -------------------------------------------------------------
BASE_URL = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo"
TIPO_DEMONSTRATIVO = "RREO"
ANEXO = "RREO-Anexo 01"     # Balanço Orçamentário

# --- Janela histórica --------------------------------------------------------
ANO_INICIAL = 2015          # MDF reorganizado nesta janela; antes a estrutura difere
PERIODOS = [1, 2, 3, 4, 5, 6]  # bimestres

# --- Colunas do RREO Anexo 01 ------------------------------------------------
# Receitas: acumulado realizado no exercício
COLUNA_RECEITA_ACUMULADA = "Até o Bimestre (c)"
# Despesas: usamos EMPENHADAS para alinhar com a leitura da SEF/SC para
# o art. 167-A (vide docs/metodologia.md). Coletamos também as LIQUIDADAS
# para auditoria/comparação.
COLUNA_DESPESA_EMPENHADA = "DESPESAS EMPENHADAS ATÉ O BIMESTRE (f)"
COLUNA_DESPESA_LIQUIDADA = "DESPESAS LIQUIDADAS ATÉ O BIMESTRE (h)"

# --- Mapeamento de contas ----------------------------------------------------
# Chave = nome canônico (snake_case) usado nos relatórios.
# Valor = descrição da conta no RREO, normalizada (sem acento, upper, stripped).
#
# IMPORTANTE: o RREO Anexo 01 traz cada conta corrente em DUAS instâncias:
#   1) na seção "RECEITAS (EXCETO INTRA-ORÇAMENTÁRIAS) (I)" / "DESPESAS (...) (VIII)"
#   2) na seção "RECEITAS (INTRA-ORÇAMENTÁRIAS) (II)" / "DESPESAS (...) (IX)"
# Para alinhar com a leitura da SEF/SC (e com a apuração correta do art. 167-A,
# que opera sobre o agregado do ente), SOMAMOS as duas linhas.
# O distintivo entre elas é o `cod_conta`: a versão intra tem sufixo "Intra"
# (ex.: `ReceitasCorrentes` vs `ReceitasCorrentesIntra`).
#
# Observação sobre transferências: o RREO Anexo 01 não detalha "Transferências
# Constitucionais e Legais a Municípios" — este recorte vive no RREO Anexo 03
# (Demonstrativo da RCL), fora desta v1.
CONTAS_RECEITA = {
    "receitas_correntes": "RECEITAS CORRENTES",
    "transferencias_correntes": "TRANSFERÊNCIAS CORRENTES",
}

CONTAS_DESPESA = {
    "despesas_correntes": "DESPESAS CORRENTES",
    "pessoal_encargos": "PESSOAL E ENCARGOS SOCIAIS",
    "juros_encargos": "JUROS E ENCARGOS DA DÍVIDA",
    "outras_despesas_correntes": "OUTRAS DESPESAS CORRENTES",
}


def normalizar(texto: str) -> str:
    """Normaliza descrição de conta para comparação resistente a variações.

    Remove acentos, espaços extras, e converte para caixa alta. Tolerante a
    pequenas variações de pontuação entre edições anuais do MDF.
    """
    if texto is None:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sem_acento.upper().split())


# Índices normalizados para lookup (descrição_normalizada → nome_canonico)
_INDICE_RECEITA = {normalizar(v): k for k, v in CONTAS_RECEITA.items()}
_INDICE_DESPESA = {normalizar(v): k for k, v in CONTAS_DESPESA.items()}


def conta_canonica(descricao: str, tipo: str) -> str | None:
    """Devolve o nome canônico para a conta, ou None se não mapeada.

    `tipo` ∈ {"receita", "despesa"}.
    """
    chave = normalizar(descricao)
    indice = _INDICE_RECEITA if tipo == "receita" else _INDICE_DESPESA
    return indice.get(chave)


# --- Gatilhos do art. 167-A da CF (EC 109/2021) -----------------------------
# A EC 109/2021 introduziu, no art. 167-A da Constituição Federal, mecanismos
# de ajuste fiscal escalonado conforme o indicador DESPESA CORRENTE / RECEITA
# CORRENTE (DC/RC). Os limiares aqui replicam as faixas de literatura fiscal:
#   < 85%   → confortável  (verde)
#   85-95%  → alerta       (amarelo)
#   ≥ 95%   → crítico      (vermelho)
GATILHO_ALERTA = 0.85
GATILHO_CRITICO = 0.95

STATUS_CONFORTAVEL = "CONFORTAVEL"
STATUS_ALERTA = "ALERTA"
STATUS_CRITICO = "CRITICO"


def classificar_dc_rc(razao: float) -> str:
    """Classifica a razão Despesa Corrente / Receita Corrente."""
    if razao is None:
        return ""
    if razao < GATILHO_ALERTA:
        return STATUS_CONFORTAVEL
    if razao < GATILHO_CRITICO:
        return STATUS_ALERTA
    return STATUS_CRITICO
