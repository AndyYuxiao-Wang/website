/* ============================================================
   CHOROPLETH CONTROL PANEL - UPDATED FOR MULTIPLE MAPS
   ------------------------------------------------------------
   Now works with both conmap and conmap_2010
   ============================================================ */

(function () {

  // ---- Parties available in the selector -------------------
  const PARTIES = [
    { key: "LAB",   label: "Labour" },
    { key: "CON",   label: "Conservative" },
    { key: "LD",    label: "Liberal Democrat" },
    { key: "GRN",   label: "Green" },
    { key: "REF",   label: "Reform" },
    { key: "SNP",   label: "SNP" },
    { key: "PLAID", label: "Plaid Cymru" },
    { key: "OTHER", label: "Other" },
    { key: "OTH",   label: "Oth" },
    { key: "UKIP",  label: "UKIP" },
    { key: "BNP",   label: "BNP" },
    { key: "RES",   label: "Respect" },
    { key: "RESTORE",   label: "Restore" }
  ];

  // ---- Build panel markup -----------------------------------
  const panel = document.createElement("div");
  panel.id = "choropleth-panel";
  panel.innerHTML = `
    <style>
      #choropleth-panel {
        position: fixed;
        top: 140px;
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
      #choropleth-panel-handle {
        margin: 0 -14px 10px -14px;
        padding: 10px 14px;
        background: var(--bbc-blue, #1656d1);
        cursor: grab;
        user-select: none;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      #choropleth-panel-handle.dragging {
        cursor: grabbing;
      }
      #choropleth-panel h4 {
        margin: 0;
        font-family: var(--font-head, "Archivo Black", sans-serif);
        font-size: 13px;
        font-weight: normal;
        letter-spacing: 0.02em;
        text-transform: uppercase;
        pointer-events: none;
      }
      #choropleth-panel-handle .cp-drag-dots {
        font-size: 12px;
        color: rgba(255,255,255,0.7);
        letter-spacing: 1px;
        pointer-events: none;
      }
      #choropleth-panel label {
        display: block;
        margin-top: 10px;
        font-weight: 700;
        font-size: 11px;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: #9a9aa3;
      }
      #choropleth-panel select {
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
      #choropleth-panel select:disabled {
        opacity: 0.4;
      }
      #choropleth-legend {
        margin-top: 12px;
      }
      #choropleth-legend .cp-bar {
        height: 10px;
        border: 1px solid rgba(255,255,255,0.15);
      }
      #choropleth-legend .cp-labels {
        display: flex;
        justify-content: space-between;
        font-size: 10px;
        font-weight: 700;
        color: #9a9aa3;
        margin-top: 4px;
      }
      #choropleth-legend .cp-title {
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #9a9aa3;
        margin-bottom: 4px;
      }
    </style>
    <div id="choropleth-panel-handle">
      <h4>Choropleth</h4>
      <span class="cp-drag-dots">⠿</span>
    </div>
    <label>Party
      <select id="choropleth-party">
        ${PARTIES.map(p => `<option value="${p.key}">${p.label}</option>`).join("")}
      </select>
    </label>
    <label>View
      <select id="choropleth-mode">
        <option value="winner">Winner (default)</option>
        <option value="share">Vote share</option>
        <option value="change">Vote share change</option>
      </select>
    </label>
    <div id="choropleth-legend"></div>
  `;
  document.body.appendChild(panel);

  const partySelect = panel.querySelector("#choropleth-party");
  const modeSelect = panel.querySelector("#choropleth-mode");
  const legendEl = panel.querySelector("#choropleth-legend");
  const dragHandle = panel.querySelector("#choropleth-panel-handle");

  // ---- Make the panel draggable via its header bar -----------
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

  function syncPartyEnabled() {
    partySelect.disabled = modeSelect.value === "winner";
  }

  // ---- Helper to get the active SVG ---------------------------
  function getActiveSvg() {
    // Check which SVG is currently visible
    const svg2010 = document.getElementById('conmap_2010');
    if (svg2010 && svg2010.style.display !== 'none') {
      return svg2010;
    }
    return document.getElementById('conmap');
  }

  // ---- Value + color helpers ---------------------------------
  function getShare(district, party) {
    const votes = district[party];
    if (!votes || !district.Total) return null;
    return (votes / district.Total) * 100;
  }

  function getShareChange(district, party) {
    const currentShare = getShare(district, party);
    const prevVotes = district["prev_" + party];
    const prevTotal = district.prev_TOTAL;
    if (currentShare === null || !prevVotes || !prevTotal) return null;
    const prevShare = (prevVotes / prevTotal) * 100;
    return currentShare - prevShare;
  }

  function shareColor(party, value) {
    const factor = Math.min(1, Math.max(0.08, value / 55));
    return blendColor(getPartyColor(party), factor);
  }

  function changeColor(party, value) {
    const cap = 20;
    const magnitude = Math.min(1, Math.abs(value) / cap);
    if (value >= 0) {
      const factor = Math.max(0.05, magnitude);
      return blendColor(getPartyColor(party), factor);
    } else {
      const factor = Math.max(0.05, magnitude);
      return blendColor("#4d4d4d", factor);
    }
  }

  const NO_DATA_COLOR = "#e8e8e8";

  // ---- Main render function - UPDATED -------------------------
  function renderPartyChoropleth(party, mode) {
    const activeSvg = getActiveSvg();
    if (!activeSvg) {
      console.warn('No active SVG found');
      return;
    }

    let foundPaths = 0;
    let missingPaths = 0;

    electionData.forEach(district => {
      const districtName = district.Name;
      const path = activeSvg.querySelector(
        `path[inkscape\\:label="${districtName}"]`
      );

      if (!path) {
        missingPaths++;
        // Only log first few missing paths to avoid console spam
        if (missingPaths <= 5) {
          console.warn(`Could not find path for: ${districtName} in active map`);
        }
        return;
      }

      foundPaths++;
      const value = mode === "share"
        ? getShare(district, party)
        : getShareChange(district, party);

      let color;
      if (value === null) {
        color = NO_DATA_COLOR;
      } else {
        color = mode === "share" ? shareColor(party, value) : changeColor(party, value);
      }

      path.removeAttribute("style");
      path.setAttribute("fill", color);
    });

    console.log(`Rendered ${foundPaths} districts, ${missingPaths} missing from active map`);
    renderLegend(party, mode);
  }

  function renderLegend(party, mode) {
    const inSegmentsView = typeof currentElectionYear !== "undefined" && currentElectionYear === 2016;
    const partyLabel = inSegmentsView && SEGMENT_LABELS[party]
      ? SEGMENT_LABELS[party]
      : (PARTIES.find(p => p.key === party) || {}).label || party;
    const baseColor = getPartyColor(party);

    if (mode === "share") {
      legendEl.innerHTML = `
        <div class="cp-title">${partyLabel} vote share</div>
        <div class="cp-bar" style="background: linear-gradient(to right, ${blendColor(baseColor, 0.08)}, ${blendColor(baseColor, 1)});"></div>
        <div class="cp-labels"><span>0%</span><span>55%+</span></div>
      `;
    } else if (mode === "change") {
      legendEl.innerHTML = `
        <div class="cp-title">${partyLabel} change vs previous</div>
        <div class="cp-bar" style="background: linear-gradient(to right, ${blendColor("#4d4d4d", 1)}, #ffffff, ${blendColor(baseColor, 1)});"></div>
        <div class="cp-labels"><span>-20pt</span><span>0</span><span>+20pt</span></div>
      `;
    } else {
      legendEl.innerHTML = `<div class="cp-title">Shaded by winning margin</div>`;
    }
  }

  // ---- Wrap the existing colorDistricts ------------------------
  const originalColorDistricts = window.colorDistricts;

  window.colorDistricts = function () {
    const mode = modeSelect.value;
    if (mode === "winner") {
      legendEl.innerHTML = `<div class="cp-title">Shaded by winning margin</div>`;
      originalColorDistricts();
    } else {
      renderPartyChoropleth(partySelect.value, mode);
    }
  };

  // ---- Wire up the controls -----------------------------------
  partySelect.addEventListener("change", () => window.colorDistricts());
  modeSelect.addEventListener("change", () => {
    syncPartyEnabled();
    window.colorDistricts();
  });

  syncPartyEnabled();

  // ---- Trigger initial render ---------------------------------
  if (document.readyState === "complete" || document.readyState === "interactive") {
    window.colorDistricts();
  } else {
    document.addEventListener("DOMContentLoaded", () => window.colorDistricts());
  }

  // ---- Also re-render when year changes -----------------------
  // Store reference to original setElectionYear
  const originalSetElectionYear = window.setElectionYear;
  if (originalSetElectionYear) {
    window.setElectionYear = function(year) {
      originalSetElectionYear(year);
      refreshPartyOptionLabels();
      // Re-render choropleth after year change
      setTimeout(() => window.colorDistricts(), 50);
    };
  }

  // ---- Electorate Segments mode: relabel party codes -----------
  // Mirrors app.js's SEGMENT_LABELS. Duplicated rather than shared so
  // this panel stays a self-contained drop-in.
  const SEGMENT_LABELS = {
    PLAID: "Muslims",
    REF: "Reformers",
    CON: "Blues",
    LD: "Liberals",
    GRN: "Left",
    LAB: "Progressives",
    OTHER: "Others",
  };

  function refreshPartyOptionLabels() {
    const inSegmentsView = typeof currentElectionYear !== "undefined" && currentElectionYear === 2016;
    Array.from(partySelect.options).forEach(opt => {
      const base = (PARTIES.find(p => p.key === opt.value) || {}).label || opt.value;
      opt.textContent = inSegmentsView && SEGMENT_LABELS[opt.value] ? SEGMENT_LABELS[opt.value] : base;
    });
  }

  refreshPartyOptionLabels();

})();