// DataPilot — Full Analytics Workspace Client Application

let activeTab = "dashboard";
let currentDataset = null;
let conversationHistory = [];
let savedInsights = JSON.parse(localStorage.getItem("datapilot_saved_insights") || "[]");
let queryHistory = JSON.parse(localStorage.getItem("datapilot_history") || "[]");
let activeCharts = {};
let latestQueryResult = null;

// Initialization
document.addEventListener("DOMContentLoaded", () => {
  initTopFileUploader();
  loadInitialDataset();
  renderSavedInsightsCount();
  setupSettingsUI();
});

// Tab Navigation
function navigateTab(tabName) {
  activeTab = tabName;
  const tabs = ["dashboard", "dataset", "copilot", "visualizations", "eda", "sql", "reports", "history", "settings"];

  tabs.forEach(t => {
    const view = document.getElementById(`tab-${t}-view`);
    const btn = document.getElementById(`nav-${t}`);
    if (t === tabName) {
      if (view) view.classList.remove("hidden");
      if (btn) btn.classList.add("active");
    } else {
      if (view) view.classList.add("hidden");
      if (btn) btn.classList.remove("active");
    }
  });

  const titles = {
    dashboard: "Dashboard Overview",
    dataset: "Dataset Profile & Schema",
    copilot: "Sense AI",
    visualizations: "Visualizations & Chart Studio",
    eda: "Automated Exploratory Data Analysis (EDA)",
    sql: "Direct DuckDB SQL Studio",
    reports: "Saved Insights & Executive Reports",
    history: "Session Query History",
    settings: "Engine & LLM Configuration"
  };
  document.getElementById("topbarTitle").textContent = titles[tabName] || "Analytics Workspace";

  if (tabName === "visualizations") fetchVisualizationsGallery();
  if (tabName === "eda") fetchAutoEDA();
  if (tabName === "reports") renderSavedInsightsGrid();
  if (tabName === "history") renderHistoryTimeline();
}

// ---------------------------------------------------------
// Dataset Ingestion & Loading
// ---------------------------------------------------------
function initTopFileUploader() {
  const input = document.getElementById("topFileInput");
  input.addEventListener("change", () => {
    if (input.files.length > 0) {
      uploadFile(input.files[0]);
    }
  });
}

async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/upload", { method: "POST", body: formData });
    const data = await res.json();
    if (res.ok) {
      onDatasetLoaded(data);
      navigateTab("dashboard");
    } else {
      alert("Upload failed: " + (data.detail || "Error loading file"));
    }
  } catch (err) {
    alert("Upload error: " + err.message);
  }
}

