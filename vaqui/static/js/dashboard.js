const fmt = (n) =>
  new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 }).format(n);
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const state = { month: new Date().toISOString().slice(0, 7), categories: [], accounts: [], hidden: false, summary: null };

async function api(url, method = "GET", body) {
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Ocurrió un error");
  return data;
}

// ---------- Mes ----------
function shiftMonth(delta) {
  const [y, m] = state.month.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  state.month = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  $("monthPicker").value = state.month;
  refresh();
}
$("monthPicker").value = state.month;
$("monthPicker").addEventListener("change", (e) => { if (e.target.value) { state.month = e.target.value; refresh(); } });
$("prevMonth").addEventListener("click", () => shiftMonth(-1));
$("nextMonth").addEventListener("click", () => shiftMonth(1));

// ---------- Resumen ----------
const money = (n) => (state.hidden ? "••••••" : fmt(n));

// Anima el número desde su valor anterior hasta el nuevo
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
function setMoney(el, value) {
  const from = Number(el.dataset.value || 0);
  el.dataset.value = value;
  if (state.hidden || reduceMotion || from === value) { el.textContent = money(value); return; }
  const start = performance.now(), dur = 700;
  cancelAnimationFrame(el._raf);
  const tick = (now) => {
    const t = Math.min((now - start) / dur, 1);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = fmt(from + (value - from) * eased);
    if (t < 1) el._raf = requestAnimationFrame(tick);
  };
  el._raf = requestAnimationFrame(tick);
}

function renderSummary() {
  const s = state.summary;
  if (!s) return;
  setMoney($("totalBalance"), s.total_balance);
  setMoney($("kpiIncome"), s.income);
  setMoney($("kpiExpense"), s.expense);
  setMoney($("kpiNet"), s.net);

  // Gasto por categoría
  const max = Math.max(...s.by_category.map((c) => c.amount), 1);
  $("categoryChart").innerHTML = s.by_category.length
    ? s.by_category.map((c) => `
        <div class="bar-row">
          <div class="bar-label"><span>${esc(c.name)}</span><strong>${money(c.amount)}</strong></div>
          <div class="bar-track"><div class="bar-fill" style="width:${(c.amount / max) * 100}%"></div></div>
        </div>`).join("")
    : `<p class="history-empty">Sin gastos este mes</p>`;

  // Presupuestos
  $("budgetList").innerHTML = s.budgets.length
    ? s.budgets.map((b) => {
        const cls = b.percent >= 100 ? "over" : b.percent >= 80 ? "warn" : "";
        return `
        <div class="bar-row">
          <div class="bar-label"><span>${esc(b.category)}</span>
            <span>${money(b.spent)} / ${money(b.limit)}
              <button class="link-btn danger" data-del-budget="${b.id}" aria-label="Quitar">✕</button></span></div>
          <div class="bar-track"><div class="bar-fill ${cls}" style="width:${Math.min(b.percent, 100)}%"></div></div>
          <div class="bar-note ${cls}">${b.percent}% usado${b.percent >= 100 ? " · ¡límite superado!" : ""}</div>
        </div>`;
      }).join("")
    : `<p class="history-empty">Aún no defines presupuestos</p>`;

  // Tendencia
  const tmax = Math.max(...s.trend.flatMap((t) => [t.income, t.expense]), 1);
  $("trendChart").innerHTML = s.trend.map((t) => `
    <div class="trend-col" title="${t.month}: ingresos ${fmt(t.income)} · gastos ${fmt(t.expense)}">
      <div class="trend-bars">
        <div class="tbar in" style="height:${(t.income / tmax) * 100}%"></div>
        <div class="tbar out" style="height:${(t.expense / tmax) * 100}%"></div>
      </div>
      <span class="trend-label">${t.month.slice(5)}/${t.month.slice(2, 4)}</span>
    </div>`).join("");

  // Cuentas
  const kinds = { cash: "Efectivo", bank: "Banco", card: "Tarjeta", savings: "Ahorros" };
  $("accountList").innerHTML = s.accounts.map((a) => `
    <li class="history-item">
      <div class="history-info"><div class="history-title">${esc(a.name)}</div>
        <div class="history-date">${kinds[a.kind] || a.kind}</div></div>
      <div class="history-amount">${money(a.balance)}</div>
      <button class="link-btn danger" data-del-account="${a.id}" aria-label="Eliminar">✕</button>
    </li>`).join("");
}

$("toggleBalance").addEventListener("click", () => {
  state.hidden = !state.hidden;
  $("toggleBalance").textContent = state.hidden ? "Mostrar" : "Ocultar";
  renderSummary(); loadMovements();
});

async function loadSummary() {
  state.summary = await api(`/api/summary?month=${state.month}`);
  state.accounts = state.summary.accounts;
  renderSummary();
}

