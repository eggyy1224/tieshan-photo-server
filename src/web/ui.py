"""Single-page HTML application for Photo Annotation Web UI.

Returns a complete HTML string with embedded CSS and vanilla JS.
No frameworks, no build step.
"""

from __future__ import annotations


def get_html() -> str:
    return _HTML


_HTML = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>鐵山誌 — 照片人臉標註</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #1a1a2e; color: #e0e0e0;
  height: 100vh; overflow: hidden;
  display: flex; flex-direction: column;
}

/* ── Top Bar ────────────────────────────────────────────────── */
.topbar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 16px; background: #16213e;
  border-bottom: 1px solid #333;
  flex-shrink: 0;
}
.topbar h1 { font-size: 16px; font-weight: 600; white-space: nowrap; }
.topbar select, .topbar input[type="checkbox"] {
  background: #0f3460; border: 1px solid #444; color: #e0e0e0;
  padding: 4px 8px; border-radius: 4px; font-size: 13px;
}
.topbar label { font-size: 13px; cursor: pointer; user-select: none; }
.topbar .stats { margin-left: auto; font-size: 12px; color: #888; white-space: nowrap; }
.topbar .photo-progress {
  font-size: 12px; padding: 3px 8px; border-radius: 4px;
  background: #0f3460; display: none;
}
.topbar .photo-progress .done { color: #2ecc71; }
.topbar .photo-progress .pending { color: #e67e22; }

/* ── Main Layout ────────────────────────────────────────────── */
.main { display: flex; flex: 1; overflow: hidden; }

/* ── Left Panel: Photo List ─────────────────────────────────── */
.photo-list {
  width: 260px; min-width: 200px;
  border-right: 1px solid #333;
  display: flex; flex-direction: column;
  background: #16213e;
}
.photo-list-header { padding: 8px; border-bottom: 1px solid #333; }
.photo-list-header input {
  width: 100%; padding: 5px 8px; border-radius: 4px;
  background: #0f3460; border: 1px solid #444; color: #e0e0e0;
  font-size: 13px;
}
.photo-list-items { flex: 1; overflow-y: auto; }
.photo-item {
  padding: 6px 10px; cursor: pointer;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  font-size: 13px; display: flex; align-items: center; gap: 6px;
}
.photo-item:hover { background: #0f3460; }
.photo-item.active { background: #1a5276; border-left: 3px solid #3498db; }
.photo-item .name {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;
  min-width: 0;
}
.photo-item .badge {
  border-radius: 10px; padding: 1px 7px;
  font-size: 11px; white-space: nowrap; font-weight: 600;
}
.photo-item .badge.all-done { background: #1e6e3e; color: #8f8; }
.photo-item .badge.has-unid { background: #b45309; color: #fed; }
.photo-item .badge.no-face { background: #333; color: #777; }

/* ── Center: Canvas ─────────────────────────────────────────── */
.canvas-area {
  flex: 1; position: relative; overflow: hidden;
  display: flex; align-items: center; justify-content: center;
  background: #111;
}
.canvas-area canvas { max-width: 100%; max-height: 100%; cursor: crosshair; }
.canvas-area .no-photo { color: #555; font-size: 18px; }
.canvas-area .loading-overlay {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  color: #888; font-size: 15px; display: none;
}

/* ── Right Panel: Face Inspector ────────────────────────────── */
.face-panel {
  width: 340px; min-width: 300px;
  border-left: 1px solid #333;
  display: flex; flex-direction: column;
  background: #16213e;
}
.face-panel-header {
  padding: 10px 12px; border-bottom: 1px solid #333;
  font-size: 14px; font-weight: 600;
  display: flex; justify-content: space-between; align-items: center;
}
.face-panel-header .progress-pill {
  font-size: 11px; font-weight: 400; padding: 2px 8px;
  border-radius: 10px; background: #0f3460;
}
.face-section-label {
  padding: 5px 12px; font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.5px;
  color: #888; background: #111; border-bottom: 1px solid #222;
}
.face-section-label.unid { color: #e67e22; }
.face-section-label.auto { color: #f39c12; }
.face-section-label.anchored { color: #2ecc71; }

#faceCards { flex: 1; overflow-y: auto; }

/* Compact face row (default for anchored) */
.face-row {
  display: flex; align-items: center; gap: 8px;
  padding: 5px 10px; border-bottom: 1px solid rgba(255,255,255,0.04);
  cursor: pointer; font-size: 12px;
}
.face-row:hover { background: #0f3460; }
.face-row.selected { background: #1a3a5c; }
.face-row .face-crop-sm {
  width: 36px; height: 36px; border-radius: 3px;
  object-fit: cover; flex-shrink: 0;
}
.face-row .face-crop-sm.anchor { border: 2px solid #2ecc71; }
.face-row .face-crop-sm.auto-match { border: 2px solid #f39c12; }
.face-row .face-crop-sm.unid { border: 2px solid #555; }
.face-row .row-label { color: #666; font-size: 11px; width: 28px; flex-shrink: 0; }
.face-row .row-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.face-row .row-name.is-anchor { color: #2ecc71; }
.face-row .row-name.is-auto { color: #f39c12; }
.face-row .row-name.is-unid { color: #999; }
.face-row .row-actions { display: flex; gap: 4px; flex-shrink: 0; }

/* Expanded face card */
.face-card-expanded {
  padding: 10px; border-bottom: 1px solid #222;
  background: #1a2a44;
}
.face-card-expanded .face-top {
  display: flex; gap: 10px; margin-bottom: 8px;
}
.face-card-expanded .face-crop-lg {
  width: 100px; height: 100px; border-radius: 6px;
  object-fit: cover; flex-shrink: 0;
}
.face-card-expanded .face-crop-lg.anchor { border: 3px solid #2ecc71; }
.face-card-expanded .face-crop-lg.auto-match { border: 3px solid #f39c12; }
.face-card-expanded .face-crop-lg.unid { border: 3px solid #555; }
.face-card-expanded .face-info { flex: 1; font-size: 12px; }
.face-card-expanded .face-info .lbl { color: #888; }
.face-card-expanded .face-info .person-name {
  font-size: 15px; font-weight: 600; margin: 2px 0 4px;
}
.face-card-expanded .face-info .person-name.anchored { color: #2ecc71; }
.face-card-expanded .face-info .person-name.auto { color: #f39c12; }

/* Matches grid */
.match-grid { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.match-card {
  display: flex; flex-direction: column; align-items: center;
  width: 80px; cursor: pointer; padding: 4px;
  border-radius: 6px; border: 2px solid transparent;
  transition: border-color 0.15s;
}
.match-card:hover { border-color: #3498db; background: rgba(52,152,219,0.1); }
.match-card img {
  width: 64px; height: 64px; border-radius: 4px;
  object-fit: cover;
}
.match-card .m-name { font-size: 11px; text-align: center; margin-top: 3px; font-weight: 500; }
.match-card .m-score { font-size: 10px; }
.match-card .m-score.HIGH { color: #2ecc71; }
.match-card .m-score.MEDIUM { color: #f39c12; }
.match-card .m-score.LOW { color: #e74c3c; }
.match-card .m-btn {
  margin-top: 3px; padding: 2px 12px; border-radius: 3px;
  background: #27ae60; color: #fff; border: none; cursor: pointer;
  font-size: 11px; font-weight: 600;
}
.match-card .m-btn:hover { background: #2ecc71; }

/* Manual assign */
.manual-assign { margin-top: 8px; }
.manual-assign select {
  width: 100%; padding: 5px 8px; border-radius: 4px;
  background: #0f3460; border: 1px solid #444; color: #e0e0e0;
  font-size: 12px;
}

/* Action buttons */
.btn-sm {
  padding: 2px 8px; border-radius: 3px; cursor: pointer;
  font-size: 10px; border: none; font-weight: 600;
}
.btn-clear { background: #7f1d1d; color: #fca5a5; }
.btn-clear:hover { background: #991b1b; }
.btn-undo { background: #7f1d1d; color: #fca5a5; }
.btn-undo:hover { background: #991b1b; }

/* ── Bottom Bar: Person Reference ───────────────────────────── */
.person-bar {
  flex-shrink: 0; border-top: 1px solid #333;
  background: #16213e; padding: 6px 10px;
  overflow-x: auto; white-space: nowrap;
  display: flex; gap: 8px; align-items: center;
}
.person-ref {
  display: inline-flex; flex-direction: column; align-items: center;
  cursor: pointer; flex-shrink: 0;
}
.person-ref img {
  width: 48px; height: 48px; border-radius: 4px;
  object-fit: cover; border: 2px solid transparent;
}
.person-ref img:hover { border-color: #3498db; }
.person-ref .pname { font-size: 10px; text-align: center; margin-top: 2px; }

/* Toast notifications */
.toast {
  position: fixed; bottom: 20px; right: 20px;
  background: #27ae60; color: #fff;
  padding: 10px 20px; border-radius: 6px;
  font-size: 14px; z-index: 1000;
  opacity: 0; transition: opacity 0.3s;
  pointer-events: none;
}
.toast.show { opacity: 1; }
.toast.error { background: #c0392b; }
</style>
</head>
<body>

<!-- Top Bar -->
<div class="topbar">
  <h1>鐵山誌照片標註</h1>
  <select id="sourceFilter">
    <option value="">所有來源</option>
  </select>
  <label>
    <input type="checkbox" id="unidFilter"> 只看未辨識
  </label>
  <span class="photo-progress" id="photoProgress"></span>
  <div class="stats" id="statsBar">載入中...</div>
</div>

<!-- Main 3-column layout -->
<div class="main">
  <!-- Left: Photo list -->
  <div class="photo-list">
    <div class="photo-list-header">
      <input type="text" id="photoSearch" placeholder="搜尋檔名...">
    </div>
    <div class="photo-list-items" id="photoListItems"></div>
  </div>

  <!-- Center: Canvas -->
  <div class="canvas-area" id="canvasArea">
    <div class="no-photo" id="noPhoto">← 選擇一張照片</div>
    <canvas id="mainCanvas" style="display:none"></canvas>
    <div class="loading-overlay" id="loadingOverlay">載入中...</div>
  </div>

  <!-- Right: Face inspector -->
  <div class="face-panel" id="facePanel">
    <div class="face-panel-header">
      <span>臉部檢視</span>
      <span class="progress-pill" id="facePill"></span>
    </div>
    <div id="faceCards">
      <div style="padding:12px;color:#666;font-size:13px;">選擇照片後顯示臉部資訊</div>
    </div>
  </div>
</div>

<!-- Bottom: Person reference bar -->
<div class="person-bar" id="personBar"></div>

<!-- Toast -->
<div class="toast" id="toast"></div>

<script>
// ── State ──────────────────────────────────────────────────────────
const S = {
  photos: [],
  allPhotos: [],
  currentPhoto: null,
  currentPhotoData: null,
  currentImage: null,
  persons: [],
  personsMap: {},
  selectedFaceId: null,
  expandedFaceId: null,
  hoveredFaceIdx: -1,
};

// ── API ───────────────────────────────────────────────────────────
async function fetchJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// ── Toast ─────────────────────────────────────────────────────────
function toast(msg, isError = false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show' + (isError ? ' error' : '');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.className = 'toast', 3000);
}

// ── Init ──────────────────────────────────────────────────────────
async function init() {
  await Promise.all([loadSourceDirs(), loadPersons()]);
  await loadPhotos();
  setupEvents();
}

async function loadSourceDirs() {
  const data = await fetchJSON('/api/source_dirs');
  const sel = document.getElementById('sourceFilter');
  for (const d of data.source_dirs) {
    const opt = document.createElement('option');
    opt.value = d.source_dir;
    opt.textContent = `${d.source_dir} (${d.count})`;
    sel.appendChild(opt);
  }
}

async function loadPersons() {
  const data = await fetchJSON('/api/persons');
  S.persons = data.persons;
  S.personsMap = {};
  for (const p of S.persons) S.personsMap[p.person_id] = p;
  renderPersonBar();
}

function renderPersonBar() {
  const bar = document.getElementById('personBar');
  bar.innerHTML = '';
  const withAnchors = S.persons.filter(p => p.anchor_count > 0);
  for (const p of withAnchors) {
    const div = document.createElement('div');
    div.className = 'person-ref';
    div.innerHTML = `
      <img src="/api/person/${p.person_id}/portrait" alt="${p.display_name}"
           onerror="this.style.display='none'">
      <span class="pname">${p.display_name}</span>
    `;
    bar.appendChild(div);
  }
}

// ── Photos ────────────────────────────────────────────────────────
async function loadPhotos() {
  const source = document.getElementById('sourceFilter').value;
  const unid = document.getElementById('unidFilter').checked;
  let url = '/api/photos?limit=1000';
  if (source) url += `&source_dir=${encodeURIComponent(source)}`;
  if (unid) url += '&has_unidentified=1';
  const data = await fetchJSON(url);
  S.allPhotos = data.photos;
  S.photos = data.photos;
  document.getElementById('statsBar').textContent = `${data.total} 張照片`;
  filterAndRenderPhotos();
}

function filterAndRenderPhotos() {
  const q = document.getElementById('photoSearch').value.toLowerCase();
  S.photos = q
    ? S.allPhotos.filter(p => p.filename.toLowerCase().includes(q))
    : S.allPhotos;
  renderPhotoList();
}

function renderPhotoList() {
  const container = document.getElementById('photoListItems');
  container.innerHTML = '';
  for (const p of S.photos) {
    const div = document.createElement('div');
    const isActive = S.currentPhoto && S.currentPhoto.photo_id === p.photo_id;
    div.className = 'photo-item' + (isActive ? ' active' : '');
    const fc = p.face_count || 0;
    const unid = p.unid_count || 0;
    const anchored = p.anchor_count || 0;
    let badgeClass, badgeText;
    if (fc === 0) {
      badgeClass = 'badge no-face'; badgeText = '0';
    } else if (unid === 0) {
      badgeClass = 'badge all-done'; badgeText = `✓${fc}`;
    } else {
      badgeClass = 'badge has-unid'; badgeText = `${unid}/${fc}`;
    }
    div.innerHTML = `
      <span class="name" title="${p.rel_path}">${p.filename}</span>
      <span class="${badgeClass}">${badgeText}</span>
    `;
    div.onclick = () => selectPhoto(p);
    container.appendChild(div);
  }
}

// ── Select Photo ──────────────────────────────────────────────────
async function selectPhoto(photo) {
  S.currentPhoto = photo;
  S.selectedFaceId = null;
  S.expandedFaceId = null;
  S.hoveredFaceIdx = -1;
  renderPhotoList();

  const canvas = document.getElementById('mainCanvas');
  const loading = document.getElementById('loadingOverlay');
  document.getElementById('noPhoto').style.display = 'none';
  canvas.style.display = 'none';
  loading.style.display = 'block';

  const [photoData, img] = await Promise.all([
    fetchJSON(`/api/photo/${photo.photo_id}`),
    loadImage(`/api/image/${photo.photo_id}?max_dim=2048`),
  ]);

  S.currentPhotoData = photoData;
  S.currentImage = img;

  loading.style.display = 'none';
  canvas.style.display = 'block';

  // Sort faces: unidentified first, then auto, then anchored
  sortFaces();

  drawCanvas();
  renderFaceCards();
  updatePhotoProgress();
}

function sortFaces() {
  if (!S.currentPhotoData) return;
  const faces = S.currentPhotoData.faces;
  const order = f => {
    if (!f.person_id) return 0;          // unidentified first
    if (f.match_method !== 'anchor') return 1;  // auto-match second
    return 2;                             // anchored last
  };
  faces.sort((a, b) => order(a) - order(b) || b.det_score - a.det_score);
}

function updatePhotoProgress() {
  const pp = document.getElementById('photoProgress');
  const pill = document.getElementById('facePill');
  if (!S.currentPhotoData) {
    pp.style.display = 'none';
    pill.textContent = '';
    return;
  }
  const faces = S.currentPhotoData.faces;
  const total = faces.length;
  const anchored = faces.filter(f => f.match_method === 'anchor').length;
  const autoM = faces.filter(f => f.person_id && f.match_method !== 'anchor').length;
  const unid = total - anchored - autoM;

  pp.style.display = 'inline';
  pp.innerHTML = `<span class="done">${anchored} 錨定</span> · <span class="pending">${unid} 待辨識</span>`;

  pill.innerHTML = unid > 0
    ? `<span style="color:#e67e22">${unid}</span>/${total}`
    : `<span style="color:#2ecc71">✓</span> ${total}`;
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

// ── Canvas Drawing ────────────────────────────────────────────────
function drawCanvas() {
  const canvas = document.getElementById('mainCanvas');
  const area = document.getElementById('canvasArea');
  const img = S.currentImage;
  if (!img) return;

  const areaW = area.clientWidth;
  const areaH = area.clientHeight;
  const scale = Math.min(areaW / img.width, areaH / img.height, 1);
  const cw = Math.floor(img.width * scale);
  const ch = Math.floor(img.height * scale);

  canvas.width = cw;
  canvas.height = ch;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0, cw, ch);

  if (!S.currentPhotoData) return;
  const faces = S.currentPhotoData.faces;

  // Adaptive font size based on image size
  const baseFontSize = Math.max(11, Math.min(16, cw / 90));

  for (let i = 0; i < faces.length; i++) {
    const f = faces[i];
    const [bx, by, bw, bh] = f.bbox;
    const x = bx * cw, y = by * ch, w = bw * cw, h = bh * ch;

    let color, lineWidth, dash;
    if (f.match_method === 'anchor') {
      color = '#2ecc71'; lineWidth = 2; dash = [];
    } else if (f.person_id) {
      color = '#f39c12'; lineWidth = 2; dash = [5, 3];
    } else {
      color = 'rgba(255,255,255,0.5)'; lineWidth = 1.5; dash = [];
    }

    const isHighlight = (i === S.hoveredFaceIdx || f.face_id === S.selectedFaceId);
    if (isHighlight) {
      color = '#3498db'; lineWidth = 3; dash = [];
      // Glow effect
      ctx.shadowColor = '#3498db';
      ctx.shadowBlur = 8;
    }

    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.setLineDash(dash);
    ctx.strokeRect(x, y, w, h);
    ctx.shadowBlur = 0;
    ctx.setLineDash([]);

    // Label background
    const pname = f.person_id ? (S.personsMap[f.person_id]?.display_name || '') : '';
    const label = pname ? `#${i+1} ${pname}` : `#${i+1}`;
    ctx.font = `bold ${baseFontSize}px sans-serif`;
    const tm = ctx.measureText(label);
    const lh = baseFontSize + 4;
    const lx = x, ly = y - 2;

    // Semi-transparent background
    ctx.fillStyle = isHighlight ? 'rgba(52,152,219,0.85)' :
      (f.match_method === 'anchor' ? 'rgba(39,174,96,0.8)' :
       f.person_id ? 'rgba(243,156,18,0.8)' : 'rgba(0,0,0,0.6)');
    ctx.fillRect(lx, ly - lh, tm.width + 8, lh);
    ctx.fillStyle = '#fff';
    ctx.fillText(label, lx + 4, ly - 4);
  }
}

// ── Face Cards (sectioned, compact/expand) ────────────────────────
function renderFaceCards() {
  const container = document.getElementById('faceCards');
  if (!S.currentPhotoData) {
    container.innerHTML = '<div style="padding:12px;color:#666">無資料</div>';
    return;
  }

  const faces = S.currentPhotoData.faces;
  if (faces.length === 0) {
    container.innerHTML = '<div style="padding:12px;color:#666">此照片無偵測到臉部</div>';
    return;
  }

  // Group faces
  const unidFaces = faces.filter(f => !f.person_id);
  const autoFaces = faces.filter(f => f.person_id && f.match_method !== 'anchor');
  const anchoredFaces = faces.filter(f => f.match_method === 'anchor');

  container.innerHTML = '';

  // Section: Unidentified
  if (unidFaces.length > 0) {
    const sec = document.createElement('div');
    sec.className = 'face-section-label unid';
    sec.textContent = `待辨識 (${unidFaces.length})`;
    container.appendChild(sec);
    for (const f of unidFaces) container.appendChild(buildFaceEntry(f, faces));
  }

  // Section: Auto-matched
  if (autoFaces.length > 0) {
    const sec = document.createElement('div');
    sec.className = 'face-section-label auto';
    sec.textContent = `自動匹配 (${autoFaces.length})`;
    container.appendChild(sec);
    for (const f of autoFaces) container.appendChild(buildFaceEntry(f, faces));
  }

  // Section: Anchored
  if (anchoredFaces.length > 0) {
    const sec = document.createElement('div');
    sec.className = 'face-section-label anchored';
    sec.textContent = `已錨定 (${anchoredFaces.length})`;
    container.appendChild(sec);
    for (const f of anchoredFaces) container.appendChild(buildFaceEntry(f, faces));
  }
}

function buildFaceEntry(f, allFaces) {
  const idx = allFaces.indexOf(f);
  const isExpanded = (f.face_id === S.expandedFaceId);
  const isSelected = (f.face_id === S.selectedFaceId);
  const isAnchored = f.match_method === 'anchor';
  const isAutoMatch = f.person_id && !isAnchored;
  const personName = f.person_id
    ? (S.personsMap[f.person_id]?.display_name || f.person_id) : '未辨識';

  if (isExpanded) {
    return buildExpandedCard(f, idx, isAnchored, isAutoMatch, personName);
  }

  // Compact row
  const row = document.createElement('div');
  row.className = 'face-row' + (isSelected ? ' selected' : '');
  row.dataset.faceId = f.face_id;

  const cropClass = isAnchored ? 'anchor' : isAutoMatch ? 'auto-match' : 'unid';
  const nameClass = isAnchored ? 'is-anchor' : isAutoMatch ? 'is-auto' : 'is-unid';

  let actionsHtml = '';
  if (isAutoMatch) {
    actionsHtml = `<button class="btn-sm btn-clear" onclick="clearAutoMatch(${f.face_id}, event)">✕</button>`;
  } else if (isAnchored) {
    actionsHtml = `<button class="btn-sm btn-undo" onclick="removeAnchor(${f.face_id}, event)">撤回</button>`;
  }

  const topMatch = (!isAnchored && f.matches.length > 0) ? f.matches[0] : null;
  let matchHint = '';
  if (topMatch && !f.person_id) {
    matchHint = `<span style="color:#888;font-size:10px;margin-left:4px">${topMatch.display_name} ${topMatch.score.toFixed(2)}</span>`;
  }

  row.innerHTML = `
    <span class="row-label">#${idx+1}</span>
    <img class="face-crop-sm ${cropClass}" src="/api/face/${f.face_id}/crop" alt="">
    <span class="row-name ${nameClass}">${personName}${matchHint}</span>
    <span class="row-actions">${actionsHtml}</span>
  `;

  row.onclick = (e) => {
    if (e.target.tagName === 'BUTTON') return;
    toggleExpand(f.face_id, idx);
  };
  row.onmouseenter = () => { S.hoveredFaceIdx = idx; drawCanvas(); };
  row.onmouseleave = () => { S.hoveredFaceIdx = -1; drawCanvas(); };

  return row;
}

function buildExpandedCard(f, idx, isAnchored, isAutoMatch, personName) {
  const card = document.createElement('div');
  card.className = 'face-card-expanded';
  card.dataset.faceId = f.face_id;

  const cropClass = isAnchored ? 'anchor' : isAutoMatch ? 'auto-match' : 'unid';
  const nameClass = isAnchored ? 'anchored' : isAutoMatch ? 'auto' : '';

  let statusHtml = '';
  if (isAnchored) statusHtml = '<div style="color:#2ecc71;font-size:11px">✓ 已錨定</div>';
  else if (isAutoMatch) statusHtml = `<div style="color:#f39c12;font-size:11px">自動匹配 (${f.match_score?.toFixed(3)})</div>`;

  let actionsHtml = '';
  if (isAnchored) {
    actionsHtml = `<button class="btn-sm btn-undo" onclick="removeAnchor(${f.face_id}, event)">撤回錨定</button>`;
  } else if (isAutoMatch) {
    actionsHtml = `<button class="btn-sm btn-clear" onclick="clearAutoMatch(${f.face_id}, event)">✕ 清除匹配</button>`;
  }

  // Matches
  let matchesHtml = '';
  if (!isAnchored && f.matches.length > 0) {
    matchesHtml = '<div class="match-grid">';
    for (const m of f.matches) {
      matchesHtml += `
        <div class="match-card" onclick="confirmAnchor(${f.face_id}, '${m.person_id}', event)">
          <img src="/api/person/${m.person_id}/portrait" alt="${m.display_name}"
               onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2264%22 height=%2264%22><rect fill=%22%23333%22 width=%2264%22 height=%2264%22/><text fill=%22%23666%22 x=%2232%22 y=%2237%22 text-anchor=%22middle%22 font-size=%2212%22>?</text></svg>'">
          <span class="m-name">${m.display_name}</span>
          <span class="m-score ${m.confidence}">${m.score.toFixed(3)}</span>
          <button class="m-btn" onclick="confirmAnchor(${f.face_id}, '${m.person_id}', event)">確認</button>
        </div>
      `;
    }
    matchesHtml += '</div>';
  }

  // Manual assign
  let manualHtml = '';
  if (!isAnchored) {
    manualHtml = `
      <div class="manual-assign">
        <select onchange="manualAssign(${f.face_id}, this.value, this)">
          <option value="">手動指定...</option>
          ${S.persons.map(p => `<option value="${p.person_id}">${p.display_name}</option>`).join('')}
        </select>
      </div>
    `;
  }

  card.innerHTML = `
    <div class="face-top">
      <img class="face-crop-lg ${cropClass}" src="/api/face/${f.face_id}/crop" alt="">
      <div class="face-info">
        <div style="color:#888;font-size:11px">#${idx+1} · face_id ${f.face_id} · ${f.det_score}</div>
        <div class="person-name ${nameClass}">${personName}</div>
        ${statusHtml}
        <div style="font-size:11px;color:#888">${f.age_est ? '~'+f.age_est+'歲' : ''} ${f.gender_est || ''}</div>
        ${actionsHtml}
      </div>
    </div>
    ${matchesHtml}
    ${manualHtml}
  `;

  card.onmouseenter = () => { S.hoveredFaceIdx = idx; drawCanvas(); };
  card.onmouseleave = () => { S.hoveredFaceIdx = -1; drawCanvas(); };

  return card;
}

function toggleExpand(faceId, idx) {
  if (S.expandedFaceId === faceId) {
    S.expandedFaceId = null;
  } else {
    S.expandedFaceId = faceId;
  }
  S.selectedFaceId = faceId;
  drawCanvas();
  renderFaceCards();
  // Scroll into view
  setTimeout(() => {
    const el = document.querySelector(`[data-face-id="${faceId}"]`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, 50);
}

function selectFace(faceId, idx) {
  S.selectedFaceId = faceId;
  S.expandedFaceId = faceId;
  drawCanvas();
  renderFaceCards();
  setTimeout(() => {
    const el = document.querySelector(`[data-face-id="${faceId}"]`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, 50);
}

// ── Anchor Actions ────────────────────────────────────────────────
async function confirmAnchor(faceId, personId, event) {
  if (event) event.stopPropagation();

  try {
    const resp = await fetch('/api/anchor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ face_id: faceId, person_id: personId }),
    });
    const result = await resp.json();
    if (result.error) {
      toast(`錯誤: ${result.message || result.error}`, true);
      return;
    }
    toast(`已錨定 → ${result.display_name} (+${result.new_auto_matches} 自動匹配)`);

    // Re-fetch photo data (faces may have changed due to cascade matching)
    if (S.currentPhoto) await selectPhoto(S.currentPhoto);

    // After re-fetch, find next unidentified face to auto-advance
    const freshUnid = S.currentPhotoData?.faces.find(f => !f.person_id);
    if (freshUnid) {
      S.expandedFaceId = freshUnid.face_id;
      S.selectedFaceId = freshUnid.face_id;
      drawCanvas();
      renderFaceCards();
      setTimeout(() => {
        const el = document.querySelector(`[data-face-id="${freshUnid.face_id}"]`);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }, 100);
    }
  } catch (err) {
    toast(`錯誤: ${err.message}`, true);
  }
}

async function manualAssign(faceId, personId, selectEl) {
  if (!personId) return;
  selectEl.disabled = true;
  await confirmAnchor(faceId, personId, null);
  selectEl.disabled = false;
  selectEl.value = '';
}

async function removeAnchor(faceId, event) {
  if (event) event.stopPropagation();
  try {
    const resp = await fetch(`/api/anchor/${faceId}`, { method: 'DELETE' });
    const result = await resp.json();
    if (result.error) { toast(`錯誤: ${result.message || result.error}`, true); return; }
    toast(`已撤回 ${result.display_name} 的錨定`);
    if (S.currentPhoto) await selectPhoto(S.currentPhoto);
  } catch (err) { toast(`錯誤: ${err.message}`, true); }
}

async function clearAutoMatch(faceId, event) {
  if (event) event.stopPropagation();
  try {
    const resp = await fetch(`/api/face/${faceId}/clear`, { method: 'POST' });
    const result = await resp.json();
    if (result.error) { toast(`錯誤: ${result.message || result.error}`, true); return; }
    toast('已清除自動匹配');
    if (S.currentPhoto) await selectPhoto(S.currentPhoto);
  } catch (err) { toast(`錯誤: ${err.message}`, true); }
}

// ── Canvas Click/Move ─────────────────────────────────────────────
function onCanvasClick(e) {
  if (!S.currentPhotoData) return;
  const canvas = document.getElementById('mainCanvas');
  const rect = canvas.getBoundingClientRect();
  const x = (e.clientX - rect.left) / rect.width;
  const y = (e.clientY - rect.top) / rect.height;

  const faces = S.currentPhotoData.faces;
  for (let i = 0; i < faces.length; i++) {
    const f = faces[i];
    const [bx, by, bw, bh] = f.bbox;
    if (x >= bx && x <= bx + bw && y >= by && y <= by + bh) {
      selectFace(f.face_id, i);
      return;
    }
  }
  S.selectedFaceId = null;
  S.expandedFaceId = null;
  drawCanvas();
  renderFaceCards();
}

function onCanvasMove(e) {
  if (!S.currentPhotoData) return;
  const canvas = document.getElementById('mainCanvas');
  const rect = canvas.getBoundingClientRect();
  const x = (e.clientX - rect.left) / rect.width;
  const y = (e.clientY - rect.top) / rect.height;

  let found = -1;
  const faces = S.currentPhotoData.faces;
  for (let i = 0; i < faces.length; i++) {
    const [bx, by, bw, bh] = faces[i].bbox;
    if (x >= bx && x <= bx + bw && y >= by && y <= by + bh) { found = i; break; }
  }
  if (found !== S.hoveredFaceIdx) {
    S.hoveredFaceIdx = found;
    drawCanvas();
  }
}

// ── Keyboard ──────────────────────────────────────────────────────
function onKeyDown(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;

  const photos = S.photos;
  if (!photos.length) return;

  if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
    e.preventDefault();
    const idx = photos.findIndex(p => p.photo_id === S.currentPhoto?.photo_id);
    const next = Math.max(0, idx - 1);
    selectPhoto(photos[next]);
  } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
    e.preventDefault();
    const idx = photos.findIndex(p => p.photo_id === S.currentPhoto?.photo_id);
    const next = Math.min(photos.length - 1, idx + 1);
    selectPhoto(photos[next]);
  } else if (e.key === 'Tab') {
    e.preventDefault();
    if (!S.currentPhotoData) return;
    // Tab cycles only through unidentified faces
    const unidFaces = S.currentPhotoData.faces.filter(f => !f.person_id);
    if (!unidFaces.length) return;
    const curIdx = unidFaces.findIndex(f => f.face_id === S.selectedFaceId);
    const nextIdx = (curIdx + 1) % unidFaces.length;
    const next = unidFaces[nextIdx];
    selectFace(next.face_id, S.currentPhotoData.faces.indexOf(next));
  } else if (e.key === 'Enter') {
    if (!S.selectedFaceId || !S.currentPhotoData) return;
    const face = S.currentPhotoData.faces.find(f => f.face_id === S.selectedFaceId);
    if (face && face.matches.length > 0 && face.match_method !== 'anchor') {
      confirmAnchor(face.face_id, face.matches[0].person_id, null);
    }
  } else if (e.key === 'Escape') {
    S.selectedFaceId = null;
    S.expandedFaceId = null;
    drawCanvas();
    renderFaceCards();
  }
}

// ── Events ────────────────────────────────────────────────────────
function setupEvents() {
  document.getElementById('sourceFilter').onchange = loadPhotos;
  document.getElementById('unidFilter').onchange = loadPhotos;
  document.getElementById('photoSearch').oninput = filterAndRenderPhotos;
  document.getElementById('mainCanvas').onclick = onCanvasClick;
  document.getElementById('mainCanvas').onmousemove = onCanvasMove;
  document.addEventListener('keydown', onKeyDown);
  window.addEventListener('resize', () => { if (S.currentImage) drawCanvas(); });
}

// ── Boot ──────────────────────────────────────────────────────────
init().catch(err => {
  console.error('Init failed:', err);
  toast('載入失敗: ' + err.message, true);
});
</script>
</body>
</html>
"""