async function loadSampleData() {
  try {
    const res = await fetch("/api/load-sample", { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      onDatasetLoaded(data);
      navigateTab("dashboard");
    } else {
      alert("Sample load failed: " + (data.detail || "Error loading sample"));
    }
  } catch (err) {
    alert("Error loading sample: " + err.message);
  }
}

async function resetDataset() {
  try {
    const res = await fetch("/api/reset-dataset", { method: "POST" });
    currentDataset = null;
    showEmptyDatasetState();
    alert("Dataset cleared. You can now upload a fresh file.");
  } catch (err) {
    alert("Reset failed: " + err.message);
  }
}

async function loadInitialDataset() {
  try {
    const res = await fetch("/api/dataset-info");
    const data = await res.json();
    if (data.loaded) {
      onDatasetLoaded(data);
    } else {
      showEmptyDatasetState();
    }
  } catch (e) {
    showEmptyDatasetState();
  }
}

function showEmptyDatasetState() {
  document.getElementById("sidebarDatasetName").textContent = "No dataset loaded";
  document.getElementById("sidebarDatasetStats").textContent = "Upload a CSV or Excel file";

  const emptyHtml = `
    <div class="workspace-card p-10 text-center border-dashed border-2 border-slate-300 bg-white">
      <div class="w-16 h-16 rounded-2xl bg-coral-50 border border-coral-200 flex items-center justify-center mx-auto mb-4 text-coral-600">
        <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg>
      </div>
      <h3 class="font-syne font-bold text-xl text-slate-900 mb-1">Upload a Dataset to Begin</h3>
      <p class="text-sm text-slate-500 max-w-md mx-auto mb-6">Drop your CSV, Excel, or Parquet file here for in-depth DuckDB analytics and Sense AI guidance.</p>
      <div class="flex justify-center gap-3">
        <button onclick="document.getElementById('topFileInput').click()" class="coral-gradient text-white text-xs font-bold px-5 py-2.5 rounded-xl shadow hover:opacity-95 transition">
          📂 Browse File
        </button>
        <button onclick="loadSampleData()" class="bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold px-5 py-2.5 rounded-xl transition border border-slate-200">
          ⚡ Or Load Sample Sales Data
        </button>
      </div>
    </div>
  `;

  const kpisGrid = document.getElementById("dashboardKpisGrid");
  if (kpisGrid) {
    kpisGrid.innerHTML = `<div class="col-span-1 sm:col-span-2 lg:col-span-4">${emptyHtml}</div>`;
  }
}

function onDatasetLoaded(data) {
  currentDataset = data;
  
  // Topbar and sidebar updates
  document.getElementById("sidebarDatasetName").textContent = data.filename;
  document.getElementById("sidebarDatasetStats").textContent = `${data.row_count.toLocaleString()} rows · ${data.column_count} cols (${data.file_size_mb} MB)`;

  // Fetch sub-data
  fetchDashboardKPIs();
  fetchSuggestedQuestions();
  renderDatasetOverviewTab(data);
}

// ---------------------------------------------------------
// Dashboard View
// ---------------------------------------------------------
async function fetchDashboardKPIs() {
  try {
    const res = await fetch("/api/dashboard-kpis");
    const data = await res.json();

    const grid = document.getElementById("dashboardKpisGrid");
    if (data.kpis && data.kpis.length > 0) {
      grid.innerHTML = data.kpis.map(k => `
        <div class="workspace-card p-5">
          <div class="text-xs font-mono font-semibold text-slate-500 uppercase tracking-wider mb-1">${k.label}</div>
          <div class="text-2xl font-syne font-extrabold text-slate-900">${k.value}</div>
          <div class="text-xs font-mono mt-1.5 flex items-center space-x-1 ${k.positive ? 'text-emerald-600' : 'text-slate-500'}">
            <span>${k.change}</span>
          </div>
        </div>
      `).join("");
    }

    if (data.overview_chart) {
      document.getElementById("dashboardOverviewTitle").textContent = data.overview_chart.title;
      renderChartCanvas("dashboardOverviewChart", "bar", data.overview_chart.labels, data.overview_chart.values, data.overview_chart.y_label);
    }
  } catch (e) {}
}

// ---------------------------------------------------------
// Dataset Overview & Schema View
// ---------------------------------------------------------
function renderDatasetOverviewTab(data) {
  const p = data.profile || {};
  
  // 6 Metric Cards
  const statsGrid = document.getElementById("datasetStatsGrid");
  statsGrid.innerHTML = `
    <div class="workspace-card p-4 text-center">
      <div class="text-xl font-syne font-bold text-slate-900">${(p.total_rows || 0).toLocaleString()}</div>
      <div class="text-[11px] font-mono text-slate-500 mt-1 uppercase font-semibold">Total Rows</div>
    </div>
    <div class="workspace-card p-4 text-center">
      <div class="text-xl font-syne font-bold text-slate-900">${p.total_cols || 0}</div>
      <div class="text-[11px] font-mono text-slate-500 mt-1 uppercase font-semibold">Columns</div>
    </div>
    <div class="workspace-card p-4 text-center">
      <div class="text-xl font-syne font-bold text-slate-900">${p.file_size_mb || 0.5} MB</div>
      <div class="text-[11px] font-mono text-slate-500 mt-1 uppercase font-semibold">File Size</div>
    </div>
    <div class="workspace-card p-4 text-center">
      <div class="text-xl font-syne font-bold ${p.duplicate_rows > 0 ? 'text-rose-600' : 'text-emerald-600'}">${p.duplicate_rows || 0}</div>
      <div class="text-[11px] font-mono text-slate-500 mt-1 uppercase font-semibold">Duplicates</div>
    </div>
    <div class="workspace-card p-4 text-center">
      <div class="text-xl font-syne font-bold text-slate-900">${p.numeric_count || 0}</div>
      <div class="text-[11px] font-mono text-slate-500 mt-1 uppercase font-semibold">Numeric Cols</div>
    </div>
    <div class="workspace-card p-4 text-center">
      <div class="text-xl font-syne font-bold text-slate-900">${p.categorical_count || 0}</div>
      <div class="text-[11px] font-mono text-slate-500 mt-1 uppercase font-semibold">Categorical</div>
    </div>
  `;

  // Quality Alert text
  const qualityAlert = document.getElementById("qualityAlertText");
  if (p.quality_issues && p.quality_issues.length > 0) {
    qualityAlert.textContent = p.quality_issues.join(" · ");
  }

  // Schema Table
  const tbody = document.getElementById("schemaTableBody");
  if (p.columns && p.columns.length > 0) {
    tbody.innerHTML = p.columns.map(c => `
      <tr class="hover:bg-slate-50 schema-row" data-col="${c.column_name.toLowerCase()}">
        <td class="p-3 font-bold text-slate-900">${c.column_name}</td>
        <td class="p-3"><span class="bg-slate-100 text-coral-600 font-bold px-2 py-0.5 rounded text-[10px]">${c.type}</span></td>
        <td class="p-3 ${c.null_pct > 0 ? 'text-rose-600 font-bold' : 'text-slate-500'}">${c.null_pct}% (${c.null_count})</td>
        <td class="p-3 text-slate-600">${c.distinct_count.toLocaleString()}</td>
        <td class="p-3 text-slate-500 truncate max-w-xs text-[12px]">${c.sample_values}</td>
      </tr>
    `).join("");
  }

  // Preview Raw Table
  if (data.preview && data.preview.length > 0) {
    const cols = Object.keys(data.preview[0]);
    document.getElementById("previewTableHead").innerHTML = `<tr>${cols.map(c => `<th class="p-3 uppercase text-[11px] font-semibold">${c}</th>`).join("")}</tr>`;
    document.getElementById("previewTableBody").innerHTML = data.preview.map(r => `
      <tr class="hover:bg-slate-50">${cols.map(c => `<td class="p-3 text-slate-700">${r[c] !== null ? r[c] : '-'}</td>`).join("")}</tr>
    `).join("");
  }
}

function filterSchemaTable() {
  const term = document.getElementById("schemaSearchInput").value.toLowerCase();
  document.querySelectorAll(".schema-row").forEach(row => {
    row.style.display = row.getAttribute("data-col").includes(term) ? "" : "none";
  });
}

// ---------------------------------------------------------
// Suggested Questions
// ---------------------------------------------------------
async function fetchSuggestedQuestions() {
  try {
    const res = await fetch("/api/suggest-questions");
    const data = await res.json();
    const suggestions = data.suggestions || [];

    // Dashboard chips
    const dBox = document.getElementById("dashboardSuggestedQuestions");
    if (dBox && suggestions.length > 0) {
      dBox.innerHTML = suggestions.map(q => `
        <button onclick="askCopilotQuestion('${q.replace(/'/g, "\\'")}')" class="w-full text-left bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-700 text-xs font-mono p-2.5 rounded-xl transition truncate">
          👉 ${q}
        </button>
      `).join("");
    }

    // Copilot quick chips
    const cBox = document.getElementById("copilotQuickChips");
    const welcomeBox = document.getElementById("copilotWelcomeSuggestions");
    if (cBox && suggestions.length > 0) {
      const chipHtml = suggestions.map(q => `
        <button onclick="askCopilotQuestion('${q.replace(/'/g, "\\'")}')" class="bg-slate-100 hover:bg-coral-50 hover:text-coral-600 border border-slate-200 text-slate-700 px-3 py-1 rounded-lg transition truncate max-w-xs">
          ${q}
        </button>
      `).join("");
      cBox.innerHTML = `<span class="text-slate-400">Suggestions:</span> ` + chipHtml;
      if (welcomeBox) welcomeBox.innerHTML = chipHtml;
    }
  } catch (e) {}
}

function askCopilotQuestion(question) {
  navigateTab("copilot");
  document.getElementById("copilotQuestionInput").value = question;
  runCopilotQuery();
}

// ---------------------------------------------------------
// AI Copilot Multi-Agent Analysis
// ---------------------------------------------------------
async function runCopilotQuery() {
  const input = document.getElementById("copilotQuestionInput");
  const question = input.value.trim();
  if (!question) return;

  const submitBtn = document.getElementById("copilotSubmitBtn");
  const submitText = document.getElementById("copilotSubmitText");
  const stepTracker = document.getElementById("copilotStepTracker");
  const timerElem = document.getElementById("trackerTimer");

  // UI state
  submitBtn.disabled = true;
  submitText.textContent = "RUNNING...";
  stepTracker.classList.remove("hidden");
  document.getElementById("emptyCopilotState")?.remove();

  let startTime = Date.now();
  const timer = setInterval(() => {
    timerElem.textContent = ((Date.now() - startTime) / 1000).toFixed(1) + "s";
  }, 100);

  // Animate step pills
  const p1 = document.getElementById("p-step-1");
  const p2 = document.getElementById("p-step-2");
  const p3 = document.getElementById("p-step-3");
  const p4 = document.getElementById("p-step-4");

  p1.className = "bg-coral-100 border border-coral-400 text-coral-800 p-2 rounded-lg font-bold animate-pulse";
  setTimeout(() => p2.className = "bg-coral-100 border border-coral-400 text-coral-800 p-2 rounded-lg font-bold animate-pulse", 600);
  setTimeout(() => p3.className = "bg-coral-100 border border-coral-400 text-coral-800 p-2 rounded-lg font-bold animate-pulse", 1200);
  setTimeout(() => p4.className = "bg-coral-100 border border-coral-400 text-coral-800 p-2 rounded-lg font-bold animate-pulse", 1800);

  const provider = localStorage.getItem("datapilot_provider") || "Ollama (Local)";
  const model_name = localStorage.getItem("datapilot_model") || "qwen2.5-coder:14b";
  const api_key = localStorage.getItem("datapilot_apikey") || "";

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        provider,
        model_name,
        api_key,
        conversation_history: conversationHistory
      })
    });

    clearInterval(timer);
    const result = await res.json();

    if (!res.ok) {
      alert("Analysis failed: " + (result.detail || "Unknown error"));
      return;
    }

    // Save to conversation turn
    conversationHistory.push({
      question: result.question,
      sql: result.sql,
      summary: result.summary
    });

    // Save to history
    saveToQueryHistory(result);

    // Render structured card into conversation thread
    appendAnalysisCard(result);
    input.value = "";

  } catch (err) {
    clearInterval(timer);
    alert("Connection Error: " + err.message);
  } finally {
    submitBtn.disabled = false;
    submitText.textContent = "RUN";
    stepTracker.classList.add("hidden");
  }
}