// ---------- Movimientos ----------
async function loadMovements() {
  const p = new URLSearchParams({ month: state.month });
  if ($("filterType").value) p.set("type", $("filterType").value);
  if ($("filterCategory").value) p.set("category_id", $("filterCategory").value);
  if ($("filterText").value.trim()) p.set("q", $("filterText").value.trim());
  const items = await api(`/api/movements?${p}`);

  $("historyList").innerHTML = items.length
    ? items.map((tx) => {
        const isIn = tx.type === "income";
        return `
        <li class="history-item">
          <div class="history-info">
            <div class="history-title">${esc(tx.description || tx.category)}</div>
            <div class="history-date">${tx.date} · ${esc(tx.category)} · ${esc(tx.account)}</div>
          </div>
          <div class="history-amount ${isIn ? "in" : "out"}">${isIn ? "+" : "−"} ${money(tx.amount)}</div>
          <button class="link-btn danger" data-del-mv="${tx.id}" aria-label="Eliminar">✕</button>
        </li>`;
      }).join("")
    : `<li class="history-empty">No hay movimientos con estos filtros</li>`;
}
["filterType", "filterCategory"].forEach((id) => $(id).addEventListener("change", loadMovements));
$("filterText").addEventListener("input", () => { clearTimeout(loadMovements.t); loadMovements.t = setTimeout(loadMovements, 250); });

// ---------- Catálogos ----------
async function loadCategories() {
  state.categories = await api("/api/categories");
  const opts = state.categories.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
  $("filterCategory").innerHTML = `<option value="">Todas las categorías</option>` + opts;
  $("bgCategory").innerHTML = state.categories.filter((c) => c.type === "expense")
    .map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
}

function fillMovementForm(type) {
  $("mvType").value = type;
  $("movementTitle").textContent = type === "income" ? "Nuevo ingreso" : "Nuevo gasto";
  $("mvCategory").innerHTML = state.categories.filter((c) => c.type === type)
    .map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
  $("mvAccount").innerHTML = state.accounts.map((a) => `<option value="${a.id}">${esc(a.name)}</option>`).join("");
  $("mvDate").value = new Date().toLocaleDateString("en-CA");
}

// ---------- Modales ----------
const openModal = (id) => $(id).classList.add("open");
const closeModal = (id) => $(id).classList.remove("open");
document.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => closeModal(b.dataset.close)));
document.querySelectorAll(".modal-overlay").forEach((o) =>
  o.addEventListener("click", (e) => { if (e.target === o) o.classList.remove("open"); }));

$("openIncome").addEventListener("click", () => { fillMovementForm("income"); openModal("movementModal"); });
$("openExpense").addEventListener("click", () => { fillMovementForm("expense"); openModal("movementModal"); });
$("openBudget").addEventListener("click", () => openModal("budgetModal"));
$("openAccount").addEventListener("click", () => openModal("accountModal"));

function submitForm(formId, errorId, modalId, url, buildBody) {
  $(formId).addEventListener("submit", async (e) => {
    e.preventDefault();
    $(errorId).textContent = "";
    try {
      await api(url, "POST", buildBody());
      closeModal(modalId);
      e.target.reset();
      await refresh();
    } catch (err) {
      $(errorId).textContent = err.message;
    }
  });
}

submitForm("movementForm", "movementError", "movementModal", "/api/movements", () => ({
  type: $("mvType").value,
  amount: Number($("mvAmount").value),
  category_id: $("mvCategory").value,
  account_id: $("mvAccount").value,
  date: $("mvDate").value,
  description: $("mvDesc").value.trim(),
}));
submitForm("budgetForm", "budgetError", "budgetModal", "/api/budgets", () => ({
  category_id: $("bgCategory").value, monthly_limit: Number($("bgLimit").value),
}));
submitForm("accountForm", "accountError", "accountModal", "/api/accounts", () => ({
  name: $("acName").value.trim(), kind: $("acKind").value, initial_balance: Number($("acInitial").value || 0),
}));

// ---------- Eliminar (delegación) ----------
document.addEventListener("click", async (e) => {
  const t = e.target.closest("[data-del-mv],[data-del-budget],[data-del-account]");
  if (!t) return;
  const [url, msg] = t.dataset.delMv ? [`/api/movements/${t.dataset.delMv}`, "¿Eliminar este movimiento?"]
    : t.dataset.delBudget ? [`/api/budgets/${t.dataset.delBudget}`, "¿Quitar este presupuesto?"]
    : [`/api/accounts/${t.dataset.delAccount}`, "¿Eliminar esta cuenta?"];
  if (!confirm(msg)) return;
  try { await api(url, "DELETE"); await refresh(); } catch (err) { alert(err.message); }
});

// ---------- Init ----------
async function refresh() { await Promise.all([loadSummary(), loadMovements()]); }
loadCategories().then(refresh);
