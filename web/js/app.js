// ---------------------------------------------------------------
// Top-level state. Populated by init() once the maps and election
// data have finished loading (see bottom of file).
// ---------------------------------------------------------------

let svg, svg2010, container, panel;
let conmapSlot, conmap2010Slot;
let originalViewBox, originalViewBox2010;

// New results-panel elements (see index.html)
let rpGainHold, rpResultTag, rpChartBig, rpChartMiniCol, rpCandidates, rpMajorityBar, rpMajorityLabel, rpMajorityValue, rpTurnoutValue, rpTurnoutChange, rpNameRibbon;

const electionDatasets = {};
const DATA_FILES = {
  2005: "data/elections/2005.json",
  2010: "data/elections/2010.json",
  2015: "data/elections/2015.json",
  2016: "data/elections/2016.json",
  2017: "data/elections/2017.json",
  2019: "data/elections/2019.json",
  eu2016: "data/elections/eu2016.json",
  2024: "data/elections/2024.json",
  2029: "data/elections/2029.json",
  1: "data/elections/au2021.json",
};

// Years that use the pre-2024-boundary map (conmap_2010) rather than conmap
const yearsUsingConmap2010 = [2005, 2010, 2015, "eu2016", 2017, 2019];

let currentElectionYear = 2024;
let electionData = [];
let currentMap = null;
let resultsChart = null;
let currentPanelView = "results"; // 'results' | 'change' | 'swing'
let pulseMarker = null;

let isDragging = false;
let offsetX, offsetY;

let isPanning = false;
let lastX = 0;
let lastY = 0;

const ALL_PARTIES = ["LAB", "CON", "LD", "GRN", "OTHER", "PLAID", "REF", "SNP", "OTH", "UKIP", "BNP", "RES", "RESTORE", "LEAVE", "REMAIN"];

// The "Electorate Segments" dataset (year 2016) isn't a real election - it's
// each constituency's underlying demographic/political tribes, plotted onto
// the same party columns so the existing pipeline can render it. Party
// codes get relabelled to segment names wherever they're shown as text.
const SEGMENTS_YEAR = 2016;
const SEGMENT_LABELS = {
  PLAID: "Muslims",
  REF: "Reformers",
  CON: "Blues",
  LD: "Liberals",
  GRN: "Left",
  LAB: "Progressives",
  OTHER: "Average", // the tribe model's catch-all/baseline segment - stored in the
                     // generic "OTHER" party-code slot for reuse, not a leftover bucket.
};

// One-line explanation per segment, for the legend panel below.
const SEGMENT_DESCRIPTIONS = {
  PLAID: "Areas with a large Muslim population.",
  REF: "Working-class, Reform-curious areas.",
  CON: "Traditionally Conservative-leaning areas.",
  LD: "Centrist, Liberal-Democrat-leaning areas.",
  GRN: "Young, graduate-heavy, Green-leaning areas.",
  LAB: "Broadly liberal-left, Labour-leaning areas.",
  OTHER: "The typical/baseline voter mix where no other segment's profile stands out.",
};

function isSegmentsView() {
  return currentElectionYear === SEGMENTS_YEAR;
}

// ---------------------------------------------------------------
// Segments legend panel - a persistent key (colour + name + one-line
// description) for the 7 tribes, shown alongside the Choropleth/
// Demographics panels whenever "Electorate Segments" is active. Built
// once on first use, then just shown/hidden by setElectionYear().
// ---------------------------------------------------------------

let segmentsLegendPanel = null;

function buildSegmentsLegendPanel() {
  const panel = document.createElement("div");
  panel.id = "segments-legend-panel";
  panel.innerHTML = `
    <style>
      #segments-legend-panel {
        position: fixed;
        top: 560px;
        right: 16px;
        z-index: 1000;
        background: var(--bbc-panel, #232327);
        box-shadow: 0 6px 24px rgba(0,0,0,0.5);
        padding: 12px 14px 14px;
        font-family: var(--font-body, "Roboto Condensed", Arial, sans-serif);
        color: #fff;
        width: 220px;
      }
      #segments-legend-panel h4 {
        margin: 0 0 8px;
        font-size: 13px;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #cfd2da;
      }
      #segments-legend-panel .sl-row {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        margin-bottom: 8px;
      }
      #segments-legend-panel .sl-swatch {
        width: 12px;
        height: 12px;
        margin-top: 3px;
        flex: none;
        border-radius: 2px;
      }
      #segments-legend-panel .sl-name {
        font-weight: 700;
        font-size: 12.5px;
        color: #fff;
      }
      #segments-legend-panel .sl-desc {
        font-size: 11.5px;
        color: #9a9aa3;
        line-height: 1.35;
      }
    </style>
    <h4>Segments key</h4>
    <div id="segments-legend-list"></div>
  `;
  document.body.appendChild(panel);

  const list = panel.querySelector("#segments-legend-list");
  Object.keys(SEGMENT_LABELS).forEach(code => {
    const row = document.createElement("div");
    row.className = "sl-row";
    row.innerHTML = `
      <span class="sl-swatch" style="background:${getPartyColor(code)}"></span>
      <span>
        <div class="sl-name">${SEGMENT_LABELS[code]}</div>
        <div class="sl-desc">${SEGMENT_DESCRIPTIONS[code] || ""}</div>
      </span>
    `;
    list.appendChild(row);
  });

  return panel;
}

function updateSegmentsLegendVisibility() {
  if (!segmentsLegendPanel) segmentsLegendPanel = buildSegmentsLegendPanel();
  segmentsLegendPanel.style.display = isSegmentsView() ? "block" : "none";
}

// Years that aren't an actual completed election - the 2029 forward
// projection - get the "PREDICTION" tag instead of "RESULT" in the
// results panel.
const PREDICTION_YEARS = [2029];

