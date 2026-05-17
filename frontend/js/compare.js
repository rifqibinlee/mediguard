(function () {
/**
 * compare.js — Split-screen Compare page.
 *
 * Left pane:  current active clusters (mirrors main map.js data, re-runnable)
 * Right pane: historical clusters (loads from /api/clusters/historical by date range)
 *
 * Each pane has its own Leaflet map instance and a compact viewport bar.
 */

const API = '/api';

const TILES = {
  dark: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
};

const TYPE_COL = { hospital: '#22c55e', clinic: '#3b82f6', pharmacy: '#a855f7' };

// ── State ──────────────────────────────────────────────────────────────────
let _initialized = false;
let _syncing = false;

const CUR = {
  map: null, tile: null,
  result: null,
  lg: { buffers: null, complaints: null, hulls: null, centroids: null },
};
const HIST = {
  map: null, tile: null,
  result: null,
  lg: { buffers: null, complaints: null, hulls: null, centroids: null },
};

let _vpTimerCur, _vpTimerHist;

// ── Expose init (called when Compare tab is clicked) ───────────────────────
window.initCompare = function () {
  if (_initialized) {
    // Invalidate map size in case the pane was hidden
    setTimeout(() => {
      CUR.map?.invalidateSize();
      HIST.map?.invalidateSize();
    }, 50);
    return;
  }
  _initialized = true;

  // Defer map init so the page div is visible and has real dimensions
  setTimeout(() => {

  // ── Current map ──────────────────────────────────────────────────────────
  CUR.map  = L.map('compare-map-current', {
    center: [4.0, 109.5], zoom: 6,
    zoomControl: false, attributionControl: false,
  });
  CUR.tile = L.tileLayer(TILES.dark, { subdomains: 'abcd', maxZoom: 20 }).addTo(CUR.map);
  CUR.lg.buffers    = L.layerGroup().addTo(CUR.map);
  CUR.lg.complaints = L.layerGroup().addTo(CUR.map);
  CUR.lg.hulls      = L.layerGroup().addTo(CUR.map);

  CUR.map.on('move', () => {
    if (_syncing) return;
    _syncing = true;
    HIST.map.setView(CUR.map.getCenter(), CUR.map.getZoom(), { animate: false });
    _syncing = false;
  });
  CUR.map.on('moveend zoomend', () => {
    clearTimeout(_vpTimerCur);
    _vpTimerCur = setTimeout(() => updateCmpVpBar('current'), 250);
    if (_syncing) return;
    _syncing = true;
    HIST.map.setView(CUR.map.getCenter(), CUR.map.getZoom(), { animate: false });
    _syncing = false;
  });

  // ── Historical map ───────────────────────────────────────────────────────
  HIST.map  = L.map('compare-map-hist', {
    center: [4.0, 109.5], zoom: 6,
    zoomControl: false, attributionControl: false,
  });
  HIST.tile = L.tileLayer(TILES.dark, { subdomains: 'abcd', maxZoom: 20 }).addTo(HIST.map);
  HIST.lg.buffers    = L.layerGroup().addTo(HIST.map);
  HIST.lg.complaints = L.layerGroup().addTo(HIST.map);
  HIST.lg.hulls      = L.layerGroup().addTo(HIST.map);

  HIST.map.on('move', () => {
    if (_syncing) return;
    _syncing = true;
    CUR.map.setView(HIST.map.getCenter(), HIST.map.getZoom(), { animate: false });
    _syncing = false;
  });
  HIST.map.on('moveend zoomend', () => {
    clearTimeout(_vpTimerHist);
    _vpTimerHist = setTimeout(() => updateCmpVpBar('hist'), 250);
    if (_syncing) return;
    _syncing = true;
    CUR.map.setView(HIST.map.getCenter(), HIST.map.getZoom(), { animate: false });
    _syncing = false;
  });

  // ── Buttons ──────────────────────────────────────────────────────────────
  document.getElementById('compare-run-btn')?.addEventListener('click', runCurrentClustering);
  document.getElementById('btn-hist-load')  ?.addEventListener('click', runHistoricalClustering);

  // ── Compact viewport bar toggles ─────────────────────────────────────────
  wireCmpVpToggle('current');
  wireCmpVpToggle('hist');

  // Load current clusters from main page state (if already computed)
  const mainResult = window._mapState?.clusterResult;
  if (mainResult) {
    CUR.result = mainResult;
    renderCompareMap(CUR, 'current');
  }

  // Auto-load default historical range
  runHistoricalClustering();

  }, 100); // end deferred init — page must be visible before Leaflet measures containers
};

// ── Wiring for compact viewport bar ───────────────────────────────────────
function wireCmpVpToggle(pane) {
  const btn = document.getElementById(`cmp-vp-toggle-${pane}`);
  const bar = document.getElementById(`cmp-vp-${pane}`);
  if (!btn || !bar) return;
  btn.addEventListener('click', () => {
    bar.classList.toggle('open');
    feather.replace({ 'stroke-width': 1.5 });
  });
}

// ── Run clustering for current pane ───────────────────────────────────────
async function runCurrentClustering() {
  const btn = document.getElementById('compare-run-btn');
  btn.classList.add('busy'); btn.textContent = 'Computing…';
  try {
    const res = await fetch(`${API}/clusters`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hospital_buffer_m: 800, clinic_buffer_m: 500, pharmacy_buffer_m: 400 }),
    });
    CUR.result = await res.json();
    renderCompareMap(CUR, 'current');
  } catch (e) { console.error('Compare current clustering:', e); }
  finally { btn.classList.remove('busy'); btn.textContent = 'Run Clustering'; }
}

