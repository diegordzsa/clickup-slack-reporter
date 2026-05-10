(function () {
  "use strict";

  const state = {
    data:        null,
    range:       "7d",
    customFrom:  null,
    customTo:    null,
    editor:      "all",
    client:      "all",
    mode:        "single",
    tableView:   "all",
    sortField:   "date",
    sortDir:     "desc",
  };

  let chartByEditor = null;
  let chartLeadtime = null;
  let chartTimeline = null;

  const COLORS = {
    ink:    "#1a1614",
    inkMute:"#8a847d",
    accent: "#b54f25",
    accentSoft: "#d97a4e",
    paper:  "#f4efe6",
    rule:   "#d8d1c2",
    compareA: "#1a1614",
    compareB: "#b54f25",
  };

  const CATEGORY_DISPLAY = {
    asignado:   "Asignado",
    en_curso:   "En curso",
    revision:   "Revision",
    aprobado:   "Aprobado",
    completado: "Completado",
  };

  Chart.defaults.font.family = '"Geist", -apple-system, sans-serif';
  Chart.defaults.font.size = 12;
  Chart.defaults.color = COLORS.ink;
  Chart.defaults.borderColor = COLORS.rule;

  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    try {
      const res = await fetch("data.json", { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      state.data = await res.json();
    } catch (err) {
      showError("No se pudo cargar data.json: " + err.message);
      return;
    }

    populateFilters();
    bindControls();
    setLastUpdated();

    document.getElementById("loader").hidden = true;
    document.getElementById("app").hidden = false;

    render();
  }

  function showError(msg) {
    document.getElementById("loader").hidden = true;
    const errBox = document.getElementById("error");
    errBox.hidden = false;
    document.getElementById("error-message").textContent = msg;
  }

  function setLastUpdated() {
    const d = state.data.generated_at ? new Date(state.data.generated_at) : new Date();
    const txt = d.toLocaleString("es-ES", {
      day: "2-digit", month: "long", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
    document.getElementById("last-updated").textContent = "Actualizado: " + txt;

    const stats = state.data.stats || {};
    const info  = (stats.total_tasks_in_snapshot || 0) + " tasks - " +
                  (stats.total_completed || 0) + " completadas - " +
                  (stats.total_editors || 0) + " editores";
    document.getElementById("snapshot-info").textContent = info;
  }

  function populateFilters() {
    const sel = document.getElementById("editor-filter");
    state.data.editors.forEach(e => {
      const opt = document.createElement("option");
      opt.value = e;
      opt.textContent = e;
      sel.appendChild(opt);
    });

    const cf = document.getElementById("client-filter");
    state.data.clients.forEach(c => {
      const btn = document.createElement("button");
      btn.className = "seg-btn";
      btn.dataset.client = c;
      btn.textContent = c;
      cf.appendChild(btn);
    });
  }

  function bindControls() {
    document.getElementById("range-buttons").addEventListener("click", e => {
      const btn = e.target.closest("button");
      if (!btn) return;
      activateInGroup("range-buttons", btn);
      state.range = btn.dataset.range;
      const customBox = document.getElementById("custom-dates");
      customBox.hidden = state.range !== "custom";
      render();
    });

    document.getElementById("date-from").addEventListener("change", e => {
      state.customFrom = e.target.value ? new Date(e.target.value) : null;
      if (state.range === "custom") render();
    });
    document.getElementById("date-to").addEventListener("change", e => {
      state.customTo = e.target.value ? new Date(e.target.value) : null;
      if (state.range === "custom") render();
    });

    document.getElementById("editor-filter").addEventListener("change", e => {
      state.editor = e.target.value;
      render();
    });

    document.getElementById("client-filter").addEventListener("click", e => {
      const btn = e.target.closest("button");
      if (!btn) return;
      activateInGroup("client-filter", btn);
      state.client = btn.dataset.client;
      render();
    });

    document.getElementById("mode-filter").addEventListener("click", e => {
      const btn = e.target.closest("button");
      if (!btn) return;
      activateInGroup("mode-filter", btn);
      state.mode = btn.dataset.mode;
      render();
    });

    document.getElementById("table-view-filter").addEventListener("click", e => {
      const btn = e.target.closest("button");
      if (!btn) return;
      activateInGroup("table-view-filter", btn);
      state.tableView = btn.dataset.view;
      renderTable();
    });

    document.querySelectorAll("#data-table th[data-sort]").forEach(th => {
      th.addEventListener("click", () => {
        const f = th.dataset.sort;
        if (state.sortField === f) {
          state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        } else {
          state.sortField = f;
          state.sortDir = "desc";
        }
        renderTable();
      });
    });
  }

  function activateInGroup(groupId, button) {
    const group = document.getElementById(groupId);
    group.querySelectorAll(".seg-btn").forEach(b => b.classList.remove("is-active"));
    button.classList.add("is-active");
  }

  function getRange(rangeId) {
    const now = new Date();
    let from, to;
    to = new Date(now);
    to.setHours(23, 59, 59, 999);

    switch (rangeId) {
      case "today":
        from = new Date(now); from.setHours(0,0,0,0);
        break;
      case "7d":
        from = new Date(now); from.setDate(from.getDate() - 6); from.setHours(0,0,0,0);
        break;
      case "30d":
        from = new Date(now); from.setDate(from.getDate() - 29); from.setHours(0,0,0,0);
        break;
      case "90d":
        from = new Date(now); from.setDate(from.getDate() - 89); from.setHours(0,0,0,0);
        break;
      case "all":
        from = new Date(2000, 0, 1);
        break;
      case "custom":
        from = state.customFrom || new Date(2000, 0, 1);
        to   = state.customTo   || new Date();
        if (state.customTo) {
          to = new Date(state.customTo); to.setHours(23,59,59,999);
        }
        break;
      default:
        from = new Date(2000, 0, 1);
    }
    return { from, to };
  }

  function getPreviousRange(rangeId) {
    const { from, to } = getRange(rangeId);
    const ms = to.getTime() - from.getTime();
    const prevTo = new Date(from.getTime() - 1);
    const prevFrom = new Date(prevTo.getTime() - ms);
    return { from: prevFrom, to: prevTo };
  }

  function applyFilters(tasks, range) {
    range = range || getRange(state.range);
    return tasks.filter(t => {
      if (!t.date_done) return false;
      const d = new Date(t.date_done);
      if (d < range.from || d > range.to) return false;
      if (state.client !== "all" && t.client !== state.client) return false;
      if (state.editor !== "all" && !t.assignees.includes(state.editor)) return false;
      return true;
    });
  }

  function applyFiltersAssigned(tasks) {
    return tasks.filter(t => {
      if (state.client !== "all" && t.client !== state.client) return false;
      if (state.editor !== "all" && !t.assignees.includes(state.editor)) return false;
      return true;
    });
  }

  function applyFiltersTransitions(transitions, range) {
    range = range || getRange(state.range);
    return transitions.filter(t => {
      if (!t.ts) return false;
      const d = new Date(t.ts);
      if (d < range.from || d > range.to) return false;
      if (state.client !== "all" && t.client !== state.client) return false;
      if (state.editor !== "all" && t.assignee !== state.editor) return false;
      return true;
    });
  }

  function render() {
    const range = getRange(state.range);
    const completedFiltered = applyFilters(state.data.completed_tasks, range);
    const transFiltered = applyFiltersTransitions(state.data.transitions, range);

    let prevCompletedFiltered = null;
    let prevTransFiltered = null;
    if (state.mode === "compare") {
      const prevRange = getPreviousRange(state.range);
      prevCompletedFiltered = applyFilters(state.data.completed_tasks, prevRange);
      prevTransFiltered = applyFiltersTransitions(state.data.transitions, prevRange);
    }

    const noteEl = document.getElementById("report-note");
    if (noteEl) noteEl.hidden = state.range !== "today";

    renderKPIs(transFiltered, completedFiltered, prevTransFiltered, prevCompletedFiltered);
    renderChartByEditor(transFiltered, prevTransFiltered);
    renderChartLeadtime(completedFiltered);
    renderChartTimeline(transFiltered, range, prevTransFiltered);
    renderTable();
  }

  function renderKPIs(transFiltered, completedFiltered, prevTrans, prevCompleted) {
    const isToday = state.range === "today";
    const subText = isToday ? "hoy" : "en el periodo";

    const asignados = applyFiltersAssigned(
      state.data.currently_assigned.filter(t => t.category === "asignado")
    );
    document.querySelector("#kpi-asignado .kpi-value").textContent = asignados.length;
    document.querySelector("#kpi-asignado .kpi-sub").textContent = "tareas en cola";

    const categories = ["en_curso", "revision", "aprobado", "completado"];
    const kpiIds = ["#kpi-en-curso", "#kpi-revision", "#kpi-aprobado", "#kpi-completado"];

    categories.forEach((cat, i) => {
      const count = transFiltered.filter(t => t.category === cat).length;
      document.querySelector(kpiIds[i] + " .kpi-value").textContent = count;
      document.querySelector(kpiIds[i] + " .kpi-sub").textContent = subText;
    });

    // Compare deltas
    const deltaEl = document.querySelector("#kpi-asignado .kpi-delta");
    if (deltaEl) { deltaEl.className = "kpi-delta"; deltaEl.textContent = ""; }

    if (prevTrans) {
      categories.forEach((cat, i) => {
        const curr = transFiltered.filter(t => t.category === cat).length;
        const prev = prevTrans.filter(t => t.category === cat).length;
        renderDelta(kpiIds[i] + " .kpi-delta", curr, prev);
      });
    } else {
      kpiIds.forEach(sel => {
        const el = document.querySelector(sel + " .kpi-delta");
        if (el) { el.className = "kpi-delta"; el.textContent = ""; }
      });
    }

    // Secondary KPIs
    const withTime = completedFiltered.filter(t => typeof t.lead_time_hours === "number" && t.lead_time_hours > 0);
    const avgH = withTime.length
      ? withTime.reduce((s, t) => s + t.lead_time_hours, 0) / withTime.length
      : 0;
    const kpiL = document.querySelector("#kpi-leadtime .kpi-value");
    if (avgH > 0) {
      const days = avgH / 24;
      kpiL.textContent = days >= 1 ? days.toFixed(1) + "d" : Math.round(avgH) + "h";
    } else {
      kpiL.textContent = "-";
    }
    document.querySelector("#kpi-leadtime .kpi-sub").textContent =
      withTime.length + " de " + completedFiltered.length + " con fechas";

    const counts = {};
    transFiltered.forEach(t => {
      counts[t.assignee] = (counts[t.assignee] || 0) + 1;
    });
    const top = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
    const kpiT = document.querySelector("#kpi-top .kpi-value");
    if (top) {
      kpiT.classList.add("is-text");
      kpiT.textContent = top[0];
      document.querySelector("#kpi-top .kpi-sub").textContent = top[1] + " transiciones";
    } else {
      kpiT.classList.remove("is-text");
      kpiT.textContent = "-";
      document.querySelector("#kpi-top .kpi-sub").textContent = "";
    }

    const active = applyFiltersAssigned(state.data.currently_assigned).length;
    document.querySelector("#kpi-active .kpi-value").textContent = active;
  }

  function renderDelta(selector, current, previous) {
    const el = document.querySelector(selector);
    if (!el) return;
    const diff = current - previous;
    const pct = previous > 0 ? Math.round((diff / previous) * 100) : null;
    const arrow = diff > 0 ? "^" : diff < 0 ? "v" : "=";
    const cls = diff > 0 ? "is-up" : diff < 0 ? "is-down" : "";
    const pctTxt = pct !== null ? Math.abs(pct) + "%" : "-";
    el.className = "kpi-delta " + cls;
    el.textContent = arrow + " " + Math.abs(diff) + " vs " + previous + " (" + pctTxt + ")";
  }

  function renderChartByEditor(transFiltered, prevTrans) {
    const counts = {};
    transFiltered.forEach(t => {
      counts[t.assignee] = (counts[t.assignee] || 0) + 1;
    });

    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 12);
    const labels = sorted.map(x => x[0]);
    const values = sorted.map(x => x[1]);

    const datasets = [{
      label: "Periodo actual",
      data: values,
      backgroundColor: COLORS.compareA,
      borderRadius: 0,
    }];

    if (prevTrans) {
      const prevCounts = {};
      prevTrans.forEach(t => {
        prevCounts[t.assignee] = (prevCounts[t.assignee] || 0) + 1;
      });
      const prevValues = labels.map(l => prevCounts[l] || 0);
      datasets.push({
        label: "Periodo anterior",
        data: prevValues,
        backgroundColor: COLORS.compareB,
        borderRadius: 0,
      });
    }

    const ctx = document.getElementById("chart-by-editor");
    if (chartByEditor) chartByEditor.destroy();
    chartByEditor = new Chart(ctx, {
      type: "bar",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: "y",
        plugins: {
          legend: { display: prevTrans ? true : false, position: "bottom", labels: { boxWidth: 12 } },
          tooltip: { backgroundColor: COLORS.ink, padding: 10 },
        },
        scales: {
          x: { grid: { color: COLORS.rule, drawBorder: false }, ticks: { precision: 0 } },
          y: { grid: { display: false }, ticks: { autoSkip: false } },
        },
      },
    });
  }

  function renderChartLeadtime(filtered) {
    const sums = {};
    filtered.forEach(t => {
      if (typeof t.lead_time_hours !== "number" || t.lead_time_hours <= 0) return;
      t.assignees.forEach(a => {
        if (!sums[a]) sums[a] = { total: 0, count: 0 };
        sums[a].total += t.lead_time_hours;
        sums[a].count += 1;
      });
    });

    const arr = Object.entries(sums)
      .map(([editor, x]) => ({ editor, days: (x.total / x.count) / 24, count: x.count }))
      .sort((a, b) => b.days - a.days)
      .slice(0, 12);

    const ctx = document.getElementById("chart-leadtime");
    if (chartLeadtime) chartLeadtime.destroy();
    chartLeadtime = new Chart(ctx, {
      type: "bar",
      data: {
        labels: arr.map(x => x.editor),
        datasets: [{
          label: "Dias promedio",
          data: arr.map(x => +x.days.toFixed(2)),
          backgroundColor: COLORS.accent,
          borderRadius: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: "y",
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: COLORS.ink, padding: 10,
            callbacks: {
              label: (item) => {
                const editor = arr[item.dataIndex];
                return item.parsed.x.toFixed(1) + " dias promedio (" + editor.count + " tareas)";
              },
            },
          },
        },
        scales: {
          x: { grid: { color: COLORS.rule, drawBorder: false }, title: { display: true, text: "Dias" } },
          y: { grid: { display: false }, ticks: { autoSkip: false } },
        },
      },
    });
  }

  function renderChartTimeline(transFiltered, range, prevTrans) {
    const byDay = bucketTransitionsByDay(transFiltered);
    const days = enumerateDays(range.from, range.to);
    const values = days.map(d => byDay[d] || 0);

    const datasets = [{
      label: "Transiciones",
      data: values,
      borderColor: COLORS.compareA,
      backgroundColor: "rgba(26, 22, 20, 0.08)",
      fill: true,
      tension: 0.25,
      pointRadius: 3,
      pointBackgroundColor: COLORS.compareA,
    }];

    if (prevTrans) {
      const prevRange = getPreviousRange(state.range);
      const prevByDay = bucketTransitionsByDay(prevTrans);
      const prevDays  = enumerateDays(prevRange.from, prevRange.to);
      const prevValues = prevDays.map(d => prevByDay[d] || 0);
      const aligned = days.map((_, i) => prevValues[i] !== undefined ? prevValues[i] : null);
      datasets.push({
        label: "Periodo anterior",
        data: aligned,
        borderColor: COLORS.compareB,
        backgroundColor: "rgba(181, 79, 37, 0.08)",
        borderDash: [4, 4],
        fill: false,
        tension: 0.25,
        pointRadius: 3,
        pointBackgroundColor: COLORS.compareB,
      });
    }

    const ctx = document.getElementById("chart-timeline");
    if (chartTimeline) chartTimeline.destroy();
    chartTimeline = new Chart(ctx, {
      type: "line",
      data: { labels: days, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: !!prevTrans, position: "bottom", labels: { boxWidth: 12 } },
          tooltip: { backgroundColor: COLORS.ink, padding: 10 },
        },
        scales: {
          x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 16 } },
          y: { beginAtZero: true, grid: { color: COLORS.rule, drawBorder: false }, ticks: { precision: 0 } },
        },
      },
    });
  }

  function bucketTransitionsByDay(transitions) {
    const out = {};
    transitions.forEach(t => {
      if (!t.ts) return;
      const key = t.ts.slice(0, 10);
      out[key] = (out[key] || 0) + 1;
    });
    return out;
  }

  function enumerateDays(from, to) {
    const days = [];
    const d = new Date(from);
    d.setHours(0, 0, 0, 0);
    const end = new Date(to);
    end.setHours(0, 0, 0, 0);
    while (d <= end) {
      days.push(d.toISOString().slice(0, 10));
      d.setDate(d.getDate() + 1);
    }
    return days;
  }

  function renderTable() {
    const range = getRange(state.range);
    let rows = [];

    if (state.tableView === "all" || state.tableView === "transitions") {
      const trans = applyFiltersTransitions(state.data.transitions, range);
      trans.forEach(t => {
        rows.push({
          name: t.name,
          client: t.client,
          list: t.list,
          assignee: t.assignee,
          category: t.category,
          date: t.ts,
          url: t.url,
        });
      });
    }

    if (state.tableView === "all" || state.tableView === "assigned") {
      const assigned = applyFiltersAssigned(
        state.data.currently_assigned.filter(t => t.category === "asignado")
      );
      assigned.forEach(t => {
        rows.push({
          name: t.name,
          client: t.client,
          list: t.list,
          assignee: t.assignees.join(", "),
          category: t.category,
          date: t.date_created,
          url: t.url,
        });
      });
    }

    if (state.tableView === "completado") {
      const completed = applyFilters(state.data.completed_tasks, range);
      completed.forEach(t => {
        rows.push({
          name: t.name,
          client: t.client,
          list: t.list,
          assignee: t.assignees.join(", "),
          category: "completado",
          date: t.date_done,
          url: t.url,
        });
      });
    }

    const sorted = [...rows].sort((a, b) => {
      const f = state.sortField;
      let av = a[f], bv = b[f];
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") {
        return state.sortDir === "asc" ? av - bv : bv - av;
      }
      av = String(av).toLowerCase(); bv = String(bv).toLowerCase();
      return state.sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
    });

    document.querySelectorAll("#data-table th").forEach(th => {
      th.classList.remove("is-sorted", "is-sorted-asc");
      if (th.dataset.sort === state.sortField) {
        th.classList.add(state.sortDir === "asc" ? "is-sorted-asc" : "is-sorted");
      }
    });

    const tbody = document.getElementById("data-table-body");
    tbody.innerHTML = "";

    sorted.slice(0, 200).forEach(row => {
      const tr = document.createElement("tr");
      const tagClass = row.client === "HAIR BIOLABS" ? "tag-hairbiolabs"
                     : row.client === "SKIN+"        ? "tag-skinplus" : "";
      const catLabel = CATEGORY_DISPLAY[row.category] || row.category;
      const catClass = "cat-" + row.category;
      tr.innerHTML =
        '<td>' + (row.url
          ? '<a href="' + row.url + '" target="_blank" rel="noopener">' + escapeHtml(row.name) + '</a>'
          : escapeHtml(row.name)) + '</td>' +
        '<td><span class="tag ' + tagClass + '">' + escapeHtml(row.client) + '</span></td>' +
        '<td>' + escapeHtml(row.list) + '</td>' +
        '<td>' + escapeHtml(row.assignee) + '</td>' +
        '<td><span class="cat-badge ' + catClass + '">' + catLabel + '</span></td>' +
        '<td class="num">' + formatDate(row.date) + '</td>';
      tbody.appendChild(tr);
    });

    const count = rows.length;
    document.getElementById("table-count").textContent =
      count + " tarea" + (count === 1 ? "" : "s") +
      (count > 200 ? " - mostrando 200" : "");
  }

  function formatDate(iso) {
    if (!iso) return "-";
    const d = new Date(iso);
    return d.toLocaleDateString("es-ES", { day: "2-digit", month: "short" });
  }
  function formatLeadtime(hours) {
    if (typeof hours !== "number" || hours <= 0) return "-";
    const days = hours / 24;
    return days >= 1 ? days.toFixed(1) + "d" : Math.round(hours) + "h";
  }
  function escapeHtml(s) {
    if (s == null) return "";
    return String(s).replace(/[&<>"']/g, ch => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;",
    }[ch]));
  }
})();