function appendAnalysisCard(data) {
  const thread = document.getElementById("conversationThread");
  const cardId = "card_" + Date.now();
  latestQueryResult = data;

  const findingsHtml = (data.key_findings || []).map(f => `
    <div class="finding-pill flex items-start space-x-2">
      <span class="text-coral-500 font-bold shrink-0">▸</span>
      <span class="text-slate-800 font-medium">${f}</span>
    </div>
  `).join("");

  const cardHtml = `
    <div class="workspace-card p-6 space-y-5" id="${cardId}">
      
      <!-- Card Header: User Query & Save Action -->
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center pb-4 border-b border-slate-100 gap-2">
        <div class="flex items-center space-x-2.5">
          <div class="w-6 h-6 rounded-full coral-gradient text-white flex items-center justify-center text-[10px] font-bold">Q</div>
          <h3 class="font-syne font-bold text-base text-slate-900">${data.question}</h3>
        </div>
        <div class="flex items-center space-x-2">
          <button onclick="saveInsightFromCard('${cardId}')" class="text-xs font-mono font-semibold bg-slate-100 hover:bg-coral-50 hover:text-coral-600 px-3 py-1.5 rounded-lg border border-slate-200 transition flex items-center space-x-1">
            <span>⭐ Save Insight</span>
          </button>
        </div>
      </div>

      <!-- 1. Executive Summary -->
      <div>
        <div class="text-xs font-mono font-bold text-slate-400 uppercase mb-1">Executive Summary:</div>
        <p class="text-sm text-slate-800 leading-relaxed font-medium bg-slate-50 p-3.5 rounded-xl border border-slate-100">${data.summary}</p>
      </div>

      <!-- 2. Key Findings (3 Discrete Cards) -->
      <div>
        <div class="text-xs font-mono font-bold text-slate-400 uppercase mb-2">Key Analytical Findings:</div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
          ${findingsHtml}
        </div>
      </div>

      <!-- 3. Interactive Visualization Card -->
      <div class="bg-slate-50/80 p-5 rounded-xl border border-slate-200">
        <div class="flex items-center justify-between mb-3">
          <div>
            <div class="font-syne font-bold text-sm text-slate-900">${data.chart?.title || 'Data Analytics'}</div>
            <div class="text-xs text-slate-500 font-mono">${data.chart?.subtitle || 'Grounded in executed SQL calculations'}</div>
          </div>
          <div class="flex items-center space-x-1.5">
            <button onclick="switchChartType('${cardId}', 'bar')" class="text-xs font-mono px-2.5 py-1 bg-white border border-slate-200 rounded-lg hover:border-coral-500">Bar</button>
            <button onclick="switchChartType('${cardId}', 'line')" class="text-xs font-mono px-2.5 py-1 bg-white border border-slate-200 rounded-lg hover:border-coral-500">Line</button>
            <button onclick="switchChartType('${cardId}', 'doughnut')" class="text-xs font-mono px-2.5 py-1 bg-white border border-slate-200 rounded-lg hover:border-coral-500">Donut</button>
          </div>
        </div>
        <div class="h-64 flex items-center justify-center">
          <canvas id="chart_${cardId}"></canvas>
        </div>
      </div>

      <!-- 4. Result Data Table with Pagination & Controls -->
      <div class="border border-slate-200 rounded-xl overflow-hidden">
        <div class="bg-slate-100 px-4 py-2.5 border-b border-slate-200 flex justify-between items-center text-xs font-mono">
          <span class="text-slate-600 font-bold">QUERY RESULT TABLE (${data.total_rows} rows)</span>
          <div class="flex items-center space-x-2">
            <button onclick="downloadResultCsv('${cardId}')" class="text-coral-600 hover:underline font-bold">Download CSV</button>
            <button onclick="copyTableData('${cardId}')" class="text-slate-600 hover:text-slate-900">Copy Data</button>
          </div>
        </div>
        <div class="overflow-x-auto max-h-56 overflow-y-auto">
          <table class="w-full text-left text-xs font-mono border-collapse" id="table_${cardId}">
            <thead class="bg-slate-50 text-slate-500 border-b border-slate-200">
              <tr>${(data.columns || []).map(c => `<th class="p-2.5 uppercase font-bold">${c}</th>`).join("")}</tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              ${(data.rows || []).slice(0, 10).map(r => `
                <tr class="hover:bg-slate-50">${(data.columns || []).map(c => `<td class="p-2.5 text-slate-700">${r[c] !== null ? r[c] : '-'}</td>`).join("")}</tr>
              `).join("")}
            </tbody>
          </table>
        </div>
        <div class="bg-slate-50 px-4 py-2 text-[11px] font-mono text-slate-500 flex justify-between">
          <span>Showing top 10 of ${data.total_rows} rows</span>
          <span>Computed deterministically in DuckDB</span>
        </div>
      </div>

      <!-- 5. Collapsible SQL Query Panel -->
      <details class="group bg-slate-900 rounded-xl overflow-hidden">
        <summary class="flex justify-between items-center px-4 py-3 cursor-pointer text-xs font-mono text-sky-400 font-bold select-none">
          <span>🦆 SQL Query (Executed in ${data.total_duration}s · DuckDB)</span>
          <span class="text-slate-500 text-[11px]">Click to view SQL ▾</span>
        </summary>
        <div class="p-4 pt-0 border-t border-slate-800">
          <div class="flex justify-end mb-1">
            <button onclick="copySqlText('${cardId}')" class="text-[11px] font-mono text-slate-400 hover:text-white">Copy SQL</button>
          </div>
          <pre class="font-mono text-xs text-sky-300 overflow-x-auto whitespace-pre-wrap" id="sql_${cardId}">${data.sql}</pre>
        </div>
      </details>

      <!-- 6. Recommendations -->
      ${data.recommendations ? `
        <div class="text-xs font-mono text-slate-600 bg-coral-50/50 p-3 rounded-xl border border-coral-100 flex items-center space-x-2">
          <span class="text-coral-500 font-bold">💡 Strategic Recommendation:</span>
          <span>${data.recommendations}</span>
        </div>
      ` : ''}

    </div>
  `;

  thread.insertAdjacentHTML("beforeend", cardHtml);

  // Render chart
  renderCopilotChart(cardId, data);
}

