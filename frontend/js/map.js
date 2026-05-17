(function () {
/**
 * map.js — Leaflet implementation for the main Map page.
 * Features:
 *  - Facility buffers, complaint dots, heatmap, DBSCAN hulls, centroids
 *  - Viewport Insights bar (updates on pan/zoom, pushes controls up)
 *  - Officer assignment modal
 */

const API = '/api';

const TYPE_COL = { hospital: '#22c55e', clinic: '#3b82f6', pharmacy: '#a855f7' };

// ── App state ──────────────────────────────────────────────────────────────
const S = {
  facilities:    [],
  complaints:    [],
  suppliers:     [],
  clusterResult: null,
  lineData:      [],
  assignments:   {},   // { cluster_id: assignment }
  officers:      [],
  currentCluster: null,
  layerVis: {
    hospital: true, clinic: true, pharmacy: true,
    supplier: true, complaints: true, heatmap: true,
  },
};

const LG = {
  buffers:    null,
  facilities: null,
  complaints: null,
  heatmap:    null,
  hulls:      null,
  centroids:  null,
  suppliers:  null,
  lines:      null,
};

const TILES = {
  dark:      'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
  light:     'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
  satellite: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
};

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
let _vpTimer;

// ── Severity colour ────────────────────────────────────────────────────────
function sevColor(score) {
  if (score >= 75) return '#ef4444';
  if (score >= 50) return '#f97316';
  if (score >= 30) return '#fbbf24';
  return '#22c55e';
}

// ── Init ───────────────────────────────────────────────────────────────────
function initMap() {
  map = L.map('map', {
    center: [4.0, 109.5], zoom: 6,
    zoomControl: false, attributionControl: false,
  });

  currentTile = L.tileLayer(TILES.dark, { subdomains: 'abcd', maxZoom: 20 });
  currentTile.addTo(map);

  LG.buffers    = L.layerGroup().addTo(map);
  LG.facilities = L.layerGroup().addTo(map);
  LG.complaints = L.layerGroup().addTo(map);
  LG.hulls      = L.layerGroup().addTo(map);
  LG.suppliers  = L.layerGroup().addTo(map);
  LG.lines      = L.layerGroup().addTo(map);

  map.on('moveend zoomend', () => {
    updateStats();
    clearTimeout(_vpTimer);
    _vpTimer = setTimeout(updateViewportBar, 250);
  });

  document.getElementById('btn-zi') ?.addEventListener('click', () => map.zoomIn());
  document.getElementById('btn-zo') ?.addEventListener('click', () => map.zoomOut());
  document.getElementById('btn-rst')?.addEventListener('click', () => map.setView([4.0, 109.5], 6));
  document.getElementById('run-btn')?.addEventListener('click', runClustering);

  document.getElementById('cp-close')?.addEventListener('click', () => {
    S.lineData = [];
    renderLines();
    document.getElementById('cluster-panel').classList.remove('open');
  });

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

  window._map        = map;
  window.setMapStyle = setMapStyle;

  wireLayerToggles();
  initViewportBar();
  initOfficerModal();
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
      radius: radii[f.type], color: TYPE_COL[f.type], weight: 1.5,
      fillColor: TYPE_COL[f.type], fillOpacity: 0.04, interactive: false,
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
    gradient: { 0.0:'#0a2a6e', 0.2:'#1a6fa8', 0.4:'#29c4a9', 0.6:'#fde84a', 0.8:'#f97316', 1.0:'#e31a1c' },
  });
  LG.heatmap.addTo(map);
  if (LG.centroids) LG.centroids.bringToFront();
}

