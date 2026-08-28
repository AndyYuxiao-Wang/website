/* ============================================================
   INFO TIP
   ------------------------------------------------------------
   A tiny shared "i" badge + hover tooltip, used to drop short
   explanations next to controls that aren't self-explanatory
   (Prediction, Notional 2019, Electorate Segments, Custom, the
   EU referendum map, the demographics panels) without cluttering
   the UI. One shared tooltip element is reused for all of them.

   Two ways to use it:
     1. Programmatically: el.appendChild(createInfoTip("explanation"))
     2. Declaratively, in static HTML:
          <span class="info-tip-icon" data-info-text="explanation"></span>
        - any of these already in the DOM when this script runs get
          wired up automatically (see bottom of file). Load this
          script before app.js/chloro.js/demographics.js/
          customPredictor.js so `createInfoTip` exists when they run.
   ============================================================ */

(function () {

  const tooltip = document.createElement("div");
  tooltip.id = "info-tip-tooltip";
  tooltip.style.cssText = `
    position: fixed;
    z-index: 1200;
    display: none;
    pointer-events: none;
    background: rgba(20,20,23,0.97);
    border: 1px solid var(--bbc-line, #3a3a40);
    color: #fff;
    font-family: var(--font-body, "Roboto Condensed", Arial, sans-serif);
    font-weight: 400;
    font-size: 12px;
    line-height: 1.45;
    padding: 8px 10px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.5);
    max-width: 260px;
    text-transform: none;
    letter-spacing: normal;
  `;
  document.body.appendChild(tooltip);

  function showTip(anchor, text) {
    tooltip.textContent = text;
    tooltip.style.left = "0px";
    tooltip.style.top = "0px";
    tooltip.style.display = "block";

    const rect = anchor.getBoundingClientRect();
    const tw = tooltip.offsetWidth;
    const th = tooltip.offsetHeight;

    let left = rect.left;
    let top = rect.bottom + 8;
    if (left + tw > window.innerWidth - 8) left = window.innerWidth - tw - 8;
    if (top + th > window.innerHeight - 8) top = rect.top - th - 8;

    tooltip.style.left = `${Math.max(8, left)}px`;
    tooltip.style.top = `${Math.max(8, top)}px`;
  }

  function hideTip() {
    tooltip.style.display = "none";
  }

  function wireIcon(icon, text) {
    icon.setAttribute("aria-label", text);
    icon.addEventListener("mouseenter", () => showTip(icon, text));
    icon.addEventListener("mouseleave", hideTip);
    // Icons often sit inside clickable controls (buttons, drag handles) -
    // hovering is enough to read the tip, so swallow clicks rather than
    // also triggering whatever the parent control does.
    icon.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();
    });
  }

  window.createInfoTip = function (text) {
    const icon = document.createElement("span");
    icon.className = "info-tip-icon";
    icon.textContent = "i";
    wireIcon(icon, text);
    return icon;
  };

  document.querySelectorAll(".info-tip-icon[data-info-text]").forEach(icon => {
    wireIcon(icon, icon.dataset.infoText);
  });

})();
