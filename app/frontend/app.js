"use strict";

const RADIUS = 80;
const HEX_WIDTH = Math.sqrt(3) * RADIUS;
const MAP_WIDTH = 3200;
const MAP_HEIGHT = 2200;
const VERSION = "Rhisseth · Artistic V6 · интерактивная сетка";
const API_BASE = "/api";
let csrfToken = '';
let canEdit = false;
let userId = '', editingTerritoryName = false;
let mapRows = [];
const creatingBarony = location.pathname.endsWith('/create-barony.html');
let availableCells = new Set(), chosenCells = new Set();
const polygons = new Map();
const cellKey = (q,r) => `${q},${r}`;
const neighbors = [[1,0],[-1,0],[0,1],[0,-1],[1,-1],[-1,1]];
function connectedSelection(cells) {
  const remaining = new Set(cells);
  if (!remaining.size) return true;
  const pending = [remaining.values().next().value]; remaining.delete(pending[0]);
  while (pending.length) {
    const [q,r] = pending.pop().split(',').map(Number);
    for (const [dq,dr] of neighbors) {
      const key = cellKey(q+dq,r+dr);
      if (remaining.delete(key)) pending.push(key);
    }
  }
  return remaining.size === 0;
}
function paintSelection() {
  const color = document.querySelector('#barony-color')?.value || '#b51f24';
  for (const [key,polygon] of polygons) {
    polygon.classList.toggle('barony-chosen', chosenCells.has(key));
    if (chosenCells.has(key)) polygon.style.setProperty('--barony-color',color);
  }
  redrawBaronyBoundaries();
  document.querySelector('#chosen-cells').textContent = chosenCells.size ? [...chosenCells].map(k=>`Q${k.split(',')[0]} R${k.split(',')[1]}`).join(' · ') : 'Гексы пока не выбраны';
  document.querySelector('#claim-choice').disabled = claiming || chosenCells.size < 2;
}
function chooseHex(row) {
  if (!creatingBarony || claiming) return;
  const key = cellKey(row.Q,row.R), next = new Set(chosenCells);
  const status = document.querySelector('#start-status');
  if (!availableCells.has(key)) { status.textContent = 'Выберите свободный гекс суши, побережья или острова.'; return; }
  if (next.has(key)) next.delete(key); else next.add(key);
  if (next.size > 3) { status.textContent = 'Начальная барония состоит из 2–3 гексов.'; return; }
  if (!connectedSelection(next)) { status.textContent = 'Все выбранные гексы должны составлять смежную территорию.'; return; }
  chosenCells = next; status.textContent = ''; paintSelection();
}

const overlay = document.querySelector("#hex-overlay");
const baronyBoundaries = document.querySelector("#barony-boundaries");
const baronyEmblems = document.querySelector("#barony-emblems");
const viewport = document.querySelector("#map-viewport");
const loading = document.querySelector("#loading");
const card = document.querySelector("#hex-card");
let selectedHex = null;
let selectedRow = null;
const form = document.querySelector("#hex-form");
const saveStatus = document.querySelector("#save-status");

