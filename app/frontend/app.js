"use strict";

const RADIUS = 80;
const HEX_WIDTH = Math.sqrt(3) * RADIUS;
const MAP_WIDTH = 3200;
const MAP_HEIGHT = 2200;
const VERSION = "Rhisseth · batell v0.3.1 · Artistic V6";
const API_BASE = "/api";
let csrfToken = '';
let canEdit = false;
let userId = '', editingTerritoryName = false;
let mapRows = [];
const creatingBarony = location.pathname.endsWith('/create-barony.html');
let availableCells = new Set(), chosenCells = new Set();
const polygons = new Map();
const rowsByKey = new Map();
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
  if (!creatingBarony) fields.push(['Проходимость','Проходимость'],['Защита','Защита'],['Плодородие','Плодородие'],['Опасность','Опасность'],['Основной ресурс','Ресурс'],['Богатство ресурса','Богатство'],['Мораль','Мораль'],['Комментарий','Комментарий']);
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
    rowsByKey.set(cellKey(row.Q,row.R),row);
    if (/^#[0-9a-f]{6}$/i.test(row['Цвет баронии'] || '')) {
      polygon.style.setProperty('--barony-color',row['Цвет баронии']);
      polygon.classList.add('barony-owned');
    }
    polygon.addEventListener('click',()=> creatingBarony ? chooseHex(row) : handleGameHexClick(row));
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

const game = { player: 1, moved: false, selected: false, unitKey: '', ownerId: '', pendingRow: null, selectedUnit: null, battle: null, general: null, armyUnits: [], armies: [] };
const gamePanel = document.querySelector('#game-panel');
const gameMessage = document.querySelector('#game-message');
const turnLabel = document.querySelector('#turn-label');
const hexActions = document.querySelector('#hex-actions');
const endTurnButton = document.querySelector('#end-turn');
const battleModal = document.querySelector('#battle-modal');

async function refreshGameResources() {
  const [armyResponse, peasantsResponse] = await Promise.all([
    fetch(`${API_BASE}/cabinet/army`, {cache:'no-store'}),
    fetch(`${API_BASE}/cabinet/peasants`, {cache:'no-store'})
  ]);
  if (!armyResponse.ok || !peasantsResponse.ok) throw new Error('Не удалось загрузить ресурсы');
  const [army, peasants] = await Promise.all([armyResponse.json(), peasantsResponse.json()]);
  const food = Number(army.inventory?.food || 0);
  const population = (peasants.hexes || []).reduce((sum, hex) => sum + Number(hex.quantity || 0), 0);
  document.querySelector('#game-resources').textContent = `G:${army.gold}  F:${food}  P:${population}`;
}

