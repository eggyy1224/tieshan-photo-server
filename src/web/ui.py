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
.topbar select, .topbar input {
  background: #0f3460; border: 1px solid #444; color: #e0e0e0;
  padding: 4px 8px; border-radius: 4px; font-size: 13px;
}
.topbar label { font-size: 13px; cursor: pointer; }
.topbar .stats { margin-left: auto; font-size: 12px; color: #888; }

/* ── Main Layout ────────────────────────────────────────────── */
.main {
  display: flex; flex: 1; overflow: hidden;
}

/* ── Left Panel: Photo List ─────────────────────────────────── */
.photo-list {
  width: 260px; min-width: 200px;
  border-right: 1px solid #333;
  display: flex; flex-direction: column;
  background: #16213e;
}
.photo-list-header {
  padding: 8px; border-bottom: 1px solid #333;
}
.photo-list-header input {
  width: 100%; padding: 4px 8px; border-radius: 4px;
  background: #0f3460; border: 1px solid #444; color: #e0e0e0;
  font-size: 13px;
}
.photo-list-items {
  flex: 1; overflow-y: auto;
}
.photo-item {
  padding: 6px 10px; cursor: pointer;
  border-bottom: 1px solid #1a1a2e;
  font-size: 13px; display: flex; justify-content: space-between;
  align-items: center;
}
.photo-item:hover { background: #0f3460; }
.photo-item.active { background: #1a5276; border-left: 3px solid #3498db; }
.photo-item .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.photo-item .badge {
  background: #444; border-radius: 10px; padding: 1px 6px;
  font-size: 11px; margin-left: 6px; white-space: nowrap;
}
.photo-item .badge.has-unid { background: #e67e22; color: #fff; }

/* ── Center: Canvas ─────────────────────────────────────────── */
.canvas-area {
  flex: 1; position: relative; overflow: hidden;
  display: flex; align-items: center; justify-content: center;
  background: #111;
}
.canvas-area canvas {
  max-width: 100%; max-height: 100%;
  cursor: crosshair;
}
.canvas-area .no-photo {
  color: #555; font-size: 18px;
}

/* ── Right Panel: Face Inspector ────────────────────────────── */
.face-panel {
  width: 320px; min-width: 280px;
  border-left: 1px solid #333;
  display: flex; flex-direction: column;
  background: #16213e;
  overflow-y: auto;
}
.face-panel-header {
  padding: 10px; border-bottom: 1px solid #333;
  font-size: 14px; font-weight: 600;
}
.face-card {
  padding: 10px; border-bottom: 1px solid #1a1a2e;
}
.face-card.selected { background: #1a3a5c; }
.face-card .face-top {
  display: flex; gap: 10px; margin-bottom: 8px;
}
.face-card .face-crop {
  width: 80px; height: 80px; border-radius: 4px;
  object-fit: cover; border: 2px solid #444;
  cursor: pointer; flex-shrink: 0;
}
.face-card .face-crop.anchor { border-color: #2ecc71; }
.face-card .face-crop.auto-match { border-color: #f39c12; }
.face-card .face-info { flex: 1; font-size: 12px; }
.face-card .face-info .label { color: #888; }
.face-card .face-info .person-name {
  font-size: 14px; font-weight: 600; color: #3498db;
}
.face-card .face-info .person-name.anchored { color: #2ecc71; }

/* Matches */
.match-list { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }
.match-item {
  display: flex; flex-direction: column; align-items: center;
  width: 72px; cursor: pointer; position: relative;
}
.match-item img {
  width: 60px; height: 60px; border-radius: 4px;
  object-fit: cover; border: 2px solid transparent;
}
.match-item img:hover { border-color: #3498db; }
.match-item .match-name { font-size: 10px; text-align: center; margin-top: 2px; }
.match-item .match-score {
  font-size: 10px; color: #888;
}
.match-item .match-score.HIGH { color: #2ecc71; }
.match-item .match-score.MEDIUM { color: #f39c12; }
.match-item .match-score.LOW { color: #e74c3c; }

/* Confirm button */
.btn {
  padding: 4px 10px; border-radius: 4px; cursor: pointer;
  font-size: 12px; border: none;
}
.btn-confirm { background: #27ae60; color: #fff; }
.btn-confirm:hover { background: #2ecc71; }
.btn-confirm:disabled { background: #555; cursor: not-allowed; }

/* Manual assign */
.manual-assign {
  margin-top: 6px;
}
.manual-assign select {
  width: 100%; padding: 4px; border-radius: 4px;
  background: #0f3460; border: 1px solid #444; color: #e0e0e0;
  font-size: 12px;
}

/* ── Bottom Bar: Person Reference ───────────────────────────── */
.person-bar {
  flex-shrink: 0;
  border-top: 1px solid #333;
  background: #16213e;
  padding: 6px 10px;
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

/* Loading */
.loading {
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  color: #888; font-size: 14px;
}

/* Toast notifications */
.toast {
  position: fixed; bottom: 20px; right: 20px;
  background: #27ae60; color: #fff;
  padding: 10px 20px; border-radius: 6px;
  font-size: 14px; z-index: 1000;
  opacity: 0; transition: opacity 0.3s;
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
  </div>

  <!-- Right: Face inspector -->
  <div class="face-panel" id="facePanel">
    <div class="face-panel-header">臉部檢視</div>
    <div id="faceCards">
      <div style="padding:10px;color:#666;font-size:13px;">選擇照片後顯示臉部資訊</div>
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
  hoveredFaceIdx: -1,
};

// ── API helpers ───────────────────────────────────────────────────
const API = (path) => path;

async function fetchJSON(path) {
  const r = await fetch(API(path));
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
  for (const p of S.persons) {
    S.personsMap[p.person_id] = p;
  }
  renderPersonBar();
}

function renderPersonBar() {
  const bar = document.getElementById('personBar');
  bar.innerHTML = '';
  // Only show persons with anchors
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
  let url = '/api/photos?limit=500';
  if (source) url += `&source_dir=${encodeURIComponent(source)}`;
  if (unid) url += '&has_unidentified=1';

  const data = await fetchJSON(url);
  S.allPhotos = data.photos;
  S.photos = data.photos;
  document.getElementById('statsBar').textContent =
    `${data.total} 張照片`;
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
    div.className = 'photo-item' +
      (S.currentPhoto && S.currentPhoto.photo_id === p.photo_id ? ' active' : '');
    const fc = p.face_count || 0;
    div.innerHTML = `
      <span class="name" title="${p.rel_path}">${p.filename}</span>
      <span class="badge${fc > 0 ? ' has-unid' : ''}">${fc}</span>
    `;
    div.onclick = () => selectPhoto(p);
    container.appendChild(div);
  }
}

// ── Select Photo ──────────────────────────────────────────────────
async function selectPhoto(photo) {
  S.currentPhoto = photo;
  S.selectedFaceId = null;
  S.hoveredFaceIdx = -1;
  renderPhotoList();

  // Show loading
  const area = document.getElementById('canvasArea');
  document.getElementById('noPhoto').style.display = 'none';
  const canvas = document.getElementById('mainCanvas');
  canvas.style.display = 'none';

  // Load image + metadata in parallel
  const [photoData, img] = await Promise.all([
    fetchJSON(`/api/photo/${photo.photo_id}`),
    loadImage(`/api/image/${photo.photo_id}?max_dim=2048`),
  ]);

  S.currentPhotoData = photoData;
  S.currentImage = img;

  // Draw
  canvas.style.display = 'block';
  drawCanvas();
  renderFaceCards();
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

  // Fit image to area
  const areaW = area.clientWidth;
  const areaH = area.clientHeight;
  const scale = Math.min(areaW / img.width, areaH / img.height, 1);
  const cw = Math.floor(img.width * scale);
  const ch = Math.floor(img.height * scale);

  canvas.width = cw;
  canvas.height = ch;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0, cw, ch);

  // Draw face boxes
  if (!S.currentPhotoData) return;
  const faces = S.currentPhotoData.faces;

  for (let i = 0; i < faces.length; i++) {
    const f = faces[i];
    const [bx, by, bw, bh] = f.bbox;
    const x = bx * cw, y = by * ch, w = bw * cw, h = bh * ch;

    // Color based on status
    let color, lineWidth, dash;
    if (f.match_method === 'anchor') {
      color = '#2ecc71'; lineWidth = 2.5; dash = [];
    } else if (f.person_id) {
      color = '#f39c12'; lineWidth = 2; dash = [6, 3];
    } else {
      color = '#888'; lineWidth = 1.5; dash = [];
    }

    // Highlight if hovered or selected
    if (i === S.hoveredFaceIdx || f.face_id === S.selectedFaceId) {
      color = '#3498db'; lineWidth = 3; dash = [];
    }

    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.setLineDash(dash);
    ctx.strokeRect(x, y, w, h);

    // Face number label
    ctx.setLineDash([]);
    const label = `#${i + 1}`;
    ctx.font = 'bold 13px sans-serif';
    const tm = ctx.measureText(label);
    const lx = x, ly = y - 4;
    ctx.fillStyle = color;
    ctx.fillRect(lx - 1, ly - 14, tm.width + 6, 16);
    ctx.fillStyle = '#fff';
    ctx.fillText(label, lx + 2, ly - 1);

    // Person name if known
    if (f.person_id) {
      const pname = S.personsMap[f.person_id]?.display_name || f.person_id;
      ctx.font = '12px sans-serif';
      const nm = ctx.measureText(pname);
      ctx.fillStyle = color;
      ctx.fillRect(x, y + h, nm.width + 6, 16);
      ctx.fillStyle = '#fff';
      ctx.fillText(pname, x + 3, y + h + 12);
    }
  }
}

// ── Face Cards ────────────────────────────────────────────────────
function renderFaceCards() {
  const container = document.getElementById('faceCards');
  if (!S.currentPhotoData) {
    container.innerHTML = '<div style="padding:10px;color:#666">無資料</div>';
    return;
  }

  const faces = S.currentPhotoData.faces;
  if (faces.length === 0) {
    container.innerHTML = '<div style="padding:10px;color:#666">此照片無偵測到臉部</div>';
    return;
  }

  container.innerHTML = '';
  for (let i = 0; i < faces.length; i++) {
    const f = faces[i];
    const card = document.createElement('div');
    card.className = 'face-card' + (f.face_id === S.selectedFaceId ? ' selected' : '');
    card.dataset.faceId = f.face_id;
    card.dataset.idx = i;

    const isAnchored = f.match_method === 'anchor';
    const isAutoMatch = f.person_id && f.match_method !== 'anchor';
    const personName = f.person_id
      ? (S.personsMap[f.person_id]?.display_name || f.person_id)
      : '未辨識';

    let cropClass = 'face-crop';
    if (isAnchored) cropClass += ' anchor';
    else if (isAutoMatch) cropClass += ' auto-match';

    let infoHtml = `
      <div><span class="label">#${i + 1}</span> face_id: ${f.face_id}</div>
      <div><span class="label">信心度:</span> ${f.det_score}</div>
    `;
    if (f.age_est) infoHtml += `<div><span class="label">年齡:</span> ~${f.age_est}</div>`;
    if (f.gender_est) infoHtml += `<div><span class="label">性別:</span> ${f.gender_est}</div>`;

    if (f.person_id) {
      const nameClass = isAnchored ? 'person-name anchored' : 'person-name';
      infoHtml += `<div class="${nameClass}">${personName}</div>`;
      if (isAnchored) infoHtml += `<div style="color:#2ecc71;font-size:11px">已錨定</div>`;
      else if (isAutoMatch) infoHtml += `<div style="color:#f39c12;font-size:11px">自動匹配 (${f.match_score?.toFixed(3)})</div>`;
    }

    // Matches section
    let matchesHtml = '<div class="match-list">';
    for (const m of f.matches) {
      matchesHtml += `
        <div class="match-item" data-face-id="${f.face_id}" data-person-id="${m.person_id}">
          <img src="/api/person/${m.person_id}/portrait"
               alt="${m.display_name}"
               onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2260%22 height=%2260%22><rect fill=%22%23333%22 width=%2260%22 height=%2260%22/><text fill=%22%23888%22 x=%2230%22 y=%2235%22 text-anchor=%22middle%22 font-size=%2210%22>?</text></svg>'">
          <span class="match-name">${m.display_name}</span>
          <span class="match-score ${m.confidence}">${m.score.toFixed(3)}</span>
          <button class="btn btn-confirm" onclick="confirmAnchor(${f.face_id}, '${m.person_id}', event)"
                  ${isAnchored ? 'disabled' : ''}>確認</button>
        </div>
      `;
    }
    matchesHtml += '</div>';

    // Manual assign dropdown
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
        <img class="${cropClass}" src="/api/face/${f.face_id}/crop"
             alt="face #${i + 1}"
             onclick="selectFace(${f.face_id}, ${i})">
        <div class="face-info">${infoHtml}</div>
      </div>
      ${matchesHtml}
      ${manualHtml}
    `;

    // Hover to highlight on canvas
    card.onmouseenter = () => { S.hoveredFaceIdx = i; drawCanvas(); };
    card.onmouseleave = () => { S.hoveredFaceIdx = -1; drawCanvas(); };

    container.appendChild(card);
  }
}

function selectFace(faceId, idx) {
  S.selectedFaceId = faceId;
  drawCanvas();
  renderFaceCards();
  // Scroll card into view
  const card = document.querySelector(`.face-card[data-face-id="${faceId}"]`);
  if (card) card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── Anchor Actions ────────────────────────────────────────────────
async function confirmAnchor(faceId, personId, event) {
  if (event) event.stopPropagation();
  const btn = event?.target;
  if (btn) { btn.disabled = true; btn.textContent = '...'; }

  try {
    const resp = await fetch('/api/anchor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ face_id: faceId, person_id: personId }),
    });
    const result = await resp.json();
    if (result.error) {
      toast(`錯誤: ${result.message || result.error}`, true);
      if (btn) { btn.disabled = false; btn.textContent = '確認'; }
      return;
    }
    toast(`已錨定 → ${result.display_name} (新自動匹配: ${result.new_auto_matches})`);
    // Reload current photo
    if (S.currentPhoto) await selectPhoto(S.currentPhoto);
  } catch (err) {
    toast(`錯誤: ${err.message}`, true);
    if (btn) { btn.disabled = false; btn.textContent = '確認'; }
  }
}

async function manualAssign(faceId, personId, selectEl) {
  if (!personId) return;
  selectEl.disabled = true;
  await confirmAnchor(faceId, personId, null);
  selectEl.disabled = false;
  selectEl.value = '';
}

// ── Canvas Click → Select Face ────────────────────────────────────
function onCanvasClick(e) {
  if (!S.currentPhotoData) return;
  const canvas = document.getElementById('mainCanvas');
  const rect = canvas.getBoundingClientRect();
  const x = (e.clientX - rect.left) / canvas.width;
  const y = (e.clientY - rect.top) / canvas.height;

  const faces = S.currentPhotoData.faces;
  for (let i = 0; i < faces.length; i++) {
    const f = faces[i];
    const [bx, by, bw, bh] = f.bbox;
    if (x >= bx && x <= bx + bw && y >= by && y <= by + bh) {
      selectFace(f.face_id, i);
      return;
    }
  }
  // Click outside any face → deselect
  S.selectedFaceId = null;
  drawCanvas();
  renderFaceCards();
}

function onCanvasMove(e) {
  if (!S.currentPhotoData) return;
  const canvas = document.getElementById('mainCanvas');
  const rect = canvas.getBoundingClientRect();
  const x = (e.clientX - rect.left) / canvas.width;
  const y = (e.clientY - rect.top) / canvas.height;

  let found = -1;
  const faces = S.currentPhotoData.faces;
  for (let i = 0; i < faces.length; i++) {
    const f = faces[i];
    const [bx, by, bw, bh] = f.bbox;
    if (x >= bx && x <= bx + bw && y >= by && y <= by + bh) {
      found = i; break;
    }
  }
  if (found !== S.hoveredFaceIdx) {
    S.hoveredFaceIdx = found;
    drawCanvas();
  }
}

// ── Keyboard Shortcuts ────────────────────────────────────────────
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
    const faces = S.currentPhotoData.faces;
    if (!faces.length) return;
    const curIdx = faces.findIndex(f => f.face_id === S.selectedFaceId);
    const nextIdx = (curIdx + 1) % faces.length;
    selectFace(faces[nextIdx].face_id, nextIdx);
  } else if (e.key === 'Enter') {
    // Confirm top match for selected face
    if (!S.selectedFaceId || !S.currentPhotoData) return;
    const face = S.currentPhotoData.faces.find(f => f.face_id === S.selectedFaceId);
    if (face && face.matches.length > 0 && face.match_method !== 'anchor') {
      confirmAnchor(face.face_id, face.matches[0].person_id, null);
    }
  }
}

// ── Event Setup ───────────────────────────────────────────────────
function setupEvents() {
  document.getElementById('sourceFilter').onchange = loadPhotos;
  document.getElementById('unidFilter').onchange = loadPhotos;
  document.getElementById('photoSearch').oninput = filterAndRenderPhotos;
  document.getElementById('mainCanvas').onclick = onCanvasClick;
  document.getElementById('mainCanvas').onmousemove = onCanvasMove;
  document.addEventListener('keydown', onKeyDown);

  // Resize handling
  window.addEventListener('resize', () => {
    if (S.currentImage) drawCanvas();
  });
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