function polygonPoints(q, r) {
  return hexCorners(q, r).map(([x,y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
}

function hexCorners(q, r) {
  const cx = HEX_WIDTH * (q + r / 2);
  const cy = RADIUS * 1.5 * r;
  return Array.from({ length: 6 }, (_, index) => {
    const angle = (60 * index - 30) * Math.PI / 180;
    return [cx + RADIUS * Math.cos(angle), cy + RADIUS * Math.sin(angle)];
  });
}

function redrawBaronyBoundaries() {
  const groups = new Map();
  const add = (id, color, key) => {
    if (!groups.has(id)) groups.set(id, {color, cells:new Set()});
    groups.get(id).cells.add(key);
  };
  mapRows.forEach(row => {
    const color = row['Цвет баронии'];
    if (/^#[0-9a-f]{6}$/i.test(color || '') && row['ID территории']) {
      add(`owned:${row['ID территории']}`, color, cellKey(row.Q,row.R));
    }
  });
  if (chosenCells.size) add('chosen', document.querySelector('#barony-color')?.value || '#b51f24', [...chosenCells][0]);
  if (chosenCells.size) groups.get('chosen').cells = new Set(chosenCells);
  baronyBoundaries.replaceChildren();
  groups.forEach(({color,cells}, id) => {
    const edges = new Map();
    cells.forEach(key => {
      const [q,r] = key.split(',').map(Number), corners = hexCorners(q,r);
      corners.forEach((point,index) => {
        const next = corners[(index+1)%6];
        const endpoint = value => `${value[0].toFixed(2)},${value[1].toFixed(2)}`;
        const edgeKey = [endpoint(point),endpoint(next)].sort().join('|');
        const record = edges.get(edgeKey) || {count:0, point, next};
        record.count++; edges.set(edgeKey,record);
      });
    });
    edges.forEach(edge => {
      if (edge.count !== 1) return;
      const line = document.createElementNS('http://www.w3.org/2000/svg','path');
      line.setAttribute('d',`M ${edge.point[0].toFixed(2)} ${edge.point[1].toFixed(2)} L ${edge.next[0].toFixed(2)} ${edge.next[1].toFixed(2)}`);
      line.setAttribute('class', id === 'chosen' ? 'barony-boundary barony-boundary-preview' : 'barony-boundary');
      line.style.stroke = color;
      baronyBoundaries.append(line);
    });
  });
  redrawBaronyEmblems();
}

function crestAsset(crest) {
  if (!crest) return '';
  return `crests/${crest.replace(/\.png$/i, '.webp')}`;
}

function redrawBaronyEmblems() {
  if (!baronyEmblems) return;
  const groups = new Map();
  const add = (id, crest, key) => {
    if (!crest) return;
    if (!groups.has(id)) groups.set(id, { crest, cells: [] });
    groups.get(id).cells.push(key);
  };
  mapRows.forEach(row => {
    if (row['ID территории'] && row['Герб баронии']) {
      add(`owned:${row['ID территории']}`, row['Герб баронии'], cellKey(row.Q, row.R));
    }
  });
  if (chosenCells.size) {
    const crest = document.querySelector('input[name="crest"]:checked')?.value;
    if (crest) add('chosen', crest, [...chosenCells][0]);
    if (groups.has('chosen')) groups.get('chosen').cells = [...chosenCells];
  }
  // Keep the emblem above the hit polygons so it remains visible and does not
  // interfere with clicking the map.
  overlay.appendChild(baronyEmblems);
  baronyEmblems.replaceChildren();
  groups.forEach(({ crest, cells }) => {
    const points = cells.map(key => {
      const [q, r] = key.split(',').map(Number);
      return [HEX_WIDTH * (q + r / 2), RADIUS * 1.5 * r];
    });
    if (!points.length) return;
    const x = points.reduce((sum, point) => sum + point[0], 0) / points.length;
    const y = points.reduce((sum, point) => sum + point[1], 0) / points.length;
    const image = document.createElementNS('http://www.w3.org/2000/svg', 'image');
    image.setAttribute('x', (x - 34).toFixed(2));
    image.setAttribute('y', (y - 50).toFixed(2));
    image.setAttribute('width', '68');
    image.setAttribute('height', '68');
    image.setAttribute('href', crestAsset(crest));
    image.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    image.setAttribute('class', 'barony-emblem');
    image.setAttribute('aria-label', 'Герб баронии');
    baronyEmblems.append(image);
  });
}

function rating(value, maximum) {
  if (!value) return "Нет данных";
  const numeric = Math.max(0, Math.min(maximum, Number.parseInt(value, 10)));
  return `<span class="rating" aria-label="${numeric} из ${maximum}">${"●".repeat(numeric)}${"○".repeat(maximum - numeric)}</span> ${value}/${maximum}`;
}

function positionCard(clientX, clientY) {
  const bounds = viewport.getBoundingClientRect();
  const width = card.offsetWidth || 310;
  const height = card.offsetHeight || 260;
  const left = Math.min(clientX - bounds.left + 14, bounds.width - width - 12);
  const top = Math.min(clientY - bounds.top + 14, bounds.height - height - 12);
  card.style.left = `${Math.max(12, left)}px`;
  card.style.top = `${Math.max(12, top)}px`;
}

function showCard(row, event, polygon) {
  selectedHex?.classList.remove("selected");
  selectedHex = polygon;
  selectedRow = row;
  selectedHex.classList.add("selected");
  const cardCrest = document.querySelector('#card-crest');
  const crest = row['Герб баронии'];
  cardCrest.hidden = !crest;
  if (crest) {
    cardCrest.src = crestAsset(crest);
    cardCrest.alt = `Герб ${row['Название баронии'] || row['Название территории'] || 'баронии'}`;
  }
  document.querySelector("#card-title").textContent = row['Название'] || `Q${row.Q} · R${row.R}`;
  document.querySelector("#card-coordinates").textContent = `Q = ${row.Q}, R = ${row.R}`;
  form.elements[0].name = 'Название';
  Array.from(form.elements).forEach((element) => {
    if (element.name) element.value = row[element.name] ?? "";
  });
  form.hidden = true;
  document.querySelector('#edit-name').hidden = !canEdit;
  document.querySelector('#edit-territory-name').hidden = creatingBarony || !(canEdit || row['Тип владельца']==='Игрок' && row['Владелец']===userId);
  form.elements[0].name = 'Название';
  const details = document.querySelector('#hex-details');
  details.replaceChildren();
  const fields = [['Имя владельца','Владелец'],['Тип владельца','Владение'],['Название территории','Территория']];
  if (row['Название баронии']) fields.push(['Название баронии','Барония']);
  fields.push(['Категория','Категория'],['Тип местности','Ландшафт'],['Дополнительный объект','Объект']);
  if (!creatingBarony) fields.push(['Проходимость','Проходимость'],['Защита','Защита'],['Плодородие','Плодородие'],['Опасность','Опасность'],['Основной ресурс','Ресурс'],['Богатство ресурса','Богатство'],['Комментарий','Комментарий']);
  for (const [key,label] of fields) {
    const line = document.createElement('div'), term = document.createElement('dt'), value = document.createElement('dd');
    term.textContent = label; value.textContent = row[key] || 'Нет данных';
    if (key === 'Тип местности' && row['Состав ландшафта']) {
      try { value.textContent = JSON.parse(row['Состав ландшафта']).map(p => document.querySelector('#show-percentages').checked ? `${p.name} ${p.percent}%` : p.name).join(' / '); } catch {}
    }
    line.append(term,value); details.append(line);
  }
  saveStatus.textContent = "";
  saveStatus.classList.remove("error");
  card.hidden = false;
  positionCard(event.clientX, event.clientY);
}

function closeCard() {
  card.hidden = true;
  selectedHex?.classList.remove("selected");
  selectedHex = null;
  selectedRow = null;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedRow) return;
  const rowBeingSaved = selectedRow;
  if (!window.confirm(`Сохранить название «${form.elements[0].value}»?`)) return;
  const button = form.querySelector("button[type=submit]");
  const payload = Object.fromEntries(new FormData(form).entries());
  button.disabled = true;
  saveStatus.textContent = "Сохранение…";
  saveStatus.classList.remove("error");
  try {
    const response = await fetch(`${API_BASE}/hexes/${rowBeingSaved.Q}/${rowBeingSaved.R}${editingTerritoryName?'/territory-name':''}`, {
      method: editingTerritoryName ? 'PATCH' : 'PUT',
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken, 'X-Hex-Revision':rowBeingSaved._revision || '' },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    Object.assign(rowBeingSaved, result.row);
    if (editingTerritoryName) {
      const refreshed = await fetch(`${API_BASE}/hexes`, {cache:'no-store'});
      if (refreshed.ok) {
        const byCoordinates = new Map((await refreshed.json()).map(row=>[`${row.Q},${row.R}`,row]));
        mapRows.forEach(row=>Object.assign(row,byCoordinates.get(`${row.Q},${row.R}`)||{}));
      }
    }
    if (selectedRow !== rowBeingSaved) return;
    const bounds = selectedHex.getBoundingClientRect();
    showCard(rowBeingSaved,{clientX:bounds.right,clientY:bounds.top},selectedHex);
    saveStatus.textContent = "Сохранено в PostgreSQL";
  } catch (error) {
    if (selectedRow === rowBeingSaved) {
      saveStatus.textContent = `Ошибка: ${error.message}`;
      saveStatus.classList.add("error");
    }
  } finally {
    button.disabled = false;
  }
});

function render(rows) {
  const fragment = document.createDocumentFragment();
  const byCoordinates = new Map(rows.map((row) => [`${Number(row.Q)},${Number(row.R)}`, row]));
  const visibleRows = [];
  // Include every cell intersecting the image, independent of legacy terrain labels.
  for (let r = 0; r < Math.ceil((MAP_HEIGHT + RADIUS) / (RADIUS * 1.5)); r++) {
    const firstQ = Math.ceil(-0.5 - r / 2);
    const lastQ = Math.floor(MAP_WIDTH / HEX_WIDTH + 0.5 - r / 2);
    for (let q = firstQ; q <= lastQ; q++) {
      visibleRows.push(byCoordinates.get(`${q},${r}`) ?? { Q: String(q), R: String(r) });
    }
  }
  visibleRows.forEach((row) => {
    const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
    polygon.setAttribute("points", polygonPoints(Number(row.Q), Number(row.R)));
    polygon.setAttribute("class", "hex-hit");
    polygons.set(cellKey(row.Q,row.R),polygon);
    if (/^#[0-9a-f]{6}$/i.test(row['Цвет баронии'] || '')) {
      polygon.style.setProperty('--barony-color',row['Цвет баронии']);
      polygon.classList.add('barony-owned');
    }
    polygon.addEventListener('click',()=>chooseHex(row));
    polygon.setAttribute("tabindex", "0");
    polygon.setAttribute("aria-label", `Гекс Q ${row.Q}, R ${row.R}: ${row["Тип местности"] || "Нет данных"}`);
    polygon.addEventListener("contextmenu", (event) => { event.preventDefault(); showCard(row, event, polygon); });
    polygon.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        const bounds = polygon.getBoundingClientRect();
        if (creatingBarony && !event.shiftKey) chooseHex(row);
        else showCard(row, { clientX: bounds.right, clientY: bounds.top }, polygon);
      }
    });
    fragment.appendChild(polygon);
  });
  mapRows = visibleRows;
  overlay.appendChild(fragment);
  redrawBaronyBoundaries();
}