function adjacentKeys(key) {
  const [q,r] = key.split(',').map(Number);
  return neighbors.map(([dq,dr])=>cellKey(q+dq,r+dr)).filter(next=>rowsByKey.has(next));
}
function movementTargets(key) {
  const result = new Set(adjacentKeys(key));
  result.delete(key); return [...result];
}
function setGameMessage(message) { gameMessage.textContent = message; }
function paintMoveTargets() {
  polygons.forEach((polygon,key)=>polygon.classList.toggle('move-target',game.selected && !game.moved && movementTargets(game.unitKey).includes(key) && rowsByKey.get(key)?.['Категория']!=='Море'));
}
function unitPosition(key) {
  const [q,r] = key.split(',').map(Number);
  return {x:HEX_WIDTH*(q+r/2), y:RADIUS*1.5*r};
}
async function createMapUnit() {
  const owned = mapRows.find(row=>row['Тип владельца']==='Игрок' && row['Владелец']===userId);
  const fallback = mapRows.find(row=>row['Категория'] && row['Категория']!=='Море') || mapRows[0];
  const start = owned || fallback;
  if (!start) return;
  const response=await fetch(`${API_BASE}/game/armies`,{cache:'no-store'});
  if (!response.ok) throw new Error(`Армии: HTTP ${response.status}`);
  game.armies=(await response.json()).generals.filter(item=>item.status==='active');
  game.general=game.armies[0] || null;
  if (!game.general) { setGameMessage('Создайте генерала и добавьте ему солдат в разделе «Армия» личного кабинета.'); return; }
  game.armyUnits=game.general.units;
  game.unitKey = cellKey(start.Q,start.R);
  game.ownerId = start['ID территории'] || '';
  const layer = document.createElementNS('http://www.w3.org/2000/svg','g'); layer.setAttribute('class','map-unit-layer'); overlay.append(layer);
  game.armies.forEach((general,index)=>{
    general.unitKey=Number.isInteger(general.q)&&Number.isInteger(general.r)?cellKey(general.q,general.r):game.unitKey;
    const image=document.createElementNS('http://www.w3.org/2000/svg','image'); image.id=`player-unit-${general.id}`; image.setAttribute('class','map-unit');
    image.setAttribute('href',general.icon); image.setAttribute('width','82'); image.setAttribute('height','82'); image.setAttribute('aria-label',`Генерал ${general.name}, юнитов: ${general.units.length}`); image.setAttribute('tabindex','0');
    image.addEventListener('click',event=>{event.stopPropagation();if(game.player!==1||game.moved)return;document.querySelectorAll('.map-unit').forEach(item=>item.classList.remove('selected'));game.general=general;game.armyUnits=general.units;game.unitKey=general.unitKey;game.selected=true;image.classList.add('selected');paintMoveTargets();setGameMessage(`Армия «${general.name}»: выберите соседний гекс.`);});
    layer.append(image); positionGeneralImage(general,index,false);
  });
  const activeResponse=await fetch(`${API_BASE}/game/active-battle`,{cache:'no-store'});
  if(activeResponse.ok){
    const active=await activeResponse.json();
    if(active.battle){game.battle=active;renderBattle();battleModal.showModal();}
  }
}
function positionGeneralImage(general,index,animate=true) { const image=document.querySelector(`#player-unit-${general.id}`) || document.getElementById(`player-unit-${general.id}`); if(!image)return; const {x,y}=unitPosition(general.unitKey);if(!animate)image.style.transition='none';image.setAttribute('x',(x-41+index*24).toFixed(2));image.setAttribute('y',(y-55).toFixed(2));if(!animate)requestAnimationFrame(()=>image.style.removeProperty('transition')); }
function moveUnitImage(key,animate=true) {
  const image=document.querySelector(`#player-unit-${game.general?.id}`); if (!image) return;
  const {x,y}=unitPosition(key); if (!animate) image.style.transition='none';
  image.setAttribute('x',(x-41).toFixed(2)); image.setAttribute('y',(y-55).toFixed(2));
  if (!animate) requestAnimationFrame(()=>image.style.removeProperty('transition'));
}
async function handleGameHexClick(row) {
  const target=cellKey(row.Q,row.R);
  if (game.player!==1 || !game.selected || game.moved || !movementTargets(game.unitKey).includes(target)) return;
  if (row['Категория']==='Море') { setGameMessage('Морские гексы недоступны: по ним смогут двигаться только корабли.'); return; }
  game.pendingRow=row;
  if(row['Тип владельца']==='Игрок'&&row['Владелец']===userId){
    try{
      const response=await fetch(`${API_BASE}/game/generals/${game.general.id}/move`,{
        method:'POST',headers:{'X-CSRF-Token':csrfToken,'Content-Type':'application/json'},
        body:JSON.stringify({q:row.Q,r:row.R})});
      const result=await response.json();if(!response.ok)throw new Error(result.error||`HTTP ${response.status}`);
      game.unitKey=target;game.general.unitKey=target;game.general.q=row.Q;game.general.r=row.R;
      game.general.logistics_left=result.logistics_left;moveUnitImage(target);
      game.selected=false;paintMoveTargets();
      if(result.battle){game.battle=result.battle;renderBattle();battleModal.showModal();hexActions.hidden=true;}
      else showHexActions();
      setGameMessage(`Армия перешла на Q${row.Q} R${row.R}. Логистика: ${result.logistics_left}.`);
    }catch(error){setGameMessage(error.message);}return;
  }
  game.pendingRow=row; game.selected=false;
  document.querySelectorAll('.map-unit').forEach(item=>item.classList.remove('selected'));
  paintMoveTargets(); closeCard(); showHexActions();
}
function showHexActions() {
  const row=game.pendingRow; if (!row) return;
  const canClaim=row['Категория']!=='Море' && row['Владелец']!==userId && adjacentKeys(cellKey(row.Q,row.R)).some(key=>rowsByKey.get(key)?.['Владелец']===userId);
  document.querySelector('#claim-hex').hidden=!canClaim;
  document.querySelector('#claim-hex').title=canClaim?'':'Гекс должен соприкасаться с вашим владением';
  hexActions.hidden=false;
}
function finishHexAction(message) { hexActions.hidden=true; endTurnButton.hidden=false; setGameMessage(message); }
document.querySelector('#claim-hex')?.addEventListener('click',()=>openBattle('Защитник', 'capture'));
document.querySelector('#hold-hex')?.addEventListener('click',async()=>{
  if(!game.pendingRow||!game.general)return;
  try{const row=game.pendingRow;const response=await fetch(`${API_BASE}/game/generals/${game.general.id}/move`,{method:'POST',headers:{'X-CSRF-Token':csrfToken,'Content-Type':'application/json'},body:JSON.stringify({q:row.Q,r:row.R})});
    const result=await response.json();if(!response.ok)throw new Error(result.error||`HTTP ${response.status}`);
    const target=cellKey(row.Q,row.R);game.unitKey=target;game.general.unitKey=target;game.general.q=row.Q;game.general.r=row.R;game.general.logistics_left=result.logistics_left;moveUnitImage(target);
    finishHexAction(`Армия перешла на Q${row.Q} R${row.R}. Логистика: ${result.logistics_left}.`);
    if(result.battle){game.battle=result.battle;renderBattle();battleModal.showModal();}
  }catch(error){setGameMessage(error.message);}
});
document.querySelector('#raid-hex')?.addEventListener('click',()=>openBattle('Местное население','raid'));
let currentGlobalTurn = null;
let skipRefreshTimer = null;
async function refreshGameClock() {
  try {
    const response = await fetch(`${API_BASE}/game/clock`, {cache:'no-store'});
    if (!response.ok) return;
    const state = await response.json();
    document.querySelector('#game-date').textContent = state.label;
    refreshGameResources().catch(error => {
      document.querySelector('#game-resources').textContent = 'Ресурсы недоступны';
      console.error('Ресурсы:', error);
    });
    if (currentGlobalTurn !== null && currentGlobalTurn !== state.turn) {
      game.moved = false; game.pendingRow = null; game.player = 1;
      setGameMessage('Начался новый глобальный ход.');
    }
    currentGlobalTurn = state.turn;
    game.player = state.voted ? 2 : 1;
    turnLabel.textContent = `Ход ${state.turn + 1} · готово ${state.ready_players}/${state.online_players}`;
    endTurnButton.textContent = state.voted ? 'Ожидание игроков' : 'Конец хода';
    endTurnButton.disabled = !state.can_vote || state.voted;
    const skip=document.querySelector('#skip-turn');skip.hidden=!state.voted;skip.disabled=!state.can_skip;
    if(state.skip_at&&!state.can_skip)skip.title=`Доступно после ${new Date(state.skip_at).toLocaleTimeString('ru-RU')}`;
    clearTimeout(skipRefreshTimer);
    if(state.skip_at&&!state.can_skip)skipRefreshTimer=setTimeout(refreshGameClock,Math.max(1000,new Date(state.skip_at).getTime()-Date.now()+250));
    if (state.can_vote) endTurnButton.hidden = false;
  } catch (error) { console.error('Часы игры:', error); }
}
endTurnButton?.addEventListener('click',async()=>{
  endTurnButton.disabled = true;
  try {
    const response = await fetch(`${API_BASE}/game/clock/end-turn`, {method:'POST',headers:{'X-CSRF-Token':csrfToken,'Content-Type':'application/json'},body:JSON.stringify({turn:currentGlobalTurn})});
    const state = await response.json();
    if (!response.ok) throw new Error(state.error || `HTTP ${response.status}`);
    hexActions.hidden = true;
    setGameMessage(state.voted ? 'Ход завершён. Ожидаем остальных игроков.' : 'Начался новый глобальный ход.');
    await refreshGameClock();
  } catch (error) { setGameMessage(error.message); endTurnButton.disabled = false; }
});
document.querySelector('#skip-turn')?.addEventListener('click',async()=>{
  try{const response=await fetch(`${API_BASE}/game/clock/skip`,{method:'POST',headers:{'X-CSRF-Token':csrfToken,'Content-Type':'application/json'},body:JSON.stringify({turn:currentGlobalTurn})});
    const result=await response.json();if(!response.ok)throw new Error(result.error||`HTTP ${response.status}`);
    await refreshGameClock();setGameMessage('Начался новый глобальный ход.');
  }catch(error){setGameMessage(error.message);}
});
if (!creatingBarony) setInterval(refreshGameClock,30000);

