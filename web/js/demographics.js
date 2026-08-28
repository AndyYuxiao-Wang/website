/* ============================================================
   DEMOGRAPHICS CHOROPLETH PANEL
   ------------------------------------------------------------
   A second, independent choropleth layer driven by
   data/demographics.json (constituency-level census/electoral
   demographics), grouped into categories (Ethnicity, Religion,
   Age, Education, Employment, Housing tenure, Other) via
   data/demographics_manifest.json.

   Sits alongside the party choropleth panel from chloro.js and
   takes over map shading whenever a category/field is selected;
   picking "Off" hands shading back to whatever chloro.js/app.js
   would otherwise draw. Independent of election year - the data
   doesn't change across years, only which SVG (2024 vs pre-2024
   boundaries) it's drawn onto.
   ============================================================ */

(function () {

  const GROUP_COLORS = {
    ethnicity: "#2f8fd1",
    religion: "#8a4fff",
    age: "#e08a1e",
    education: "#1e9e5a",
    employment: "#d1345b",
    housing: "#c9a227",
    other: "#8d8d95",
  };

  let manifest = null;       // { groups: [...], fields: [...] }
  let dataByName = new Map(); // Name -> record
  let fieldStats = {};        // key -> { min, max, mean }
  let ranksByField = {};       // key -> Map(Name -> rank), 1 = highest value
  let seatCount = 0;
  let loaded = false;
  let activeFieldKey = "";    // "" = layer off
  let currentResultsPanelSeat = null; // seat currently shown in the results panel, if any

  // Notable-stat thresholds (see computeNotableStats). A field only counts
  // as notable at all if it's in the top/bottom NOTABLE_FRACTION by rank
  // AND clears a minimum-requirement floor - otherwise a seat with e.g.
  // 0.5% Jewish population gets flagged just because most seats have ~0%
  // and it technically lands in the top quintile.
  const NOTABLE_FRACTION = 0.20;
  const MIN_ABS_FLOOR = 1.0;         // percentage points
  const MIN_TOP_MEAN_MULT = 1.5;     // top value must be >= 1.5x the national mean
  const MIN_BOTTOM_GAP_FRACTION = 0.15;  // bottom value must be >= 15% of the median below it

  // A qualifying "top" value under this is still real, but too small in
  // absolute terms to headline (1.9% Jewish next to 51.7% Degree-educated
  // makes the small community look like the bigger story) - list it as a
  // footnote instead of a main entry.
  const FOOTNOTE_ABS_FLOOR = 3.0;

  // "Low" is only a meaningful flag for fields with a substantial *typical*
  // value. Rare/skewed fields (Pakistani, Muslim, Jewish, ...) have a mean
  // pulled well above the pack by a handful of concentrated seats - Muslim's
  // mean is 5.5% but its median is 1.8%, since most seats sit low and a few
  // spike very high - so gating on the mean still lets near-zero "lows" like
  // 0.5% Muslim through. Gating on the *median* instead means bottom flags
  // are skipped entirely for any field where "near zero" already IS the
  // typical seat (Pakistani, Muslim, Jewish, Sikh, ...), while still firing
  // for fields most seats genuinely sit high on (Christian, Owner-Occupied,
  // Degrees, ...).
  const MIN_MEDIAN_FOR_BOTTOM = 5.0;

  // ---- Build panel markup -----------------------------------
  const panel = document.createElement("div");
  panel.id = "demographics-panel";
  panel.innerHTML = `
    <style>
      #demographics-panel {
        position: fixed;
        top: 420px;
        right: 16px;
        z-index: 1000;
        background: var(--bbc-panel, #232327);
        border: none;
        box-shadow: 0 6px 24px rgba(0,0,0,0.5);
        padding: 0 14px 14px;
        font-family: var(--font-body, "Roboto Condensed", Arial, sans-serif);
        font-size: 13px;
        color: #fff;
        width: 220px;
      }
      #demographics-panel-handle {
        margin: 0 -14px 10px -14px;
        padding: 10px 14px;
        background: #0c8f6e;
        cursor: grab;
        user-select: none;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      #demographics-panel-handle.dragging { cursor: grabbing; }
      #demographics-panel h4 {
        margin: 0;
        font-family: var(--font-head, "Archivo Black", sans-serif);
        font-size: 13px;
        font-weight: normal;
        letter-spacing: 0.02em;
        text-transform: uppercase;
        pointer-events: none;
      }
      #demographics-panel-handle .dp-drag-dots {
        font-size: 12px;
        color: rgba(255,255,255,0.7);
        letter-spacing: 1px;
        pointer-events: none;
      }
      #demographics-panel label {
        display: block;
        margin-top: 10px;
        font-weight: 700;
        font-size: 11px;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: #9a9aa3;
      }
      #demographics-panel select {
        width: 100%;
        margin-top: 4px;
        padding: 6px 8px;
        border: 1px solid var(--bbc-line, #3a3a40);
        font-family: var(--font-body, "Roboto Condensed", Arial, sans-serif);
        font-weight: 700;
        font-size: 13px;
        background: var(--bbc-panel-2, #2c2c31);
        color: #fff;
      }
      #demographics-panel select:disabled { opacity: 0.4; }
      #demographics-legend { margin-top: 12px; }
      #demographics-legend .dp-bar {
        height: 10px;
        border: 1px solid rgba(255,255,255,0.15);
      }
      #demographics-legend .dp-labels {
        display: flex;
        justify-content: space-between;
        font-size: 10px;
        font-weight: 700;
        color: #9a9aa3;
        margin-top: 4px;
      }
      #demographics-legend .dp-title {
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #9a9aa3;
        margin-bottom: 4px;
      }
      #demographics-note {
        margin-top: 10px;
        font-size: 11px;
        line-height: 1.4;
        color: #cfa93a;
      }
    </style>
    <div id="demographics-panel-handle">
      <h4>Demographics</h4>
      <span class="dp-drag-dots">⠿</span>
    </div>
    <label>Category
      <select id="demographics-category" disabled>
        <option value="">Loading…</option>
      </select>
    </label>
    <label>Field
      <select id="demographics-field" disabled></select>
    </label>
    <div id="demographics-legend"></div>
    <div id="demographics-note"></div>
  `;
  document.body.appendChild(panel);

  const categorySelect = panel.querySelector("#demographics-category");
  const fieldSelect = panel.querySelector("#demographics-field");
  const legendEl = panel.querySelector("#demographics-legend");
  const noteEl = panel.querySelector("#demographics-note");
  const dragHandle = panel.querySelector("#demographics-panel-handle");

  if (window.createInfoTip) {
    dragHandle.querySelector("h4").appendChild(window.createInfoTip(
      "Shades the map by a chosen census/demographic statistic per constituency. Only covers 2024-boundary maps, since that's the only boundary this data is keyed to."
    ));
  }

  // ---- Hover tooltip (shows the active field's value for the seat
  // under the cursor) ------------------------------------------------
  const tooltip = document.createElement("div");
  tooltip.id = "demographics-tooltip";
  tooltip.style.cssText = `
    position: fixed;
    z-index: 1100;
    display: none;
    pointer-events: none;
    background: rgba(20,20,23,0.95);
    border: 1px solid var(--bbc-line, #3a3a40);
    color: #fff;
    font-family: var(--font-body, "Roboto Condensed", Arial, sans-serif);
    font-size: 12px;
    padding: 6px 10px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.5);
    max-width: 220px;
  `;
  document.body.appendChild(tooltip);

  function showTooltip(x, y, name) {
    const field = manifest.fields.find(f => f.key === activeFieldKey);
    const record = dataByName.get(name);
    if (!field || !record) { tooltip.style.display = "none"; return; }

    const value = record[field.key];
    const rank = ranksByField[field.key].get(name);
    const valueText = (typeof value === "number") ? `${value.toFixed(1)}%` : "no data";
    const rankText = rank ? ` (${ordinal(rank)} of ${seatCount})` : "";

    tooltip.innerHTML = `
      <div style="font-weight:700;">${name}</div>
      <div style="color:#cfd2da;">${field.label}: <strong>${valueText}</strong>${rankText}</div>
    `;

    const offset = 16;
    let left = x + offset;
    let top = y + offset;
    if (left + 220 > window.innerWidth) left = x - 220 - offset;
    if (top + 60 > window.innerHeight) top = y - 60 - offset;

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
    tooltip.style.display = "block";
  }

  function hideTooltip() {
    tooltip.style.display = "none";
  }

  // Delegated so it works regardless of which SVG (conmap / conmap_2010)
  // is currently mounted, and doesn't need re-wiring on year/map switches.
  document.addEventListener("mousemove", (e) => {
    if (!activeFieldKey || !loaded) { hideTooltip(); return; }

    const el = e.target;
    if (!el || el.tagName !== "path" || !el.hasAttribute("inkscape:label")) {
      hideTooltip();
      return;
    }

    const name = el.getAttribute("inkscape:label");
    if (!dataByName.has(name)) { hideTooltip(); return; }

    showTooltip(e.clientX, e.clientY, name);
  });

  // ---- Draggable, same behaviour as the choropleth panel -----
  (function makeDraggable() {
    let isDragging = false;
    let offsetX = 0;
    let offsetY = 0;

    dragHandle.addEventListener("mousedown", (e) => {
      isDragging = true;
      const rect = panel.getBoundingClientRect();
      offsetX = e.clientX - rect.left;
      offsetY = e.clientY - rect.top;
      panel.style.left = `${rect.left}px`;
      panel.style.top = `${rect.top}px`;
      panel.style.right = "auto";
      dragHandle.classList.add("dragging");
      e.preventDefault();
    });

    document.addEventListener("mousemove", (e) => {
      if (!isDragging) return;
      const maxLeft = window.innerWidth - panel.offsetWidth;
      const maxTop = window.innerHeight - panel.offsetHeight;
      const newLeft = Math.min(Math.max(0, e.clientX - offsetX), maxLeft);
      const newTop = Math.min(Math.max(0, e.clientY - offsetY), maxTop);
      panel.style.left = `${newLeft}px`;
      panel.style.top = `${newTop}px`;
    });

    document.addEventListener("mouseup", () => {
      if (isDragging) {
        isDragging = false;
        dragHandle.classList.remove("dragging");
      }
    });
  })();

  // ---- Coordinate with the party choropleth panel -------------
  // Only one shading layer makes sense at a time; pause the party
  // panel's controls while a demographic field is active, and hand
  // them back (respecting its own winner-mode disabling) when not.
  function setPartyPanelEnabled(enabled) {
    const partySelect = document.getElementById("choropleth-party");
    const modeSelect = document.getElementById("choropleth-mode");
    if (modeSelect) modeSelect.disabled = !enabled;
    if (partySelect) partySelect.disabled = !enabled || (modeSelect && modeSelect.value === "winner");
  }

  // ---- Load data + manifest -----------------------------------
  async function loadData() {
    const [manifestRes, dataRes] = await Promise.all([
      fetch("data/demographics_manifest.json"),
      fetch("data/demographics.json"),
    ]);
    if (!manifestRes.ok) throw new Error(`Failed to load demographics manifest: ${manifestRes.status}`);
    if (!dataRes.ok) throw new Error(`Failed to load demographics data: ${dataRes.status}`);

    manifest = await manifestRes.json();
    const records = await dataRes.json();

    records.forEach(r => dataByName.set(r.Name, r));
    seatCount = records.length;

    manifest.fields.forEach(f => {
      let min = Infinity, max = -Infinity, sum = 0, n = 0;
      records.forEach(r => {
        const v = r[f.key];
        if (typeof v === "number") {
          if (v < min) min = v;
          if (v > max) max = v;
          sum += v;
          n++;
        }
      });

      const ranked = records
        .filter(r => typeof r[f.key] === "number")
        .sort((a, b) => b[f.key] - a[f.key]); // descending, 1st = highest

      const mid = Math.floor(ranked.length / 2);
      const median = ranked.length === 0 ? 0
        : ranked.length % 2 === 0
          ? (ranked[mid - 1][f.key] + ranked[mid][f.key]) / 2
          : ranked[mid][f.key];

      fieldStats[f.key] = { min, max, mean: n ? sum / n : 0, median };

      const rankMap = new Map();
      ranked.forEach((r, i) => rankMap.set(r.Name, i + 1)); // 1 = highest value
      ranksByField[f.key] = rankMap;
    });

    loaded = true;
    buildCategoryOptions();

    // If a results panel was opened before this fetch resolved, it's
    // showing a "loading" placeholder - fill it in now.
    if (currentResultsPanelSeat) renderResultsPanelDemographics(currentResultsPanelSeat);
  }

  // ---- Notable stats: rank every field for one seat, keep the extremes --
  // Returns { main, footnotes } for the top/bottom NOTABLE_FRACTION of all
  // seats for a field, after clearing the minimum-requirement floor so
  // near-zero values in long-tailed fields (Jewish, Chinese, Pakistani...)
  // don't get flagged just for technically landing in the top/bottom
  // quintile. Qualifying "top" values under FOOTNOTE_ABS_FLOOR go to
  // footnotes rather than main (real, but too small to headline next to a
  // 50%-scale stat); "bottom" flags are skipped entirely for fields whose
  // national mean doesn't clear MIN_MEAN_FOR_BOTTOM, since for rare/skewed
  // fields being near-0% is the typical case everywhere, not a standout.
  function computeNotableStats(name) {
    const record = dataByName.get(name);
    if (!record || !loaded) return { main: [], footnotes: [] };

    const cutoff = Math.max(1, Math.round(seatCount * NOTABLE_FRACTION));
    const main = [];
    const footnotes = [];

    manifest.fields.forEach(f => {
      const value = record[f.key];
      if (typeof value !== "number") return;

      const rank = ranksByField[f.key].get(name);
      if (rank == null) return;

      const stats = fieldStats[f.key];
      const isTop = rank <= cutoff;
      const isBottom = rank > seatCount - cutoff;
      if (!isTop && !isBottom) return;

      if (isTop) {
        const minRequired = Math.max(MIN_ABS_FLOOR, stats.mean * MIN_TOP_MEAN_MULT);
        if (value < minRequired) return;

        const item = { field: f, value, direction: "top", displayRank: rank };
        (value < FOOTNOTE_ABS_FLOOR ? footnotes : main).push(item);
      } else {
        if (stats.median < MIN_MEDIAN_FOR_BOTTOM) return;

        const gap = stats.median - value;
        const minGap = Math.max(MIN_ABS_FLOOR, stats.median * MIN_BOTTOM_GAP_FRACTION);
        if (gap < minGap) return;

        main.push({ field: f, value, direction: "bottom", displayRank: seatCount - rank + 1 });
      }
    });

    main.sort((a, b) => a.displayRank - b.displayRank);
    footnotes.sort((a, b) => b.value - a.value);
    return { main, footnotes };
  }

  // ---- Render into the main results panel's extension box -------------
  function renderResultsPanelDemographics(name) {
    currentResultsPanelSeat = name;

    const descEl = document.getElementById("rp-ext-description");
    const headerEl = document.getElementById("rp-ext-demo-header");
    const listEl = document.getElementById("rp-ext-demo-list");
    const footEl = document.getElementById("rp-ext-demo-footnotes");
    if (!descEl || !headerEl || !listEl || !footEl) return;

    if (!loaded) {
      descEl.textContent = "";
      headerEl.textContent = "Demographics";
      listEl.innerHTML = `<div class="rp-ext-demo-empty">Loading…</div>`;
      footEl.innerHTML = "";
      return;
    }

    // Coverage is still being filled in by hand - most seats don't have one
    // yet, so this is blank for now on those.
    const record = dataByName.get(name);
    descEl.textContent = (record && record.Description) || "";

    const { main, footnotes } = computeNotableStats(name);
    headerEl.textContent = "Notable demographics";
    if (window.createInfoTip) {
      headerEl.appendChild(window.createInfoTip(
        "Stats where this seat sits in roughly the top or bottom fifth of all constituencies, skipping near-zero values in categories where that's the norm everywhere (e.g. Jewish, Sikh population)."
      ));
    }

    if (!main.length && !footnotes.length) {
      listEl.innerHTML = `<div class="rp-ext-demo-empty">No standout demographics — within normal range on every measure.</div>`;
      footEl.innerHTML = "";
      return;
    }

    listEl.innerHTML = main.length
      ? main.map(it => `
          <div class="rp-ext-demo-row">
            <span class="rp-ext-demo-badge ${it.direction === "top" ? "rp-ext-top" : "rp-ext-bottom"}">${it.direction === "top" ? "HIGH" : "LOW"}</span>
            <span class="rp-ext-demo-label">${it.field.label}</span>
            <span class="rp-ext-demo-value">${it.value.toFixed(1)}%</span>
          </div>
        `).join("")
      : `<div class="rp-ext-demo-empty">No major standouts — see below.</div>`;

    footEl.innerHTML = footnotes.length
      ? `Also: ${footnotes.map(it => `${it.field.label} ${it.value.toFixed(1)}%`).join(", ")}`
      : "";
  }

  // Wraps app.js's displayElectionResults (a plain global function - see
  // app.js's comment on window.colorDistricts for why reassigning
  // window.X here also redirects app.js's own internal calls to X()).
  const previousDisplayElectionResults = window.displayElectionResults;
  window.displayElectionResults = function (name) {
    if (previousDisplayElectionResults) previousDisplayElectionResults(name);
    renderResultsPanelDemographics(name);
  };

  function ordinal(n) {
    const rem100 = n % 100;
    if (rem100 >= 11 && rem100 <= 13) return `${n}th`;
    switch (n % 10) {
      case 1: return `${n}st`;
      case 2: return `${n}nd`;
      case 3: return `${n}rd`;
      default: return `${n}th`;
    }
  }

  function buildCategoryOptions() {
    categorySelect.disabled = false;
    categorySelect.innerHTML = `
      <option value="">Off</option>
      ${manifest.groups.map(g => `<option value="${g.key}">${g.label}</option>`).join("")}
    `;
    buildFieldOptions("");
  }

  function buildFieldOptions(groupKey) {
    if (!groupKey) {
      fieldSelect.innerHTML = "";
      fieldSelect.disabled = true;
      return;
    }
    const fields = manifest.fields.filter(f => f.group === groupKey);
    fieldSelect.innerHTML = fields.map(f => `<option value="${f.key}">${f.label}</option>`).join("");
    fieldSelect.disabled = false;
  }

  // ---- Colour + legend helpers ---------------------------------
  function colorFactor(value, min, max) {
    if (max === min) return 0.6;
    const t = (value - min) / (max - min);
    return Math.min(1, Math.max(0.10, t));
  }

  function fieldColor(group, value, stats) {
    return blendColor(GROUP_COLORS[group] || "#8d8d95", colorFactor(value, stats.min, stats.max));
  }

  function renderLegend(field, stats) {
    const groupColor = GROUP_COLORS[field.group] || "#8d8d95";
    legendEl.innerHTML = `
      <div class="dp-title">${field.label}</div>
      <div class="dp-bar" style="background: linear-gradient(to right, ${blendColor(groupColor, 0.10)}, ${blendColor(groupColor, 1)});"></div>
      <div class="dp-labels"><span>${stats.min.toFixed(1)}%</span><span>${stats.max.toFixed(1)}%</span></div>
    `;
  }

  function clearLegend() {
    legendEl.innerHTML = "";
  }

  // ---- Main render -----------------------------------------------
  function renderDemographicsChoropleth() {
    const activeSvg = (typeof getActiveSvg === "function") ? getActiveSvg() : null;
    const field = manifest.fields.find(f => f.key === activeFieldKey);
    if (!activeSvg || !field) return;

    const stats = fieldStats[activeFieldKey];
    let found = 0, missing = 0;

    dataByName.forEach((record, name) => {
      const path = activeSvg.querySelector(`path[inkscape\\:label="${name}"]`);
      if (!path) { missing++; return; }
      found++;

      const value = record[activeFieldKey];
      const color = (typeof value === "number") ? fieldColor(field.group, value, stats) : "#e8e8e8";

      path.removeAttribute("style");
      path.setAttribute("fill", color);
    });

    renderLegend(field, stats);

    const usingOldBoundaries = (typeof svg2010 !== "undefined") && activeSvg === svg2010;
    noteEl.textContent = usingOldBoundaries
      ? "This map uses pre-2024 boundaries — demographic data is on 2024 boundaries, so some seats won't shade."
      : "";

    console.log(`Demographics: shaded ${found} districts, ${missing} missing from active map`);
  }

  // ---- Wrap window.colorDistricts (chained after chloro.js) -----
  const previousColorDistricts = window.colorDistricts;

  window.colorDistricts = function () {
    if (activeFieldKey && loaded) {
      renderDemographicsChoropleth();
    } else if (previousColorDistricts) {
      previousColorDistricts();
    }
  };

  // ---- Wire controls ----------------------------------------------
  categorySelect.addEventListener("change", () => {
    const groupKey = categorySelect.value;
    buildFieldOptions(groupKey);

    if (!groupKey) {
      activeFieldKey = "";
      clearLegend();
      noteEl.textContent = "";
      hideTooltip();
      setPartyPanelEnabled(true);
      window.colorDistricts();
      return;
    }

    setPartyPanelEnabled(false);
    activeFieldKey = fieldSelect.value;
    window.colorDistricts();
  });

  fieldSelect.addEventListener("change", () => {
    activeFieldKey = fieldSelect.value;
    window.colorDistricts();
  });

  // ---- Kick off data load ------------------------------------------
  loadData().catch(err => {
    console.error(err);
    categorySelect.innerHTML = `<option value="">Failed to load</option>`;
  });

})();