document.querySelector("#close-card").addEventListener("click", closeCard);
document.querySelector('#show-percentages').checked = localStorage.getItem('rhisseth-show-percentages') !== 'false';
document.querySelector('#show-percentages').addEventListener('change', event => {
  localStorage.setItem('rhisseth-show-percentages', String(event.target.checked));
  if (selectedRow) showCard(selectedRow, {clientX:viewport.getBoundingClientRect().left+parseFloat(card.style.left),clientY:viewport.getBoundingClientRect().top+parseFloat(card.style.top)},selectedHex);
});
document.querySelector('#edit-name').addEventListener('click', () => {
  editingTerritoryName = false;
  document.querySelector('#name-label').textContent = 'Географическое название';
  form.elements[0].name = 'Название';
  form.elements[0].value = selectedRow['Название'] || '';
  form.hidden = false;
  document.querySelector('#edit-name').hidden = true;
  form.elements.namedItem('Название').focus();
});
document.querySelector('#edit-territory-name').addEventListener('click', () => {
  editingTerritoryName = true;
  document.querySelector('#name-label').textContent = 'Название территории';
  form.elements[0].name = 'Название территории';
  form.elements[0].value = selectedRow['Название территории'] || '';
  form.hidden = false;
  form.elements[0].disabled = false;
  form.querySelector('[type=submit]').disabled = false;
  document.querySelector('#cancel-name').disabled = false;
  form.elements[0].focus();
});
document.querySelector('#cancel-name').addEventListener('click', () => {
  form.hidden = true;
  form.elements[0].value = selectedRow?.[form.elements[0].name] || '';
  document.querySelector('#edit-name').hidden = !canEdit;
});
document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeCard(); });
viewport.addEventListener("pointerdown", (event) => { if (!card.contains(event.target) && event.button === 0) closeCard(); });

