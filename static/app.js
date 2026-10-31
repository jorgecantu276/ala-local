"use strict";
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
let state,
  currentView = "agenda",
  selectedDay = null,
  editing = null,
  month = new Date().getMonth(),
  year = new Date().getFullYear(),
  saving = false;
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const form = $("#booking-form");
const field = (name) => form.elements.namedItem(name);
const dateKey = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const tz = () => state.settings.timezone;
function parts(date, zone = tz()) {
  const p = new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(date));
  return Object.fromEntries(
    p.filter((x) => x.type !== "literal").map((x) => [x.type, x.value]),
  );
}
function localInput(iso) {
  const p = parts(iso);
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
function localDay(iso) {
  return localInput(iso).slice(0, 10);
}
function label(iso, compact = false) {
  return new Intl.DateTimeFormat("es-MX", {
    timeZone: tz(),
    day: "2-digit",
    month: "short",
    ...(compact ? {} : { year: "numeric" }),
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(iso));
}
// Resolve a wall-clock input in the selected IANA zone, including DST gaps and repeated hours.
function zonedISO(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!m) throw Error("Completa las fechas de la reserva.");
  const target = Date.UTC(...[+m[1], +m[2] - 1, +m[3], +m[4], +m[5]]),
    offsets = new Set();
  for (let h = -36; h <= 36; h += 6) {
    const probe = target + h * 3600000,
      p = parts(probe);
    offsets.add(
      Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second) -
        probe,
    );
  }
  const candidates = [...offsets]
    .map((o) => target - o)
    .filter((v) => localInput(v) === value);
  if (!candidates.length)
    throw Error(
      "Esa hora no existe por el cambio de horario. Elige otra hora.",
    );
  if (candidates.length > 1)
    throw Error(
      "Esa hora se repite por el cambio de horario. Elige una hora fuera de ese intervalo.",
    );
  return new Date(candidates[0]).toISOString();
}
async function api(path, method = "GET", data) {
  const r = await fetch(path, {
    method,
    ...(data
      ? {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        }
      : {}),
  });
  const result = await r.json();
  if (!r.ok) throw Error(result.error || "No se pudo completar la operación.");
  return result;
}
function notify(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => ($("#toast").hidden = true), 4500);
}
function setView(name) {
  currentView = name;
  $$(".view").forEach((e) => (e.hidden = e.id !== `view-${name}`));
  $$(".nav-item").forEach((e) =>
    e.classList.toggle("active", e.dataset.view === name),
  );
  if (name === "settings" && state) renderSettings();
}
function ownerName(b) {
  return b.kind === "Vuelo" ? state.settings.people[b.owner] : "Mantenimiento";
}
function ownerClass(b) {
  return b.kind === "Mantenimiento" ? "maintenance" : `owner${b.owner}`;
}
function filtered() {
  const f = $("#person-filter").value;
  return state.bookings.filter(
    (b) =>
      (b.status !== "Cancelada" || $("#include-cancelled").checked) &&
      (f === "all" || String(b.owner) === f),
  );
}
function intersectsDay(b, key) {
  return (
    localDay(b.start) <= key &&
    localDay(new Date(new Date(b.end).getTime() - 1)) >= key
  );
}
function monthItems() {
  const first = `${year}-${String(month + 1).padStart(2, "0")}-01`,
    last = dateKey(new Date(year, month + 1, 0));
  return filtered().filter(
    (b) =>
      localDay(b.start) <= last &&
      localDay(new Date(new Date(b.end).getTime() - 1)) >= first,
  );
}
function renderSelectors() {
  const opts = state.settings.people
    .map((p, i) => `<option value="${i}">${esc(p)}</option>`)
    .join("");
  for (const id of ["person-filter", "report-person"]) {
    const old = $(`#${id}`).value;
    $(`#${id}`).innerHTML =
      '<option value="all">Todas las personas</option>' + opts;
    $(`#${id}`).value = old || "all";
  }
  field("owner").innerHTML = opts;
  $("#person-one-label").textContent = state.settings.people[0];
  $("#person-two-label").textContent = state.settings.people[1];
  $("#legend").innerHTML =
    state.settings.people
      .map((p, i) => `<span><i class="swatch owner${i}"></i>${esc(p)}</span>`)
      .join("") +
    '<span><i class="swatch maintenance"></i>Mantenimiento</span>';
  $("#aircraft-label").textContent = [
    state.settings.aircraft,
    state.settings.model,
  ]
    .filter(Boolean)
    .join(" / ");
  $("#timezone-label").textContent = tz();
  $("#buffer-label").innerHTML = `${state.settings.buffer} <small>min</small>`;
  $("#setup-notice").hidden = !(
    state.settings.aircraft === "Mi aeronave" &&
    state.settings.people[0] === "Persona 1"
  );
}
function renderCalendar() {
  $("#month-title").textContent = new Intl.DateTimeFormat("es-MX", {
    month: "long",
    year: "numeric",
  }).format(new Date(year, month, 15));
  const first = new Date(year, month, 1),
    offset = (first.getDay() + 6) % 7,
    start = new Date(year, month, 1 - offset),
    cells =
      Math.ceil((offset + new Date(year, month + 1, 0).getDate()) / 7) * 7;
  const items = filtered(),
    today = localDay(new Date());
  let html = "";
  for (let i = 0; i < cells; i++) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    const key = dateKey(d),
      bookings = items.filter((b) => intersectsDay(b, key));
    const events = bookings
      .slice(0, 2)
      .map(
        (b) =>
          `<span class="event ${ownerClass(b)} ${b.status === "Cancelada" ? "cancelled" : ""}">${esc(ownerName(b))}${b.kind === "Vuelo" ? " · " + esc(b.destination) : ""}</span>`,
      )
      .join("");
    html += `<button class="day ${d.getMonth() !== month ? "outside" : ""} ${key === today ? "is-today" : ""} ${key === selectedDay ? "selected" : ""}" data-day="${key}" aria-label="${key}, ${bookings.length} reservas" aria-pressed="${key === selectedDay}"><span class="day-number">${d.getDate()}</span>${events}${bookings.length > 2 ? `<span class="more-events">+${bookings.length - 2} más</span>` : ""}</button>`;
  }
  $("#calendar").innerHTML = html;
  const all = state.bookings.filter(
    (b) =>
      b.status !== "Cancelada" &&
      localDay(b.start) <= dateKey(new Date(year, month + 1, 0)) &&
      localDay(new Date(new Date(b.end).getTime() - 1)) >=
        dateKey(new Date(year, month, 1)),
  );
  $("#count-all").textContent = all.length;
  $("#count-one").textContent = all.filter((b) => b.owner === 0).length;
  $("#count-two").textContent = all.filter((b) => b.owner === 1).length;
  renderList();
}
function renderList() {
  const bookings = selectedDay
    ? filtered().filter((b) => intersectsDay(b, selectedDay))
    : monthItems();
  $("#list-title").textContent = selectedDay
    ? `Reservas del ${selectedDay.split("-").reverse().join("/")}`
    : "Reservas del mes";
  $("#clear-day").hidden = !selectedDay;
  if (!bookings.length) {
    $("#booking-list").innerHTML =
      `<div class="empty-state"><h2>Sin reservas ${selectedDay ? "este día" : "en este periodo"}</h2><p class="small muted">Agrega un viaje o un bloqueo de mantenimiento.</p><button class="secondary" id="empty-new">＋ Crear reserva</button></div>`;
    return;
  }
  $("#booking-list").innerHTML = bookings
    .map(
      (b) =>
        `<article class="booking-row ${ownerClass(b)} ${b.status === "Cancelada" ? "cancelled" : ""}"><div class="row-stripe"></div><div><p class="route-title">${b.kind === "Vuelo" ? `${esc(b.origin)} → ${esc(b.destination)}` : "Bloqueo de mantenimiento"}</p><p class="route-person">${esc(ownerName(b))}</p></div><div class="booking-dates"><div><span>Inicio</span> ${esc(label(b.start, true))}</div><div><span>Regreso</span> ${esc(label(b.end, true))}</div></div><span class="status ${b.status.toLowerCase()}">${esc(b.status)}</span><button class="quiet edit-button" data-edit="${b.id}">Abrir ↗</button></article>`,
    )
    .join("");
}
function renderSettings() {
  const f = $("#settings-form");
  for (const k of ["aircraft", "model", "base", "timezone", "buffer"])
    f.elements.namedItem(k).value = state.settings[k];
  f.elements.person0.value = state.settings.people[0];
  f.elements.person1.value = state.settings.people[1];
  $("#settings-status").textContent = "";
}
function renderHistory() {
  $("#history").innerHTML = state.history.length
    ? state.history
        .map(
          (h) =>
            `<div class="history-row"><span>${esc(h.action)}${h.booking_id ? " de reserva" : ""}</span><time>${esc(label(h.at))}</time></div>`,
        )
        .join("")
    : '<p class="small muted">El historial aparecerá al guardar la primera reserva.</p>';
}
async function load(initial = false) {
  try {
    state = await api("/api/state");
    $("#connection-error").hidden = true;
    if (initial) {
      const p = parts(new Date());
      year = +p.year;
      month = +p.month - 1;
      $("#report-from").value = dateKey(new Date(year, month, 1));
      $("#report-to").value = dateKey(new Date(year, month + 1, 0));
    }
    renderSelectors();
    renderCalendar();
    renderHistory();
    if (currentView === "settings") renderSettings();
  } catch (e) {
    $("#connection-error").textContent =
      "No se pudo conectar a la agenda. " + e.message;
    $("#connection-error").hidden = false;
  }
}
function openBooking(id) {
  if (!state) return;
  editing = id ? state.bookings.find((b) => b.id === id) : null;
  form.reset();
  $("#booking-error").hidden = true;
  $("#dialog-title").textContent = editing ? "Editar reserva" : "Nueva reserva";
  $("#booking-timezone").textContent = "Horarios en " + tz();
  if (editing) {
    for (const k of [
      "kind",
      "owner",
      "origin",
      "destination",
      "status",
      "notes",
    ])
      field(k).value = editing[k] ?? "";
    field("start").value = localInput(editing.start);
    field("end").value = localInput(editing.end);
  } else {
    const day = selectedDay || localDay(new Date());
    field("start").value = day + "T09:00";
    field("end").value = day + "T18:00";
    field("owner").value = "0";
  }
  syncKind();
  availability();
  $("#booking-dialog").showModal();
  field("kind").focus();
}
function syncKind() {
  const m = field("kind").value === "Mantenimiento";
  $("#owner-field").hidden = m;
  for (const k of ["origin", "destination"]) {
    field(k).disabled = m;
    field(k).required = !m;
  }
  availability();
}
function bookingPayload() {
  return {
    kind: field("kind").value,
    owner: +field("owner").value,
    origin: field("origin").value,
    destination: field("destination").value,
    start: zonedISO(field("start").value),
    end: zonedISO(field("end").value),
    status: field("status").value,
    notes: field("notes").value,
    ...(editing ? { version: editing.version } : {}),
  };
}
function availability() {
  if (!state) return;
  const el = $("#availability");
  el.classList.remove("conflict");
  let message = "";
  try {
    const b = bookingPayload(),
      start = +new Date(b.start),
      end = +new Date(b.end),
      gap = state.settings.buffer * 60000;
    if (end <= start)
      throw Error("La liberación debe ser posterior al inicio.");
    if (b.status === "Cancelada")
      message = "Al guardar como cancelada, se libera este periodo.";
    else {
      const hit = state.bookings.find(
        (x) =>
          x.id !== editing?.id &&
          x.status !== "Cancelada" &&
          start < +new Date(x.end) + gap &&
          end + gap > +new Date(x.start),
      );
      if (hit)
        throw Error(
          `Conflicto con ${ownerName(hit)}: ${label(hit.start)} a ${label(hit.end)}. Margen: ${state.settings.buffer} min.`,
        );
      message =
        "Periodo disponible en la agenda actual. Se comprobará otra vez al guardar.";
    }
  } catch (e) {
    message = e.message;
    el.classList.add("conflict");
  }
  el.textContent = message;
}
async function submitBooking(e) {
  e.preventDefault();
  if (saving) return;
  saving = true;
  $("#save-booking").disabled = true;
  $("#booking-error").hidden = true;
  try {
    await api(
      editing ? "/api/bookings/" + editing.id : "/api/bookings",
      editing ? "PUT" : "POST",
      bookingPayload(),
    );
    $("#booking-dialog").close();
    await load();
    notify("Reserva guardada. La agenda está actualizada.");
  } catch (e) {
    $("#booking-error").textContent = e.message;
    $("#booking-error").hidden = false;
  } finally {
    saving = false;
    $("#save-booking").disabled = false;
  }
}
async function download(path, filename, status) {
  try {
    if (status) status.textContent = "Generando documento…";
    const r = await fetch(path);
    if (!r.ok) {
      const d = await r.json();
      throw Error(d.error);
    }
    const url = URL.createObjectURL(await r.blob()),
      a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    if (status)
      status.textContent =
        "Documento generado. Revisa las descargas de tu navegador.";
  } catch (e) {
    if (status) status.textContent = e.message;
    else notify(e.message);
  }
}
async function exportReport(type) {
  const a = $("#report-from").value,
    b = $("#report-to").value;
  if (!a || !b || a > b) {
    $("#export-status").textContent = "Selecciona un periodo válido.";
    return;
  }
  const buttons = [$("#export-pdf"), $("#export-pptx")];
  buttons.forEach((b) => (b.disabled = true));
  await download(
    `/api/report.${type}?` +
      new URLSearchParams({
        from: a,
        to: b,
        person: $("#report-person").value,
      }),
    `programa-de-vuelos.${type}`,
    $("#export-status"),
  );
  buttons.forEach((b) => (b.disabled = false));
}
document.addEventListener("click", (e) => {
  const nav = e.target.closest("[data-view]");
  if (nav) setView(nav.dataset.view);
  const day = e.target.closest("[data-day]");
  if (day) {
    selectedDay = day.dataset.day;
    renderCalendar();
  }
  const edit = e.target.closest("[data-edit]");
  if (edit) openBooking(edit.dataset.edit);
  if (e.target.closest("#empty-new")) openBooking();
});
$("#new-booking").onclick = () => openBooking();
$("#refresh").onclick = () => load();
$("#prev-month").onclick = () => {
  month--;
  if (month < 0) {
    month = 11;
    year--;
  }
  selectedDay = null;
  renderCalendar();
};
$("#next-month").onclick = () => {
  month++;
  if (month > 11) {
    month = 0;
    year++;
  }
  selectedDay = null;
  renderCalendar();
};
$("#today").onclick = () => {
  const p = parts(new Date());
  year = +p.year;
  month = +p.month - 1;
  selectedDay = localDay(new Date());
  renderCalendar();
};
$("#clear-day").onclick = () => {
  selectedDay = null;
  renderCalendar();
};
$("#person-filter").onchange = renderCalendar;
$("#include-cancelled").onchange = renderCalendar;
$("#close-dialog").onclick = $("#cancel-dialog").onclick = () =>
  $("#booking-dialog").close();
form.onsubmit = submitBooking;
form.addEventListener("input", availability);
field("kind").onchange = syncKind;
$("#booking-dialog").addEventListener("cancel", (e) => {
  if (saving) e.preventDefault();
});
$("#settings-form").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.currentTarget,
    button = $("button[type=submit]", f);
  button.disabled = true;
  const data = Object.fromEntries(new FormData(f));
  data.people = [data.person0, data.person1];
  data.buffer = +data.buffer;
  data.version = state.settings.version;
  try {
    await api("/api/settings", "PUT", data);
    await load();
    $("#settings-status").textContent = "Configuración guardada.";
    notify("Configuración guardada.");
  } catch (err) {
    $("#settings-status").textContent = err.message;
  } finally {
    button.disabled = false;
  }
};
$("#export-pdf").onclick = () => exportReport("pdf");
$("#export-pptx").onclick = () => exportReport("pptx");
$("#backup").onclick = () => download("/api/backup", "ala-local-respaldo.json");
window.addEventListener("focus", () => {
  if (state && !$("#booking-dialog").open && currentView === "agenda") load();
});
load(true);