function isPredictionView() {
  return PREDICTION_YEARS.includes(currentElectionYear);
}

// The user-built "Custom" what-if prediction (see customPredictor.js) lives
// under this string key in electionDatasets, alongside the numeric years.
const CUSTOM_YEAR_KEY = "custom";

function isCustomView() {
  return currentElectionYear === CUSTOM_YEAR_KEY;
}

function displayLabel(partyCode) {
  if (isSegmentsView() && SEGMENT_LABELS[partyCode]) return SEGMENT_LABELS[partyCode];
  return partyCode;
}

// ---------------------------------------------------------------
// Map / year switching
// ---------------------------------------------------------------

function getMapForYear(year) {
  return yearsUsingConmap2010.includes(year) ? svg2010 : svg;
}

// Shows exactly one map. Both wrappers are absolutely positioned on top of
// each other (see style.css), so the inactive one must be fully removed
// from layout via display:none on the *wrapper* too - otherwise, even with
// its content hidden, an empty positioned div still intercepts clicks meant
// for the map underneath it.
function showMap(map) {
  const showConmap = map === svg;
  conmapSlot.style.display = showConmap ? "block" : "none";
  conmap2010Slot.style.display = showConmap ? "none" : "block";
  svg.style.display = showConmap ? "block" : "none";
  if (svg2010) svg2010.style.display = showConmap ? "none" : "block";
}

// A data-year value parses to its Number form for every real year (keeps
// currentElectionYear comparable to SEGMENTS_YEAR/PREDICTION_YEARS and
// chloro.js's own `=== 2016` checks, all numeric) - except non-numeric keys
// like the "custom" what-if predictor's tab, which stay a plain string.
function parseYearKey(raw) {
  const n = Number(raw);
  return Number.isNaN(n) ? raw : n;
}

function setElectionYear(year) {
  if (electionDatasets[year]) {
    currentElectionYear = year;
    electionData = electionDatasets[year];

    // Switch maps if needed
    const newMap = getMapForYear(year);
    if (newMap !== currentMap) {
      showMap(newMap);
      currentMap = newMap;

      // Update the global svg reference
      window.currentSvg = newMap;

      // Reset view based on the new map
      resetView();
    }

    colorDistricts(); // Re-color the map with the new data
    resetView(); // Reset the view to show the updated map
    displayOverallResults();
    updateSegmentsLegendVisibility();

    document.querySelectorAll("#election-controls button[data-year]").forEach(btn => {
      btn.classList.toggle("active", parseYearKey(btn.dataset.year) === year);
    });
  } else {
    console.warn(`No data available for year ${year}`);
  }
}

// Function to get the current active SVG
function getActiveSvg() {
  return currentMap || svg;
}

// ---------------------------------------------------------------
// Vote share / turnout helpers
// ---------------------------------------------------------------

function calculateVoteShare(votes, electorate) {
  return ((votes / electorate) * 100).toFixed(1);
}

function calculateTurnout(electorate, total) {
  return ((total / electorate) * 100).toFixed(1);
}

function numOrZero(v) {
  return v === "" || v == null ? 0 : Number(v);
}

// Function to get the color based on party
function getPartyColor(party) {
  switch (party) {
    case "LAB": return "#dd1f19";
    case "CON": return "#0088dd";
    case "LD": return "#faa813";
    case "GRN": return "#6ab21e";
    case "OTHER": return "#a1a1a1";
    case "PLAID": return "#008142";
    case "OTH": return "#b40653";
    case "REF": return "#00e6e6";
    case "SNP": return "#fdf38f";
    case "UKIP": return "#6d3177";
    case "BNP": return "#313d75";
    case "RES": return "#46801c";
    case "RESTORE": return "#051e40";
    case "LEAVE": return "#003399";
    case "REMAIN": return "#ffcc00";
    default: return "#cccccc";
  }
}

function colorDistricts() {
  const activeSvg = getActiveSvg();

  electionData.forEach(district => {
    const districtName = district.Name;
    const winner = district.Winner;
    const baseColor = getPartyColor(winner);

    // Find the winner's vote count
    const winnerVotes = district[winner];
    const totalVotes = district.Total;

    // Defensive: skip if missing data
    if (!winnerVotes || !totalVotes || !baseColor) {
      console.warn(`Missing data for ${districtName}`);
      return;
    }

    // Calculate the vote share ratio (0 to 1)
    const voteShareRatio = winnerVotes / totalVotes;

    // A straight two-way vote (currently just the EU referendum) never dips
    // below a 0.5 share, unlike a multi-party FPTP result where 0.5 is
    // already a landslide - so it needs its own, steeper factor curve
    // anchored at 0.5 rather than the general-election one below, which
    // would paint almost every seat at full saturation.
    const factor = currentElectionYear === "eu2016"
      ? (voteShareRatio - 0.5) * 4
      : voteShareRatio * 4.5 - 0.8;

    // Blend the color: lighter if vote share is low
    const blendedColor = blendColor(baseColor, factor);

    const path = activeSvg.querySelector(
      `path[inkscape\\:label="${districtName}"]`
    );

    if (path) {
      path.removeAttribute("style");
      path.setAttribute("fill", blendedColor);

      path.setAttribute("stroke", "#FFFFFF");
      path.setAttribute("stroke-width", "0.08");
      path.setAttribute("stroke-linejoin", "mitter");
      path.setAttribute("stroke-color", "#FFFFFF");
    } else {
      console.warn(`Could not find path for: ${districtName}`);
    }
  });
}

