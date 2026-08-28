/* ============================================================
   CUSTOM PREDICTOR
   ------------------------------------------------------------
   A user-driven "what if" prediction. The user types in target
   national vote shares (either one UK-wide number per party, or
   separate UK/Scotland/Wales numbers with England inferred from
   the difference), and this works backwards to a transfer matrix
   per voter "tribe" (segment) that would produce that outcome
   when applied to the real tribe-level seat allocation - using
   predictionTable.xlsx's priority-ordered list of plausible
   segment + party-pair churn axes, tried in order, with a
   generic non-segment-specific catch-all ("last resort") for
   whatever's left unexplained.

   Runs entirely client-side against data/alloc.json (exported by
   pipeline/scripts/07_export_alloc.py from the *Alloc.csv files
   and predictionTable.xlsx - re-run that script if either source
   changes). Nothing here touches the real Prediction/Segments
   datasets; the result is stored under electionDatasets["custom"]
   and rendered through the exact same map/panel/ticker code every
   other year already uses (see app.js's setElectionYear).
   ============================================================ */

(function () {

  const SEGMENTS = ["Muslim", "Left", "Progressives", "Average", "Liberal", "Blues", "Reforms"];
  const BASELINE_PARTIES = ["Labour", "Conservative", "Reform", "LibDem", "Green", "Oth", "SNP", "Plaid"];
  const PIPELINE_PARTIES = BASELINE_PARTIES.concat(["Restore"]);

  const PARTY_TO_CODE = {
    Labour: "LAB", Conservative: "CON", Reform: "REF", Restore: "RESTORE",
    LibDem: "LD", Green: "GRN", Oth: "OTHER", SNP: "SNP", Plaid: "PLAID",
  };

  const PARTY_LABELS = {
    Labour: "Labour", Conservative: "Conservative", Reform: "Reform",
    LibDem: "Lib Dem", Green: "Green", SNP: "SNP", Plaid: "Plaid",
    Oth: "Other", Restore: "Restore",
  };

  // Display/input order.
  const DISPLAY_ORDER = ["Labour", "Conservative", "Reform", "LibDem", "Green", "SNP", "Plaid", "Oth", "Restore"];

  let alloc = null;      // parsed data/alloc.json
  let loaded = false;
  let loadError = null;

  // ---- Build panel markup -----------------------------------
  const panel = document.createElement("div");
  panel.id = "custom-predictor-panel";
  panel.style.display = "none";
  panel.innerHTML = `
    <style>
      #custom-predictor-panel {
        position: fixed;
        top: 140px;
        left: 16px;
        z-index: 1000;
        background: var(--bbc-panel, #232327);
        border: none;
        box-shadow: 0 6px 24px rgba(0,0,0,0.5);
        padding: 0 14px 14px;
        font-family: var(--font-body, "Roboto Condensed", Arial, sans-serif);
        font-size: 13px;
        color: #fff;
        width: 300px;
        max-height: 80vh;
        overflow-y: auto;
      }
      #custom-predictor-panel-handle {
        position: sticky;
        top: 0;
        margin: 0 -14px 10px -14px;
        padding: 10px 14px;
        background: var(--bbc-custom, #0c8f6e);
        cursor: grab;
        user-select: none;
        display: flex;
        align-items: center;
        justify-content: space-between;
        z-index: 1;
      }
      #custom-predictor-panel-handle.dragging { cursor: grabbing; }
      #custom-predictor-panel h4 {
        margin: 0;
        font-family: var(--font-head, "Archivo Black", sans-serif);
        font-size: 13px;
        font-weight: normal;
        letter-spacing: 0.02em;
        text-transform: uppercase;
        pointer-events: none;
      }
      #custom-predictor-panel-handle .cp-drag-dots {
        font-size: 12px;
        color: rgba(255,255,255,0.7);
        letter-spacing: 1px;
        pointer-events: none;
      }
      #custom-predictor-panel .cp-mode-row {
        display: flex;
        gap: 6px;
        margin-bottom: 10px;
      }
      #custom-predictor-panel .cp-mode-btn {
        flex: 1;
        padding: 6px 4px;
        font-family: var(--font-body, "Roboto Condensed", Arial, sans-serif);
        font-weight: 700;
        font-size: 11px;
        letter-spacing: 0.02em;
        text-transform: uppercase;
        background: var(--bbc-panel-2, #2c2c31);
        color: #9a9aa3;
        border: 1px solid var(--bbc-line, #3a3a40);
        cursor: pointer;
      }
      #custom-predictor-panel .cp-mode-btn.active {
        background: var(--bbc-custom, #0c8f6e);
        color: #fff;
        border-color: var(--bbc-custom, #0c8f6e);
      }
      #custom-predictor-panel table {
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 10px;
      }
      #custom-predictor-panel th {
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #9a9aa3;
        text-align: right;
        padding: 0 0 4px;
      }
      #custom-predictor-panel th.cp-party-col { text-align: left; }
      #custom-predictor-panel td {
        padding: 2px 0;
        vertical-align: middle;
      }
      #custom-predictor-panel td.cp-party-label {
        font-weight: 700;
        font-size: 12px;
      }
      #custom-predictor-panel input[type="number"] {
        width: 52px;
        padding: 4px 5px;
        border: 1px solid var(--bbc-line, #3a3a40);
        background: var(--bbc-panel-2, #2c2c31);
        color: #fff;
        font-family: var(--font-body, "Roboto Condensed", Arial, sans-serif);
        font-size: 12px;
        text-align: right;
      }
      #custom-predictor-panel .cp-sum-row td {
        padding-top: 6px;
        border-top: 1px solid var(--bbc-line, #3a3a40);
        font-size: 11px;
        color: #9a9aa3;
        text-align: right;
      }
      #custom-predictor-panel .cp-simulate-btn {
        width: 100%;
        padding: 10px;
        background: var(--bbc-custom, #0c8f6e);
        color: #fff;
        border: none;
        font-family: var(--font-head, "Archivo Black", sans-serif);
        font-size: 13px;
        letter-spacing: 0.02em;
        text-transform: uppercase;
        cursor: pointer;
      }
      #custom-predictor-panel .cp-simulate-btn:hover { background: var(--bbc-custom-dark, #075c47); }
      #custom-predictor-panel .cp-simulate-btn:disabled { opacity: 0.5; cursor: default; }
      #custom-predictor-panel .cp-status {
        margin-top: 8px;
        font-size: 11px;
        line-height: 1.4;
        color: #cfa93a;
        white-space: pre-line;
      }
      #custom-predictor-panel .cp-hidden { display: none !important; }
      #custom-predictor-panel input[type="number"][readonly] {
        opacity: 0.55;
        cursor: default;
      }
    </style>
    <div id="custom-predictor-panel-handle">
      <h4>Custom Predictor</h4>
      <span class="cp-drag-dots">⠿</span>
    </div>
    <div class="cp-mode-row">
      <button type="button" class="cp-mode-btn active" data-mode="national">National</button>
      <button type="button" class="cp-mode-btn" data-mode="breakdown">UK / Scotland / Wales</button>
    </div>
    <div id="cp-national-inputs">
      <table>
        <thead><tr><th class="cp-party-col">Party</th><th>National %</th></tr></thead>
        <tbody id="cp-national-rows"></tbody>
        <tfoot><tr class="cp-sum-row"><td></td><td id="cp-national-sum">-</td></tr></tfoot>
      </table>
    </div>
    <div id="cp-breakdown-inputs" class="cp-hidden">
      <table>
        <thead><tr>
          <th class="cp-party-col">Party</th><th>UK %</th><th>Scot %</th><th>Wales %</th>
        </tr></thead>
        <tbody id="cp-breakdown-rows"></tbody>
      </table>
    </div>
    <button type="button" class="cp-simulate-btn" id="cp-simulate-btn" disabled>Loading data...</button>
    <div class="cp-status" id="cp-status"></div>
  `;
  document.body.appendChild(panel);

  const nationalRows = panel.querySelector("#cp-national-rows");
  const breakdownRows = panel.querySelector("#cp-breakdown-rows");
  const nationalInputs = panel.querySelector("#cp-national-inputs");
  const breakdownInputs = panel.querySelector("#cp-breakdown-inputs");
  const nationalSumEl = panel.querySelector("#cp-national-sum");
  const simulateBtn = panel.querySelector("#cp-simulate-btn");
  const statusEl = panel.querySelector("#cp-status");
  const dragHandle = panel.querySelector("#custom-predictor-panel-handle");
  const modeButtons = panel.querySelectorAll(".cp-mode-btn");

  if (window.createInfoTip) {
    dragHandle.querySelector("h4").appendChild(window.createInfoTip(
      "Enter target national (or UK/Scotland/Wales) vote shares and this works backwards to a plausible seat-by-seat result, using the same voter-“tribe” model as the Prediction map."
    ));
  }

  // ---- Draggable, same pattern as the choropleth/demographics panels --
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

  // ---- Mode toggle --------------------------------------------------
  let mode = "national"; // "national" | "breakdown"

  modeButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      mode = btn.dataset.mode;
      modeButtons.forEach(b => b.classList.toggle("active", b === btn));
      nationalInputs.classList.toggle("cp-hidden", mode !== "national");
      breakdownInputs.classList.toggle("cp-hidden", mode !== "breakdown");
    });
  });

  // ---- Toggle panel from the "Custom" tab button ---------------------
  // (a separate concern from app.js's own data-year click listener,
  // which tries to switch the map to electionDatasets["custom"] - that's
  // a no-op with a console warning until the first Simulate click.)
  const tabButton = document.querySelector('#election-controls button[data-year="custom"]');
  if (tabButton) {
    tabButton.addEventListener("click", () => {
      panel.style.display = panel.style.display === "none" ? "block" : "none";
    });
  }

  // ---- Apply an arbitrary segment matrix (9x9 per segment) to one seat's
  // real 2024 tribal baseline. Returns { segment: { party: votes } } in
  // real vote counts. Used both to find out what the unmodified built-in
  // matrix currently predicts (for target-gap purposes) and, after churn
  // has modified a copy of that matrix, to produce the actual final
  // per-seat projection - always a single hop straight from each voter's
  // real 2024 party, never a chain of two separately-built matrices.
  function applyMatrixToSeat(seat, matrices) {
    const result = {};
    const seatTotal = seat.prev_TOTAL || 0;

    SEGMENTS.forEach(seg => {
      result[seg] = {};
      PIPELINE_PARTIES.forEach(p => { result[seg][p] = 0; });

      const segPct = seat.segments[seg] || {};
      const matrixForSeg = matrices[seg];
      BASELINE_PARTIES.forEach(from => {
        // seat.segments[seg][party] is a PERCENTAGE POINT of that seat's
        // own electorate (they sum to ~100 across all 7 segments x parties
        // for a seat) - not a vote count, and not comparable/summable
        // across seats with different turnouts until converted via that
        // seat's own prev_TOTAL.
        const v = (segPct[from] || 0) / 100 * seatTotal;
        if (!v) return;
        const row = matrixForSeg[from];
        PIPELINE_PARTIES.forEach(to => {
          const pct = row ? (row[to] || 0) : (to === from ? 100 : 0);
          if (pct) result[seg][to] += v * pct / 100;
        });
      });
    });

    return result;
  }

  // ---- Baseline computation ------------------------------------------
  // totalVotes = the nation's total 2024 electorate turnout being
  // reallocated. `total` (real votes per party, nationally) isn't computed
  // here - it's filled in afterwards straight from the actual "Prediction"
  // (2029) dataset, so the input panel's defaults - and the swing ratios -
  // match what the Prediction tab is actually showing.
  function computeNationBaseline(nationData) {
    return { totalVotes: nationData.totalVotes };
  }

  // ---- Real Prediction (2029) totals, per nation -----------------------
  // Sums the actual "Prediction" tab's per-seat vote counts, bucketed by
  // nation via alloc's own seat lists.
  function computePredictionTotals(predictionRecords, allocNations) {
    const seatToNation = {};
    ["england", "scotland", "wales"].forEach(nation => {
      allocNations[nation].seats.forEach(seat => { seatToNation[seat.Seat] = nation; });
    });

    const total = { england: {}, scotland: {}, wales: {} };
    ["england", "scotland", "wales"].forEach(nation => {
      PIPELINE_PARTIES.forEach(p => { total[nation][p] = 0; });
    });

    predictionRecords.forEach(rec => {
      const nation = seatToNation[rec.Name];
      if (!nation) return;
      PIPELINE_PARTIES.forEach(p => {
        total[nation][p] += Number(rec[PARTY_TO_CODE[p]]) || 0;
      });
    });

    return total;
  }

  let baselines = null; // { england, scotland, wales } -> { total, totalVotes }
  let ukTotalVotes = 0;
  let ukPct = {}; // whole-UK current % per party, for National-mode defaults

  function buildTable() {
    nationalRows.innerHTML = "";
    breakdownRows.innerHTML = "";

    DISPLAY_ORDER.forEach(party => {
      const label = PARTY_LABELS[party];
      const nationalDefault = (ukPct[party] || 0).toFixed(1);

      const nRow = document.createElement("tr");
      nRow.innerHTML = `
        <td class="cp-party-label">${label}</td>
        <td><input type="number" step="0.1" min="0" max="100" data-party="${party}" class="cp-input-national" value="${nationalDefault}"></td>
      `;
      nationalRows.appendChild(nRow);

      const ukDefault = nationalDefault;
      const scotDefault = ((baselines.scotland.total[party] / baselines.scotland.totalVotes) * 100 || 0).toFixed(1);
      const walesDefault = ((baselines.wales.total[party] / baselines.wales.totalVotes) * 100 || 0).toFixed(1);

      const bRow = document.createElement("tr");
      bRow.innerHTML = `
        <td class="cp-party-label">${label}</td>
        <td><input type="number" step="0.1" min="0" max="100" data-party="${party}" class="cp-input-uk" value="${ukDefault}"></td>
        <td><input type="number" step="0.1" min="0" max="100" data-party="${party}" class="cp-input-scot" value="${scotDefault}"></td>
        <td><input type="number" step="0.1" min="0" max="100" data-party="${party}" class="cp-input-wales" value="${walesDefault}"></td>
      `;
      breakdownRows.appendChild(bRow);
    });

    setupAutoOth(nationalRows, "cp-input-national", updateNationalSum);
    setupAutoOth(breakdownRows, "cp-input-uk", null);
    setupAutoOth(breakdownRows, "cp-input-scot", null);
    setupAutoOth(breakdownRows, "cp-input-wales", null);

    const ukVotesTotal = baselines.england.totalVotes + baselines.scotland.totalVotes + baselines.wales.totalVotes;
    setupSingleNationParty("SNP", "scot", "wales", baselines.scotland.totalVotes, ukVotesTotal);
    setupSingleNationParty("Plaid", "wales", "scot", baselines.wales.totalVotes, ukVotesTotal);

    updateNationalSum();
  }

  // SNP only contests Scotland and Plaid only contests Wales, so in the
  // UK/Scotland/Wales breakdown table only their home-nation column means
  // anything - the OTHER nation's column is locked at 0, and the UK-wide
  // column (which would otherwise let a user set it inconsistently with
  // the home-nation figure) is auto-derived from the home-nation column,
  // the same way "Other" auto-fills as a remainder.
  function setupSingleNationParty(party, homeCol, otherCol, homeVotes, ukVotes) {
    const ukInput = breakdownRows.querySelector(`input.cp-input-uk[data-party="${party}"]`);
    const homeInput = breakdownRows.querySelector(`input.cp-input-${homeCol}[data-party="${party}"]`);
    const otherInput = breakdownRows.querySelector(`input.cp-input-${otherCol}[data-party="${party}"]`);
    if (!ukInput || !homeInput || !otherInput) return;

    otherInput.value = "0.0";
    otherInput.readOnly = true;
    otherInput.dispatchEvent(new Event("input", { bubbles: true }));

    ukInput.readOnly = true;
    function recomputeUk() {
      const homeVal = parseFloat(homeInput.value) || 0;
      ukInput.value = (ukVotes > 0 ? (homeVal * homeVotes / ukVotes) : 0).toFixed(1);
      ukInput.dispatchEvent(new Event("input", { bubbles: true }));
    }
    homeInput.addEventListener("input", recomputeUk);
    recomputeUk();
  }

  // "Oth" is never typed directly - it auto-fills as 100 minus whatever the
  // other parties in that column currently sum to, recomputing live as the
  // user edits any of them (matches "Other" being a remainder category, not
  // an independently-set target).
  function setupAutoOth(rows, inputClass, onChange) {
    const inputs = Array.from(rows.querySelectorAll(`input.${inputClass}`));
    const othInput = inputs.find(el => el.dataset.party === "Oth");
    if (!othInput) return;
    othInput.readOnly = true;

    const others = inputs.filter(el => el.dataset.party !== "Oth");

    function recompute() {
      let sum = 0;
      others.forEach(el => { sum += parseFloat(el.value) || 0; });
      othInput.value = Math.max(0, 100 - sum).toFixed(1);
      if (onChange) onChange();
    }

    others.forEach(el => el.addEventListener("input", recompute));
    recompute();
  }

  function updateNationalSum() {
    let sum = 0;
    nationalRows.querySelectorAll("input").forEach(el => { sum += parseFloat(el.value) || 0; });
    nationalSumEl.textContent = `Total: ${sum.toFixed(1)}%`;
  }

  // ---- Read inputs ----------------------------------------------------
  function readNationalInputs() {
    const pct = {};
    nationalRows.querySelectorAll("input").forEach(el => {
      pct[el.dataset.party] = parseFloat(el.value) || 0;
    });
    return pct;
  }

  function readBreakdownInputs() {
    const uk = {}, scotland = {}, wales = {};
    breakdownRows.querySelectorAll(".cp-input-uk").forEach(el => { uk[el.dataset.party] = parseFloat(el.value) || 0; });
    breakdownRows.querySelectorAll(".cp-input-scot").forEach(el => { scotland[el.dataset.party] = parseFloat(el.value) || 0; });
    breakdownRows.querySelectorAll(".cp-input-wales").forEach(el => { wales[el.dataset.party] = parseFloat(el.value) || 0; });
    return { uk, scotland, wales };
  }

  // ---- Renormalise a set of target percentages to sum to 100 ----------
  // (votes are conserved - we're reallocating the existing electorate,
  // not creating turnout out of nowhere)
  function renormalise(pct) {
    let sum = 0;
    PIPELINE_PARTIES.forEach(p => { sum += pct[p] || 0; });
    const out = {};
    if (sum <= 0) {
      PIPELINE_PARTIES.forEach(p => { out[p] = 0; });
      return out;
    }
    PIPELINE_PARTIES.forEach(p => { out[p] = (pct[p] || 0) * 100 / sum; });
    return out;
  }

  // ---- Proportional national swing, per nation --------------------------
  // No table, no chains, no bin. Every party gets ONE ratio per nation:
  // target votes / the built-in matrix's own predicted votes. Each seat's
  // built-in (fixed-matrix) result is scaled by that same ratio for every
  // party, then renormalised back to the seat's real turnout so shares
  // still sum to 100. A party a seat barely has (e.g. 3% Labour) ends up
  // moving by the same proportion as everywhere else, not getting shoved
  // to 0 or blown up past what's plausible for that seat - and a party
  // with a real, non-zero built-in prediction (Restore included - it's a
  // genuine destination in the fixed matrix, not a 2024-baseline party)
  // scales cleanly to whatever the user asks, including exactly 0.
  function computeNationRatios(nationBaseline, targetPct) {
    const { totalVotes } = nationBaseline;
    const target = {};
    PIPELINE_PARTIES.forEach(p => { target[p] = (targetPct[p] || 0) / 100 * totalVotes; });
    return { target, totalVotes };
  }

  function projectSeatScaled(seat, fixedMatrices, ratio) {
    const result = applyMatrixToSeat(seat, fixedMatrices);
    const baseline = {};
    PIPELINE_PARTIES.forEach(p => { baseline[p] = 0; });
    SEGMENTS.forEach(seg => {
      PIPELINE_PARTIES.forEach(p => { baseline[p] += result[seg][p]; });
    });

    let seatTotal = 0, scaledTotal = 0;
    const scaled = {};
    PIPELINE_PARTIES.forEach(p => {
      seatTotal += baseline[p];
      const v = baseline[p] * (ratio[p] != null ? ratio[p] : 1);
      scaled[p] = v;
      scaledTotal += v;
    });

    const projected = {};
    PIPELINE_PARTIES.forEach(p => {
      projected[p] = scaledTotal > 0 ? (scaled[p] / scaledTotal) * seatTotal : 0;
    });
    return projected;
  }

  // ---- Full per-nation result, with iterative tactical-voting correction
  // Tactical voting and local flows run AFTER the proportional swing, and
  // they systematically pull vote shares further (squeezed parties lose
  // more, winnable ones gain) - so a ratio calibrated only against the
  // pre-tactical swing lands short of the user's actual typed target once
  // tactical voting has run. This re-solves for the ratio by running the
  // whole seat -> swing -> tactical voting -> local flows pipeline a few
  // times, each time nudging the ratio by (target / what actually came
  // out), until the final post-tactical national total is close to the
  // target (or a small iteration cap is hit). Not exact, but close.
  function computeNationResult(nationData, fixedMatrices, nationBaseline, targetPct) {
    const { target, totalVotes } = computeNationRatios(nationBaseline, targetPct);

    const ratio = {};
    PIPELINE_PARTIES.forEach(p => {
      const baselineVotes = nationBaseline.total[p] || 0;
      ratio[p] = baselineVotes > 1e-6 ? target[p] / baselineVotes : 1;
    });

    let seatResults = null;
    const MAX_ITER = 6;
    for (let iter = 0; iter < MAX_ITER; iter++) {
      seatResults = nationData.seats.map(seat => {
        const scaled = projectSeatScaled(seat, fixedMatrices, ratio);
        const tactical = applyTacticalVoting(seat, Object.assign({}, scaled));
        const final = applyLocalFlows(seat, tactical);
        return { seat, final };
      });

      const actual = {};
      PIPELINE_PARTIES.forEach(p => { actual[p] = 0; });
      seatResults.forEach(({ final }) => {
        PIPELINE_PARTIES.forEach(p => { actual[p] += final[p] || 0; });
      });

      let maxRelErr = 0;
      PIPELINE_PARTIES.forEach(p => {
        if (target[p] > 1e-6) {
          maxRelErr = Math.max(maxRelErr, Math.abs(actual[p] - target[p]) / target[p]);
        } else if (actual[p] > 1e-6) {
          maxRelErr = Math.max(maxRelErr, 1);
        }
      });
      if (maxRelErr < 0.005 || iter === MAX_ITER - 1) break;

      PIPELINE_PARTIES.forEach(p => {
        if (target[p] <= 1e-6) {
          ratio[p] = 0;
        } else if (actual[p] > 1e-6) {
          ratio[p] *= target[p] / actual[p];
        }
      });
    }

    const actualFinal = {};
    PIPELINE_PARTIES.forEach(p => { actualFinal[p] = 0; });
    seatResults.forEach(({ final }) => {
      PIPELINE_PARTIES.forEach(p => { actualFinal[p] += final[p] || 0; });
    });
    const shortfall = PIPELINE_PARTIES.reduce((s, p) => s + Math.abs(target[p] - actualFinal[p]), 0);

    return { seatResults, shortfall, totalVotes };
  }

  // ---- Tactical voting ---------------------------------------------------
  // Every party is tiered by how far behind the projected leader it is (the
  // incumbent is always tier 1, whatever its own gap): tier 1 within 5pts
  // of the leader, tier 2 within 5-10pts, tier 3 within 10-15pts, beyond
  // that not tiered at all. Tier 1 never tactically votes - it's already
  // winning. Every other party (tier 2, tier 3, and non-tiered) tactically
  // votes for any tiered party in a STRICTLY BETTER tier than its own (a
  // non-tiered donor can vote for any tiered party) - at their normal TVPCT
  // rate for non-tiered donors, 40% of it for tier 2, 80% of it for tier 3.
  // That transfer cascades down the donor's TVMatrix preference ranking
  // restricted to those eligible candidates - at each ranked candidate, the
  // amount of whatever's still left that actually moves there is scaled by
  // BOTH that candidate's personal appeal to this donor's tactical voters
  // (the TVPCT willingness matrix) AND that candidate's own tier strength
  // (100%/50%/25% - is voting for them practically worth it, given their
  // own viability), and the rest cascades to the next-ranked candidate.
  // Whatever's left once the ranked list of eligible candidates runs out
  // simply stays with the donor - it never overflows anywhere else.
  const TIER_STRENGTH = { 1: 1, 2: 0.5, 3: 0.25 };
  const DONOR_TVPCT_MULT = { 2: 0.4, 3: 0.8 }; // non-tiered donors use 1

  function cascadingTransfer(donor, votes, tier) {
    const donorTier = tier[donor];
    if (donorTier === 1) return;

    const mult = donorTier != null ? DONOR_TVPCT_MULT[donorTier] : 1;
    const transfer = votes[donor] * ((alloc.tvPct[donor] || 0) / 100) * mult;
    if (transfer <= 0) return;

    const prefs = alloc.tvMatrix[donor] || {};
    const willingness = alloc.tvWillingness[donor] || {};
    const rankedEligible = PIPELINE_PARTIES
      .filter(p => p !== donor
        && (prefs[p] != null ? prefs[p] : -1) > 0
        && tier[p] != null
        && (donorTier == null || tier[p] < donorTier))
      .sort((a, b) => prefs[a] - prefs[b]);

    let remaining = transfer;
    for (const candidate of rankedEligible) {
      if (remaining <= 0) break;
      const amount = remaining * ((willingness[candidate] || 0) / 100) * TIER_STRENGTH[tier[candidate]];
      votes[candidate] += amount;
      remaining -= amount;
    }

    votes[donor] -= (transfer - remaining);
  }

  function applyTacticalVoting(seat, votes) {
    const total = PIPELINE_PARTIES.reduce((s, p) => s + (votes[p] || 0), 0);

    const tier = {};
    if (total > 0) {
      let leader = PIPELINE_PARTIES[0];
      PIPELINE_PARTIES.forEach(p => {
        if ((votes[p] || 0) > (votes[leader] || 0)) leader = p;
      });
      const leaderShare = (votes[leader] || 0) / total * 100;

      PIPELINE_PARTIES.forEach(p => {
        const share = (votes[p] || 0) / total * 100;
        const gap = leaderShare - share;
        if (gap <= 5) tier[p] = 1;
        else if (gap <= 10) tier[p] = 2;
        else if (gap <= 15) tier[p] = 3;
        // else: not a tactical-voting destination at all
      });
    }

    const previous = alloc.winners[seat.Seat];
    if (previous && PIPELINE_PARTIES.includes(previous)) tier[previous] = 1;

    if (Object.keys(tier).length <= 1) return votes;

    PIPELINE_PARTIES.forEach(donor => {
      if (tier[donor] === 1) return;
      cascadingTransfer(donor, votes, tier);
    });

    return votes;
  }

  // ---- Local flows --------------------------------------------------------
  // Ports 05_export_svg_output.py's per-seat LocalFlows.xlsx override: only
  // the handful of seats with their own sheet are affected, and it's
  // all-or-nothing per seat, matching the Python try/except - if the sheet
  // doesn't have every pipeline party as a row (05's `.loc[parties, parties]`
  // would raise), the whole override is skipped for that seat.
  function applyLocalFlows(seat, votes) {
    const matrix = alloc.localFlows[seat.Seat];
    if (!matrix) return votes;
    if (!PIPELINE_PARTIES.every(p => matrix[p])) return votes;

    const newVotes = {};
    PIPELINE_PARTIES.forEach(p => { newVotes[p] = 0; });
    PIPELINE_PARTIES.forEach(oldP => {
      const v = votes[oldP];
      if (!v) return;
      const row = matrix[oldP];
      PIPELINE_PARTIES.forEach(newP => {
        newVotes[newP] += v * (row[newP] || 0) / 100;
      });
    });
    return newVotes;
  }

  function buildRecord(seat, projected) {
    const rec = { Name: seat.Seat };
    let total = 0;
    PIPELINE_PARTIES.forEach(p => {
      const code = PARTY_TO_CODE[p];
      const v = Math.round(projected[p] || 0);
      rec[code] = v;
      total += v;
    });
    rec.OTH = "";
    rec.UKIP = "";
    rec.BNP = "";
    rec.RES = "";
    rec.Total = total;
    rec.Electorate = seat.prev_Electorate;

    let winner = null, best = -1;
    PIPELINE_PARTIES.forEach(p => {
      const code = PARTY_TO_CODE[p];
      if (rec[code] > best) { best = rec[code]; winner = code; }
    });
    rec.Winner = winner;

    rec.prev_Electorate = seat.prev_Electorate;
    rec.prev_LAB = seat.prev_LAB;
    rec.prev_CON = seat.prev_CON;
    rec.prev_REF = seat.prev_REF;
    rec.prev_RESTORE = 0;
    rec.prev_LD = seat.prev_LD;
    rec.prev_GRN = seat.prev_GRN;
    rec.prev_OTHER = seat.prev_OTHER;
    rec.prev_SNP = seat.prev_SNP == null ? "" : seat.prev_SNP;
    rec.prev_PLAID = seat.prev_PLAID == null ? "" : seat.prev_PLAID;
    rec.prev_OTH = seat.prev_OTH == null ? "" : seat.prev_OTH;
    rec.prev_UKIP = seat.prev_UKIP == null ? "" : seat.prev_UKIP;
    rec.prev_BNP = seat.prev_BNP == null ? "" : seat.prev_BNP;
    rec.prev_RES = seat.prev_RES == null ? "" : seat.prev_RES;
    rec.prev_TOTAL = seat.prev_TOTAL;

    return rec;
  }

  // ---- Simulate ---------------------------------------------------------
  function simulate() {
    if (!loaded) return;

    const t0 = performance.now();
    statusEl.textContent = "";

    let nationTargets; // { england: pct, scotland: pct, wales: pct }

    if (mode === "national") {
      // A single UK-wide % per party does NOT mean "target this % in every
      // nation" - England/Scotland/Wales have very different baseline mixes
      // (Conservative is far weaker in Scotland/Wales than England, for
      // instance), so forcing the same target % everywhere invented a huge,
      // implausible swing wherever a party's regional baseline differs from
      // its UK-wide one. Instead: work out ONE ratio per party (target UK
      // votes / the built-in matrix's own predicted UK votes) and apply
      // THAT SAME ratio to each nation's own baseline - a party that's
      // "down 4 points nationally" moves by that same proportion in each
      // nation, rather than being forced to an absolute % that might be
      // wildly wrong for that nation's actual baseline.
      //
      // This also handles SNP/Plaid correctly with no special-casing: their
      // baseline is already ~0 in England/Wales (SNP) or England/Scotland
      // (Plaid), so applying the UK-wide ratio to a ~0 baseline there keeps
      // them at ~0, while their home nation's own (non-zero) baseline
      // absorbs the ratio and lands on the user's intended UK-wide total.
      const pctRaw = renormalise(readNationalInputs());
      const ukVotes = baselines.england.totalVotes + baselines.scotland.totalVotes + baselines.wales.totalVotes;

      const ukRatio = {};
      PIPELINE_PARTIES.forEach(p => {
        const targetVotes = (pctRaw[p] || 0) / 100 * ukVotes;
        const ukBaselineVotes = (baselines.england.total[p] || 0) + (baselines.scotland.total[p] || 0) + (baselines.wales.total[p] || 0);
        ukRatio[p] = ukBaselineVotes > 1e-6 ? targetVotes / ukBaselineVotes : 1;
      });

      function nationTargetFromRatio(nationKey) {
        const out = {};
        PIPELINE_PARTIES.forEach(p => {
          const baselineVotes = baselines[nationKey].total[p] || 0;
          const targetVotes = baselineVotes * ukRatio[p];
          out[p] = baselines[nationKey].totalVotes > 0 ? (targetVotes / baselines[nationKey].totalVotes) * 100 : 0;
        });
        return renormalise(out);
      }

      nationTargets = {
        england: nationTargetFromRatio("england"),
        scotland: nationTargetFromRatio("scotland"),
        wales: nationTargetFromRatio("wales"),
      };
    } else {
      const { uk, scotland, wales } = readBreakdownInputs();
      const ukNorm = renormalise(uk);
      const scotNorm = renormalise(scotland);
      const walesNorm = renormalise(wales);

      const ukVotes = baselines.england.totalVotes + baselines.scotland.totalVotes + baselines.wales.totalVotes;
      const scotVotes = baselines.scotland.totalVotes;
      const walesVotes = baselines.wales.totalVotes;
      const engVotes = baselines.england.totalVotes;

      const englandPctRaw = {};
      let clamped = false;
      PIPELINE_PARTIES.forEach(p => {
        const ukTargetVotes = (ukNorm[p] || 0) / 100 * ukVotes;
        const scotTargetVotes = (scotNorm[p] || 0) / 100 * scotVotes;
        const walesTargetVotes = (walesNorm[p] || 0) / 100 * walesVotes;
        let engTargetVotes = ukTargetVotes - scotTargetVotes - walesTargetVotes;
        if (engTargetVotes < 0) { engTargetVotes = 0; clamped = true; }
        englandPctRaw[p] = engVotes > 0 ? (engTargetVotes / engVotes) * 100 : 0;
      });

      nationTargets = {
        england: renormalise(englandPctRaw),
        scotland: scotNorm,
        wales: walesNorm,
      };

      if (clamped) {
        statusEl.textContent = "Note: England's inferred share went negative for at least one party " +
          "(the UK-wide target was lower than what Scotland + Wales alone would need) - clamped to 0%.";
      }
    }

    const records = [];
    let totalShortfall = 0;
    let totalVotesAll = 0;

    ["england", "scotland", "wales"].forEach(nation => {
      const fixedMatrices = alloc.flowMatrices[nation];
      const { seatResults, shortfall, totalVotes } = computeNationResult(alloc.nations[nation], fixedMatrices, baselines[nation], nationTargets[nation]);
      totalShortfall += shortfall;
      totalVotesAll += totalVotes;
      seatResults.forEach(({ seat, final }) => {
        records.push(buildRecord(seat, final));
      });
    });

    electionDatasets[CUSTOM_YEAR_KEY] = records;
    setElectionYear(CUSTOM_YEAR_KEY);

    const shortfallPct = totalVotesAll > 0 ? (totalShortfall / totalVotesAll) * 100 : 0;
    const note = shortfallPct > 0.5
      ? `\nHeads up: the final result is still about ${shortfallPct.toFixed(1)}% off your targets after tactical voting and local flows - a party at or near 0% is the most likely case this can't fully close.`
      : "";
    const elapsedS = ((performance.now() - t0) / 1000).toFixed(1);
    statusEl.textContent = (statusEl.textContent ? statusEl.textContent + "\n" : "") +
      `Simulated in ${elapsedS}s (incl. tactical voting + local flows for all ${records.length} seats).${note}`;
  }

  simulateBtn.addEventListener("click", () => {
    if (!loaded) return;
    simulateBtn.disabled = true;
    const prevLabel = simulateBtn.textContent;
    simulateBtn.textContent = "Simulating...";
    statusEl.textContent = "Simulating...";
    // Defer the heavy synchronous work one frame so the "Simulating..."
    // status actually paints before the main thread blocks.
    setTimeout(() => {
      try {
        simulate();
      } finally {
        simulateBtn.disabled = false;
        simulateBtn.textContent = prevLabel;
      }
    }, 20);
  });

  // ---- Load alloc.json + the actual Prediction (2029) dataset -----------
  Promise.all([
    fetch("data/alloc.json").then(res => {
      if (!res.ok) throw new Error(`Failed to load alloc.json: ${res.status}`);
      return res.json();
    }),
    fetch("data/elections/2029.json").then(res => {
      if (!res.ok) throw new Error(`Failed to load 2029.json: ${res.status}`);
      return res.json();
    }),
  ])
    .then(([allocData, predictionRecords]) => {
      alloc = allocData;

      const predictionTotals = computePredictionTotals(predictionRecords, alloc.nations);

      baselines = {
        england: computeNationBaseline(alloc.nations.england),
        scotland: computeNationBaseline(alloc.nations.scotland),
        wales: computeNationBaseline(alloc.nations.wales),
      };
      ["england", "scotland", "wales"].forEach(nation => {
        baselines[nation].total = predictionTotals[nation];
      });

      ukTotalVotes = baselines.england.totalVotes + baselines.scotland.totalVotes + baselines.wales.totalVotes;
      PIPELINE_PARTIES.forEach(p => {
        const sum = baselines.england.total[p] + baselines.scotland.total[p] + baselines.wales.total[p];
        ukPct[p] = ukTotalVotes > 0 ? (sum / ukTotalVotes) * 100 : 0;
      });

      loaded = true;
      buildTable();
      simulateBtn.disabled = false;
      simulateBtn.textContent = "Simulate";
    })
    .catch(err => {
      loadError = err;
      console.error(err);
      simulateBtn.textContent = "Failed to load data";
      statusEl.textContent = String(err.message || err);
    });

})();