function renderCopilotChart(cardId, data) {
  const canvas = document.getElementById(`chart_${cardId}`);
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  const spec = data.chart || {};
  const rows = data.rows || [];
  const cols = data.columns || [];

  if (rows.length === 0 || cols.length === 0) return;

  const xCol = spec.x_col && cols.includes(spec.x_col) ? spec.x_col : cols[0];
  const yCol = spec.y_col && cols.includes(spec.y_col) ? spec.y_col : (cols[1] || cols[0]);

  const labels = rows.map(r => r[xCol]);
  const values = rows.map(r => r[yCol]);
  const chartType = spec.chart_type === "line" ? "line" : (spec.chart_type === "doughnut" || spec.chart_type === "pie" ? "doughnut" : "bar");

  activeCharts[cardId] = new Chart(ctx, {
    type: chartType,
    data: {
      labels: labels,
      datasets: [{
        label: yCol,
        data: values,
        backgroundColor: chartType === "doughnut" 
          ? ['#f43f5e', '#38bdf8', '#fbbf24', '#34d399', '#a78bfa', '#f472b6']
          : 'rgba(244, 63, 94, 0.85)',
        borderColor: '#e11d48',
        borderWidth: 1,
        borderRadius: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: chartType === "doughnut" }
      },
      scales: chartType === "doughnut" ? {} : {
        x: { grid: { display: false } },
        y: { grid: { color: '#f1f5f9' } }
      }
    }
  });
}

