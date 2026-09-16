"use strict";

const RADIUS = 80;
const HEX_WIDTH = Math.sqrt(3) * RADIUS;
const VERSION = "Rhisseth · Artistic V5 · интерактивная сетка";
const API_BASE = "/api";
let csrfToken = '';

const overlay = document.querySelector("#hex-overlay");
const viewport = document.querySelector("#map-viewport");
const loading = document.querySelector("#loading");
const card = document.querySelector("#hex-card");
let selectedHex = null;
let selectedRow = null;
const form = document.querySelector("#hex-form");
const saveStatus = document.querySelector("#save-status");

function polygonPoints(q, r) {
  const cx = HEX_WIDTH * (q + r / 2);
  const cy = RADIUS * 1.5 * r;
  return Array.from({ length: 6 }, (_, index) => {
    const angle = (60 * index - 30) * Math.PI / 180;
    return `${(cx + RADIUS * Math.cos(angle)).toFixed(2)},${(cy + RADIUS * Math.sin(angle)).toFixed(2)}`;
  }).join(" ");
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
  document.querySelector("#card-title").textContent = `Q${row.Q} · R${row.R}`;
  document.querySelector("#card-coordinates").textContent = `Q = ${row.Q}, R = ${row.R}`;
  Array.from(form.elements).forEach((element) => {
    if (element.name) element.value = row[element.name] ?? "";
  });
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
  const button = form.querySelector("button[type=submit]");
  const payload = Object.fromEntries(new FormData(form).entries());
  button.disabled = true;
  saveStatus.textContent = "Сохранение…";
  saveStatus.classList.remove("error");
  try {
    const response = await fetch(`${API_BASE}/hexes/${selectedRow.Q}/${selectedRow.R}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    Object.assign(selectedRow, result.row);
    selectedHex.setAttribute("aria-label", `Гекс Q ${selectedRow.Q}, R ${selectedRow.R}: ${selectedRow["Тип местности"]}`);
    saveStatus.textContent = "Сохранено в PostgreSQL";
  } catch (error) {
    saveStatus.textContent = `Ошибка: ${error.message}`;
    saveStatus.classList.add("error");
  } finally {
    button.disabled = false;
  }
});

function render(rows) {
  const fragment = document.createDocumentFragment();
  rows.filter((row) => row["Категория"] !== "Вне полотна").forEach((row) => {
    const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
    polygon.setAttribute("points", polygonPoints(Number(row.Q), Number(row.R)));
    polygon.setAttribute("class", "hex-hit");
    polygon.setAttribute("tabindex", "0");
    polygon.setAttribute("aria-label", `Гекс Q ${row.Q}, R ${row.R}: ${row["Тип местности"]}`);
    polygon.addEventListener("contextmenu", (event) => { event.preventDefault(); showCard(row, event, polygon); });
    polygon.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        const bounds = polygon.getBoundingClientRect();
        showCard(row, { clientX: bounds.right, clientY: bounds.top }, polygon);
      }
    });
    fragment.appendChild(polygon);
  });
  overlay.appendChild(fragment);
}

document.querySelector("#close-card").addEventListener("click", closeCard);
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
  document.querySelector('#user-status').textContent = `${identity.login} · ${identity.role}`;
  if (!identity.can_edit) {
    for (const element of form.elements) element.disabled = true;
    document.querySelector('#editor-hint').textContent = 'Режим просмотра · правая кнопка — сведения о гексе';
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

loadData()
  .then(({ rows, source }) => {
    render(rows);
    document.querySelector("#data-status").textContent = `${VERSION} · источник: ${source}`;
    loading.remove();
  })
  .catch((error) => {
    loading.textContent = `Не удалось загрузить данные карты: ${error.message}. Запустите приложение через локальный веб-сервер.`;
    loading.classList.add("error");
  });