// ── Run historical clustering ──────────────────────────────────────────────
async function runHistoricalClustering() {
  const btn   = document.getElementById('btn-hist-load');
  const from  = document.getElementById('hist-from')?.value || null;
  const to    = document.getElementById('hist-to')?.value   || null;
  if (btn) { btn.classList.add('busy'); btn.textContent = 'Loading…'; }
  try {
    const res = await fetch(`${API}/clusters/historical`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date_from: from, date_to: to,
        hospital_buffer_m: 800, clinic_buffer_m: 500, pharmacy_buffer_m: 400,
      }),
    });
    HIST.result = await res.json();
    renderCompareMap(HIST, 'hist');
  } catch (e) { console.error('Historical clustering:', e); }
  finally {
    if (btn) { btn.classList.remove('busy'); btn.textContent = 'Load Historical'; }
  }
}

// ── Render a compare pane's map ────────────────────────────────────────────
function renderCompareMap(state, pane) {
  const result = state.result;
  if (!result) return;

  // Complaints
  state.lg.complaints.clearLayers();
  (result.complaints || []).forEach(c => {
    const inside = c.inside_buffer;
    const color  = pane === 'hist' ? (inside ? 'rgba(56,189,248,0.2)' : '#38bdf8')
                                   : (inside ? '#ffffff' : '#f97316');
    L.circleMarker([+c.lat, +c.lng], {
      radius: 3.5,
      fillColor: color, color: 'transparent',
      fillOpacity: inside ? 0.3 : 0.75,
    }).addTo(state.lg.complaints);
  });

  // Hulls
  state.lg.hulls.clearLayers();
  const hullColor = pane === 'hist' ? '#38bdf8' : '#fbbf24';
  (result.dbscan_clusters || []).forEach(c => {
    if (c.hull_coords?.length >= 3) {
      const latlngs = c.hull_coords.map(([lng, lat]) => [lat, lng]);
      L.polygon(latlngs, {
        color: hullColor, weight: 1.5,
        fillColor: hullColor, fillOpacity: 0.09,
      })
      .on('click', () => showCmpClusterTooltip(state.map, c, pane))
      .addTo(state.lg.hulls);
    }
  });

  // Centroids (L.markerClusterGroup)
  if (state.lg.centroids) { state.map.removeLayer(state.lg.centroids); state.lg.centroids = null; }
  const dotClass = pane === 'hist' ? 'centroid-dot-hist' : 'centroid-dot';
  const aggClass = pane === 'hist' ? 'centroid-agg-hist' : 'centroid-agg';

  state.lg.centroids = L.markerClusterGroup({
    maxClusterRadius: 70, animate: true, animateAddingMarkers: false,
    spiderfyOnMaxZoom: false, showCoverageOnHover: false, zoomToBoundsOnClick: true,
    iconCreateFunction: cluster => {
      const total = cluster.getAllChildMarkers().reduce((s, m) => s + (m._count || 0), 0);
      const sz = Math.min(26 + Math.log2(total + 1) * 7, 54);
      return L.divIcon({
        html: `<div class="${aggClass}" style="width:${sz}px;height:${sz}px">${total}</div>`,
        className: '', iconSize: [sz, sz], iconAnchor: [sz / 2, sz / 2],
      });
    },
  });

  (result.dbscan_clusters || []).forEach(c => {
    const n  = c.complaint_count;
    const sz = Math.min(22 + n * 0.5, 40);
    const m  = L.marker([+c.centroid_lat, +c.centroid_lng], {
      icon: L.divIcon({
        html: `<div class="${dotClass}" style="width:${sz}px;height:${sz}px">${n}</div>`,
        className: '', iconSize: [sz, sz], iconAnchor: [sz / 2, sz / 2],
      }),
      zIndexOffset: 900,
    });
    m._count = n;
    m.on('click', () => showCmpClusterTooltip(state.map, c, pane));
    state.lg.centroids.addLayer(m);
  });
  state.lg.centroids.addTo(state.map);

  // Stats
  updateCmpStats(pane, result);
  updateCmpVpBar(pane);

  // Fit bounds to all complaints if any
  const pts = (result.complaints || []).map(c => [+c.lat, +c.lng]).filter(p => p[0] && p[1]);
  if (pts.length > 0) {
    try { state.map.fitBounds(pts, { padding: [40, 40], maxZoom: 10 }); } catch (_) {}
  }
}