// ── Render: clusters ───────────────────────────────────────────────────────
function renderClusters() {
  LG.hulls.clearLayers();
  if (LG.centroids) { map.removeLayer(LG.centroids); LG.centroids = null; }
  if (!S.clusterResult?.dbscan_clusters.length) return;

  S.clusterResult.dbscan_clusters.forEach(c => {
    if (c.hull_coords?.length >= 3) {
      const latlngs = c.hull_coords.map(([lng, lat]) => [lat, lng]);
      const asgn = S.assignments[c.cluster_id];
      const hullColor = asgn?.status === 'completed' ? '#22c55e'
                      : asgn?.status === 'investigating' ? '#38bdf8' : '#fbbf24';
      L.polygon(latlngs, {
        color: hullColor, weight: 1.5,
        fillColor: hullColor, fillOpacity: 0.09,
      })
      .on('click', () => onCentroidClick(c))
      .addTo(LG.hulls);
    }
  });

  LG.centroids = L.markerClusterGroup({
    maxClusterRadius: 70, animate: true, animateAddingMarkers: false,
    spiderfyOnMaxZoom: false, showCoverageOnHover: false,
    zoomToBoundsOnClick: true,
    iconCreateFunction: cluster => {
      const total = cluster.getAllChildMarkers().reduce((s, m) => s + (m._count || 0), 0);
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
    const asgn = S.assignments[c.cluster_id];
    const bg = asgn?.status === 'completed'    ? '#22c55e'
             : asgn?.status === 'investigating' ? '#38bdf8'
             : '#fbbf24';
    const glow = asgn?.status === 'completed'    ? 'rgba(34,197,94,.5)'
               : asgn?.status === 'investigating' ? 'rgba(56,189,248,.5)'
               : 'rgba(251,191,36,.5)';
    const m = L.marker([+c.centroid_lat, +c.centroid_lng], {
      icon: L.divIcon({
        html: `<div class="centroid-dot" style="width:${sz}px;height:${sz}px;background:${bg};box-shadow:0 0 14px ${glow}">${n}</div>`,
        className: '', iconSize: [sz, sz], iconAnchor: [sz / 2, sz / 2],
      }),
      zIndexOffset: 900,
    });
    m._count = n;
    m.on('click', () => onCentroidClick(c));
    LG.centroids.addLayer(m);
  });
  LG.centroids.addTo(map);

  // Sync cluster dropdown
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

// ── Render: lines ─────────────────────────────────────────────────────────
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

function renderAll() {
  renderBuffers();
  renderFacilities();
  renderComplaints();
  renderHeatmap();
  renderClusters();
  renderSuppliers();
  renderLines();
  updateStats();
  updateViewportBar();
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

  document.getElementById('stat-total-cmp') && (document.getElementById('stat-total-cmp').textContent = allCmps.length.toLocaleString());
  document.getElementById('stat-vis-cmp')   && (document.getElementById('stat-vis-cmp').textContent   = visCmps.length.toLocaleString());
  document.getElementById('stat-total-cls') && (document.getElementById('stat-total-cls').textContent = allCls.length);
  document.getElementById('stat-vis-cls')   && (document.getElementById('stat-vis-cls').textContent   = visCls.length);
  document.getElementById('stat-loss')      && (document.getElementById('stat-loss').textContent      =
    'RM ' + (visLoss >= 1000 ? (visLoss / 1000).toFixed(1) + 'k' : visLoss.toFixed(0)));
}

// ══════════════════════════════════════════════════════════════════════════
// VIEWPORT INSIGHTS BAR
// ══════════════════════════════════════════════════════════════════════════

function initViewportBar() {
  const bar    = document.getElementById('vp-bar');
  const toggle = document.getElementById('vp-toggle');
  if (!bar || !toggle) return;

  toggle.addEventListener('click', () => {
    const isOpen = bar.classList.toggle('open');
    // Push layers/controls/legend up when bar is open
    const wrap = document.getElementById('main-map-wrap');
    if (wrap) wrap.style.setProperty('--vp-offset', isOpen ? '160px' : '36px');
    feather.replace({ 'stroke-width': 1.5 });
  });
}

function updateViewportBar() {
  if (!map || !S.clusterResult?.dbscan_clusters) return;
  const bounds = map.getBounds();

  // Clusters whose centroid is in viewport
  const visClusters = S.clusterResult.dbscan_clusters
    .filter(c => bounds.contains([+c.centroid_lat, +c.centroid_lng]))
    .sort((a, b) => b.severity_score - a.severity_score);

  // Top medicines from DBSCAN complaints in viewport
  const medCounts = {};
  for (const c of S.clusterResult.complaints) {
    if (c.cluster_type !== 'dbscan') continue;
    if (!bounds.contains([+c.lat, +c.lng])) continue;
    const med = c.medicine_name || c.medicine_id || 'Unknown';
    medCounts[med] = (medCounts[med] || 0) + 1;
  }
  const topMeds = Object.entries(medCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);

  // Update badges
  const clBadge  = document.getElementById('vp-cluster-badge');
  const medBadge = document.getElementById('vp-meds-badge');
  if (clBadge)  clBadge.textContent  = `${visClusters.length} cluster${visClusters.length !== 1 ? 's' : ''}`;
  if (medBadge) medBadge.textContent = `${topMeds.length} medicine${topMeds.length !== 1 ? 's' : ''}`;

  // Render cluster cards
  const clList = document.getElementById('vp-clusters-list');
  if (clList) {
    if (!visClusters.length) {
      clList.innerHTML = '<span class="vp-empty">No clusters in current view</span>';
    } else {
      clList.innerHTML = visClusters.map(c => {
        const asgn = S.assignments[c.cluster_id];
        const statusCls = asgn ? `status-${asgn.status}` : '';
        const statusDot = asgn
          ? `<span class="vpc-status-dot ${asgn.status}" title="${asgn.status}"></span>`
          : '';
        const topMed = Object.keys(c.top_medicines || {})[0] || '—';
        const fillPct = Math.min(100, Math.round(c.severity_score));
        const fillClr = sevColor(c.severity_score);
        const loss = (c.total_loss || 0) >= 1000
          ? 'RM ' + (c.total_loss / 1000).toFixed(1) + 'k'
          : 'RM ' + (c.total_loss || 0).toFixed(0);
        return `
          <div class="vp-cluster-card ${statusCls}" onclick="window._vpClickCluster('${c.cluster_id}')">
            <div class="vpc-id">${c.cluster_id} ${statusDot}</div>
            <div class="vpc-sev-bar"><div class="vpc-sev-fill" style="width:${fillPct}%;background:${fillClr}"></div></div>
            <div class="vpc-cmp">${c.complaint_count} complaints · sev ${c.severity_score}</div>
            <div class="vpc-med">${topMed}</div>
            <div class="vpc-loss">${loss}</div>
          </div>`;
      }).join('');
    }
  }

  // Render medicine cards
  const medList = document.getElementById('vp-meds-list');
  if (medList) {
    if (!topMeds.length) {
      medList.innerHTML = '<span class="vp-empty">No data in current view</span>';
    } else {
      medList.innerHTML = topMeds.map(([med, cnt]) => `
        <div class="vp-med-card">
          <div class="vpm-name" title="${med}">${med}</div>
          <div class="vpm-count">${cnt}</div>
          <div class="vpm-label">complaints</div>
        </div>`).join('');
    }
  }
}

// Click on a cluster card in the viewport bar
window._vpClickCluster = function(clusterId) {
  const c = S.clusterResult?.dbscan_clusters?.find(x => x.cluster_id === clusterId);
  if (!c) return;
  navigateToCluster(clusterId);
  onCentroidClick(c);
};

// ══════════════════════════════════════════════════════════════════════════
// OFFICER ASSIGNMENT MODAL
// ══════════════════════════════════════════════════════════════════════════

function initOfficerModal() {
  document.getElementById('modal-close')?.addEventListener('click', closeOfficerModal);
  document.getElementById('officer-modal')?.addEventListener('click', e => {
    if (e.target === document.getElementById('officer-modal')) closeOfficerModal();
  });
  document.getElementById('btn-assign-officer')?.addEventListener('click', () => {
    if (S.currentCluster) openOfficerModal(S.currentCluster);
  });
  document.getElementById('btn-complete-raid')?.addEventListener('click', async () => {
    if (!S.currentCluster) return;
    await completeRaid(S.currentCluster.cluster_id);
  });
}

function openOfficerModal(cluster) {
  document.getElementById('modal-cluster-id').textContent   = cluster.cluster_id;
  document.getElementById('modal-cluster-info').textContent =
    `${cluster.complaint_count} complaints · Severity ${cluster.severity_score} · Est. loss MYR ${(cluster.total_loss || 0).toLocaleString('en-MY', { minimumFractionDigits: 2 })}`;

  const list = document.getElementById('officer-list');
  if (!S.officers.length) {
    list.innerHTML = '<div class="placeholder" style="height:80px">No officers loaded</div>';
  } else {
    list.innerHTML = S.officers.map(o => {
      const initials = o.name.replace(/^(Insp\.|DSP|Sgt\.)\s*/i, '').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
      return `
        <div class="officer-row">
          <div class="off-avatar">${initials}</div>
          <div class="off-info">
            <div class="off-name">${o.name}</div>
            <div class="off-meta">${o.department} · Rank: ${o.rank}</div>
          </div>
          <div class="off-state">${o.state}</div>
          <button class="btn-off-assign" onclick="window._assignOfficer('${cluster.cluster_id}','${o.officer_id}','${o.name.replace(/'/g, "\\'")}')">Assign</button>
        </div>`;
    }).join('');
  }

  document.getElementById('officer-modal').classList.add('open');
  feather.replace({ 'stroke-width': 1.5 });
}

function closeOfficerModal() {
  document.getElementById('officer-modal').classList.remove('open');
}

window._assignOfficer = async function(clusterId, officerId, officerName) {
  try {
    const res = await fetch(`${API}/clusters/${clusterId}/assign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ officer_id: officerId }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    S.assignments[clusterId] = data.assignment;
    closeOfficerModal();
    refreshAssignmentUI(clusterId);
    renderClusters();
    updateViewportBar();
  } catch (e) {
    console.error('Assign officer:', e);
  }
};

async function completeRaid(clusterId) {
  try {
    const res = await fetch(`${API}/clusters/${clusterId}/complete`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    S.assignments[clusterId] = data.assignment;
    refreshAssignmentUI(clusterId);
    renderClusters();
    updateViewportBar();
  } catch (e) { console.error('Complete raid:', e); }
}

function refreshAssignmentUI(clusterId) {
  const asgn = S.assignments[clusterId];
  if (!asgn || !S.currentCluster || S.currentCluster.cluster_id !== clusterId) return;

  const badge    = document.getElementById('cp-assign-badge');
  const btnAssign = document.getElementById('btn-assign-officer');
  const btnComplete = document.getElementById('btn-complete-raid');

  if (asgn.status === 'unassigned' || !asgn.officer_id) {
    badge.style.display = 'none';
    btnAssign.style.display = '';
    btnComplete.style.display = 'none';
  } else if (asgn.status === 'investigating') {
    badge.className = 'assign-badge assigned';
    badge.textContent = `Investigating · ${asgn.officer_name}`;
    badge.style.display = '';
    btnAssign.style.display = 'none';
    btnComplete.style.display = '';
  } else if (asgn.status === 'completed') {
    badge.className = 'assign-badge completed';
    badge.textContent = `Raided · ${asgn.officer_name}`;
    badge.style.display = '';
    btnAssign.style.display = 'none';
    btnComplete.style.display = 'none';
  }
}

// ── Click handlers ─────────────────────────────────────────────────────────
function onCentroidClick(cluster) {
  S.currentCluster = cluster;

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
  feather.replace({ 'stroke-width': 1.5 });

  // Refresh assignment status UI
  refreshAssignmentUI(cluster.cluster_id);
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
    const [fR, cR, sR, flR, clR, offR] = await Promise.all([
      fetch(`${API}/facilities`),
      fetch(`${API}/complaints`),
      fetch(`${API}/suppliers`),
      fetch(`${API}/filters`),
      fetch(`${API}/clusters/latest`),
      fetch(`${API}/officers`),
    ]);
    S.facilities = await fR.json();
    S.complaints = await cR.json();
    S.suppliers  = await sR.json();
    S.officers   = await offR.json().catch(() => []);
    populateDropdowns(await flR.json());
    populateNavigate();

    const cached = await clR.json();
    if (cached?.summary) {
      S.clusterResult = cached;
      if (cached.auto_dbscan && window.updateAutoParams)
        window.updateAutoParams(cached.auto_dbscan);
    }

    // Load existing assignments
    try {
      const asgns = await (await fetch(`${API}/assignments`)).json();
      asgns.forEach(a => { S.assignments[a.cluster_id] = a; });
    } catch (_) {}

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
  const pts = S.facilities.filter(f => f.district === district && f.lat && f.lng);
  if (!pts.length) return;
  const lats = pts.map(p => +p.lat), lngs = pts.map(p => +p.lng);
  map.fitBounds([
    [Math.min(...lats) - 0.02, Math.min(...lngs) - 0.02],
    [Math.max(...lats) + 0.02, Math.max(...lngs) + 0.02],
  ], { padding: [60, 60], maxZoom: 13 });
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
  const distSel = document.getElementById('nav-district');
  if (distSel) {
    const districts = [...new Set([
      ...S.complaints.map(c => c.district),
      ...S.facilities .map(f => f.district),
    ].filter(Boolean))].sort();
    distSel.innerHTML = '<option value="">Select district</option>';
    districts.forEach(d =>
      distSel.insertAdjacentHTML('beforeend', `<option value="district:${d}">${d}</option>`)
    );
  }
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
  ['an-state'].forEach(id => {
    const el = document.getElementById(id); if (!el) return;
    (filters.states || []).forEach(s =>
      el.insertAdjacentHTML('beforeend', `<option value="${s}">${s}</option>`));
  });
  ['an-med'].forEach(id => {
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

// Expose for compare page to read current cluster result
window._mapState = S;

})();