// Function to blend a hex color with white based on a factor (0 = white, 1 = full color)
function blendColor(hexColor, factor) {
  const r = parseInt(hexColor.slice(1, 3), 16);
  const g = parseInt(hexColor.slice(3, 5), 16);
  const b = parseInt(hexColor.slice(5, 7), 16);

  const clamp = v => Math.min(255, Math.max(0, Math.round(v)));

  const blendedR = clamp(r * factor + 255 * (1 - factor));
  const blendedG = clamp(g * factor + 255 * (1 - factor));
  const blendedB = clamp(b * factor + 255 * (1 - factor));

  return `rgb(${blendedR}, ${blendedG}, ${blendedB})`;
}

// Darken a hex color toward black by `factor` (1 = unchanged, 0 = black).
// Used for the ribbon's hold-state triangle - a subtle shade of the
// winner's own color, the same role --bbc-blue-dark plays for the static
// theme.
function darkenColor(hexColor, factor = 0.6) {
  const r = parseInt(hexColor.slice(1, 3), 16);
  const g = parseInt(hexColor.slice(3, 5), 16);
  const b = parseInt(hexColor.slice(5, 7), 16);
  const clamp = v => Math.min(255, Math.max(0, Math.round(v)));
  const toHex = v => clamp(v).toString(16).padStart(2, "0");
  return `#${toHex(r * factor)}${toHex(g * factor)}${toHex(b * factor)}`;
}

// WCAG relative luminance -> pick readable text color for an arbitrary
// party-color background (matters most for pale colors like SNP's yellow).
function readableTextColor(hexColor) {
  const lin = c => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  const r = lin(parseInt(hexColor.slice(1, 3), 16));
  const g = lin(parseInt(hexColor.slice(3, 5), 16));
  const b = lin(parseInt(hexColor.slice(5, 7), 16));
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return luminance > 0.5 ? "#14151a" : "#ffffff";
}

// ---------------------------------------------------------------
// Gain/Hold + swing helpers
// ---------------------------------------------------------------

function getPreviousWinner(district) {
  let best = null;
  let bestVotes = 0;
  ALL_PARTIES.forEach(p => {
    const v = numOrZero(district["prev_" + p]);
    if (v > bestVotes) {
      bestVotes = v;
      best = p;
    }
  });
  return best;
}

function gainHoldHtml(district) {
  const winner = district.Winner;
  // Plain text, not colored by party: the whole bar is now shaded in the
  // winner's color (see applyResultTheme), so coloring the winner's own
  // name the same color would make it invisible against its own background.
  const winnerLabel = displayLabel(winner);

  if (isSegmentsView()) {
    // No "previous winner" concept here - this is a single demographic
    // snapshot, not a comparison between two elections.
    return `${winnerLabel} SEGMENT`;
  }

  const prevWinner = getPreviousWinner(district);

  if (!prevWinner) {
    return `${winnerLabel} WIN`;
  }
  if (prevWinner === winner) {
    return `${winnerLabel} HOLD`;
  }
  // The *previous* party's name keeps its own color - it's a different
  // party from the bar's background color, so it still reads clearly and
  // echoes the "from" party the same way the ribbon's triangle does.
  return `${winnerLabel} GAIN from <span style="color:${getPartyColor(prevWinner)}">${prevWinner}</span>`;
}

// Recolors the gain/hold bar, majority bar and name ribbon to the winning
// party's color, with readable (white or dark) text picked per-bar from
// the background's luminance (matters for pale colors like SNP's yellow).
// The ribbon's flag triangle carries the "gain" story: on a hold it's just
// a darker shade of the winner's color, but on a gain it's the *previous*
// winner's color, so the flag visually shows the seat flipping from one
// party's color to the other's.
function applyResultTheme(district, winnerParty, segmentsMode) {
  const themedBars = [rpGainHold, rpMajorityBar, rpNameRibbon];

  if (segmentsMode) {
    themedBars.forEach(el => {
      if (!el) return;
      el.style.removeProperty("background");
      el.style.removeProperty("color");
    });
    rpNameRibbon.style.removeProperty("--rp-triangle-color");
    if (rpResultTag) {
      rpResultTag.style.removeProperty("background");
      rpResultTag.style.removeProperty("color");
    }
    return;
  }

  const winnerColor = getPartyColor(winnerParty);
  const textColor = readableTextColor(winnerColor);
  themedBars.forEach(el => {
    if (!el) return;
    el.style.background = winnerColor;
    el.style.color = textColor;
  });

  const prevWinner = getPreviousWinner(district);
  const isGain = prevWinner && prevWinner !== winnerParty;
  const darkWinnerColor = darkenColor(winnerColor);
  const triangleColor = isGain ? getPartyColor(prevWinner) : darkWinnerColor;
  rpNameRibbon.style.setProperty("--rp-triangle-color", triangleColor);

  // RESULT/PREDICTION tag: same party color as the ribbons, but darker -
  // same shade the triangle uses on a hold - so it reads as part of the
  // same themed group without competing with the ribbon for attention.
  if (rpResultTag) {
    rpResultTag.style.background = darkWinnerColor;
    rpResultTag.style.color = readableTextColor(darkWinnerColor);
  }
}

