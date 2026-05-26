# Poupança Corrente — Estado de Santa Catarina

Painel público de transparência fiscal sobre a poupança corrente do Estado de Santa Catarina, com dados oficiais do Siconfi/STN e indicadores constitucionais derivados da EC 109/2021 (art. 167-A da CF).

> **Site publicado:** GitHub Pages deste repositório.
> **Atualização:** automática, mensal (dia 5, 09:00 UTC).

## O que o painel responde

- Receitas e despesas correntes do Estado, bimestre a bimestre.
- Poupança corrente bruta e indicador DC ÷ RC.
- Posição em relação aos gatilhos constitucionais (confortável / alerta / crítica).
- Crescimento ano-contra-ano e composição da despesa corrente.

Detalhes metodológicos em [docs/metodologia.md](docs/metodologia.md) e contexto legal em [docs/ec-109.md](docs/ec-109.md).

## Pipeline

```
Siconfi/STN  →  src/extract.py  →  data/raw/*.json
                                       ↓
                              src/transform.py
                                       ↓
                   data/processed/poupanca_sc.{csv,parquet}
                                       ↓
                          site/  (Chart.js + PapaParse)
                                       ↓
                              GitHub Pages
```

## Rodar localmente

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt

python -m src.extract --ano 2024     # teste rápido
python -m src.transform              # consolida
python -m http.server 8000 --directory site
# abra http://localhost:8000
```

Para a série completa (2015 → ano corrente), use `python -m src.extract` sem argumentos.

## Estrutura

```
.
├── src/
│   ├── config.py       # constantes (id_ente, contas, gatilhos)
│   ├── extract.py      # baixa JSONs com cache incremental e retry
│   └── transform.py    # consolida CSV + Parquet, calcula indicadores
├── site/               # painel HTML estático
├── data/
│   ├── raw/            # JSONs versionados (auditoria)
│   └── processed/      # CSV + Parquet
├── docs/               # metodologia e contexto legal
├── .github/workflows/
│   ├── atualizar-dados.yml   # cron mensal
│   └── publicar-pages.yml    # deploy do site
├── CLAUDE.md           # contexto fiscal para o assistente
├── requirements.txt
└── README.md
```

## Licença e uso
Dados são públicos (Siconfi/STN). Código aberto. Cite as fontes oficiais ao reutilizar análises.