function switchChartType(cardId, type) {
  const chart = activeCharts[cardId];
  if (!chart) return;

  chart.config.type = type;
  if (type === "doughnut") {
    chart.data.datasets[0].backgroundColor = ['#f43f5e', '#38bdf8', '#fbbf24', '#34d399', '#a78bfa', '#f472b6'];
    chart.options.scales = {};
  } else {
    chart.data.datasets[0].backgroundColor = 'rgba(244, 63, 94, 0.85)';
    chart.options.scales = {
      x: { grid: { display: false } },
      y: { grid: { color: '#f1f5f9' } }
    };
  }
  chart.update();
}

function clearCopilotConversation() {
  conversationHistory = [];
  document.getElementById("conversationThread").innerHTML = `
    <div class="workspace-card p-6 bg-slate-50 border-dashed border-2 border-slate-200 text-center py-10" id="emptyCopilotState">
      <h3 class="font-syne font-bold text-lg text-slate-900 mb-1">New Conversation Thread</h3>
      <p class="text-xs text-slate-500 font-mono">Ask a fresh question to begin analysis.</p>
    </div>
  `;
}

// ---------------------------------------------------------
// Saved Insights & Reports
// ---------------------------------------------------------
function saveInsightFromCard(cardId) {
  if (!latestQueryResult) return;
  const insight = {
    id: Date.now(),
    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    question: latestQueryResult.question,
    summary: latestQueryResult.summary,
    key_findings: latestQueryResult.key_findings,
    sql: latestQueryResult.sql
  };

  savedInsights.unshift(insight);
  localStorage.setItem("datapilot_saved_insights", JSON.stringify(savedInsights));
  renderSavedInsightsCount();
  alert("⭐ Insight added to your Executive Report!");
}