// Classic pendulum swing. Normally between the two leading candidates, but
// if the seat changed hands the incumbent is always one side of the swing -
// even if they've since fallen to 3rd or worse - since "swing" here means
// the swing that actually cost/won them the seat, not just a top-2 snapshot.
function computeSwing(district, candidates) {
  const totalPrev = numOrZero(district.prev_TOTAL);
  const totalNow = numOrZero(district.Total);
  if (!totalPrev || !totalNow) return null;

  const winner = district.Winner;
  // In segments mode "prev_" is the actual last election, not a previous
  // segment snapshot - there's no incumbent concept, so always compare the
  // top two current segments instead.
  const prevWinner = isSegmentsView() ? null : getPreviousWinner(district);

  let partyA, partyB;
  if (prevWinner && prevWinner !== winner) {
    partyA = winner;
    partyB = prevWinner;
  } else if (candidates.length >= 2) {
    partyA = candidates[0].party;
    partyB = candidates[1].party;
  } else {
    return null;
  }

  const shareOf = (party, total, prefix) => (numOrZero(district[prefix + party]) / total) * 100;

  const aShareNow = shareOf(partyA, totalNow, "");
  const bShareNow = shareOf(partyB, totalNow, "");
  const aShareThen = shareOf(partyA, totalPrev, "prev_");
  const bShareThen = shareOf(partyB, totalPrev, "prev_");

  const aChange = aShareNow - aShareThen;
  const bChange = bShareNow - bShareThen;
  const swingValue = (aChange - bChange) / 2;

  return {
    magnitude: Math.abs(swingValue),
    partyA,
    partyB,
    fromParty: swingValue >= 0 ? partyB : partyA,
    toParty: swingValue >= 0 ? partyA : partyB,
  };
}

// ---------------------------------------------------------------
// Map marker: pulsing ring on the clicked constituency
// ---------------------------------------------------------------

function showPulseMarker(path) {
  const activeSvg = getActiveSvg();
  if (pulseMarker && pulseMarker.parentNode) {
    pulseMarker.parentNode.removeChild(pulseMarker);
  }

  const bbox = path.getBBox();
  const cx = bbox.x + bbox.width / 2;
  const cy = bbox.y + bbox.height / 2;
  const r = Math.max(bbox.width, bbox.height) * 0.4 || 2;

  const svgNS = "http://www.w3.org/2000/svg";
  const marker = document.createElementNS(svgNS, "g");
  marker.setAttribute("class", "pulse-marker");
  marker.innerHTML = `
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#ffffff" stroke-width="${r * 0.12}">
      <animate attributeName="r" values="${r * 0.3};${r * 2.2}" dur="1.4s" repeatCount="indefinite" />
      <animate attributeName="opacity" values="0.9;0" dur="1.4s" repeatCount="indefinite" />
    </circle>
    <circle cx="${cx}" cy="${cy}" r="${r * 0.35}" fill="#ffffff" opacity="0.9" />
  `;
  activeSvg.appendChild(marker);
  pulseMarker = marker;
}

function clearPulseMarker() {
  if (pulseMarker && pulseMarker.parentNode) {
    pulseMarker.parentNode.removeChild(pulseMarker);
  }
  pulseMarker = null;
}

// ---------------------------------------------------------------
// Results panel: candidate list + header/majority/turnout
// ---------------------------------------------------------------

function buildCandidateList(district) {
  const candidates = ALL_PARTIES
    .map(party => ({ party, votes: district[party], prevVotes: district["prev_" + party] }))
    .filter(c => numOrZero(c.votes) > 0)
    .sort((a, b) => numOrZero(b.votes) - numOrZero(a.votes));
  return candidates;
}

function renderCandidateList(district, candidates) {
  const winnerParty = district.Winner;
  rpCandidates.classList.toggle("rp-segments-mode", isSegmentsView());
  rpCandidates.innerHTML = candidates.map(c => `
    <div class="rp-cand-row ${c.party === winnerParty ? "rp-cand-winner" : ""}">
      <span class="rp-cand-party" style="background:${getPartyColor(c.party)}">${displayLabel(c.party)}</span>
      <span class="rp-cand-name"></span>
      <span class="rp-cand-votes">${numOrZero(c.votes).toLocaleString()}</span>
    </div>
  `).join("");
}

// ---------------------------------------------------------------
// Panel chart views: Results / Change / Swing
// ---------------------------------------------------------------

function miniIconSvg(view) {
  if (view === "change") {
    return `<svg viewBox="0 0 40 24"><rect x="2" y="2" width="5" height="20" fill="#fff"/><rect x="9" y="6" width="5" height="16" fill="#fff"/><rect x="16" y="10" width="5" height="12" fill="#fff"/><rect x="23" y="14" width="5" height="8" fill="#fff"/><rect x="30" y="17" width="5" height="5" fill="#fff"/></svg>`;
  }
  if (view === "swing") {
    return `<svg viewBox="0 0 40 24"><path d="M2,22 A18,18 0 0 1 38,22 Z" fill="none" stroke="#fff" stroke-width="2"/></svg>`;
  }
  return `<svg viewBox="0 0 40 24"><rect x="3" y="10" width="6" height="12" fill="#fff"/><rect x="13" y="4" width="6" height="18" fill="#fff"/><rect x="23" y="14" width="6" height="8" fill="#fff"/><rect x="33" y="8" width="6" height="14" fill="#fff"/></svg>`;
}

const PANEL_VIEWS = [
  { key: "results", label: "Results" },
  { key: "change", label: "Change" },
  { key: "swing", label: "Swing" },
];

const barValueLabelPlugin = {
  id: "barValueLabels",
  afterDatasetsDraw(chart) {
    const { ctx } = chart;
    chart.data.datasets.forEach((dataset, i) => {
      const meta = chart.getDatasetMeta(i);
      meta.data.forEach((bar, index) => {
        const value = dataset.data[index];
        const label = dataset._labelFormat ? dataset._labelFormat(value) : value;
        ctx.save();
        ctx.fillStyle = "#fff";
        ctx.font = "bold 11px 'Roboto Condensed', Arial, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(label, bar.x, value >= 0 ? bar.y - 6 : bar.y + 14);
        ctx.restore();
      });
    });
  },
};

