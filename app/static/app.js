// Options Toolkit client behavior: calculator field toggling, ticker price
// autofill, and the expiry payoff chart (inline SVG, theme-aware via CSS vars).

(function () {
  "use strict";

  // --- Calculator: show only the inputs the chosen structure uses -----------
  const structureSelect = document.getElementById("structure-select");
  if (structureSelect) {
    const groups = document.querySelectorAll("[data-for]");
    const sync = () => {
      const s = structureSelect.value;
      groups.forEach((g) => {
        const show = g.dataset.for.split(" ").includes(s);
        g.style.display = show ? "" : "none";
        g.querySelectorAll("input, select").forEach((el) => (el.disabled = !show));
      });
    };
    structureSelect.addEventListener("change", sync);
    sync();
  }

  // --- Trade form: autofill last price hint from yfinance -------------------
  const tickerInput = document.getElementById("ticker-input");
  const priceHint = document.getElementById("price-hint");
  if (tickerInput && priceHint) {
    tickerInput.addEventListener("change", async () => {
      const t = tickerInput.value.trim();
      if (!t) return;
      priceHint.textContent = "fetching price…";
      try {
        const res = await fetch(`/api/price/${encodeURIComponent(t)}`);
        const data = await res.json();
        priceHint.textContent =
          data.price != null
            ? `last price: $${data.price.toFixed(2)}`
            : "price unavailable (offline?) — enter values manually";
      } catch {
        priceHint.textContent = "price unavailable — enter values manually";
      }
    });
  }

  // --- Payoff chart ----------------------------------------------------------
  const chartEl = document.getElementById("payoff-chart");
  if (!chartEl || !chartEl.dataset.curve || chartEl.dataset.curve === "None") return;

  const data = JSON.parse(chartEl.dataset.curve);
  const pts = data.points; // [[price, pl], ...]
  const W = 720, H = 320;
  const M = { top: 16, right: 16, bottom: 34, left: 64 };
  const iw = W - M.left - M.right, ih = H - M.top - M.bottom;

  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  let yMin = Math.min(...ys, 0), yMax = Math.max(...ys, 0);
  const pad = (yMax - yMin) * 0.08 || 1;
  yMin -= pad; yMax += pad;

  const X = (v) => M.left + ((v - xMin) / (xMax - xMin)) * iw;
  const Y = (v) => M.top + ((yMax - v) / (yMax - yMin)) * ih;

  const fmt$ = (v) =>
    (v < 0 ? "-$" : "$") + Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 });

  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Profit and loss at expiry across underlying prices" });

  // gridlines + y ticks at nice round steps (recessive)
  const niceStep = (raw) => {
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    for (const m of [1, 2, 2.5, 5, 10]) if (raw <= m * mag) return m * mag;
    return 10 * mag;
  };
  const step = niceStep((yMax - yMin) / 5);
  for (let v = Math.ceil(yMin / step) * step; v <= yMax; v += step) {
    const y = Y(v);
    svg.appendChild(el("line", { x1: M.left, x2: W - M.right, y1: y, y2: y,
      stroke: "var(--grid)", "stroke-width": 1 }));
    const t = el("text", { x: M.left - 8, y: y + 4, "text-anchor": "end",
      fill: "var(--muted)", "font-size": 11, style: "font-variant-numeric: tabular-nums" });
    t.textContent = fmt$(v);
    svg.appendChild(t);
  }
  // x ticks
  for (let i = 0; i <= 4; i++) {
    const v = xMin + ((xMax - xMin) * i) / 4;
    const t = el("text", { x: X(v), y: H - M.bottom + 18, "text-anchor": "middle",
      fill: "var(--muted)", "font-size": 11, style: "font-variant-numeric: tabular-nums" });
    t.textContent = "$" + v.toFixed(0);
    svg.appendChild(t);
  }

  // profit/loss region fills, split at the zero line (diverging polarity)
  const zeroY = Y(0);
  const clipAbove = el("clipPath", { id: "clip-above" });
  clipAbove.appendChild(el("rect", { x: M.left, y: M.top, width: iw, height: Math.max(0, zeroY - M.top) }));
  const clipBelow = el("clipPath", { id: "clip-below" });
  clipBelow.appendChild(el("rect", { x: M.left, y: zeroY, width: iw, height: Math.max(0, H - M.bottom - zeroY) }));
  svg.appendChild(clipAbove);
  svg.appendChild(clipBelow);

  const areaPath =
    `M ${X(xs[0])} ${zeroY} ` +
    pts.map((p) => `L ${X(p[0])} ${Y(p[1])}`).join(" ") +
    ` L ${X(xs[xs.length - 1])} ${zeroY} Z`;
  svg.appendChild(el("path", { d: areaPath, fill: "var(--profit-fill)", "clip-path": "url(#clip-above)" }));
  svg.appendChild(el("path", { d: areaPath, fill: "var(--loss-fill)", "clip-path": "url(#clip-below)" }));

  // zero baseline (the reference the eye reads polarity against)
  svg.appendChild(el("line", { x1: M.left, x2: W - M.right, y1: zeroY, y2: zeroY,
    stroke: "var(--baseline)", "stroke-width": 1.5 }));

  // payoff line
  const linePath = "M " + pts.map((p) => `${X(p[0])} ${Y(p[1])}`).join(" L ");
  svg.appendChild(el("path", { d: linePath, fill: "none", stroke: "var(--accent)",
    "stroke-width": 2, "stroke-linejoin": "round" }));

  // breakevens + spot markers (direct labels, muted)
  (data.breakevens || []).forEach((be) => {
    if (be < xMin || be > xMax) return;
    svg.appendChild(el("line", { x1: X(be), x2: X(be), y1: M.top, y2: H - M.bottom,
      stroke: "var(--muted)", "stroke-width": 1, "stroke-dasharray": "4 3" }));
    const t = el("text", { x: X(be) + 4, y: M.top + 12, fill: "var(--muted)", "font-size": 11 });
    t.textContent = `BE $${be.toFixed(2)}`;
    svg.appendChild(t);
  });
  if (data.spot >= xMin && data.spot <= xMax) {
    svg.appendChild(el("line", { x1: X(data.spot), x2: X(data.spot), y1: M.top, y2: H - M.bottom,
      stroke: "var(--ink-2)", "stroke-width": 1, "stroke-dasharray": "2 3" }));
    const t = el("text", { x: X(data.spot) + 4, y: H - M.bottom - 6, fill: "var(--ink-2)", "font-size": 11 });
    t.textContent = `spot $${data.spot.toFixed(2)}`;
    svg.appendChild(t);
  }

  // hover layer: crosshair + tooltip
  const cross = el("line", { y1: M.top, y2: H - M.bottom, stroke: "var(--ink-2)",
    "stroke-width": 1, visibility: "hidden" });
  const dot = el("circle", { r: 4.5, fill: "var(--accent)", stroke: "var(--surface)",
    "stroke-width": 2, visibility: "hidden" });
  svg.appendChild(cross);
  svg.appendChild(dot);

  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip";
  chartEl.appendChild(svg);
  chartEl.appendChild(tooltip);

  svg.addEventListener("mousemove", (ev) => {
    const rect = svg.getBoundingClientRect();
    const px = ((ev.clientX - rect.left) / rect.width) * W;
    if (px < M.left || px > W - M.right) return;
    const price = xMin + ((px - M.left) / iw) * (xMax - xMin);
    let best = pts[0];
    for (const p of pts) if (Math.abs(p[0] - price) < Math.abs(best[0] - price)) best = p;
    const x = X(best[0]), y = Y(best[1]);
    cross.setAttribute("x1", x); cross.setAttribute("x2", x);
    cross.setAttribute("visibility", "visible");
    dot.setAttribute("cx", x); dot.setAttribute("cy", y);
    dot.setAttribute("visibility", "visible");
    tooltip.style.display = "block";
    tooltip.innerHTML =
      `<span style="font-variant-numeric: tabular-nums">$${best[0].toFixed(2)} → ` +
      `<strong class="${best[1] >= 0 ? "pos" : "neg"}">${fmt$(best[1])}</strong></span>`;
    const tx = (x / W) * rect.width, ty = (y / H) * rect.height;
    tooltip.style.left = Math.min(tx + 12, rect.width - 130) + "px";
    tooltip.style.top = Math.max(ty - 36, 0) + "px";
  });
  svg.addEventListener("mouseleave", () => {
    cross.setAttribute("visibility", "hidden");
    dot.setAttribute("visibility", "hidden");
    tooltip.style.display = "none";
  });
})();