async function loadData() {
  const identityResponse = await fetch(`${API_BASE}/me`, { cache: "no-store" });
  if (identityResponse.status === 401) {
    window.location.href = '/index.php';
    throw new Error('Требуется вход');
  }
  if (!identityResponse.ok) throw new Error(`HTTP ${identityResponse.status}`);
  const identity = await identityResponse.json();
  csrfToken = identity.csrf;
  canEdit = identity.can_edit;
  userId = identity.id;
  if (creatingBarony) canEdit = false;
  document.querySelector('#admin-link').hidden = !canEdit;
  document.querySelector('#admin-link').href = identity.role === 'admin' ? '/admin/users' : '/admin/hexes';
  document.querySelector('#user-status').textContent = identity.login;
  const userRole = document.querySelector('#user-role');
  if (userRole) userRole.textContent = `· ${identity.role}`;
  if (!canEdit) {
    for (const element of form.elements) element.disabled = true;
    const editorHint = document.querySelector('#editor-hint');
    if (editorHint) editorHint.textContent = creatingBarony ? 'Нажатие — выбрать гекс · правая кнопка — сведения' : 'Режим просмотра · правая кнопка — сведения о гексе';
  }
  const response = await fetch(`${API_BASE}/hexes`, { cache: "no-store" });
  if (!response.ok) throw new Error(`PostgreSQL API: HTTP ${response.status}`);
  return { rows: await response.json(), source: "PostgreSQL" };
}