// ── Cluster popup on compare map ───────────────────────────────────────────
function showCmpClusterTooltip(mapInst, c, pane) {
  const topMed = Object.keys(c.top_medicines || {})[0] || '—';
  const color  = pane === 'hist' ? '#38bdf8' : '#fbbf24';
  L.popup({ className: 'lf-tip', closeButton: true })
    .setLatLng([+c.centroid_lat, +c.centroid_lng])
    .setContent(`
      <b style="color:${color}">${c.cluster_id}</b><br>
      ${c.complaint_count} complaints · Sev ${c.severity_score}<br>
      Top: ${topMed}<br>
      Loss: MYR ${(c.total_loss || 0).toLocaleString('en-MY', { minimumFractionDigits: 2 })}
    `)
    .openOn(mapInst);
}

// ── Update stats for a compare pane ───────────────────────────────────────
function updateCmpStats(pane, result) {
  const suffix = pane === 'hist' ? 'hist' : 'cur';
  const clsEl  = document.getElementById(`cmp-${suffix}-cls`);
  const cmpEl  = document.getElementById(`cmp-${suffix}-cmp`);
  if (clsEl) clsEl.textContent = (result.dbscan_clusters || []).length;
  if (cmpEl) cmpEl.textContent = (result.summary?.total_complaints || 0).toLocaleString();
}

// ── Compact viewport bar update ────────────────────────────────────────────
function updateCmpVpBar(pane) {
  const state   = pane === 'hist' ? HIST : CUR;
  const mapInst = state.map;
  const result  = state.result;
  if (!mapInst || !result?.dbscan_clusters) return;

  const suffix   = pane === 'hist' ? 'hist' : 'current';
  const accentClr = pane === 'hist' ? '#38bdf8' : '#fbbf24';
  const bounds   = mapInst.getBounds();

  // Visible clusters
  const vis = (result.dbscan_clusters || [])
    .filter(c => bounds.contains([+c.centroid_lat, +c.centroid_lng]))
    .sort((a, b) => b.severity_score - a.severity_score);

  // Visible complaints + top medicines
  const visCmps = (result.complaints || []).filter(c => bounds.contains([+c.lat, +c.lng]));
  const medCounts = {};
  for (const c of visCmps) {
    if (c.cluster_type !== 'dbscan') continue;
    const med = c.medicine_name || c.medicine_id || 'Unknown';
    medCounts[med] = (medCounts[med] || 0) + 1;
  }
  const topMeds = Object.entries(medCounts).sort((a, b) => b[1] - a[1]).slice(0, 6);

  // Badges
  const cntEl = document.getElementById(`cmp-vp-cnt-${suffix}`);
  const visEl = document.getElementById(`cmp-vp-vis-cmp-${suffix}`);
  if (cntEl) cntEl.textContent = `${vis.length} cluster${vis.length !== 1 ? 's' : ''}`;
  if (visEl) visEl.textContent = `${visCmps.length} complaint${visCmps.length !== 1 ? 's' : ''}`;

  // Cluster cards
  const listEl = document.getElementById(`cmp-vp-list-${suffix}`);
  if (listEl) {
    if (!vis.length) {
      listEl.innerHTML = '<span class="vp-empty">No clusters in view</span>';
    } else {
      const cardCls = pane === 'hist' ? 'ccc-id hist' : 'ccc-id current';
      listEl.innerHTML = vis.map(c => {
        const topMed  = Object.keys(c.top_medicines || {})[0] || '—';
        const fillPct = Math.min(100, Math.round(c.severity_score));
        return `
          <div class="cmp-cluster-card ${pane}" onclick="window._cmpClickCluster('${pane}','${c.cluster_id}')">
            <div class="${cardCls}">${c.cluster_id}</div>
            <div class="ccc-sev-bar"><div class="ccc-sev-fill" style="width:${fillPct}%;background:${accentClr}"></div></div>
            <div class="ccc-cmp">${c.complaint_count} · sev ${c.severity_score}</div>
            <div class="ccc-med" title="${topMed}">${topMed}</div>
          </div>`;
      }).join('');
    }
  }

  // Medicine cards
  const medsEl = document.getElementById(`cmp-vp-meds-${suffix}`);
  if (medsEl) {
    if (!topMeds.length) {
      medsEl.innerHTML = '<span class="vp-empty">No data in view</span>';
    } else {
      medsEl.innerHTML = topMeds.map(([med, cnt]) => `
        <div class="cmp-med-card">
          <div class="cmp-med-name" title="${med}">${med}</div>
          <div class="cmp-med-count" style="color:${accentClr}">${cnt}</div>
          <div class="cmp-med-label">complaints</div>
        </div>`).join('');
    }
  }
}

// Navigate compare map to a cluster
window._cmpClickCluster = function(pane, clusterId) {
  const state  = pane === 'hist' ? HIST : CUR;
  const result = state.result;
  if (!result) return;
  const c = (result.dbscan_clusters || []).find(x => x.cluster_id === clusterId);
  if (!c) return;
  if (c.hull_coords?.length >= 3) {
    state.map.fitBounds(c.hull_coords.map(([lng, lat]) => [lat, lng]), { padding: [40, 40] });
  } else {
    state.map.setView([+c.centroid_lat, +c.centroid_lng], 13);
  }
  showCmpClusterTooltip(state.map, c, pane);
};

})();