function renderResultsBarChart(hostEl, district, candidates) {
  const canvas = document.createElement("canvas");
  hostEl.appendChild(canvas);

  const shown = candidates.filter(c => numOrZero(c.votes) > 0);
  const shares = shown.map(c => (numOrZero(c.votes) / district.Total) * 100);
  const maxShare = Math.max(...shares, 10);

  if (resultsChart) resultsChart.destroy();
  resultsChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels: shown.map(c => displayLabel(c.party)),
      datasets: [{
        data: shares.map(s => Number(s.toFixed(1))),
        backgroundColor: shown.map(c => getPartyColor(c.party)),
        borderWidth: 0,
        barPercentage: 0.85,
        categoryPercentage: 0.8,
        _labelFormat: v => `${v}%`,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
      },
      scales: {
        y: {
          beginAtZero: true,
          max: Math.ceil((maxShare * 1.25) / 10) * 10,
          ticks: { display: false },
          grid: { color: "rgba(255,255,255,0.08)" },
        },
        x: {
          grid: { display: false },
          ticks: { color: "#e4e4e8", font: { family: "'Roboto Condensed', Arial, sans-serif", weight: "700", size: 11 } },
        },
      },
      layout: { padding: { top: 18, bottom: 0, left: 4, right: 4 } },
    },
    plugins: [barValueLabelPlugin],
  });
}

function renderChangeBarChart(hostEl, district, candidates) {
  const canvas = document.createElement("canvas");
  hostEl.appendChild(canvas);

  const totalPrev = numOrZero(district.prev_TOTAL);
  const shown = candidates.filter(c => numOrZero(c.votes) > 0);

  if (!totalPrev) {
    hostEl.innerHTML = `<div style="color:#9a9aa3;font-size:13px;text-align:center;align-self:center;width:100%;">No prior result to compare</div>`;
    return;
  }

  const changes = shown.map(c => {
    const nowShare = (numOrZero(c.votes) / district.Total) * 100;
    const thenShare = (numOrZero(c.prevVotes) / totalPrev) * 100;
    return nowShare - thenShare;
  });

  const maxAbs = Math.max(...changes.map(Math.abs), 5);

  if (resultsChart) resultsChart.destroy();
  resultsChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels: shown.map(c => displayLabel(c.party)),
      datasets: [{
        data: changes.map(c => Number(c.toFixed(1))),
        backgroundColor: shown.map(c => getPartyColor(c.party)),
        borderWidth: 0,
        barPercentage: 0.85,
        categoryPercentage: 0.8,
        _labelFormat: v => `${v > 0 ? "+" : ""}${v}`,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
      },
      scales: {
        y: {
          min: -Math.ceil((maxAbs * 1.3) / 5) * 5,
          max: Math.ceil((maxAbs * 1.3) / 5) * 5,
          ticks: { display: false },
          grid: {
            color: ctx => (ctx.tick.value === 0 ? "rgba(255,255,255,0.4)" : "rgba(255,255,255,0.08)"),
          },
        },
        x: {
          grid: { display: false },
          ticks: { color: "#e4e4e8", font: { family: "'Roboto Condensed', Arial, sans-serif", weight: "700", size: 11 } },
        },
      },
      layout: { padding: { top: 18, bottom: 18, left: 4, right: 4 } },
    },
    plugins: [barValueLabelPlugin],
  });
}

function renderSwingGauge(hostEl, district, candidates) {
  const swing = computeSwing(district, candidates);

  if (!swing) {
    hostEl.innerHTML = `<div style="color:#9a9aa3;font-size:13px;text-align:center;align-self:center;width:100%;">No prior result to compare</div>`;
    return;
  }

  // partyA (the current leader) sits on the left (180deg side), partyB on
  // the right (0deg side) - the classic swingometer layout. The needle
  // deflects from vertical toward whichever party is gaining, and the
  // colour boundary between the two wedges sits exactly on the needle.
  const W = 240, H = 160;
  const cx = W / 2, cy = H - 14, R = 100;
  const toXY = deg => {
    const rad = (deg * Math.PI) / 180;
    return [cx + R * Math.cos(rad), cy - R * Math.sin(rad)];
  };

  const colorA = getPartyColor(swing.partyA);
  const colorB = getPartyColor(swing.partyB);

  const maxDeflect = 80;
  const degPerPercent = 8;
  const deflect = Math.min(maxDeflect, swing.magnitude * degPerPercent);
  const towardA = swing.toParty === swing.partyA;
  const needleAngle = 90 + (towardA ? deflect : -deflect);

  const [lx, ly] = toXY(180);
  const [sx, sy] = toXY(needleAngle);
  const [rx, ry] = toXY(0);
  const [nx, ny] = [sx, sy];

  hostEl.innerHTML = `
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;width:100%;">
      <svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:260px;">
        <path d="M ${cx},${cy} L ${lx},${ly} A ${R},${R} 0 0 1 ${sx},${sy} Z" fill="${colorB}" />
        <path d="M ${cx},${cy} L ${sx},${sy} A ${R},${R} 0 0 1 ${rx},${ry} Z" fill="${colorA}" />
        <line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" stroke="#ffffff" stroke-width="4" stroke-linecap="round" />
        <circle cx="${cx}" cy="${cy}" r="6" fill="#ffffff" />
      </svg>
      <div style="text-align:center;margin-top:4px;">
        <div style="font-family:'Archivo Black',sans-serif;font-size:20px;">${swing.magnitude.toFixed(1)}% SWING</div>
        <div style="font-family:'Roboto Condensed',sans-serif;font-weight:700;font-size:13px;color:#cfd2da;margin-top:2px;">${displayLabel(swing.fromParty)} to ${displayLabel(swing.toParty)}</div>
      </div>
    </div>
  `;
}