function renderSavedInsightsCount() {
  const badge = document.getElementById("savedCountBadge");
  if (badge) badge.textContent = savedInsights.length;
}

function renderSavedInsightsGrid() {
  const grid = document.getElementById("savedInsightsGrid");
  if (savedInsights.length === 0) {
    grid.innerHTML = "<div class='col-span-2 text-center p-8 text-slate-500 font-mono text-xs'>No saved insights yet. Click '⭐ Save Insight' on any AI response card to add it here.</div>";
    return;
  }

  grid.innerHTML = savedInsights.map((ins, idx) => `
    <div class="workspace-card p-5 space-y-3">
      <div class="flex justify-between items-start border-b border-slate-100 pb-2">
        <h4 class="font-syne font-bold text-sm text-slate-900 truncate max-w-xs">#${savedInsights.length - idx}: ${ins.question}</h4>
        <button onclick="removeSavedInsight(${idx})" class="text-slate-400 hover:text-rose-600 text-xs font-mono">✕ Remove</button>
      </div>
      <p class="text-xs text-slate-700 font-medium">${ins.summary}</p>
      <div class="space-y-1">
        ${(ins.key_findings || []).map(f => `<div class="text-[11px] font-mono text-slate-600">▸ ${f}</div>`).join("")}
      </div>
      <pre class="bg-slate-900 text-sky-300 p-2 rounded text-[10px] font-mono truncate">${ins.sql}</pre>
    </div>
  `).join("");
}

function removeSavedInsight(idx) {
  savedInsights.splice(idx, 1);
  localStorage.setItem("datapilot_saved_insights", JSON.stringify(savedInsights));
  renderSavedInsightsCount();
  renderSavedInsightsGrid();
}

async function exportFullExecutiveReport() {
  if (!currentDataset) {
    alert("Please upload a dataset first.");
    return;
  }

  try {
    const res = await fetch("/api/generate-report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dataset_name: currentDataset.filename,
        saved_insights: savedInsights
      })
    });
    const htmlContent = await res.text();
    const win = window.open("", "_blank");
    win.document.write(htmlContent);
    win.document.close();
  } catch (e) {
    alert("Report generation failed: " + e.message);
  }
}

// ---------------------------------------------------------
// Automated EDA Tab
// ---------------------------------------------------------
async function fetchAutoEDA() {
  try {
    const res = await fetch("/api/auto-eda");
    const data = await res.json();

    // 1. Numeric stats
    const numBody = document.getElementById("edaNumericBody");
    if (data.numeric_summaries && data.numeric_summaries.length > 0) {
      numBody.innerHTML = data.numeric_summaries.map(s => `
        <tr class="hover:bg-slate-50 font-mono text-xs">
          <td class="p-3 font-bold text-slate-900">${s.column}</td>
          <td class="p-3 text-slate-700">${s.mean.toLocaleString()}</td>
          <td class="p-3 text-slate-700">${s.std.toLocaleString()}</td>
          <td class="p-3 text-slate-700">${s.min.toLocaleString()}</td>
          <td class="p-3 text-slate-700">${s.q25.toLocaleString()}</td>
          <td class="p-3 font-bold text-coral-600">${s.median.toLocaleString()}</td>
          <td class="p-3 text-slate-700">${s.q75.toLocaleString()}</td>
          <td class="p-3 text-slate-700">${s.max.toLocaleString()}</td>
          <td class="p-3 text-slate-700">${s.skew}</td>
        </tr>
      `).join("");
    }

    // 2. Categorical breakdown
    const catBox = document.getElementById("edaCatContainer");
    if (data.categorical_summaries && data.categorical_summaries.length > 0) {
      catBox.innerHTML = data.categorical_summaries.map(c => `
        <div class="bg-slate-50 p-3.5 rounded-xl border border-slate-200">
          <div class="font-syne font-bold text-xs text-slate-900 uppercase mb-2">${c.column}</div>
          <div class="space-y-1.5">
            ${c.top_values.map(v => `
              <div class="flex justify-between text-xs font-mono">
                <span class="text-slate-700 truncate max-w-[200px]">${v.label}</span>
                <span class="text-slate-500 font-bold">${v.count.toLocaleString()} (${v.pct}%)</span>
              </div>
            `).join("")}
          </div>
        </div>
      `).join("");
    }

    // 3. Correlation matrix
    const corrBox = document.getElementById("edaCorrContainer");
    if (data.correlation_matrix) {
      const cols = data.correlation_matrix.columns;
      const matrix = data.correlation_matrix.data;
      corrBox.innerHTML = `
        <table class="w-full text-center text-xs font-mono border-collapse">
          <thead>
            <tr class="bg-slate-100">${cols.map(c => `<th class="p-2 truncate max-w-[80px]">${c}</th>`).join("")}</tr>
          </thead>
          <tbody>
            ${matrix.map((row, i) => `
              <tr class="border-b border-slate-100">
                ${row.map(val => `<td class="p-2 font-bold ${val > 0.6 ? 'text-coral-600 bg-coral-50' : 'text-slate-700'}">${val}</td>`).join("")}
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;
    }
  } catch (e) {}
}

