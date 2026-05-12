(function () {
/**
 * map.js — Leaflet implementation
 * Replaces deck.gl entirely. Uses:
 *  - Leaflet core for all map primitives
 *  - leaflet.heat for smooth Canvas heatmap (no WebGL timing issues)
 *  - Leaflet.markercluster for zoom-based centroid aggregation
 */

const API = '/api';

// ── Colours ────────────────────────────────────────────────────────────────
const TYPE_COL = { hospital: '#22c55e', clinic: '#3b82f6', pharmacy: '#a855f7' };

// ── App state ──────────────────────────────────────────────────────────────
const S = {
  facilities:    [],
  complaints:    [],
  suppliers:     [],
  clusterResult: null,
  lineData:      [],
  layerVis: {
    hospital: true, clinic: true, pharmacy: true,
    supplier: true, complaints: true, heatmap: true,
  },
};

// ── Layer references ───────────────────────────────────────────────────────
const LG = {
  buffers:    null,
  facilities: null,
  complaints: null,
  heatmap:    null,   // L.heatLayer — added/removed directly
  hulls:      null,
  centroids:  null,   // L.markerClusterGroup — added/removed directly
  suppliers:  null,
  lines:      null,
};

// ── Tile URLs ──────────────────────────────────────────────────────────────
const TILES = {
  dark:      'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
  light:     'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
  satellite: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
};

// ── State bounding boxes for navigate-to ──────────────────────────────────
const STATE_BOUNDS = {
  'Kuala Lumpur':    [[3.058, 101.626], [3.228, 101.754]],
  'Selangor':        [[2.698, 101.296], [3.839, 101.986]],
  'Johor':           [[1.328, 102.864], [2.544, 104.278]],
  'Penang':          [[5.198, 100.170], [5.567, 100.560]],
  'Perak':           [[3.578, 100.366], [5.847, 101.977]],
  'Kedah':           [[5.528,  99.588], [6.711, 101.176]],
  'Negeri Sembilan': [[2.404, 101.724], [3.208, 102.602]],
  'Melaka':          [[2.081, 101.933], [2.570, 102.566]],
};

let map, currentTile;

// ── Init ───────────────────────────────────────────────────────────────────
function initMap() {
  map = L.map('map', {
    center: [4.0, 109.5], zoom: 6,
    zoomControl: false, attributionControl: false,
  });

  currentTile = L.tileLayer(TILES.dark, { subdomains: 'abcd', maxZoom: 20 });
  currentTile.addTo(map);

  // Ordered layer groups (bottom → top)
  LG.buffers    = L.layerGroup().addTo(map);
  LG.facilities = L.layerGroup().addTo(map);
  LG.complaints = L.layerGroup().addTo(map);
  LG.hulls      = L.layerGroup().addTo(map);
  LG.suppliers  = L.layerGroup().addTo(map);
  LG.lines      = L.layerGroup().addTo(map);
  // heatmap and centroids are added above these when created

  map.on('moveend zoomend', updateStats);

  // Zoom / reset controls
  document.getElementById('btn-zi') ?.addEventListener('click', () => map.zoomIn());
  document.getElementById('btn-zo') ?.addEventListener('click', () => map.zoomOut());
  document.getElementById('btn-rst')?.addEventListener('click', () => map.setView([4.0, 109.5], 6));

  // Run clustering
  document.getElementById('run-btn')?.addEventListener('click', runClustering);

  // Close cluster panel
  document.getElementById('cp-close')?.addEventListener('click', () => {
    S.lineData = [];
    renderLines();
    document.getElementById('cluster-panel').classList.remove('open');
  });

  // Navigate — three separate dropdowns
  const navHandler = e => {
    const val = e.target.value;
    if (!val) return;
    const colon = val.indexOf(':');
    const type  = val.slice(0, colon);
    const key   = val.slice(colon + 1);
    if      (type === 'state'    && STATE_BOUNDS[key]) map.fitBounds(STATE_BOUNDS[key], { padding: [40, 40] });
    else if (type === 'district') navigateToDistrict(key);
    else if (type === 'cluster')  navigateToCluster(key);
  };
  document.getElementById('nav-state')   ?.addEventListener('change', navHandler);
  document.getElementById('nav-district')?.addEventListener('change', navHandler);
  document.getElementById('nav-cluster') ?.addEventListener('change', navHandler);

  // Map style buttons (wired from index.html via window.setMapStyle)
  window._map         = map;
  window.setMapStyle  = setMapStyle;

  wireLayerToggles();
  loadInitialData();
}

// ── Map style ──────────────────────────────────────────────────────────────
function setMapStyle(style) {
  map.removeLayer(currentTile);
  currentTile = L.tileLayer(TILES[style], {
    subdomains: style === 'satellite' ? '' : 'abcd',
    maxZoom: 20,
  });
  currentTile.addTo(map);
  currentTile.bringToBack();
  document.querySelectorAll('.style-btn')
    .forEach(b => b.classList.toggle('active', b.dataset.style === style));
}

// ── Render: buffers ────────────────────────────────────────────────────────
function renderBuffers() {
  LG.buffers.clearLayers();
  if (!S.clusterResult) return;
  const { hospital_buffer_m, clinic_buffer_m, pharmacy_buffer_m } = S.clusterResult.params;
  const radii = { hospital: hospital_buffer_m, clinic: clinic_buffer_m, pharmacy: pharmacy_buffer_m };

  S.facilities.forEach(f => {
    if (!S.layerVis[f.type]) return;
    L.circle([+f.lat, +f.lng], {
      radius: radii[f.type],
      color: TYPE_COL[f.type], weight: 1.5,
      fillColor: TYPE_COL[f.type], fillOpacity: 0.04,
      interactive: false,
    }).addTo(LG.buffers);
  });
}

// ── Render: facility dots ──────────────────────────────────────────────────
function renderFacilities() {
  LG.facilities.clearLayers();
  S.facilities.forEach(f => {
    if (!S.layerVis[f.type]) return;
    L.circleMarker([+f.lat, +f.lng], {
      radius: f.type === 'hospital' ? 8 : 6,
      fillColor: TYPE_COL[f.type],
      color: 'rgba(255,255,255,0.45)', weight: 1, fillOpacity: 0.9,
    })
    .bindTooltip(`<b>${f.name}</b><br><small>${f.type} · ${f.district || ''}</small>`,
                 { sticky: true, className: 'lf-tip' })
    .addTo(LG.facilities);
  });
}

// ── Render: complaint dots ─────────────────────────────────────────────────
function renderComplaints() {
  LG.complaints.clearLayers();
  if (!S.layerVis.complaints) return;
  const data = S.clusterResult ? S.clusterResult.complaints : S.complaints;

  data.forEach(c => {
    const inside = S.clusterResult && c.inside_buffer;
    L.circleMarker([+c.lat, +c.lng], {
      radius: 4,
      fillColor: inside ? '#ffffff' : '#f97316',
      color: 'transparent', fillOpacity: inside ? 0.3 : 0.85,
    })
    .on('click', () => onComplaintClick(c))
    .addTo(LG.complaints);
  });
}

// ── Render: heatmap ────────────────────────────────────────────────────────
// Uses leaflet.heat — Canvas-based, no WebGL timing issues.
// Cluster centroids are weighted by complaint count; noise points weight 0.15.
function renderHeatmap() {
  if (LG.heatmap) { map.removeLayer(LG.heatmap); LG.heatmap = null; }
  if (!S.layerVis.heatmap || !S.clusterResult) return;

  const maxN = Math.max(...S.clusterResult.dbscan_clusters.map(c => c.complaint_count), 1);

  const pts = [
    ...S.clusterResult.dbscan_clusters.map(c => [
      parseFloat(c.centroid_lat), parseFloat(c.centroid_lng),
      c.complaint_count / maxN,
    ]),
    ...S.clusterResult.complaints
      .filter(c => c.cluster_type === 'noise')
      .map(c => [parseFloat(c.lat), parseFloat(c.lng), 0.15]),
  ];
  if (!pts.length) return;

  LG.heatmap = L.heatLayer(pts, {
    radius: 55, blur: 12, maxZoom: 17, max: 0.25,
    gradient: {
      0.0:  '#0a2a6e',
      0.2:  '#1a6fa8',
      0.4:  '#29c4a9',
      0.6:  '#fde84a',
      0.8:  '#f97316',
      1.0:  '#e31a1c',
    },
  });
  LG.heatmap.addTo(map);
  // Ensure heatmap sits below cluster markers
  if (LG.centroids) LG.centroids.bringToFront();
}

// ── Render: convex hulls + markercluster centroids ─────────────────────────
function renderClusters() {
  LG.hulls.clearLayers();
  if (LG.centroids) { map.removeLayer(LG.centroids); LG.centroids = null; }
  if (!S.clusterResult?.dbscan_clusters.length) return;

  // Convex hulls
  S.clusterResult.dbscan_clusters.forEach(c => {
    if (c.hull_coords?.length >= 3) {
      const latlngs = c.hull_coords.map(([lng, lat]) => [lat, lng]);
      L.polygon(latlngs, {
        color: '#fbbf24', weight: 1.5,
        fillColor: '#fbbf24', fillOpacity: 0.09,
      })
      .on('click', () => onCentroidClick(c))
      .addTo(LG.hulls);
    }
  });

  // Marker cluster group — merges nearby centroids when zoomed out
  LG.centroids = L.markerClusterGroup({
    maxClusterRadius: 70,
    animate: true,
    animateAddingMarkers: false,
    spiderfyOnMaxZoom: false,
    showCoverageOnHover: false,
    zoomToBoundsOnClick: true,
    iconCreateFunction: cluster => {
      // Aggregated icon: sum complaint counts of child clusters
      const total = cluster.getAllChildMarkers()
        .reduce((s, m) => s + (m._count || 0), 0);
      const sz = Math.min(28 + Math.log2(total + 1) * 7, 58);
      return L.divIcon({
        html: `<div class="centroid-agg" style="width:${sz}px;height:${sz}px">${total}</div>`,
        className: '', iconSize: [sz, sz], iconAnchor: [sz / 2, sz / 2],
      });
    },
  });

  S.clusterResult.dbscan_clusters.forEach(c => {
    const n  = c.complaint_count;
    const sz = Math.min(24 + n * 0.5, 42);
    const m  = L.marker([+c.centroid_lat, +c.centroid_lng], {
      icon: L.divIcon({
        html: `<div class="centroid-dot" style="width:${sz}px;height:${sz}px">${n}</div>`,
        className: '', iconSize: [sz, sz], iconAnchor: [sz / 2, sz / 2],
      }),
      zIndexOffset: 900,
    });
    m._count = n;
    m.on('click', () => onCentroidClick(c));
    LG.centroids.addLayer(m);
  });

  LG.centroids.addTo(map);

  // Sync cluster navigate dropdown every time clusters are rendered
  const clsSel = document.getElementById('nav-cluster');
  if (clsSel) {
    const clusters = S.clusterResult?.dbscan_clusters ?? [];
    if (!clusters.length) {
      clsSel.innerHTML = '<option value="">No clusters available</option>';
    } else {
      clsSel.innerHTML = '<option value="">Select cluster</option>';
      [...clusters]
        .sort((a, b) => b.severity_score - a.severity_score)
        .forEach(c =>
          clsSel.insertAdjacentHTML('beforeend',
            `<option value="cluster:${c.cluster_id}">${c.cluster_id} · ${c.complaint_count} complaints</option>`)
        );
    }
  }
}

// ── Render: suppliers ─────────────────────────────────────────────────────
function renderSuppliers() {
  LG.suppliers.clearLayers();
  if (!S.layerVis.supplier) return;
  S.suppliers.forEach(s => {
    L.circleMarker([+s.lat, +s.lng], {
      radius: 5,
      fillColor: s.is_suspicious ? '#ef4444' : '#ec4899',
      color: 'rgba(255,255,255,0.45)', weight: 1, fillOpacity: 0.9,
    })
    .bindTooltip(`<b>${s.name}</b><br><small>${s.is_suspicious ? '⚠ Suspicious' : '✓ Licensed'}</small>`,
                 { sticky: true, className: 'lf-tip' })
    .on('click', () => onSupplierClick(s))
    .addTo(LG.suppliers);
  });
}

// ── Render: connection lines ───────────────────────────────────────────────
function renderLines() {
  LG.lines.clearLayers();
  S.lineData.forEach(l => {
    L.polyline([l.from, l.to], {
      color:     l.suspicious ? '#ef4444' : 'rgba(255,255,255,0.5)',
      weight:    1.5, opacity: 0.85,
      dashArray: l.suspicious ? null : '5 4',
    }).addTo(LG.lines);
  });
}

// ── Render all ─────────────────────────────────────────────────────────────
function renderAll() {
  renderBuffers();
  renderFacilities();
  renderComplaints();
  renderHeatmap();
  renderClusters();
  renderSuppliers();
  renderLines();
  updateStats();
}

// ── Stats bar ──────────────────────────────────────────────────────────────
function updateStats() {
  if (!map) return;
  const bounds  = map.getBounds();
  const cr      = S.clusterResult;
  const allCmps = cr ? cr.complaints  : S.complaints;
  const allCls  = cr ? cr.dbscan_clusters : [];

  const visCmps = allCmps.filter(c => bounds.contains([+c.lat, +c.lng]));
  const visCls  = allCls .filter(c => bounds.contains([+c.centroid_lat, +c.centroid_lng]));
  const visLoss = visCmps.reduce((a, c) => a + (c.estimated_loss || 0), 0);

  const el = id => document.getElementById(id);
  el('stat-total-cmp')?.nodeType && (el('stat-total-cmp').textContent = allCmps.length.toLocaleString());
  el('stat-vis-cmp')  && (el('stat-vis-cmp').textContent  = visCmps.length.toLocaleString());
  el('stat-total-cls')&& (el('stat-total-cls').textContent = allCls.length);
  el('stat-vis-cls')  && (el('stat-vis-cls').textContent  = visCls.length);
  el('stat-loss')     && (el('stat-loss').textContent     =
    'RM ' + (visLoss >= 1000 ? (visLoss / 1000).toFixed(1) + 'k' : visLoss.toFixed(0)));
}

// ── Click handlers ─────────────────────────────────────────────────────────
function onCentroidClick(cluster) {
  document.getElementById('cp-id')   .textContent = cluster.cluster_id;
  document.getElementById('cp-count').textContent = cluster.complaint_count;
  document.getElementById('cp-loss') .textContent =
    (cluster.total_loss || 0).toLocaleString('en-MY', { minimumFractionDigits: 2 });
  document.getElementById('cp-sev')  .textContent = cluster.severity_score;

  const cmps = (S.clusterResult?.complaints || [])
    .filter(c => c.cluster_id === cluster.cluster_id);

  document.getElementById('cp-cmp-list').innerHTML = cmps.length
    ? cmps.map(c => `
      <div class="cmp-item">
        <div class="cmp-top">
          <span class="cmp-id">${c.complaint_id}</span>
          <span class="cmp-date">${c.date}</span>
        </div>
        <div class="cmp-med">${c.medicine_name || c.medicine_id}
          <span class="tag ${c.verified ? 'tag-verified' : 'tag-unverified'}">
            ${c.verified ? '✓ Verified' : 'Unverified'}
          </span>
        </div>
        <div class="cmp-loss">MYR ${(c.estimated_loss||0).toFixed(2)} · ${c.district||''}, ${c.state||''}</div>
      </div>`).join('')
    : '<div class="empty-hint">No complaints</div>';

  const sups = cluster.nearby_suppliers || [];
  document.getElementById('cp-sup-list').innerHTML = sups.length
    ? sups.map(s => `
      <div class="sup-item">
        <div class="sup-name">${s.name}</div>
        <div class="sup-meta">${s.city || ''}, ${s.state || ''}</div>
        <span class="sup-flag ${s.is_suspicious ? 'bad' : 'ok'}">
          ${s.is_suspicious ? '⚠ Suspicious' : '✓ Licensed'}
        </span>
      </div>`).join('')
    : '<div class="empty-hint">No linked suppliers</div>';

  S.lineData = sups.map(s => ({
    from:      [+cluster.centroid_lat, +cluster.centroid_lng],
    to:        [+s.lat, +s.lng],
    suspicious: s.is_suspicious,
  }));
  renderLines();
  document.getElementById('cluster-panel').classList.add('open');
}

async function onSupplierClick(supplier) {
  try {
    const facs = await (await fetch(`${API}/suppliers/${supplier.supplier_id}/facilities`)).json();
    S.lineData = facs.map(f => ({
      from: [+supplier.lat, +supplier.lng],
      to:   [+f.lat, +f.lng],
      suspicious: false,
    }));
    renderLines();
  } catch (e) { console.error('Supplier click:', e); }
}

function onComplaintClick(c) {
  if (c.cluster_type === 'dbscan' && S.clusterResult) {
    const cl = S.clusterResult.dbscan_clusters.find(x => x.cluster_id === c.cluster_id);
    if (cl) onCentroidClick(cl);
  }
}

// ── Data fetching ──────────────────────────────────────────────────────────
async function loadInitialData() {
  try {
    const [fR, cR, sR, flR, clR] = await Promise.all([
      fetch(`${API}/facilities`),
      fetch(`${API}/complaints`),
      fetch(`${API}/suppliers`),
      fetch(`${API}/filters`),
      fetch(`${API}/clusters/latest`),   // ← load cached cluster from disk
    ]);
    S.facilities = await fR.json();
    S.complaints = await cR.json();
    S.suppliers  = await sR.json();
    populateDropdowns(await flR.json());
    populateNavigate();   // districts from loaded data

    const cached = await clR.json();
    if (cached?.summary) {
      S.clusterResult = cached;
      if (cached.auto_dbscan && window.updateAutoParams)
        window.updateAutoParams(cached.auto_dbscan);
    }

    renderAll();
  } catch (e) { console.error('Load failed:', e); }
}

async function runClustering() {
  const btn = document.getElementById('run-btn');
  btn.classList.add('busy'); btn.textContent = 'Computing…';
  try {
    const res = await fetch(`${API}/clusters`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(window.getBufferParams()),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    S.clusterResult = await res.json();
    S.lineData      = [];
    if (S.clusterResult.auto_dbscan && window.updateAutoParams)
      window.updateAutoParams(S.clusterResult.auto_dbscan);
    renderAll();
  } catch (e) {
    console.error('Clustering:', e);
    alert('Clustering failed — check the console.');
  } finally {
    btn.classList.remove('busy'); btn.textContent = 'Run Clustering';
  }
}

// ── Navigate helpers ───────────────────────────────────────────────────────

function navigateToDistrict(district) {
  // Use facility positions — geographically correct district↔lat/lng mapping
  const pts = S.facilities.filter(f => f.district === district && f.lat && f.lng);
  if (!pts.length) return;
  const lats = pts.map(p => +p.lat), lngs = pts.map(p => +p.lng);
  map.fitBounds([
    [Math.min(...lats) - 0.02, Math.min(...lngs) - 0.02],
    [Math.max(...lats) + 0.02, Math.max(...lngs) + 0.02],
  ], { padding: [60, 60], maxZoom: 13 });  // maxZoom forces Leaflet to zoom in
}

function navigateToCluster(clusterId) {
  const c = S.clusterResult?.dbscan_clusters?.find(x => x.cluster_id === clusterId);
  if (!c) return;
  if (c.hull_coords?.length >= 3) {
    map.fitBounds(c.hull_coords.map(([lng, lat]) => [lat, lng]), { padding: [60, 60] });
  } else {
    map.setView([+c.centroid_lat, +c.centroid_lng], 14);
  }
}

function populateNavigate() {
  // ── Districts ──────────────────────────────────────────────────────────
  const distSel = document.getElementById('nav-district');
  if (distSel) {
    const districts = [...new Set([
      ...S.complaints.map(c => c.district),
      ...S.facilities .map(f => f.district),
    ].filter(Boolean))].sort();
    distSel.innerHTML = '<option value="">Select district</option>';
    districts.forEach(d =>
      distSel.insertAdjacentHTML('beforeend',
        `<option value="district:${d}">${d}</option>`)
    );
  }

  // ── Clusters ───────────────────────────────────────────────────────────
  const clsSel = document.getElementById('nav-cluster');
  if (clsSel) {
    const clusters = S.clusterResult?.dbscan_clusters ?? [];
    if (!clusters.length) {
      clsSel.innerHTML = '<option value="">Run clustering first</option>';
    } else {
      clsSel.innerHTML = '<option value="">Select cluster</option>';
      [...clusters]
        .sort((a, b) => b.severity_score - a.severity_score)
        .forEach(c =>
          clsSel.insertAdjacentHTML('beforeend',
            `<option value="cluster:${c.cluster_id}">${c.cluster_id} · ${c.complaint_count} complaints</option>`)
        );
    }
  }
}


function populateDropdowns(filters) {
  ['map-state','an-state'].forEach(id => {
    const el = document.getElementById(id); if (!el) return;
    (filters.states || []).forEach(s =>
      el.insertAdjacentHTML('beforeend', `<option value="${s}">${s}</option>`));
  });
  ['map-med','an-med'].forEach(id => {
    const el = document.getElementById(id); if (!el) return;
    (filters.medicines || []).forEach(m =>
      el.insertAdjacentHTML('beforeend', `<option value="${m.medicine_id}">${m.name}</option>`));
  });
}

function wireLayerToggles() {
  const MAP = {
    'lyr-hospital':   () => { renderFacilities(); renderBuffers(); },
    'lyr-clinic':     () => { renderFacilities(); renderBuffers(); },
    'lyr-pharmacy':   () => { renderFacilities(); renderBuffers(); },
    'lyr-supplier':   renderSuppliers,
    'lyr-complaints': renderComplaints,
    'lyr-heatmap':    renderHeatmap,
  };
  const KEY = {
    'lyr-hospital': 'hospital', 'lyr-clinic': 'clinic',
    'lyr-pharmacy': 'pharmacy', 'lyr-supplier': 'supplier',
    'lyr-complaints': 'complaints', 'lyr-heatmap': 'heatmap',
  };
  Object.entries(MAP).forEach(([id, fn]) =>
    document.getElementById(id)?.addEventListener('change', e => {
      S.layerVis[KEY[id]] = e.target.checked; fn();
    })
  );
}

document.addEventListener('DOMContentLoaded', initMap);

})(); // end IIFE