function renderPanelViews(district, candidates) {
  rpChartMiniCol.innerHTML = "";
  PANEL_VIEWS.filter(v => v.key !== currentPanelView).forEach(v => {
    const btn = document.createElement("button");
    btn.className = "rp-chart-mini";
    btn.innerHTML = `${miniIconSvg(v.key)}<span>${v.label}</span>`;
    btn.addEventListener("click", () => {
      currentPanelView = v.key;
      renderPanelViews(district, candidates);
    });
    rpChartMiniCol.appendChild(btn);
  });

  rpChartBig.innerHTML = "";
  if (currentPanelView === "results") renderResultsBarChart(rpChartBig, district, candidates);
  else if (currentPanelView === "change") renderChangeBarChart(rpChartBig, district, candidates);
  else renderSwingGauge(rpChartBig, district, candidates);
}

// ---------------------------------------------------------------
// Pre-2024-boundary side panel: estimated 2016 EU referendum result
// ---------------------------------------------------------------
// Old-boundary years show this instead of the profile/demographics tab
// (see demographics.js), since that data is keyed to 2024 boundaries.
// Independent of whichever year is actually on screen - the referendum
// result belongs to the pre-2024 seat itself, not to any one election year.

let brexitByName = null;

function getBrexitByName() {
  if (!brexitByName) {
    brexitByName = new Map((electionDatasets["eu2016"] || []).map(d => [d.Name, d]));
  }
  return brexitByName;
}

function renderBrexitBar(districtName) {
  const barEl = document.getElementById("rp-brexit-bar");
  const labelsEl = document.getElementById("rp-brexit-labels");
  if (!barEl || !labelsEl) return;

  const record = getBrexitByName().get(districtName);
  if (!record) {
    barEl.innerHTML = "";
    labelsEl.innerHTML = `<div class="rp-brexit-empty">No estimate available for this seat.</div>`;
    return;
  }

  const leaveShare = (record.LEAVE / record.Total) * 100;
  const remainShare = 100 - leaveShare;

  barEl.innerHTML = `
    <div class="rp-brexit-bar-seg" style="width:${leaveShare}%;background:${getPartyColor("LEAVE")};color:#fff">${leaveShare >= 20 ? leaveShare.toFixed(0) + "%" : ""}</div>
    <div class="rp-brexit-bar-seg" style="width:${remainShare}%;background:${getPartyColor("REMAIN")};color:#1a1a1a">${remainShare >= 20 ? remainShare.toFixed(0) + "%" : ""}</div>
  `;
  labelsEl.innerHTML = `
    <span>Leave ${leaveShare.toFixed(1)}%</span>
    <span>Remain ${remainShare.toFixed(1)}%</span>
  `;
}

// ---------------------------------------------------------------
// Full district results
// ---------------------------------------------------------------

function displayElectionResults(districtName) {
  const district = electionData.find(data => data.Name === districtName);

  // Northern Ireland is drawn on the map (so its outline isn't a hole) but
  // isn't covered by any dataset in this app, which is GB-only throughout -
  // show a plain "not available" state instead of a panel full of blanks.
  panel.classList.toggle("rp-unavailable", !district);
  if (!district) {
    rpNameRibbon.textContent = districtName.toUpperCase();
    rpNameRibbon.style.removeProperty("background");
    rpNameRibbon.style.removeProperty("color");
    rpNameRibbon.style.removeProperty("--rp-triangle-color");
    panel.classList.add("rp-visible");
    panel.classList.remove("rp-animate");
    void panel.offsetWidth; // force reflow so the animation class can retrigger
    panel.classList.add("rp-animate");
    return;
  }

  const candidates = buildCandidateList(district);
  const winnerParty = district.Winner;
  const segmentsMode = isSegmentsView();

  panel.classList.toggle("rp-segments-mode", segmentsMode);
  const oldBoundaries = yearsUsingConmap2010.includes(currentElectionYear);
  panel.classList.toggle("rp-old-boundaries", oldBoundaries);
  if (oldBoundaries) renderBrexitBar(districtName);
  rpResultTag.textContent = segmentsMode ? "SEGMENTS" : (isCustomView() ? "CUSTOM" : (isPredictionView() ? "PREDICTION" : "RESULT"));
  rpMajorityLabel.textContent = segmentsMode ? "LEAD" : "MAJORITY";

  rpGainHold.innerHTML = gainHoldHtml(district);
  applyResultTheme(district, winnerParty, segmentsMode);

  renderCandidateList(district, candidates);

  const majority = candidates.length > 1
    ? numOrZero(candidates[0].votes) - numOrZero(candidates[1].votes)
    : numOrZero(candidates[0] && candidates[0].votes);
  rpMajorityValue.textContent = majority.toLocaleString();

  const turnout = calculateTurnout(district.Electorate, district.Total);
  rpTurnoutValue.textContent = `${turnout}%`;

  if (numOrZero(district.prev_TOTAL) && numOrZero(district.prev_Electorate)) {
    const prevTurnout = calculateTurnout(district.prev_Electorate, district.prev_TOTAL);
    const delta = (turnout - prevTurnout).toFixed(1);
    rpTurnoutChange.textContent = `${delta > 0 ? "+" : ""}${delta}%`;
    rpTurnoutChange.classList.toggle("rp-up", delta > 0);
    rpTurnoutChange.classList.toggle("rp-down", delta < 0);
  } else {
    rpTurnoutChange.textContent = "";
    rpTurnoutChange.classList.remove("rp-up", "rp-down");
  }

  rpNameRibbon.textContent = districtName.toUpperCase();

  currentPanelView = "results";
  renderPanelViews(district, candidates);

  panel.classList.add("rp-visible");
  panel.classList.remove("rp-animate");
  void panel.offsetWidth; // force reflow so the animation class can retrigger
  panel.classList.add("rp-animate");
}

