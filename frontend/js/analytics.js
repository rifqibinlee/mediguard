(function () {
/**
 * analytics.js
 * Renders all KPI cards, Chart.js charts, cluster ranking, and supplier table.
 * Depends on: Chart.js CDN bundle, window.loadAnalytics exposed to index.html
 */

const API = '/api';

// ── State ──────────────────────────────────────────────────────────────────
const CHARTS  = { meds: null, ts: null, loss: null };
const FILTERS = { state: '', district: '', date_from: '', date_to: '', medicine_id: '' };

// ── Error banner ───────────────────────────────────────────────────────────

function showError(msg) {
  let banner = document.getElementById('an-error');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'an-error';
    banner.style.cssText = `
      position:fixed;bottom:20px;left:50%;transform:translateX(-50%);z-index:999;
      background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.4);
      color:#ef4444;padding:10px 20px;font-family:var(--hf);font-size:11px;
      letter-spacing:1.5px;text-transform:uppercase;backdrop-filter:blur(12px);`;
    document.body.appendChild(banner);
  }
  banner.textContent = msg;
  banner.style.display = 'block';
  setTimeout(() => { banner.style.display = 'none'; }, 5000);
}

async function safeFetch(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status}: ${detail.slice(0, 120)}`);
  }
  return res.json();
}

// ── Chart.js dark theme ────────────────────────────────────────────────────
function applyChartDefaults() {
  if (typeof Chart === 'undefined') return;
  Chart.defaults.color                              = '#7eaac6';
  Chart.defaults.font.family                        = "'DM Sans', sans-serif";
  Chart.defaults.font.size                          = 11;
  Chart.defaults.borderColor                        = 'rgba(255,255,255,0.05)';
  Chart.defaults.plugins.tooltip.backgroundColor   = 'rgba(4,14,28,0.95)';
  Chart.defaults.plugins.tooltip.borderColor        = 'rgba(255,255,255,0.10)';
  Chart.defaults.plugins.tooltip.borderWidth        = 1;
  Chart.defaults.plugins.tooltip.padding            = 10;
  Chart.defaults.plugins.tooltip.titleColor         = '#e8f0f8';
  Chart.defaults.plugins.tooltip.bodyColor          = '#7eaac6';
}

// ── Helpers ────────────────────────────────────────────────────────────────

/** Build a query string from the current FILTERS state + any extras. */
function qs(extra = {}) {
  const p = new URLSearchParams();
  Object.entries({ ...FILTERS, ...extra }).forEach(([k, v]) => {
    if (v !== '' && v !== null && v !== undefined) p.set(k, v);
  });
  return p.size ? '?' + p : '';
}

/** Read buffer slider values from the map page sidebar (always in DOM). */
function mapParams() {
  return new URLSearchParams({
    hospital_buffer_m: document.getElementById('buf-hosp')?.value || 800,
    clinic_buffer_m:   document.getElementById('buf-clin')?.value || 500,
    pharmacy_buffer_m: document.getElementById('buf-phar')?.value || 400,
  });
}

/** Destroy old chart instance and create a new one. */
function makeChart(key, canvasId, config) {
  CHARTS[key]?.destroy();
  CHARTS[key] = null;
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  CHARTS[key] = new Chart(canvas.getContext('2d'), config);
}

const fmt    = n  => typeof n === 'number' ? n.toLocaleString('en-MY') : (n ?? '—');
const fmtMYR = n  => typeof n === 'number'
  ? 'MYR ' + n.toLocaleString('en-MY', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  : '—';
const fmtK   = n  => n >= 1_000_000
  ? 'RM ' + (n / 1_000_000).toFixed(2) + 'M'
  : n >= 1_000
  ? 'RM ' + (n / 1_000).toFixed(1) + 'k'
  : fmtMYR(n);

// ── 1. KPI cards ───────────────────────────────────────────────────────────

async function loadSummary() {
  try {
    const data = await safeFetch(`${API}/analytics/summary${qs()}`);
    document.getElementById('kpi-total')   .textContent = fmt(data.total_complaints);
    document.getElementById('kpi-loss')    .textContent = fmtK(data.total_loss_myr);
    document.getElementById('kpi-verified').textContent =
      typeof data.verification_rate_pct === 'number'
        ? data.verification_rate_pct.toFixed(1) + '%' : '—';
  } catch (e) { console.error('Summary:', e); showError('Analytics API error — check data_loader.py NaN fix'); }
}

// ── 2. Most-faked medicines — horizontal bar ───────────────────────────────

async function loadMedicines() {
  try {
    const res  = await fetch(`${API}/analytics/medicines${qs({ limit: 10 })}`);
    const data = await res.json();
    renderMedChart(data);
  } catch (e) { console.error('Medicines chart error:', e); }
}

function renderMedChart(data) {
  makeChart('meds', 'chart-meds', {
    type: 'bar',
    data: {
      labels: data.map(d => d.name ?? d.medicine_id),
      datasets: [
        {
          label: 'Complaints',
          data:            data.map(d => d.complaint_count),
          backgroundColor: 'rgba(249,115,22,0.65)',
          borderColor:     'rgba(249,115,22,0.90)',
          borderWidth: 1, borderRadius: 2,
        },
        {
          label: 'Verified Fake',
          data:            data.map(d => d.verified_count),
          backgroundColor: 'rgba(239,68,68,0.55)',
          borderColor:     'rgba(239,68,68,0.80)',
          borderWidth: 1, borderRadius: 2,
        },
      ],
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#7eaac6', boxWidth: 10 } } },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,0.05)' } },
        y: { grid: { display: false }, ticks: { font: { size: 11 } } },
      },
    },
  });
}

// ── 3. Time series — dual-axis line ───────────────────────────────────────

async function loadTimeseries() {
  try {
    const res  = await fetch(`${API}/analytics/timeseries${qs({ granularity: 'monthly' })}`);
    const data = await res.json();
    renderTsChart(data.series || []);
  } catch (e) { console.error('Timeseries error:', e); }
}

function renderTsChart(series) {
  makeChart('ts', 'chart-ts', {
    type: 'line',
    data: {
      labels: series.map(s => s.period),
      datasets: [
        {
          label: 'Complaints',
          data:            series.map(s => s.complaint_count),
          borderColor:     'rgba(249,115,22,0.90)',
          backgroundColor: 'rgba(249,115,22,0.08)',
          fill: true, tension: 0.4,
          pointRadius: 3, pointHoverRadius: 5,
          yAxisID: 'y',
        },
        {
          label: 'Est. Loss (MYR)',
          data:            series.map(s => s.total_loss),
          borderColor:     'rgba(251,191,36,0.85)',
          backgroundColor: 'transparent',
          fill: false, tension: 0.4,
          borderDash: [4, 3],
          pointRadius: 2, pointHoverRadius: 4,
          yAxisID: 'y1',
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { color: '#7eaac6', boxWidth: 12 } } },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: { maxTicksLimit: 12 },
        },
        y: {
          position: 'left',
          grid: { color: 'rgba(255,255,255,0.04)' },
          title: { display: true, text: 'Complaints', color: '#7eaac6', font: { size: 10 } },
        },
        y1: {
          position: 'right',
          grid: { display: false },
          title: { display: true, text: 'MYR', color: '#7eaac6', font: { size: 10 } },
        },
      },
    },
  });
}

// ── 4. Loss by category — doughnut ────────────────────────────────────────

const CAT_COLS = [
  'rgba(249,115,22,0.80)', 'rgba(251,191,36,0.80)', 'rgba(168,85,247,0.80)',
  'rgba(59,130,246,0.80)', 'rgba(34,197,94,0.80)',  'rgba(236,72,153,0.80)',
  'rgba(20,184,166,0.80)', 'rgba(99,102,241,0.80)', 'rgba(234,179,8,0.80)',
];

async function loadLosses() {
  try {
    const res  = await fetch(`${API}/analytics/losses${qs({ group_by: 'category' })}`);
    const data = await res.json();
    renderLossChart(data.breakdown || []);
  } catch (e) { console.error('Loss chart error:', e); }
}

function renderLossChart(breakdown) {
  const col = b => b.category ?? b.state ?? b.medicine_name ?? '—';
  makeChart('loss', 'chart-loss', {
    type: 'doughnut',
    data: {
      labels: breakdown.map(col),
      datasets: [{
        data:            breakdown.map(b => b.total_loss),
        backgroundColor: CAT_COLS,
        borderColor:     'rgba(255,255,255,0.08)',
        borderWidth: 1, hoverOffset: 6,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      cutout: '62%',
      plugins: {
        legend: {
          position: 'right',
          labels: { color: '#7eaac6', boxWidth: 10, font: { size: 11 }, padding: 10 },
        },
        tooltip: {
          callbacks: {
            label: ctx => ' ' + fmtMYR(ctx.parsed) + '  (' + ctx.label + ')',
          },
        },
      },
    },
  });
}

// ── 5. Cluster ranking list ────────────────────────────────────────────────

async function loadClusterRanking() {
  try {
    const res  = await fetch(`${API}/analytics/clusters?` + mapParams() + '&limit=8');
    const data = await res.json();

    // Sync the KPI clusters count
    const n = data.summary?.n_dbscan_clusters;
    if (n !== undefined) document.getElementById('kpi-clusters').textContent = fmt(n);

    renderClusterRanking(data.clusters || []);
  } catch (e) { console.error('Cluster ranking error:', e); }
}

function renderClusterRanking(clusters) {
  const el = document.getElementById('cr-list');
  if (!el) return;

  if (!clusters.length) {
    el.innerHTML = `<div class="placeholder" style="height:120px;">
      No clusters found — press <strong>Run Clustering</strong> on the Map page first.
    </div>`;
    return;
  }

  el.innerHTML = clusters.map((c, i) => {
    const topState = c.state_breakdown
      ? (Object.entries(c.state_breakdown).sort((a, b) => b[1] - a[1])[0]?.[0] ?? '—')
      : '—';
    const topMeds = Object.keys(c.top_medicines || {}).slice(0, 2).join(', ') || '—';
    const lossStr = fmtMYR(c.total_loss);

    return `
      <div class="cr-row">
        <div class="cr-rank">${i + 1}</div>
        <div class="cr-info">
          <div class="cr-cid">${c.cluster_id}</div>
          <div class="cr-meta">
            ${fmt(c.complaint_count)} complaints · ${lossStr} · ${topState}
          </div>
          <div class="cr-meta" style="color:var(--dim);margin-top:2px;font-size:11px;">
            ${topMeds}
          </div>
        </div>
        <div class="cr-right">
          <div class="cr-sev">${c.severity_score}</div>
          <div class="cr-sevl">SEVERITY</div>
        </div>
      </div>`;
  }).join('');
}

// ── 6. Supplier risk table ─────────────────────────────────────────────────

async function loadSuppliers() {
  try {
    const res  = await fetch(`${API}/analytics/suppliers${qs({ limit: 15 })}`);
    const data = await res.json();
    renderSupplierTable(data);
  } catch (e) { console.error('Supplier table error:', e); }
}

function renderSupplierTable(suppliers) {
  const tbody = document.getElementById('sup-tbody');
  if (!tbody) return;

  if (!suppliers.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="placeholder" style="height:60px;">No data</td></tr>`;
    return;
  }

  tbody.innerHTML = suppliers.map(s => `
    <tr>
      <td title="${s.name}">${s.name}</td>
      <td>${s.state || '—'}</td>
      <td style="text-align:center;">${s.facilities_supplied ?? 0}</td>
      <td style="text-align:center;">${s.linked_complaints ?? 0}</td>
      <td>
        <span class="s-badge ${s.is_suspicious ? 's' : 'l'}">
          ${s.is_suspicious ? '⚠ Suspicious' : '✓ Licensed'}
        </span>
      </td>
    </tr>`).join('');
}