document.querySelector('#logout').addEventListener('click', async () => {
  const body = new URLSearchParams({ csrf: csrfToken });
  const response = await fetch('/logout', { method: 'POST', body });
  if (response.ok) window.location.href = '/index.php';
});
let claiming = false;
document.querySelector('#start-game').addEventListener('click', () => {
  window.location.href = 'create-barony.html';
});
async function setupPlayerPage() {
  if (!creatingBarony) return;
  const response = await fetch('/api/start/options',{cache:'no-store'});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  if (creatingBarony && result.started) { location.replace('cabinet.html'); return; }
  updateAvailableCells(result);
  const crestList = document.querySelector('#crest-list');
  result.crests.forEach((crest,index) => {
    const label = document.createElement('label'), input = document.createElement('input'), img = document.createElement('img');
    input.type = 'radio'; input.name = 'crest'; input.value = crest; input.required = true; input.checked = index === 0;
    input.addEventListener('change',()=>{
      const defaults = ['#b51f24','#2355aa','#257346','#50545b','#dec78a'];
      document.querySelector('#barony-color').value = defaults[index % defaults.length];
      document.querySelector('#start-status').textContent = '';
      paintSelection();
    });
    img.src = `crests/${crest}`; img.alt = `Герб ${index+1}`;
    label.append(input,img); crestList.append(label);
  });
  document.querySelector('#barony-color').addEventListener('input',paintSelection);
  document.querySelector('#clear-selection').addEventListener('click',()=>{ chosenCells.clear(); paintSelection(); });
  document.querySelector('#random-barony').addEventListener('click',pickRandomBarony);
  document.querySelector('#barony-form').addEventListener('submit',claimBarony);
  paintSelection();
  if (!availableCells.size) document.querySelector('#start-status').textContent = 'Свободных гексов пока нет.';
}
function updateAvailableCells(result) {
  availableCells = new Set(result.available_cells.map(c=>cellKey(...c)));
  for (const [key,polygon] of polygons) {
    polygon.classList.toggle('barony-available',availableCells.has(key));
    polygon.classList.toggle('barony-unavailable',!availableCells.has(key));
  }
}
async function pickRandomBarony() {
  if (claiming) return;
  claiming = true;
  paintSelection();
  const button = document.querySelector('#random-barony');
  button.disabled = true;
  try {
    const response = await fetch('/api/start/options?random=true',{cache:'no-store'});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    if (result.started) { location.href = 'cabinet.html'; return; }
    updateAvailableCells(result);
    chosenCells = new Set(result.random_cells.map(c=>cellKey(...c)));
    paintSelection();
    document.querySelector('#start-status').textContent = chosenCells.size ? `Случайный набор: ${chosenCells.size} смежных гекса. Подтвердите создание или выберите другой набор.` : 'Свободных смежных гексов пока нет.';
  } catch (error) {
    document.querySelector('#start-status').textContent = error.message;
  } finally { claiming = false; button.disabled = false; paintSelection(); }
}
async function claimBarony(event) {
  event.preventDefault();
  if (claiming || chosenCells.size < 2 || !connectedSelection(chosenCells)) return;
  const payload = {
    name: document.querySelector('#barony-name').value,
    crest: document.querySelector('input[name=crest]:checked').value,
    color: document.querySelector('#barony-color').value,
    agreement: document.querySelector('#barony-agreement').checked,
    cells: [...chosenCells].map(key=>key.split(',').map(Number))
  };
  claiming = true; paintSelection();
  document.querySelector('#start-status').textContent = 'Создание баронии…';
  try {
    const response = await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrfToken},body:JSON.stringify(payload)});
    const result = await response.json();
    if (!response.ok) {
      if (response.status === 409) {
        const refreshed = await fetch('/api/start/options',{cache:'no-store'});
        if (refreshed.ok) {
          const options = await refreshed.json();
          if (options.started) { location.href = 'cabinet.html'; return; }
          updateAvailableCells(options);
          chosenCells = new Set([...chosenCells].filter(key=>availableCells.has(key)));
          if (!connectedSelection(chosenCells)) chosenCells.clear();
        }
      }
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    location.href = 'cabinet.html';
  } catch (error) {
    document.querySelector('#start-status').textContent = error.message;
  } finally { claiming = false; paintSelection(); }
}

loadData()
  .then(async ({ rows, source }) => {
    render(rows);
    await setupPlayerPage();
    document.querySelector("#data-status").textContent = `${VERSION} · источник: ${source}`;
    loading.remove();
  })
  .catch((error) => {
    loading.textContent = `Не удалось загрузить данные карты: ${error.message}. Запустите приложение через локальный веб-сервер.`;
    loading.classList.add("error");
  });