// ---------------------------------------------------------------
// National seat ticker
// ---------------------------------------------------------------

function calculateOverallResults() {
  const seatCounts = {};
  let totalVotes = 0;
  const partyVotes = {};

  electionData.forEach(district => {
    const winner = district.Winner;
    if (!winner) return;

    seatCounts[winner] = (seatCounts[winner] || 0) + 1;

    ALL_PARTIES.forEach(p => {
      if (district[p]) {
        partyVotes[p] = (partyVotes[p] || 0) + district[p];
        totalVotes += district[p];
      }
    });
  });

  return { seatCounts, partyVotes, totalVotes };
}

function displayOverallResults() {
  const { seatCounts, partyVotes, totalVotes } = calculateOverallResults();
  const sortedParties = Object.keys(seatCounts).sort((a, b) => seatCounts[b] - seatCounts[a]);

  const segmentsMode = isSegmentsView();
  const label = segmentsMode ? "UK SEGMENTS" : "UK SEATS";
  const yearLabel = segmentsMode ? "BY AREA" : (isCustomView() ? "CUSTOM" : currentElectionYear);
  let html = `<div class="ort-label">${label}</div><div class="ort-year">${yearLabel}</div>`;
  sortedParties.forEach(party => {
    html += `
      <div class="ort-party" style="background:${getPartyColor(party)}">
        <span>${displayLabel(party)}</span><span>${seatCounts[party]}</span>
      </div>
    `;
  });

  document.getElementById("overall-results").innerHTML = html;

  // Thin proportional vote-share sliver underneath the seat ticker -
  // same party set/order as above, widths driven by vote share rather
  // than seat count.
  const voteShareParties = Object.keys(partyVotes).sort((a, b) => partyVotes[b] - partyVotes[a]);
  let sliverHtml = "";
  voteShareParties.forEach(party => {
    const votes = partyVotes[party];
    if (!votes || !totalVotes) return;
    const pct = (votes / totalVotes) * 100;
    const color = getPartyColor(party);
    const textColor = readableTextColor(color);
    const showLabel = pct >= 3.5;
    sliverHtml += `
      <div class="ort-voteshare-seg" style="width:${pct}%;background:${color};" title="${displayLabel(party)}: ${pct.toFixed(1)}%">
        ${showLabel ? `<span style="color:${textColor}">${pct.toFixed(1)}%</span>` : ""}
      </div>
    `;
  });

  document.getElementById("overall-voteshare").innerHTML = sliverHtml;
}

// ---------------------------------------------------------------
// Map interaction: panning, click-to-zoom, results panel dragging
// ---------------------------------------------------------------

function setupPanning(svgElement) {
  svgElement.addEventListener("mousedown", (e) => {
    isPanning = true;
    lastX = e.clientX;
    lastY = e.clientY;
    svgElement.style.cursor = "grabbing";
  });

  svgElement.addEventListener("mousemove", (e) => {
    if (!isPanning) return;

    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;

    // Get the current viewBox and zoom level (scale)
    const currentViewBox = svgElement.getAttribute("viewBox").split(" ").map(Number);
    const [x, y, width, height] = currentViewBox;

    // Calculate the zoom level based on the width or height of the viewBox
    const zoomX = width / svgElement.clientWidth;
    const zoomY = height / svgElement.clientHeight;

    // Adjust panning movement based on zoom level
    const adjustedDx = dx * zoomX;
    const adjustedDy = dy * zoomY;

    // Calculate new viewBox position
    const newX = x - adjustedDx;
    const newY = y - adjustedDy;

    // Set new viewBox for panning effect
    svgElement.setAttribute("viewBox", `${newX} ${newY} ${width} ${height}`);

    // Update last mouse position for the next move
    lastX = e.clientX;
    lastY = e.clientY;
  });

  svgElement.addEventListener("mouseup", () => {
    isPanning = false;
    svgElement.style.cursor = "move";
  });

  svgElement.addEventListener("mouseleave", () => {
    isPanning = false;
    svgElement.style.cursor = "move";
  });
}

function setupClickHandlers(svgElement) {
  svgElement.querySelectorAll("path").forEach(function (path) {
    path.addEventListener("click", function (event) {
      event.stopPropagation();
      zoomToDistrict(event.target);
    });
  });
}

function zoomToDistrict(path) {
  const activeSvg = getActiveSvg();

  // Get bounding box of the district
  const bbox = path.getBBox();

  // Add some padding around the district
  const padding = 30;
  const x = bbox.x - padding;
  const y = bbox.y - padding;
  const width = bbox.width + padding * 2;
  const height = bbox.height + padding * 2;

  // Set new viewBox to zoom to the district
  activeSvg.setAttribute("viewBox", `${x} ${y} ${width} ${height}`);

  showPulseMarker(path);

  // Display election results for the district
  const districtName = path.getAttribute("inkscape:label");
  displayElectionResults(districtName);
}

function resetView() {
  const activeSvg = getActiveSvg();
  if (activeSvg === svg) {
    activeSvg.setAttribute("viewBox", originalViewBox);
  } else if (activeSvg === svg2010 && originalViewBox2010) {
    activeSvg.setAttribute("viewBox", originalViewBox2010);
  }

  clearPulseMarker();

  if (panel) panel.classList.remove("rp-visible");
  if (resultsChart) {
    resultsChart.destroy();
    resultsChart = null;
  }
}

// chloro.js wraps/reads these as globals, so expose them explicitly
window.setElectionYear = setElectionYear;
window.colorDistricts = colorDistricts;
window.getPartyColor = getPartyColor;
window.getActiveSvg = getActiveSvg;

// ---------------------------------------------------------------
// Bootstrap: load the two maps + all election datasets, then wire
// up the page. Runs once on DOMContentLoaded.
// ---------------------------------------------------------------

