/* Painel Poupança Corrente SC — front-end estático.
 * Lê o CSV gerado pelo pipeline e monta KPIs, gráficos e tabela.
 *
 * O caminho do CSV é relativo ao site/. No workflow de deploy,
 * o CSV é copiado para o lado do index.html — o script reescreve
 * a referência se o arquivo "./data/processed/poupanca_sc.csv"
 * existir. Em desenvolvimento local, o pipeline grava em
 * "../data/processed/", de modo que o site servido em `site/` ainda
 * consegue ler subindo um nível.
 */
(function () {
  "use strict";

  // --- Configuração -----------------------------------------------------
  const CAMINHOS_CSV = [
    "./data/processed/poupanca_sc.csv",   // após deploy (pasta empacotada)
    "../data/processed/poupanca_sc.csv",  // dev local servindo site/
  ];

  // Faixas constitucionais (art. 167-A da CF — EC 109/2021)
  const GATILHO_ALERTA = 0.85;
  const GATILHO_CRITICO = 0.95;

  // Cores (espelham styles.css)
  const COR_VERDE = "#16a34a";
  const COR_AMARELO = "#d97706";
  const COR_VERMELHO = "#dc2626";
  const COR_AZUL = "#0b2545";
  const COR_AZUL_ACENTO = "#2563eb";

  const fmtBRL = (v) =>
    v == null || isNaN(v)
      ? "—"
      : new Intl.NumberFormat("pt-BR", {
          style: "currency",
          currency: "BRL",
          maximumFractionDigits: 0,
        }).format(v);

  const fmtBRLcurto = (v) => {
    if (v == null || isNaN(v)) return "—";
    const abs = Math.abs(v);
    if (abs >= 1e9) return `R$ ${(v / 1e9).toFixed(1)} bi`;
    if (abs >= 1e6) return `R$ ${(v / 1e6).toFixed(1)} mi`;
    return fmtBRL(v);
  };

  const fmtPct = (v, casas = 1) =>
    v == null || isNaN(v) ? "—" : `${(v * 100).toFixed(casas)}%`;

  const classeStatus = (status) => {
    if (status === "CONFORTAVEL") return "verde";
    if (status === "ALERTA") return "amarelo";
    if (status === "CRITICO") return "vermelho";
    return "neutro";
  };

  // --- Inicialização ----------------------------------------------------
  document.addEventListener("DOMContentLoaded", () => {
    montarAbas();
    carregarCSV()
      .then((linhas) => renderizar(linhas))
      .catch((err) => {
        console.error(err);
        const banner = document.getElementById("banner-status");
        document.getElementById("banner-titulo").textContent =
          "Não foi possível carregar os dados.";
        document.getElementById("banner-detalhe").textContent =
          err.message || "Erro desconhecido.";
        banner.classList.remove("banner--neutro");
        banner.classList.add("banner--vermelho");
      });
  });

  function montarAbas() {
    const abas = document.querySelectorAll(".aba");
    abas.forEach((btn) => {
      btn.addEventListener("click", () => {
        abas.forEach((b) => b.setAttribute("aria-selected", "false"));
        btn.setAttribute("aria-selected", "true");
        document
          .querySelectorAll(".painel")
          .forEach((p) => p.classList.add("oculto"));
        const alvo = document.getElementById(`painel-${btn.dataset.aba}`);
        if (alvo) alvo.classList.remove("oculto");
      });
    });
  }

  async function carregarCSV() {
    let ultimoErro = null;
    for (const caminho of CAMINHOS_CSV) {
      try {
        const resposta = await fetch(caminho, { cache: "no-store" });
        if (!resposta.ok) {
          ultimoErro = new Error(`HTTP ${resposta.status} em ${caminho}`);
          continue;
        }
        const texto = await resposta.text();
        return new Promise((resolve, reject) => {
          Papa.parse(texto, {
            header: true,
            dynamicTyping: true,
            skipEmptyLines: true,
            complete: (r) => resolve(r.data),
            error: reject,
          });
        });
      } catch (e) {
        ultimoErro = e;
      }
    }
    throw ultimoErro || new Error("CSV não encontrado.");
  }

  // --- Renderização principal -------------------------------------------
  function renderizar(linhas) {
    if (!linhas || linhas.length === 0) {
      throw new Error("Conjunto de dados vazio.");
    }
    // Garante ordenação cronológica
    linhas.sort((a, b) => {
      if (a.ano !== b.ano) return a.ano - b.ano;
      return a.bimestre - b.bimestre;
    });

    const ultima = linhas[linhas.length - 1];
    const anterior = linhas.length >= 5 ? linhas[linhas.length - 5] : null;

    atualizarBanner(ultima);
    atualizarKPIs(ultima, anterior);
    renderizarHistorico(linhas);
    renderizarRazao(linhas);
    renderizarComposicao(ultima);
    renderizarYoY(linhas);
    renderizarTabela(linhas);

    const ultAtual = document.getElementById("ultima-atualizacao");
    if (ultAtual) ultAtual.textContent = ultima.rotulo_periodo || "—";
  }

  function atualizarBanner(ultima) {
    const banner = document.getElementById("banner-status");
    const titulo = document.getElementById("banner-titulo");
    const detalhe = document.getElementById("banner-detalhe");
    banner.classList.remove(
      "banner--neutro", "banner--verde", "banner--amarelo", "banner--vermelho"
    );
    const cls = classeStatus(ultima.status_constitucional);
    banner.classList.add(`banner--${cls}`);

    const mensagens = {
      CONFORTAVEL: "Zona confortável (art. 167-A da CF)",
      ALERTA: "Zona de alerta — DC ÷ RC entre 85% e 95%",
      CRITICO: "Zona crítica — DC ÷ RC ≥ 95%",
    };
    titulo.textContent =
      mensagens[ultima.status_constitucional] || "Status indisponível";
    detalhe.textContent = `Referência: ${ultima.rotulo_periodo} · DC÷RC = ${fmtPct(
      ultima.dc_rc, 2
    )}`;
  }

  function atualizarKPIs(ultima, anterior) {
    document.getElementById("kpi-rc").textContent = fmtBRLcurto(ultima.receitas_correntes);
    document.getElementById("kpi-dc").textContent = fmtBRLcurto(ultima.despesas_correntes);
    document.getElementById("kpi-poup-valor").textContent = fmtBRLcurto(ultima.poupanca_bruta);
    document.getElementById("kpi-razao-valor").textContent = fmtPct(ultima.dc_rc, 1);

    // YoY no rodapé (compara com bimestre equivalente do ano anterior)
    const yoyRC = ultima.yoy_receitas_correntes;
    const yoyDC = ultima.yoy_despesas_correntes;
    document.getElementById("kpi-rc-yoy").textContent =
      yoyRC != null ? `YoY: ${fmtPct(yoyRC, 1)}` : "—";
    document.getElementById("kpi-dc-yoy").textContent =
      yoyDC != null ? `YoY: ${fmtPct(yoyDC, 1)}` : "—";

    const rodapePoup = ultima.poupanca_bruta >= 0
      ? "Receitas correntes cobrem despesas correntes."
      : "Despesas correntes excedem receitas correntes.";
    document.getElementById("kpi-poup-rodape").textContent = rodapePoup;

    // Pinta KPI de Poupança e Razão conforme status
    const kpiPoup = document.getElementById("kpi-poup");
    kpiPoup.classList.remove("kpi--verde", "kpi--amarelo", "kpi--vermelho");
    kpiPoup.classList.add(ultima.poupanca_bruta >= 0 ? "kpi--verde" : "kpi--vermelho");

    const kpiRazao = document.getElementById("kpi-razao");
    kpiRazao.classList.remove("kpi--verde", "kpi--amarelo", "kpi--vermelho");
    kpiRazao.classList.add(`kpi--${classeStatus(ultima.status_constitucional)}`);
  }

  // --- Gráficos ---------------------------------------------------------
  let cacheCharts = {};

  function destruirGrafico(id) {
    if (cacheCharts[id]) { cacheCharts[id].destroy(); delete cacheCharts[id]; }
  }

  function renderizarHistorico(linhas) {
    destruirGrafico("g-historico");
    const ctx = document.getElementById("g-historico").getContext("2d");
    const labels = linhas.map((l) => l.rotulo_periodo);

    cacheCharts["g-historico"] = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Receita Corrente",
            data: linhas.map((l) => l.receitas_correntes),
            borderColor: COR_AZUL_ACENTO,
            backgroundColor: "rgba(37, 99, 235, 0.08)",
            fill: true,
            tension: 0.25,
          },
          {
            label: "Despesa Corrente",
            data: linhas.map((l) => l.despesas_correntes),
            borderColor: COR_VERMELHO,
            backgroundColor: "rgba(220, 38, 38, 0.06)",
            fill: false,
            tension: 0.25,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${fmtBRL(ctx.parsed.y)}`,
            },
          },
        },
        scales: {
          y: {
            ticks: { callback: (v) => fmtBRLcurto(v) },
            grid: { color: "#eef0f4" },
          },
          x: { grid: { display: false } },
        },
      },
    });
  }

  // Plugin que pinta as bandas das zonas constitucionais no fundo
  const pluginBandasZonas = {
    id: "bandasZonas",
    beforeDraw(chart, _args, opts) {
      const { ctx, chartArea, scales } = chart;
      const escala = scales.y;
      if (!escala) return;
      const yAlerta = escala.getPixelForValue(GATILHO_ALERTA);
      const yCritico = escala.getPixelForValue(GATILHO_CRITICO);
      const yTopo = chartArea.top;
      const yBase = chartArea.bottom;
      const xEsq = chartArea.left;
      const xLarg = chartArea.right - chartArea.left;

      ctx.save();
      // Verde até 85%
      ctx.fillStyle = "rgba(22, 163, 74, 0.10)";
      ctx.fillRect(xEsq, Math.max(yAlerta, yTopo), xLarg, yBase - Math.max(yAlerta, yTopo));
      // Amarelo 85-95%
      ctx.fillStyle = "rgba(217, 119, 6, 0.14)";
      const yAmareloTopo = Math.max(yCritico, yTopo);
      const yAmareloBase = Math.min(yAlerta, yBase);
      if (yAmareloBase > yAmareloTopo)
        ctx.fillRect(xEsq, yAmareloTopo, xLarg, yAmareloBase - yAmareloTopo);
      // Vermelho acima de 95%
      ctx.fillStyle = "rgba(220, 38, 38, 0.14)";
      ctx.fillRect(xEsq, yTopo, xLarg, Math.min(yCritico, yBase) - yTopo);
      ctx.restore();
    },
  };

  function renderizarRazao(linhas) {
    destruirGrafico("g-razao");
    const ctx = document.getElementById("g-razao").getContext("2d");
    const labels = linhas.map((l) => l.rotulo_periodo);

    cacheCharts["g-razao"] = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "DC ÷ RC (bimestre)",
            data: linhas.map((l) => l.dc_rc),
            borderColor: "#94a3b8",
            borderDash: [4, 4],
            pointRadius: 0,
            tension: 0.25,
            fill: false,
          },
          {
            label: "DC ÷ RC (média móvel 12m)",
            data: linhas.map((l) => l.dc_rc_12m),
            borderColor: COR_AZUL,
            borderWidth: 2.5,
            pointRadius: 2,
            tension: 0.25,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: { label: (c) => `${c.dataset.label}: ${fmtPct(c.parsed.y, 2)}` },
          },
        },
        scales: {
          y: {
            min: Math.max(0, Math.min(...linhas.map((l) => l.dc_rc).filter((v) => v != null && !isNaN(v))) - 0.05),
            max: 1.05,
            ticks: { callback: (v) => fmtPct(v, 0) },
            grid: { color: "#eef0f4" },
          },
          x: { grid: { display: false } },
        },
      },
      plugins: [pluginBandasZonas],
    });
  }

  function renderizarComposicao(ultima) {
    destruirGrafico("g-composicao");
    const ctx = document.getElementById("g-composicao").getContext("2d");
    const partes = [
      { rotulo: "Pessoal e Encargos", valor: ultima.pessoal_encargos, cor: "#0b2545" },
      { rotulo: "Juros e Encargos da Dívida", valor: ultima.juros_encargos, cor: "#d97706" },
      { rotulo: "Outras Despesas Correntes", valor: ultima.outras_despesas_correntes, cor: "#2563eb" },
    ].filter((p) => p.valor != null && !isNaN(p.valor) && p.valor > 0);

    cacheCharts["g-composicao"] = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: partes.map((p) => p.rotulo),
        datasets: [{ data: partes.map((p) => p.valor), backgroundColor: partes.map((p) => p.cor) }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: {
              label: (c) => {
                const total = c.dataset.data.reduce((a, b) => a + b, 0);
                const pct = total ? (c.parsed / total) : 0;
                return `${c.label}: ${fmtBRL(c.parsed)} (${fmtPct(pct, 1)})`;
              },
            },
          },
        },
      },
    });
  }

  function renderizarYoY(linhas) {
    destruirGrafico("g-yoy");
    const ctx = document.getElementById("g-yoy").getContext("2d");
    const validas = linhas.filter(
      (l) => l.yoy_receitas_correntes != null && !isNaN(l.yoy_receitas_correntes)
    );
    const labels = validas.map((l) => l.rotulo_periodo);

    cacheCharts["g-yoy"] = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Receita Corrente (YoY)",
            data: validas.map((l) => l.yoy_receitas_correntes),
            backgroundColor: COR_AZUL_ACENTO,
          },
          {
            label: "Despesa Corrente (YoY)",
            data: validas.map((l) => l.yoy_despesas_correntes),
            backgroundColor: COR_VERMELHO,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: { label: (c) => `${c.dataset.label}: ${fmtPct(c.parsed.y, 1)}` },
          },
        },
        scales: {
          y: {
            ticks: { callback: (v) => fmtPct(v, 0) },
            grid: { color: "#eef0f4" },
          },
          x: { grid: { display: false } },
        },
      },
    });
  }

  function renderizarTabela(linhas) {
    const tbody = document.querySelector("#tabela-historico tbody");
    tbody.innerHTML = "";
    // Em ordem reversa (mais recente primeiro)
    [...linhas].reverse().forEach((l) => {
      const cls = classeStatus(l.status_constitucional);
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${l.rotulo_periodo ?? "—"}</td>
        <td>${fmtBRL(l.receitas_correntes)}</td>
        <td>${fmtBRL(l.despesas_correntes)}</td>
        <td>${fmtBRL(l.poupanca_bruta)}</td>
        <td>${fmtPct(l.dc_rc, 2)}</td>
        <td><span class="status-pill status-pill--${cls}">${l.status_constitucional || "—"}</span></td>
      `;
      tbody.appendChild(tr);
    });
  }
})();