// ---------------------------------------------------------
// SQL Studio
// ---------------------------------------------------------
function setSqlSnippet(type) {
  if (type === "top_revenue") {
    document.getElementById("rawSqlEditor").value = "SELECT category, SUM(sales) AS total_sales, AVG(profit) AS avg_profit\nFROM dataset\nGROUP BY 1\nORDER BY total_sales DESC\nLIMIT 10;";
  } else if (type === "monthly_trend") {
    document.getElementById("rawSqlEditor").value = "SELECT order_date, SUM(sales) AS daily_sales\nFROM dataset\nGROUP BY 1\nORDER BY 1 ASC\nLIMIT 15;";
  }
}

async function executeRawSqlStudio() {
  const sql = document.getElementById("rawSqlEditor").value.trim();
  const statusElem = document.getElementById("sqlStudioStatus");
  statusElem.textContent = "Running query in DuckDB...";

  try {
    const res = await fetch("/api/query-sql", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sql })
    });
    const data = await res.json();

    if (!data.success) {
      statusElem.textContent = "Error: " + data.error;
      alert("SQL Error: " + data.error);
      return;
    }

    statusElem.textContent = `Executed in ${data.exec_time}s (${data.row_count} rows returned)`;

    // Table
    const thead = document.getElementById("studioTableHead");
    const tbody = document.getElementById("studioTableBody");
    thead.innerHTML = `<tr>${data.columns.map(c => `<th class="p-2.5 uppercase">${c}</th>`).join("")}</tr>`;
    tbody.innerHTML = data.rows.slice(0, 15).map(r => `
      <tr class="hover:bg-slate-50">${data.columns.map(c => `<td class="p-2.5 text-slate-700">${r[c]}</td>`).join("")}</tr>
    `).join("");

    // Auto Chart
    if (data.rows.length > 0 && data.columns.length >= 2) {
      const labels = data.rows.map(r => r[data.columns[0]]);
      const values = data.rows.map(r => r[data.columns[1]]);
      renderChartCanvas("studioChartCanvas", "bar", labels, values, data.columns[1]);
    }
  } catch (err) {
    statusElem.textContent = "Failed: " + err.message;
  }
}

// ---------------------------------------------------------
// History & Utilities
// ---------------------------------------------------------
function saveToQueryHistory(data) {
  queryHistory.unshift({
    id: Date.now(),
    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    question: data.question,
    sql: data.sql
  });
  if (queryHistory.length > 30) queryHistory.pop();
  localStorage.setItem("datapilot_history", JSON.stringify(queryHistory));
}

function renderHistoryTimeline() {
  const list = document.getElementById("historyTimelineList");
  if (queryHistory.length === 0) {
    list.innerHTML = "<div class='text-xs text-slate-500 font-mono p-4 text-center'>No queries executed in this session.</div>";
    return;
  }

  list.innerHTML = queryHistory.map((h, idx) => `
    <div onclick="askCopilotQuestion('${h.question.replace(/'/g, "\\'")}')" class="workspace-card p-4 hover:border-coral-500 cursor-pointer transition flex justify-between items-center">
      <div>
        <div class="text-[11px] font-mono text-slate-400">#${queryHistory.length - idx} · ${h.time}</div>
        <div class="font-syne font-bold text-sm text-slate-900 mt-0.5">${h.question}</div>
        <pre class="text-[10px] font-mono text-slate-500 truncate max-w-md mt-1">${h.sql}</pre>
      </div>
      <span class="text-coral-600 font-bold text-xs font-mono">Re-run →</span>
    </div>
  `).join("");
}

function clearAllHistory() {
  queryHistory = [];
  localStorage.removeItem("datapilot_history");
  renderHistoryTimeline();
}

function renderChartCanvas(canvasId, type, labels, values, datasetLabel) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  if (activeCharts[canvasId]) {
    activeCharts[canvasId].destroy();
  }

  activeCharts[canvasId] = new Chart(ctx, {
    type: type,
    data: {
      labels: labels,
      datasets: [{
        label: datasetLabel,
        data: values,
        backgroundColor: 'rgba(244, 63, 94, 0.85)',
        borderColor: '#e11d48',
        borderWidth: 1,
        borderRadius: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: '#f1f5f9' } }
      }
    }
  });
}

function copySqlText(cardId) {
  const sql = document.getElementById(`sql_${cardId}`).textContent;
  navigator.clipboard.writeText(sql);
  alert("SQL copied to clipboard!");
}