async function loadSvgInto(url, slotId) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  document.getElementById(slotId).innerHTML = await res.text();
}

async function loadElectionDatasets() {
  const entries = await Promise.all(
    Object.entries(DATA_FILES).map(async ([year, url]) => {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
      return [year, await res.json()];
    })
  );
  entries.forEach(([year, data]) => { electionDatasets[year] = data; });
}

async function init() {
  await Promise.all([
    loadSvgInto("maps/conmap.svg", "conmap-slot"),
    loadSvgInto("maps/conmap_2010.svg", "conmap-2010-slot"),
    loadElectionDatasets(),
  ]);

  svg = document.getElementById("conmap");
  svg2010 = document.getElementById("conmap_2010");
  conmapSlot = document.getElementById("conmap-slot");
  conmap2010Slot = document.getElementById("conmap-2010-slot");
  container = document.getElementById("map-container");
  panel = document.getElementById("results-panel");

  rpGainHold = document.getElementById("rp-gainhold");
  rpResultTag = document.getElementById("rp-result-tag");
  rpChartBig = document.getElementById("rp-chart-big");
  rpChartMiniCol = document.getElementById("rp-chart-mini-col");
  rpCandidates = document.getElementById("rp-candidates");
  rpMajorityBar = panel.querySelector(".rp-majority");
  rpMajorityLabel = document.getElementById("rp-majority-label");
  rpMajorityValue = document.getElementById("rp-majority-value");
  rpTurnoutValue = document.getElementById("rp-turnout-value");
  rpTurnoutChange = document.getElementById("rp-turnout-change");
  rpNameRibbon = document.getElementById("rp-name-ribbon");

  originalViewBox = svg.getAttribute("viewBox");
  originalViewBox2010 = svg2010 ? svg2010.getAttribute("viewBox") : null;

  currentElectionYear = 2024;
  electionData = electionDatasets[currentElectionYear];
  currentMap = svg;
  window.currentSvg = svg;

  // Results panel dragging
  panel.addEventListener("mousedown", function (e) {
    if (!e.target.closest(".rp-header")) return;
    isDragging = true;
    offsetX = e.clientX - panel.getBoundingClientRect().left;
    offsetY = e.clientY - panel.getBoundingClientRect().top;
  });

  document.addEventListener("mousemove", function (e) {
    if (isDragging) {
      panel.style.left = `${e.clientX - offsetX}px`;
      panel.style.top = `${e.clientY - offsetY}px`;
    }
  });

  document.addEventListener("mouseup", function () {
    isDragging = false;
  });

  // Panning + click-to-zoom on both maps
  setupPanning(svg);
  if (svg2010) setupPanning(svg2010);
  setupClickHandlers(svg);
  if (svg2010) setupClickHandlers(svg2010);

  // Initially show conmap and hide conmap_2010
  showMap(svg);

  // Year selector buttons
  document.querySelectorAll("#election-controls button[data-year]").forEach(btn => {
    btn.addEventListener("click", () => setElectionYear(parseYearKey(btn.dataset.year)));
  });
  document.querySelector('#election-controls button[data-year="2024"]').classList.add("active");

  // A few of these buttons aren't a real historical election result, so
  // they get a short explanation rather than leaving the user to guess.
  const YEAR_BUTTON_INFO = {
    eu2016: "Estimated Leave/Remain vote by constituency, modelled onto the pre-2024 boundaries used on this map. Not an official result.",
    2029: "A forward projection: each seat is split into political “tribes” (see Electorate Segments), each tribe's vote is swung by current polling, then squeezed for tactical voting toward the strongest challenger to the front-runner.",
    1: "The 2019 general election result, recalculated onto the 2024 boundaries so it's directly comparable to the 2024 result on this map.",
    2016: "Not a real election — shows each constituency's estimated mix of political “tribes” (Muslims, Left, Progressives, Average, Liberals, Blues, Reformers), the segments the Prediction map swings individually.",
    custom: "Build your own what-if result: enter target national vote shares and this works backwards to a plausible seat-by-seat map, using the same tribe/segment model as the Prediction map.",
  };
  if (window.createInfoTip) {
    document.querySelectorAll("#election-controls button[data-year]").forEach(btn => {
      const info = YEAR_BUTTON_INFO[parseYearKey(btn.dataset.year)];
      if (info) btn.appendChild(window.createInfoTip(info));
    });
  }

  // Zoom controls
  document.getElementById("zoom-in").addEventListener("click", function () {
    const activeSvg = getActiveSvg();
    const [x, y, w, h] = activeSvg.getAttribute("viewBox").split(" ").map(Number);
    const zoomFactor = 0.8;
    const newW = w * zoomFactor;
    const newH = h * zoomFactor;
    const newX = x + (w - newW) / 2;
    const newY = y + (h - newH) / 2;
    activeSvg.setAttribute("viewBox", `${newX} ${newY} ${newW} ${newH}`);
  });

  document.getElementById("zoom-out").addEventListener("click", function () {
    const activeSvg = getActiveSvg();
    const [x, y, w, h] = activeSvg.getAttribute("viewBox").split(" ").map(Number);
    const zoomFactor = 1.2;
    const newW = w * zoomFactor;
    const newH = h * zoomFactor;
    const newX = x - (newW - w) / 2;
    const newY = y - (newH - h) / 2;
    activeSvg.setAttribute("viewBox", `${newX} ${newY} ${newW} ${newH}`);
  });

  document.getElementById("reset-btn").addEventListener("click", resetView);

  colorDistricts();
  displayOverallResults();
  updateSegmentsLegendVisibility();
  resetView();
}

document.addEventListener("DOMContentLoaded", init);