function unitCard(unit) {
  const button=document.createElement('button'); button.type='button'; button.className='battle-unit';
  button.dataset.side=unit.side; button.dataset.id=unit.id;
  if (unit.health<=0) button.classList.add('defeated');
  if (unit.moved || unit.attacked || !unit.active) button.classList.add('spent');
  if(unit.side==='attacker'&&game.battle?.battle.deployment_locked&&!game.battle?.eligible_unit_ids?.includes(unit.id))button.disabled=true;
  const label=document.createElement('span'); label.textContent=`${unit.name} · ${unit.health}/${unit.max_health} · ${unit.x},${unit.y}`;
  if(!unit.is_wall){const img=document.createElement('img');img.src=unit.image_path;img.alt=unit.name;button.append(img);}
  button.append(label); button.addEventListener('click',()=>battleUnitClick(unit));button.addEventListener('contextmenu',event=>{event.preventDefault();showBattleUnitDetails(unit);}); return button;
}
function showBattleUnitDetails(unit){
  const dialog=document.querySelector('#battle-unit-details');document.querySelector('#battle-unit-details-title').textContent=unit.name;
  const body=document.querySelector('#battle-unit-details-body');body.replaceChildren();
  for(const [label,value] of Object.entries({'Сторона':unit.side==='attacker'?'Нападающий':'Защитник','Здоровье':`${unit.health}/${unit.max_health}`,'Атака':unit.attack,'Защита':unit.defense,'Броня':unit.armor,'Дальность':unit.attack_range,'Скорость':unit.speed,'Инициатива':unit.initiative})){
    const line=document.createElement('p');line.textContent=`${label}: ${value}`;body.append(line);
  }
  dialog.showModal();
}
function tacticalDistance(a,b){return Math.max(Math.abs(a.x-b.x),Math.abs(a.y-b.y),Math.abs(a.x+a.y-b.x-b.y));}
function battleReachable(unit,x,y,units){
  if(unit.moved||unit.attacked||unit.speed<1||units.some(other=>other.id!==unit.id&&other.health>0&&other.x===x&&other.y===y))return false;
  const seen=new Set([`${unit.x},${unit.y}`]),queue=[[unit.x,unit.y,0]];
  while(queue.length){const [cx,cy,steps]=queue.shift();if(cx===x&&cy===y)return true;if(steps>=unit.speed)continue;
    for(const [dx,dy] of neighbors){const nx=cx+dx,ny=cy+dy,key=`${nx},${ny}`;
      if(nx<0||nx>=10||ny<0||ny>=10||seen.has(key)||units.some(other=>other.id!==unit.id&&other.health>0&&other.x===nx&&other.y===ny))continue;
      seen.add(key);queue.push([nx,ny,steps+1]);
    }
  }
  return false;
}
function battleLog(message) { const line=document.createElement('li'); line.textContent=message; document.querySelector('#battle-log').append(line); line.scrollIntoView({block:'nearest'}); }
function battleAttackLog(event,units){
  const details=event.details||{};
  const attacker=units.find(unit=>unit.id===details.attacker_id)?.name||`Юнит №${details.attacker_id}`;
  const target=units.find(unit=>unit.id===details.target_id)?.name||`юнита №${details.target_id}`;
  return `Раунд ${event.round}: ${attacker} атаковал ${target}. Бросок атаки: ${details.attack_roll}. Бросок защиты: ${details.defense_roll}. Урон: ${details.damage}.`;
}
async function battleCommand(path,payload) {
  const response=await fetch(`${API_BASE}${path}`,{method:'POST',headers:{'X-CSRF-Token':csrfToken,'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const data=await response.json(); if (!response.ok) throw new Error(data.error||`HTTP ${response.status}`);
  game.battle=data; game.selectedUnit=null; renderBattle();
}
async function openBattle(_enemy,purpose='capture') {
  if (!game.general || !game.pendingRow) return;
  try {
    await battleCommand(`/game/hexes/${game.pendingRow.Q}/${game.pendingRow.R}/${purpose}`,{general_id:game.general.id});
    hexActions.hidden=true; endTurnButton.hidden=true; battleModal.showModal();
  } catch(error) { setGameMessage(`Бой не начался: ${error.message}`); }
}
function renderBattle() {
  const state=game.battle; if (!state) return;
  document.querySelector('#attackers').replaceChildren(...state.units.filter(u=>u.side==='attacker').map(unitCard));
  document.querySelector('#defenders').replaceChildren(...state.units.filter(u=>u.side==='defender').map(unitCard));
  document.querySelector('#battle-log').replaceChildren();
  const attacks=state.events.filter(event=>event.type==='attack').slice(-12);
  if(attacks.length)attacks.forEach(event=>battleLog(battleAttackLog(event,state.units)));
  else battleLog('Атак пока не было.');
  document.querySelector('#battle-status').textContent=state.battle.status==='active'
    ? state.battle.deployment_locked
      ? `Раунд ${state.battle.round_number}. Действуют: ${state.units.filter(u=>state.eligible_unit_ids.includes(u.id)).map(u=>u.name).join(', ') || 'защитники'}.`
      : 'Расставьте бойцов в первых четырёх столбцах и нажмите «Начать бой».'
    : `Бой завершён: ${state.battle.status}`;
  document.querySelector('#battle-deploy').hidden=state.battle.status!=='active'||state.battle.deployment_locked;
  document.querySelector('#battle-end-round').disabled=state.battle.status!=='active'||!state.battle.deployment_locked;
  document.querySelector('#battle-retreat').disabled=state.battle.status!=='active'||state.battle.round_number<2;
  const targetRow=rowsByKey.get(cellKey(state.battle.target_q,state.battle.target_r));
  document.querySelector('#battle-destroy').hidden=!(state.battle.status==='attacker_won'&&state.battle.purpose==='raid'
    &&!(state.battle.target_owner_type==='Игрок'&&state.battle.target_owner_id===userId)
    &&!state.battle.destroyed_at&&Number(targetRow?.['Уровень гекса']||0)>0);
  const field=document.querySelector('#battle-grid'); field.replaceChildren();
  for(let y=0;y<10;y++)for(let x=0;x<10;x++){
    const cell=document.createElement('button'); cell.type='button'; cell.className='battle-cell'; cell.title=`${x},${y}`;
    if(y%2)cell.style.transform='translateX(50%)';
    const unit=state.units.find(item=>item.health>0&&item.x===x&&item.y===y);
    if(unit){if(unit.is_wall)cell.textContent='▦';else{const img=document.createElement('img');img.src=unit.image_path;img.alt=unit.name;cell.append(img);}cell.title=`${unit.name}: ${unit.health}/${unit.max_health}`;cell.classList.add(unit.is_wall?'wall':unit.side);}
    if(unit&&state.eligible_unit_ids.includes(unit.id))cell.classList.add('active-unit');
    if(unit&&game.selectedUnit?.id===unit.id)cell.classList.add('selected-unit');
    if(game.selectedUnit&&state.battle.deployment_locked){
      if(!unit&&battleReachable(game.selectedUnit,x,y,state.units))cell.classList.add('reachable');
      if(unit&&unit.side==='defender'&&game.selectedUnit.side==='attacker'&&!game.selectedUnit.attacked&&tacticalDistance(game.selectedUnit,unit)<=game.selectedUnit.attack_range&&!(game.selectedUnit.moved&&game.selectedUnit.attack_range>2))cell.classList.add('attackable');
    }
    if(unit)cell.addEventListener('contextmenu',event=>{event.preventDefault();showBattleUnitDetails(unit);});
    cell.addEventListener('click',()=>unit?battleUnitClick(unit):battleMove(x,y));field.append(cell);
  }
}
async function battleUnitClick(unit) {
  if (!game.battle || game.battle.battle.status!=='active' || unit.health<=0) return;
  if (unit.side==='attacker') {if(game.battle.battle.deployment_locked&&!game.battle.eligible_unit_ids.includes(unit.id))return;game.selectedUnit=unit;renderBattle();document.querySelector('#battle-status').textContent=`${unit.name}: выберите цель или зелёный гекс`;return;}
  if(!game.battle.battle.deployment_locked)return;
  if (!game.selectedUnit) return;
  try {await battleCommand(`/game/battles/${game.battle.battle.id}/units/${game.selectedUnit.id}/attack`,{target_id:unit.id,round:game.battle.battle.round_number});}
  catch(error){document.querySelector('#battle-status').textContent=error.message;}
}
async function battleMove(x,y) {
  if (!game.selectedUnit || game.battle?.battle.status!=='active') return;
  if(!game.battle.battle.deployment_locked){
    if(x>3||game.battle.units.some(unit=>unit.id!==game.selectedUnit.id&&unit.health>0&&unit.x===x&&unit.y===y))return;
    game.selectedUnit.x=x;game.selectedUnit.y=y;renderBattle();return;
  }
  try {await battleCommand(`/game/battles/${game.battle.battle.id}/units/${game.selectedUnit.id}/move`,{x,y,round:game.battle.battle.round_number});}
  catch(error){document.querySelector('#battle-status').textContent=error.message;}
}
document.querySelector('#battle-deploy')?.addEventListener('click',async()=>{
  const positions=game.battle.units.filter(unit=>unit.side==='attacker'&&unit.health>0).map(({id,x,y})=>({id,x,y}));
  try{await battleCommand(`/game/battles/${game.battle.battle.id}/deployment`,{positions});}
  catch(error){document.querySelector('#battle-status').textContent=error.message;}
});
document.querySelector('#battle-end-round')?.addEventListener('click',async()=>{
  try {await battleCommand(`/game/battles/${game.battle.battle.id}/end-turn`,{round:game.battle.battle.round_number});}
  catch(error){document.querySelector('#battle-status').textContent=error.message;}
});
document.querySelector('#battle-retreat')?.addEventListener('click',async()=>{
  if(!window.confirm('Отступить и завершить действия армии в этом ходу?'))return;
  try {await battleCommand(`/game/battles/${game.battle.battle.id}/retreat`,{round:game.battle.battle.round_number});}
  catch(error){document.querySelector('#battle-status').textContent=error.message;}
});
document.querySelector('#battle-destroy')?.addEventListener('click',async()=>{
  try{
    const response=await fetch(`${API_BASE}/game/battles/${game.battle.battle.id}/destroy`,{method:'POST',headers:{'X-CSRF-Token':csrfToken}});
    const data=await response.json();if(!response.ok)throw new Error(data.error||`HTTP ${response.status}`);
    game.battle=data.battle;const row=rowsByKey.get(cellKey(game.battle.battle.target_q,game.battle.battle.target_r));
    if(row){row['Уровень гекса']=String(data.new_level);row['Постройка']=data.building;}
    renderBattle();
  }catch(error){document.querySelector('#battle-status').textContent=error.message;}
});
document.querySelector('#finish-battle')?.addEventListener('click',async()=>{
  if(game.battle?.battle.status==='active')return;
  battleModal.close();game.battle=null;game.selectedUnit=null;game.pendingRow=null;game.selected=false;hexActions.hidden=true;
  try{const response=await fetch(`${API_BASE}/hexes`,{cache:'no-store'});const data=await response.json();if(!response.ok)throw new Error(data.error||`HTTP ${response.status}`);
    polygons.forEach(polygon=>polygon.remove());polygons.clear();rowsByKey.clear();render(data);
    const army=await fetch(`${API_BASE}/game/armies`,{cache:'no-store'});if(army.ok){game.armies=(await army.json()).generals.filter(item=>item.status==='active');
      document.querySelectorAll('.map-unit').forEach(image=>{if(!game.armies.some(general=>image.id===`player-unit-${general.id}`))image.remove();});
      for(const general of game.armies){general.unitKey=cellKey(general.q,general.r);positionGeneralImage(general,0,false);}
      game.general=game.armies.find(general=>general.id===game.general?.id)||game.armies[0]||null;
      if(game.general){game.unitKey=game.general.unitKey;game.armyUnits=game.general.units;}
    }
    await refreshGameClock();setGameMessage('Бой завершён. Карта обновлена.');
  }catch(error){setGameMessage(`Не удалось обновить карту: ${error.message}`);}
});

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
  document.querySelector('#admin-link').href = '/admin/hexes';
  document.querySelector('#admin-menu-item').hidden = !canEdit;
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
  if (window.parent !== window && typeof window.parent.openPageModal === 'function') {
    window.parent.openPageModal(new URL('create-barony.html', window.location.href).href);
  } else {
    window.location.href = 'create-barony.html';
  }
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
    if (!creatingBarony) await refreshGameClock();
    if (!creatingBarony) await createMapUnit();
    await setupPlayerPage();
    document.querySelector("#data-status").textContent = `${VERSION} · источник: ${source}`;
    loading.remove();
  })
  .catch((error) => {
    loading.textContent = `Не удалось загрузить данные карты: ${error.message}. Повторите попытку или обратитесь к администратору.`;
    loading.classList.add("error");
  });