// ── Filter wiring ──────────────────────────────────────────────────────────

/** Populate district dropdown dynamically when state changes. */
async function updateDistricts(state) {
  const el = document.getElementById('an-district');
  if (!el) return;
  el.innerHTML = '<option value="">All Districts</option>';
  if (!state) return;
  try {
    const res  = await fetch(`${API}/complaints?state=${encodeURIComponent(state)}`);
    const cmps = await res.json();
    const dsts = [...new Set(cmps.map(c => c.district).filter(Boolean))].sort();
    dsts.forEach(d =>
      el.insertAdjacentHTML('beforeend', `<option value="${d}">${d}</option>`)
    );
  } catch (e) { console.error('District update error:', e); }
}

function wireFilters() {
  const g = id => document.getElementById(id);

  g('an-state')   ?.addEventListener('change', e => {
    FILTERS.state    = e.target.value;
    FILTERS.district = '';
    if (g('an-district')) g('an-district').value = '';
    updateDistricts(FILTERS.state);
  });
  g('an-district')?.addEventListener('change', e => { FILTERS.district    = e.target.value; });
  g('an-from')    ?.addEventListener('change', e => { FILTERS.date_from   = e.target.value; });
  g('an-to')      ?.addEventListener('change', e => { FILTERS.date_to     = e.target.value; });
  g('an-med')     ?.addEventListener('change', e => { FILTERS.medicine_id = e.target.value; });
  g('an-apply')   ?.addEventListener('click',  loadAnalytics);
}

// ── Entry points ───────────────────────────────────────────────────────────

async function loadAnalytics() {
  applyChartDefaults();
  await Promise.allSettled([
    loadSummary(),
    loadMedicines(),
    loadTimeseries(),
    loadLosses(),
    loadClusterRanking(),
    loadSuppliers(),
  ]);
}

document.addEventListener('DOMContentLoaded', wireFilters);

// Called by index.html page-switch when Analytics tab is clicked
window.loadAnalytics = loadAnalytics;

})(); // end IIFE