function copyTableData(cardId) {
  if (!latestQueryResult || !latestQueryResult.rows) return;
  navigator.clipboard.writeText(JSON.stringify(latestQueryResult.rows, null, 2));
  alert("Data copied as JSON to clipboard!");
}

function downloadResultCsv(cardId) {
  if (!latestQueryResult || !latestQueryResult.rows) return;
  const cols = latestQueryResult.columns;
  const rows = latestQueryResult.rows;
  const csv = [cols.join(","), ...rows.map(r => cols.map(c => `"${(r[c] ?? '').toString().replace(/"/g, '""')}"`).join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `DataPilot_Query_${Date.now()}.csv`;
  a.click();
}

function setupSettingsUI() {
  const p = localStorage.getItem("datapilot_provider") || "Ollama (Local)";
  const m = localStorage.getItem("datapilot_model") || "qwen2.5-coder:14b";
  const k = localStorage.getItem("datapilot_apikey") || "";

  document.getElementById("settingsProviderSelect").value = p;
  document.getElementById("settingsModelInput").value = m;
  document.getElementById("settingsApiKeyInput").value = k;
  document.getElementById("topbarModelPill").textContent = m;
  onSettingsProviderChange();
}

function onSettingsProviderChange() {
  const p = document.getElementById("settingsProviderSelect").value;
  const box = document.getElementById("settingsApiKeyBox");
  if (p === "Ollama (Local)") {
    box.classList.add("hidden");
  } else {
    box.classList.remove("hidden");
  }
}

function saveSettings() {
  const p = document.getElementById("settingsProviderSelect").value;
  const m = document.getElementById("settingsModelInput").value;
  const k = document.getElementById("settingsApiKeyInput").value;

  localStorage.setItem("datapilot_provider", p);
  localStorage.setItem("datapilot_model", m);
  localStorage.setItem("datapilot_apikey", k);
  document.getElementById("topbarModelPill").textContent = m;

  alert("Settings saved successfully!");
}

// ---------------------------------------------------------
// Visualizations Studio & Gallery
// ---------------------------------------------------------
async function fetchVisualizationsGallery() {
  try {
    const res = await fetch("/api/visualizations-gallery");
    const data = await res.json();

    // Populate dropdowns for custom builder
    const xSelect = document.getElementById("vizXColSelect");
    const ySelect = document.getElementById("vizYColSelect");

    const cats = data.categorical_cols || [];
    const nums = data.numeric_cols || [];

    xSelect.innerHTML = [...cats, ...nums].map(c => `<option value="${c}">${c}</option>`).join("");
    ySelect.innerHTML = nums.map(c => `<option value="${c}">${c}</option>`).join("");

    // Initial render of custom builder if first time
    if (!activeCharts["customStudioChartCanvas"]) {
      renderCustomStudioChart();
    }

    // Render 4 Pre-built Gallery Charts
    const galleryGrid = document.getElementById("visualizationsGalleryGrid");
    if (data.gallery && data.gallery.length > 0) {
      galleryGrid.innerHTML = data.gallery.map(g => `
        <div class="workspace-card p-5 space-y-3">
          <div class="flex justify-between items-start border-b border-slate-100 pb-2">
            <div>
              <h4 class="font-syne font-bold text-sm text-slate-900">${g.title}</h4>
              <p class="text-xs font-mono text-slate-500">${g.subtitle}</p>
            </div>
            <span class="text-xs font-mono bg-coral-50 text-coral-600 font-bold px-2.5 py-0.5 rounded-full uppercase">${g.type}</span>
          </div>
          <div class="h-60 flex items-center justify-center">
            <canvas id="canvas_${g.id}"></canvas>
          </div>
        </div>
      `).join("");

      // Render chart instances
      setTimeout(() => {
        data.gallery.forEach(g => {
          renderChartCanvas(`canvas_${g.id}`, g.type, g.labels, g.values, g.label);
        });
      }, 100);
    }
  } catch (e) {}
}

async function renderCustomStudioChart() {
  const x_col = document.getElementById("vizXColSelect").value;
  const y_col = document.getElementById("vizYColSelect").value;
  const agg_func = document.getElementById("vizAggSelect").value;
  const chart_type = document.getElementById("vizTypeSelect").value;

  if (!x_col || !y_col) return;

  try {
    const res = await fetch("/api/custom-chart", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ x_col, y_col, agg_func, chart_type })
    });
    const data = await res.json();
    if (res.ok) {
      renderChartCanvas("customStudioChartCanvas", data.type, data.labels, data.values, `${data.agg} (${data.y_col})`);
    } else {
      alert("Chart builder error: " + (data.detail || "Failed to aggregate data"));
    }
  } catch (err) {
    alert("Error rendering custom chart: " + err.message);
  }
}

function downloadCustomChartPng() {
  const canvas = document.getElementById("customStudioChartCanvas");
  if (!canvas) return;
  const link = document.createElement("a");
  link.download = `DataPilot_Visual_${Date.now()}.png`;
  link.href = canvas.toDataURL("image/png");
  link.click();
}
