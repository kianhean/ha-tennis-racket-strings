/* Strung (racket_tracker) — Zero-YAML bundled Lovelace cards
 * Registers <strung-racket-card> and <strung-bag-card> with visual editors.
 */

const SESSION_TYPE_LABELS = {
  singles_match: "Singles match",
  doubles_match: "Doubles match",
  practice: "Practice",
  ball_machine: "Ball machine",
};

const SURFACE_LABELS = {
  hard: "Hard",
  clay: "Clay",
  grass: "Grass",
  indoor: "Indoor",
};

const STATUS_META = {
  ready: { label: "Match ready", color: "#16a34a", bg: "rgba(22,163,74,0.12)" },
  practice: { label: "Practice", color: "#d97706", bg: "rgba(217,119,6,0.14)" },
  due: { label: "Restring due", color: "#dc2626", bg: "rgba(220,38,38,0.12)" },
  broken: { label: "Strings broke", color: "#dc2626", bg: "rgba(220,38,38,0.14)" },
  unstrung: { label: "No restrings", color: "#64748b", bg: "rgba(100,116,139,0.12)" },
};

function esc(val) {
  if (val === null || val === undefined) return "";
  return String(val)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtStars(rating) {
  if (!rating) return "";
  const n = Math.max(0, Math.min(5, Number(rating)));
  return "★".repeat(n) + "☆".repeat(5 - n);
}

function freshnessColor(pct) {
  if (pct === null || pct === undefined) return "#94a3b8";
  if (pct >= 70) return "#16a34a";
  if (pct >= 35) return "#d97706";
  return "#dc2626";
}

const SHARED_STYLES = `
  :host {
    display: block;
    font-family: var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif);
    color: var(--primary-text-color);
  }
  ha-card {
    padding: 16px;
    overflow: hidden;
  }
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 14px;
  }
  .title {
    font-size: 18px;
    font-weight: 600;
    margin: 0;
  }
  .muted {
    color: var(--secondary-text-color);
    font-size: 12.5px;
  }
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    font-weight: 600;
    padding: 3px 9px;
    border-radius: 999px;
    white-space: nowrap;
  }
  .btn-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 12px 0;
  }
  button.strung-btn {
    appearance: none;
    border: 1px solid var(--divider-color, rgba(0,0,0,0.14));
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color);
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 12.5px;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    transition: opacity 0.15s;
  }
  button.strung-btn:hover { opacity: 0.85; }
  button.strung-btn.primary {
    background: var(--primary-color, #03a9f4);
    border-color: var(--primary-color, #03a9f4);
    color: var(--text-primary-color, #fff);
  }
  button.strung-btn.danger {
    color: var(--error-color, #dc2626);
    border-color: rgba(220,38,38,0.35);
  }
  button.icon-btn {
    appearance: none;
    border: 1px solid var(--divider-color, rgba(0,0,0,0.12));
    background: transparent;
    color: var(--primary-text-color);
    border-radius: 6px;
    width: 28px;
    height: 28px;
    cursor: pointer;
    font-size: 13px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  button.icon-btn.del { color: var(--error-color, #dc2626); }
  .metrics {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 10px;
    margin: 12px 0;
  }
  .metric {
    background: var(--secondary-background-color, rgba(127,127,127,0.08));
    border-radius: 10px;
    padding: 10px 12px;
  }
  .metric-k {
    font-size: 11px;
    color: var(--secondary-text-color);
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }
  .metric-v {
    font-size: 16px;
    font-weight: 700;
    margin-top: 2px;
  }
  .section-title {
    font-size: 13.5px;
    font-weight: 600;
    margin: 16px 0 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .table-wrap {
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12.5px;
  }
  th {
    text-align: left;
    font-size: 11px;
    color: var(--secondary-text-color);
    padding: 7px 8px;
    border-bottom: 1px solid var(--divider-color, rgba(0,0,0,0.12));
  }
  td {
    padding: 8px;
    border-bottom: 1px solid var(--divider-color, rgba(0,0,0,0.06));
    vertical-align: middle;
  }
  .stars { color: #f59e0b; letter-spacing: 1px; white-space: nowrap; }
  .thumb {
    width: 44px;
    height: 44px;
    object-fit: cover;
    border-radius: 8px;
    display: block;
  }
  .hero-thumb {
    width: 64px;
    height: 64px;
    object-fit: cover;
    border-radius: 10px;
    border: 1px solid var(--divider-color, rgba(0,0,0,0.12));
    flex-shrink: 0;
  }
  .chart-box {
    background: var(--secondary-background-color, rgba(127,127,127,0.06));
    border-radius: 10px;
    padding: 10px;
    margin-top: 8px;
  }
  .modal-bg {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.45);
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
  }
  .modal {
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color);
    border-radius: 14px;
    width: 100%;
    max-width: 440px;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 20px 44px rgba(0,0,0,0.35);
    padding: 18px 20px;
  }
  .modal h3 { margin: 0 0 12px; font-size: 16px; }
  .form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
  .field.full { grid-column: 1 / -1; }
  .field label { font-size: 11.5px; font-weight: 600; color: var(--secondary-text-color); }
  .field input, .field select, .field textarea {
    padding: 8px 10px;
    border-radius: 8px;
    border: 1px solid var(--divider-color, rgba(0,0,0,0.2));
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color);
    font-size: 13.5px;
    font-family: inherit;
  }
  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 14px;
  }
  .error-banner {
    background: rgba(220,38,38,0.12);
    color: var(--error-color, #dc2626);
    padding: 8px 10px;
    border-radius: 8px;
    font-size: 12.5px;
    margin-bottom: 10px;
  }
  .bar-track {
    height: 6px;
    background: var(--divider-color, rgba(127,127,127,0.2));
    border-radius: 999px;
    overflow: hidden;
    margin: 6px 0;
  }
  .bag-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 12px;
    margin-top: 8px;
  }
  .racket-tile {
    border: 1px solid var(--divider-color, rgba(0,0,0,0.12));
    border-radius: 12px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .racket-tile.due { border-color: rgba(220,38,38,0.45); }
`;

class StrungRacketCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("strung-racket-card-editor");
  }

  static getStubConfig() {
    return { config_entry_id: "", show_chart: true, show_history: true, show_sessions: true };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._data = null;
    this._strings = [];
    this._modal = null;
    this._error = null;
    this._lastStateHash = null;
    this._loading = false;
  }

  setConfig(config) {
    this._config = {
      show_chart: true,
      show_history: true,
      show_sessions: true,
      ...config,
    };
    this._data = null;
    this._load();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    const hash = this._stateHash(hass);
    if (first || hash !== this._lastStateHash) {
      this._lastStateHash = hash;
      this._load();
    }
  }

  _stateHash(hass) {
    if (!hass || !hass.states) return "";
    return Object.keys(hass.states)
      .filter((k) => k.endsWith("_restrings") || k.endsWith("_hours_played") || k.endsWith("_estimated_tension"))
      .map((k) => `${k}:${hass.states[k].last_updated}`)
      .join("|");
  }

  getCardSize() {
    return 6;
  }

  async _load() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      let entryId = this._config.config_entry_id;
      if (!entryId) {
        const bag = await this._hass.callWS({ type: "racket_tracker/bag" });
        if (bag.rackets && bag.rackets.length > 0) {
          entryId = bag.rackets[0].config_entry_id;
        }
      }
      if (!entryId) {
        this._data = { empty: true };
      } else {
        this._data = await this._hass.callWS({
          type: "racket_tracker/racket",
          config_entry_id: entryId,
        });
        if (this._strings.length === 0) {
          const res = await this._hass.callWS({ type: "racket_tracker/strings" });
          this._strings = res.strings || [];
        }
      }
      this._error = null;
    } catch (err) {
      this._error = err?.message || "Failed to load racket data";
    } finally {
      this._loading = false;
      this._render();
    }
  }

  async _callService(service, data) {
    try {
      await this._hass.callService("racket_tracker", service, data);
      this._modal = null;
      this._error = null;
      await this._load();
    } catch (err) {
      this._error = err?.message || `Action ${service} failed`;
      this._render();
    }
  }

  _renderChart(restrings, calibrations, unit) {
    const ordered = [...restrings].reverse();
    if (ordered.length === 0) return "";
    const points = ordered
      .filter((r) => r.main_tension != null)
      .map((r) => ({ date: r.date, tension: Number(r.main_tension) }));
    if (points.length === 0) return "";

    const allTensions = [
      ...points.map((p) => p.tension),
      ...calibrations.map((c) => Number(c.tension)),
    ];
    const minT = Math.floor(Math.min(...allTensions) - 3);
    const maxT = Math.ceil(Math.max(...allTensions) + 2);
    const spanT = Math.max(maxT - minT, 4);

    const dates = [
      ...points.map((p) => Date.parse(p.date)),
      ...calibrations.map((c) => Date.parse(c.date)),
      Date.now(),
    ].filter((d) => !Number.isNaN(d));
    const minD = Math.min(...dates);
    const maxD = Math.max(...dates, minD + 86400000);
    const spanD = Math.max(maxD - minD, 86400000);

    const W = 460;
    const H = 140;
    const padL = 36;
    const padR = 12;
    const padT = 12;
    const padB = 22;
    const xOf = (ts) => padL + ((ts - minD) / spanD) * (W - padL - padR);
    const yOf = (t) => padT + ((maxT - t) / spanT) * (H - padT - padB);

    // Step polyline for strung tension
    const stepCoords = [];
    for (let i = 0; i < points.length; i++) {
      const x = xOf(Date.parse(points[i].date));
      const y = yOf(points[i].tension);
      if (i > 0) stepCoords.push(`${x.toFixed(1)},${yOf(points[i - 1].tension).toFixed(1)}`);
      stepCoords.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }
    const lastPt = points[points.length - 1];
    stepCoords.push(`${xOf(Date.now()).toFixed(1)},${yOf(lastPt.tension).toFixed(1)}`);

    const calDots = calibrations
      .filter((c) => c.date && c.tension != null)
      .map((c) => {
        const cx = xOf(Date.parse(c.date)).toFixed(1);
        const cy = yOf(Number(c.tension)).toFixed(1);
        const title = `${c.date}: ${c.tension} ${unit}${c.tool ? ` (${c.tool})` : ""}`;
        return `<circle cx="${cx}" cy="${cy}" r="4.5" fill="#0d9488" stroke="#fff" stroke-width="1.5"><title>${esc(title)}</title></circle>`;
      })
      .join("");

    return `
      <div class="section-title">
        <span>Tension &amp; Calibrations</span>
        <span class="muted">${calibrations.length} measured</span>
      </div>
      <div class="chart-box">
        <svg viewBox="0 0 ${W} ${H}" width="100%" height="140">
          <line x1="${padL}" y1="${padT}" x2="${W - padR}" y2="${padT}" stroke="var(--divider-color, #e0e0e0)" stroke-dasharray="2 3"/>
          <line x1="${padL}" y1="${H - padB}" x2="${W - padR}" y2="${H - padB}" stroke="var(--divider-color, #e0e0e0)"/>
          <text x="${padL - 5}" y="${padT + 4}" text-anchor="end" font-size="10" fill="var(--secondary-text-color)">${maxT}</text>
          <text x="${padL - 5}" y="${H - padB}" text-anchor="end" font-size="10" fill="var(--secondary-text-color)">${minT}</text>
          <polyline fill="none" stroke="var(--primary-color, #03a9f4)" stroke-width="2" points="${stepCoords.join(" ")}"/>
          ${calDots}
        </svg>
        <div class="muted" style="display:flex;gap:14px;justify-content:center;font-size:11px">
          <span><span style="color:var(--primary-color,#03a9f4)">━</span> Strung (${esc(unit)})</span>
          <span><span style="color:#0d9488">●</span> Measured calibration</span>
        </div>
      </div>
    `;
  }

  _renderModal() {
    if (!this._modal || !this._data?.racket) return "";
    const r = this._data.racket;
    const unit = this._data.tension_unit || "lbs";
    const { type, item } = this._modal;
    const datalist = `<datalist id="strung-catalog">${this._strings
      .slice(0, 1200)
      .map((s) => `<option value="${esc(s)}"></option>`)
      .join("")}</datalist>`;

    if (type === "add_restring" || type === "edit_restring") {
      const rec = item || {};
      const title = type === "edit_restring" ? "Edit Restring" : "Log Restring";
      return `
        <div class="modal-bg" data-close="1">
          <div class="modal">
            <h3>${title} — ${esc(r.name)}</h3>
            ${this._error ? `<div class="error-banner">${esc(this._error)}</div>` : ""}
            ${datalist}
            <form id="modal-form">
              <div class="form-grid">
                <div class="field full">
                  <label>Main string *</label>
                  <input name="main_string" list="strung-catalog" required value="${esc(rec.main_string || "")}" placeholder="e.g. Solinco Hyper-G 1.25">
                </div>
                <div class="field">
                  <label>Main tension (${esc(unit)}) *</label>
                  <input name="main_tension" type="number" step="0.5" min="1" max="100" required value="${esc(rec.main_tension ?? (unit === "kg" ? 23 : 52))}">
                </div>
                <div class="field">
                  <label>Date</label>
                  <input name="date" type="date" value="${esc(rec.date || new Date().toISOString().slice(0, 10))}">
                </div>
                <div class="field">
                  <label>Cross string (hybrid)</label>
                  <input name="cross_string" list="strung-catalog" value="${esc(rec.cross_string && rec.cross_string !== rec.main_string ? rec.cross_string : "")}">
                </div>
                <div class="field">
                  <label>Cross tension (${esc(unit)})</label>
                  <input name="cross_tension" type="number" step="0.5" min="1" max="100" value="${esc(rec.cross_tension && rec.cross_tension !== rec.main_tension ? rec.cross_tension : "")}">
                </div>
                <div class="field">
                  <label>Cost (${esc(this._data.currency || "")})</label>
                  <input name="cost" type="number" step="0.01" min="0" value="${esc(rec.cost ?? "")}">
                </div>
                <div class="field">
                  <label>Stringer</label>
                  <input name="stringer" value="${esc(rec.stringer || "")}">
                </div>
                <div class="field full">
                  <label>Rating (1–5)</label>
                  <input name="rating" type="number" min="1" max="5" step="1" value="${esc(rec.rating ?? "")}">
                </div>
                <div class="field full">
                  <label>Notes</label>
                  <textarea name="notes" rows="2">${esc(rec.notes || "")}</textarea>
                </div>
              </div>
              <div class="modal-actions">
                <button type="button" class="strung-btn" data-close="1">Cancel</button>
                <button type="submit" class="strung-btn primary">Save</button>
              </div>
            </form>
          </div>
        </div>
      `;
    }

    if (type === "rate") {
      const latest = this._data.restrings[0] || {};
      return `
        <div class="modal-bg" data-close="1">
          <div class="modal">
            <h3>Rate Current Strings — ${esc(r.name)}</h3>
            ${this._error ? `<div class="error-banner">${esc(this._error)}</div>` : ""}
            <form id="modal-form">
              <div class="field">
                <label>Rating (1–5)</label>
                <input name="rating" type="number" min="1" max="5" required value="${esc(latest.rating || 4)}">
              </div>
              <div class="field">
                <label>Notes</label>
                <textarea name="notes" rows="3">${esc(latest.notes || "")}</textarea>
              </div>
              <div class="modal-actions">
                <button type="button" class="strung-btn" data-close="1">Cancel</button>
                <button type="submit" class="strung-btn primary">Save Rating</button>
              </div>
            </form>
          </div>
        </div>
      `;
    }

    if (type === "log_play" || type === "edit_play") {
      const sess = item || {};
      const title = type === "edit_play" ? "Edit Play Session" : "Log Play Session";
      return `
        <div class="modal-bg" data-close="1">
          <div class="modal">
            <h3>${title} — ${esc(r.name)}</h3>
            ${this._error ? `<div class="error-banner">${esc(this._error)}</div>` : ""}
            <form id="modal-form">
              <div class="form-grid">
                <div class="field">
                  <label>Hours *</label>
                  <input name="hours" type="number" step="0.25" min="0.1" max="24" required value="${esc(sess.hours ?? r.session_hours ?? 1.5)}">
                </div>
                <div class="field">
                  <label>Date</label>
                  <input name="date" type="date" value="${esc(sess.date || new Date().toISOString().slice(0, 10))}">
                </div>
                <div class="field">
                  <label>Session type</label>
                  <select name="session_type">
                    <option value="">—</option>
                    ${Object.entries(SESSION_TYPE_LABELS)
                      .map(([k, v]) => `<option value="${k}" ${sess.session_type === k ? "selected" : ""}>${v}</option>`)
                      .join("")}
                  </select>
                </div>
                <div class="field">
                  <label>Surface</label>
                  <select name="surface">
                    <option value="">—</option>
                    ${Object.entries(SURFACE_LABELS)
                      .map(([k, v]) => `<option value="${k}" ${sess.surface === k ? "selected" : ""}>${v}</option>`)
                      .join("")}
                  </select>
                </div>
                <div class="field full">
                  <label>Notes</label>
                  <input name="notes" value="${esc(sess.notes || "")}" placeholder="Optional">
                </div>
              </div>
              <div class="modal-actions">
                <button type="button" class="strung-btn" data-close="1">Cancel</button>
                <button type="submit" class="strung-btn primary">Save</button>
              </div>
            </form>
          </div>
        </div>
      `;
    }

    if (type === "calibrate") {
      return `
        <div class="modal-bg" data-close="1">
          <div class="modal">
            <h3>Calibrate Tension — ${esc(r.name)}</h3>
            ${this._error ? `<div class="error-banner">${esc(this._error)}</div>` : ""}
            <form id="modal-form">
              <div class="form-grid">
                <div class="field">
                  <label>Measured mains (${esc(unit)}) *</label>
                  <input name="tension" type="number" step="0.1" min="1" max="100" required value="${esc(r.estimated_tension ?? "")}">
                </div>
                <div class="field">
                  <label>Date</label>
                  <input name="date" type="date" value="${new Date().toISOString().slice(0, 10)}">
                </div>
                <div class="field full">
                  <label>Tool / meter</label>
                  <input name="tool" placeholder="e.g. ERT 300, RacquetTune">
                </div>
              </div>
              <div class="modal-actions">
                <button type="button" class="strung-btn" data-close="1">Cancel</button>
                <button type="submit" class="strung-btn primary">Calibrate</button>
              </div>
            </form>
          </div>
        </div>
      `;
    }
    return "";
  }

  _bindEvents() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-action]").forEach((el) => {
      el.addEventListener("click", async () => {
        const act = el.dataset.action;
        const entryId = this._data.racket.config_entry_id;
        if (act === "add_restring") {
          this._modal = { type: "add_restring" };
          this._error = null;
          this._render();
        } else if (act === "usual_setup") {
          if (confirm(`Log usual setup for ${this._data.racket.name} today?`)) {
            await this._callService("repeat_restring", { config_entry_id: entryId });
          }
        } else if (act === "rate") {
          this._modal = { type: "rate" };
          this._error = null;
          this._render();
        } else if (act === "log_play") {
          this._modal = { type: "log_play" };
          this._error = null;
          this._render();
        } else if (act === "calibrate") {
          this._modal = { type: "calibrate" };
          this._error = null;
          this._render();
        } else if (act === "broke") {
          if (confirm("Mark the current strings as broken today?")) {
            await this._callService("update_restring", { config_entry_id: entryId, broken: true });
          }
        } else if (act === "edit_restring") {
          const item = this._data.restrings.find((x) => x.id === el.dataset.id);
          this._modal = { type: "edit_restring", item };
          this._error = null;
          this._render();
        } else if (act === "delete_restring") {
          if (confirm("Delete this restring?")) {
            await this._callService("delete_restring", {
              config_entry_id: entryId,
              restring_id: el.dataset.id,
            });
          }
        } else if (act === "edit_play") {
          const item = this._data.play_sessions.find((x) => x.id === el.dataset.id);
          this._modal = { type: "edit_play", item };
          this._error = null;
          this._render();
        } else if (act === "delete_play") {
          if (confirm("Delete this play session?")) {
            await this._callService("delete_play", {
              config_entry_id: entryId,
              session_id: el.dataset.id,
            });
          }
        }
      });
    });

    root.querySelectorAll("[data-close]").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (e.target === el) {
          this._modal = null;
          this._error = null;
          this._render();
        }
      });
    });

    const form = root.querySelector("#modal-form");
    if (form) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const fd = new FormData(form);
        const entryId = this._data.racket.config_entry_id;
        const { type, item } = this._modal;

        if (type === "add_restring" || type === "edit_restring") {
          const payload = {
            config_entry_id: entryId,
            main_string: fd.get("main_string").trim(),
            main_tension: Number(fd.get("main_tension")),
          };
          if (type === "edit_restring") payload.restring_id = item.id;
          if (fd.get("date")) payload.date = fd.get("date");
          if (fd.get("cross_string")) payload.cross_string = fd.get("cross_string").trim();
          if (fd.get("cross_tension")) payload.cross_tension = Number(fd.get("cross_tension"));
          if (fd.get("cost") !== "") payload.cost = Number(fd.get("cost"));
          if (fd.get("stringer")) payload.stringer = fd.get("stringer").trim();
          if (fd.get("rating")) payload.rating = Number(fd.get("rating"));
          if (fd.get("notes")) payload.notes = fd.get("notes").trim();
          await this._callService(type === "edit_restring" ? "update_restring" : "add_restring", payload);
        } else if (type === "rate") {
          const payload = { config_entry_id: entryId, rating: Number(fd.get("rating")) };
          if (fd.get("notes")) payload.notes = fd.get("notes").trim();
          await this._callService("update_restring", payload);
        } else if (type === "log_play" || type === "edit_play") {
          const payload = { config_entry_id: entryId, hours: Number(fd.get("hours")) };
          if (type === "edit_play") payload.session_id = item.id;
          if (fd.get("date")) payload.date = fd.get("date");
          if (fd.get("session_type")) payload.session_type = fd.get("session_type");
          if (fd.get("surface")) payload.surface = fd.get("surface");
          if (fd.get("notes")) payload.notes = fd.get("notes").trim();
          await this._callService(type === "edit_play" ? "update_play" : "log_play", payload);
        } else if (type === "calibrate") {
          const payload = { config_entry_id: entryId, tension: Number(fd.get("tension")) };
          if (fd.get("date")) payload.date = fd.get("date");
          if (fd.get("tool")) payload.tool = fd.get("tool").trim();
          await this._callService("calibrate_tension", payload);
        }
      });
    }
  }

  _render() {
    if (!this._data) {
      this.shadowRoot.innerHTML = `<style>${SHARED_STYLES}</style><ha-card><div class="muted">Loading racket…</div></ha-card>`;
      return;
    }
    if (this._data.empty) {
      this.shadowRoot.innerHTML = `<style>${SHARED_STYLES}</style><ha-card><div class="muted">Add a racket under Settings → Devices &amp; services → Strung.</div></ha-card>`;
      return;
    }

    const r = this._data.racket;
    const unit = this._data.tension_unit || "lbs";
    const cur = this._data.currency || "";
    const status = STATUS_META[r.status] || STATUS_META.unstrung;
    const fresh = r.freshness;
    const dash = fresh != null ? Math.round((fresh / 100) * 163.4) : 0;
    const fCol = freshnessColor(fresh);
    const tensionStr =
      r.main_tension != null
        ? `${r.main_tension}${r.cross_tension && r.cross_tension !== r.main_tension ? `/${r.cross_tension}` : ""} ${unit}`
        : "—";

    const historyRows = (this._data.restrings || [])
      .map(
        (rec) => `
      <tr>
        <td>${rec.image_url ? `<img class="thumb" src="${esc(rec.image_url)}">` : ""}</td>
        <td><strong>${esc(rec.date)}</strong></td>
        <td>${esc(rec.main_string)}${rec.cross_string && rec.cross_string !== rec.main_string ? ` / ${esc(rec.cross_string)}` : ""}</td>
        <td>${esc(rec.main_tension)}${rec.cross_tension && rec.cross_tension !== rec.main_tension ? `/${esc(rec.cross_tension)}` : ""} ${esc(rec.tension_unit || unit)}</td>
        <td>${rec.cost != null ? `${esc(rec.cost)} ${esc(cur)}` : ""}</td>
        <td class="stars">${fmtStars(rec.rating)}</td>
        <td>${esc(rec.notes || "")}${rec.broken_date ? ` <span class="muted">(broke ${esc(rec.broken_date)})</span>` : ""}</td>
        <td style="white-space:nowrap;text-align:right">
          <button class="icon-btn" title="Edit" data-action="edit_restring" data-id="${esc(rec.id)}">✏️</button>
          <button class="icon-btn del" title="Delete" data-action="delete_restring" data-id="${esc(rec.id)}">🗑️</button>
        </td>
      </tr>`
      )
      .join("");

    const sessionRows = (this._data.play_sessions || [])
      .slice(0, 10)
      .map(
        (s) => `
      <tr>
        <td>${esc(s.date)}</td>
        <td><strong>${esc(s.hours)} h</strong></td>
        <td>${esc(SESSION_TYPE_LABELS[s.session_type] || "—")}</td>
        <td>${esc(SURFACE_LABELS[s.surface] || "—")}</td>
        <td>${esc(s.notes || "")}</td>
        <td style="white-space:nowrap;text-align:right">
          <button class="icon-btn" title="Edit" data-action="edit_play" data-id="${esc(s.id)}">✏️</button>
          <button class="icon-btn del" title="Delete" data-action="delete_play" data-id="${esc(s.id)}">🗑️</button>
        </td>
      </tr>`
      )
      .join("");

    this.shadowRoot.innerHTML = `
      <style>${SHARED_STYLES}</style>
      <ha-card>
        ${this._error && !this._modal ? `<div class="error-banner">${esc(this._error)}</div>` : ""}
        <div class="header">
          <div style="display:flex;align-items:center;gap:12px">
            ${r.image_url ? `<img class="hero-thumb" src="${esc(r.image_url)}">` : ""}
            <div>
              <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                <h2 class="title">${esc(r.name)}</h2>
                <span class="pill" style="color:${status.color};background:${status.bg}">${esc(status.label)}</span>
              </div>
              <div style="font-weight:600;color:var(--primary-color,#03a9f4);margin-top:2px">
                ${r.strings ? `${esc(r.strings)} @ ${esc(tensionStr)}` : "No restrings logged yet"}
              </div>
              <div class="muted">
                ${r.last_restrung ? `Strung ${esc(r.last_restrung)} (${esc(r.days_since)} d ago)` : ""}
                ${r.rating ? ` · <span class="stars">${fmtStars(r.rating)}</span>` : ""}
              </div>
            </div>
          </div>
          ${
            fresh != null
              ? `<svg width="62" height="62" viewBox="0 0 62 62" style="flex-shrink:0">
                  <circle cx="31" cy="31" r="26" fill="none" stroke="var(--divider-color,#e0e0e0)" stroke-width="6"/>
                  <circle cx="31" cy="31" r="26" fill="none" stroke="${fCol}" stroke-width="6"
                    stroke-dasharray="${dash} 163.4" stroke-linecap="round" transform="rotate(-90 31 31)"/>
                  <text x="31" y="35" text-anchor="middle" font-size="14" font-weight="700" fill="${fCol}">${fresh}%</text>
                </svg>`
              : ""
          }
        </div>

        <div class="metrics">
          ${
            r.estimated_tension != null
              ? `<div class="metric"><div class="metric-k">Est. Tension</div><div class="metric-v">${esc(r.estimated_tension)} ${esc(unit)}</div><div class="muted">-${Math.round(r.estimated_tension_loss || 0)}%</div></div>`
              : ""
          }
          ${
            r.hours_played != null
              ? `<div class="metric"><div class="metric-k">Played</div><div class="metric-v">${esc(r.hours_played)} h</div><div class="muted">${r.tracking === "logged" ? "Logged" : "Weekly est."}</div></div>`
              : ""
          }
          ${
            r.due_date
              ? `<div class="metric"><div class="metric-k">Next Restring</div><div class="metric-v">${esc(r.due_date)}</div><div class="muted">${r.days_until_due < 0 ? `${Math.abs(r.days_until_due)} d overdue` : `in ${r.days_until_due} d`}</div></div>`
              : ""
          }
          <div class="metric"><div class="metric-k">Restrings</div><div class="metric-v">${esc(r.restring_count)}</div><div class="muted">${esc(r.total_cost)} ${esc(cur)} total</div></div>
        </div>

        <div class="btn-row">
          <button class="strung-btn primary" data-action="add_restring">＋ Log Restring</button>
          <button class="strung-btn" data-action="usual_setup">🔁 Usual Setup</button>
          ${r.restring_count > 0 ? `<button class="strung-btn" data-action="rate">⭐ Rate</button>` : ""}
          ${r.tracking === "logged" ? `<button class="strung-btn" data-action="log_play">🎾 Log Play</button>` : ""}
          ${r.estimated_tension != null ? `<button class="strung-btn" data-action="calibrate">📏 Calibrate</button>` : ""}
          ${r.restring_count > 0 && !r.broken_date ? `<button class="strung-btn danger" data-action="broke">💥 Broke</button>` : ""}
        </div>

        ${this._config.show_chart ? this._renderChart(this._data.restrings || [], this._data.calibrations || [], unit) : ""}

        ${
          this._config.show_history
            ? `<div class="section-title"><span>Restring History</span><span class="muted">${(this._data.restrings || []).length} total</span></div>
               ${
                 historyRows
                   ? `<div class="table-wrap"><table><thead><tr><th></th><th>Date</th><th>Strings</th><th>Tension</th><th>Cost</th><th>Rating</th><th>Notes</th><th></th></tr></thead><tbody>${historyRows}</tbody></table></div>`
                   : `<div class="muted">No restrings logged yet.</div>`
               }`
            : ""
        }

        ${
          this._config.show_sessions && sessionRows
            ? `<div class="section-title"><span>Recent Play Sessions</span><span class="muted">${(this._data.play_sessions || []).length} logged</span></div>
               <div class="table-wrap"><table><thead><tr><th>Date</th><th>Hours</th><th>Type</th><th>Surface</th><th>Notes</th><th></th></tr></thead><tbody>${sessionRows}</tbody></table></div>`
            : ""
        }
      </ha-card>
      ${this._renderModal()}
    `;
    this._bindEvents();
  }
}

class StrungRacketCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._rackets = [];
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._loadRackets();
  }

  async _loadRackets() {
    try {
      const bag = await this._hass.callWS({ type: "racket_tracker/bag" });
      this._rackets = bag.rackets || [];
      this._render();
    } catch {
      /* ignore */
    }
  }

  _emit() {
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      })
    );
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>${SHARED_STYLES}</style>
      <div class="field">
        <label>Racket</label>
        <select id="racket-sel">
          <option value="">First available racket</option>
          ${this._rackets
            .map(
              (r) =>
                `<option value="${esc(r.config_entry_id)}" ${this._config.config_entry_id === r.config_entry_id ? "selected" : ""}>${esc(r.name)}</option>`
            )
            .join("")}
        </select>
      </div>
      <label style="display:flex;align-items:center;gap:8px;margin:8px 0;font-size:13px">
        <input type="checkbox" id="show-chart" ${this._config.show_chart !== false ? "checked" : ""}> Show tension &amp; calibration chart
      </label>
      <label style="display:flex;align-items:center;gap:8px;margin:8px 0;font-size:13px">
        <input type="checkbox" id="show-history" ${this._config.show_history !== false ? "checked" : ""}> Show restring history table
      </label>
      <label style="display:flex;align-items:center;gap:8px;margin:8px 0;font-size:13px">
        <input type="checkbox" id="show-sessions" ${this._config.show_sessions !== false ? "checked" : ""}> Show recent play sessions
      </label>
    `;
    this.shadowRoot.querySelector("#racket-sel").addEventListener("change", (e) => {
      this._config = { ...this._config, config_entry_id: e.target.value };
      this._emit();
    });
    for (const [id, key] of [
      ["#show-chart", "show_chart"],
      ["#show-history", "show_history"],
      ["#show-sessions", "show_sessions"],
    ]) {
      this.shadowRoot.querySelector(id).addEventListener("change", (e) => {
        this._config = { ...this._config, [key]: e.target.checked };
        this._emit();
      });
    }
  }
}

class StrungBagCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("strung-bag-card-editor");
  }

  static getStubConfig() {
    return { title: "Tennis Bag", show_kpis: true, show_readiness: true, show_comparison: true };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._bag = null;
    this._lastStateHash = null;
    this._loading = false;
  }

  setConfig(config) {
    this._config = {
      title: "Tennis Bag",
      show_kpis: true,
      show_readiness: true,
      show_comparison: true,
      ...config,
    };
    this._load();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    const hash = Object.keys(hass?.states || {})
      .filter((k) => k.endsWith("_restrings") || k.endsWith("_hours_played") || k.endsWith("_restring_due"))
      .map((k) => `${k}:${hass.states[k].last_updated}`)
      .join("|");
    if (first || hash !== this._lastStateHash) {
      this._lastStateHash = hash;
      this._load();
    }
  }

  getCardSize() {
    return 6;
  }

  async _load() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      this._bag = await this._hass.callWS({ type: "racket_tracker/bag" });
    } catch {
      this._bag = null;
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _render() {
    if (!this._bag) {
      this.shadowRoot.innerHTML = `<style>${SHARED_STYLES}</style><ha-card><div class="muted">Loading tennis bag…</div></ha-card>`;
      return;
    }
    const t = this._bag.totals;
    const cur = this._bag.currency || "";

    const kpis = this._config.show_kpis
      ? `<div class="metrics">
          <div class="metric"><div class="metric-k">Play Time (30d)</div><div class="metric-v">${esc(t.hours_last_30d)} h</div></div>
          <div class="metric"><div class="metric-k">Spend (${new Date().getFullYear()})</div><div class="metric-v">${esc(t.cost_this_year)} ${esc(cur)}</div><div class="muted">${esc(t.restrings_this_year)} restrings</div></div>
          <div class="metric"><div class="metric-k">Bag Cost / Hour</div><div class="metric-v">${t.cost_per_hour != null ? `${esc(t.cost_per_hour)} ${esc(cur)}/h` : "—"}</div></div>
          <div class="metric"><div class="metric-k">Match Ready</div><div class="metric-v">${esc(t.ready_count)} / ${esc(t.racket_count)}</div><div class="muted">${t.due_count ? `${t.due_count} due` : "All good"}</div></div>
        </div>`
      : "";

    const readiness = this._config.show_readiness
      ? `<div class="section-title"><span>Grab a Racket — Bag Readiness</span><span class="muted">Ranked by freshness</span></div>
         <div class="bag-grid">
           ${this._bag.rackets
             .map((r) => {
               const st = STATUS_META[r.status] || STATUS_META.unstrung;
               const pct = r.freshness ?? 0;
               const col = freshnessColor(r.freshness);
               return `
                 <div class="racket-tile ${r.status === "due" || r.status === "broken" ? "due" : ""}">
                   <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
                     <div>
                       <div style="font-weight:700;font-size:15px">${esc(r.name)}</div>
                       <div class="muted">${esc([r.brand, r.model].filter(Boolean).join(" ") || "Tennis racket")}</div>
                     </div>
                     <span class="pill" style="color:${st.color};background:${st.bg}">${esc(st.label)}${r.freshness != null ? ` · ${r.freshness}%` : ""}</span>
                   </div>
                   <div style="font-size:13px;font-weight:600;color:var(--primary-color,#03a9f4)">${esc(r.strings || "No restrings yet")}</div>
                   <div class="bar-track"><div style="width:${pct}%;height:100%;background:${col}"></div></div>
                   <div class="muted" style="display:flex;justify-content:space-between">
                     <span>${r.estimated_tension != null ? `Est. ${r.estimated_tension} ${r.tension_unit}` : r.main_tension != null ? `Strung ${r.main_tension} ${r.tension_unit}` : "—"}</span>
                     <span>${r.hours_played != null ? `${r.hours_played} h played` : r.days_since != null ? `${r.days_since} d old` : ""}</span>
                   </div>
                   <div class="btn-row" style="margin:4px 0 0">
                     ${
                       r.tracking === "logged"
                         ? `<button class="strung-btn primary" data-play="${esc(r.config_entry_id)}" data-hours="${esc(r.session_hours)}">+${esc(r.session_hours)}h Play</button>`
                         : ""
                     }
                     <button class="strung-btn" data-usual="${esc(r.config_entry_id)}" data-name="${esc(r.name)}">Usual Setup</button>
                   </div>
                 </div>`;
             })
             .join("")}
         </div>`
      : "";

    const comparison =
      this._config.show_comparison && this._bag.setups.length > 0
        ? `<div class="section-title"><span>String Setup Showdown</span><span class="muted">Across all rackets</span></div>
           <div class="table-wrap">
             <table>
               <thead><tr><th>Setup</th><th>Jobs</th><th>Avg Rating</th><th>Avg Life</th><th>Break Rate</th><th>Cost / Hr</th></tr></thead>
               <tbody>
                 ${this._bag.setups
                   .map(
                     (s) => `
                   <tr>
                     <td><strong>${esc(s.setup)}</strong></td>
                     <td>${esc(s.jobs)}</td>
                     <td class="stars">${s.average_rating != null ? `${esc(s.average_rating)} ★ <span class="muted">(${esc(s.ratings)})</span>` : "—"}</td>
                     <td>${s.average_life_hours != null ? `${esc(s.average_life_hours)} h` : ""}${s.average_life_days != null ? ` <span class="muted">(${esc(s.average_life_days)} d)</span>` : s.average_life_hours == null ? "—" : ""}</td>
                     <td>${s.breakage_rate != null ? `${esc(s.breakage_rate)}%` : "—"}</td>
                     <td>${s.cost_per_hour != null ? `${esc(s.cost_per_hour)} ${esc(cur)}/h` : "—"}</td>
                   </tr>`
                   )
                   .join("")}
               </tbody>
             </table>
           </div>`
        : "";

    this.shadowRoot.innerHTML = `
      <style>${SHARED_STYLES}</style>
      <ha-card>
        <div class="header">
          <h2 class="title">${esc(this._config.title || "Tennis Bag")}</h2>
          <span class="muted">${esc(t.racket_count)} rackets · ${esc(t.restrings_total)} restrings</span>
        </div>
        ${kpis}
        ${readiness}
        ${comparison}
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll("[data-play]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await this._hass.callService("racket_tracker", "log_play", {
          config_entry_id: btn.dataset.play,
          hours: Number(btn.dataset.hours || 1.5),
        });
        await this._load();
      });
    });
    this.shadowRoot.querySelectorAll("[data-usual]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (confirm(`Log usual setup for ${btn.dataset.name} today?`)) {
          await this._hass.callService("racket_tracker", "repeat_restring", {
            config_entry_id: btn.dataset.usual,
          });
          await this._load();
        }
      });
    });
  }
}

class StrungBagCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  _emit() {
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      })
    );
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>${SHARED_STYLES}</style>
      <div class="field">
        <label>Title</label>
        <input id="title-in" value="${esc(this._config.title || "Tennis Bag")}">
      </div>
      <label style="display:flex;align-items:center;gap:8px;margin:8px 0;font-size:13px">
        <input type="checkbox" id="show-kpis" ${this._config.show_kpis !== false ? "checked" : ""}> Show bag KPIs
      </label>
      <label style="display:flex;align-items:center;gap:8px;margin:8px 0;font-size:13px">
        <input type="checkbox" id="show-readiness" ${this._config.show_readiness !== false ? "checked" : ""}> Show Grab a Racket readiness cards
      </label>
      <label style="display:flex;align-items:center;gap:8px;margin:8px 0;font-size:13px">
        <input type="checkbox" id="show-comparison" ${this._config.show_comparison !== false ? "checked" : ""}> Show String Setup Showdown table
      </label>
    `;
    this.shadowRoot.querySelector("#title-in").addEventListener("input", (e) => {
      this._config = { ...this._config, title: e.target.value };
      this._emit();
    });
    for (const [id, key] of [
      ["#show-kpis", "show_kpis"],
      ["#show-readiness", "show_readiness"],
      ["#show-comparison", "show_comparison"],
    ]) {
      this.shadowRoot.querySelector(id).addEventListener("change", (e) => {
        this._config = { ...this._config, [key]: e.target.checked };
        this._emit();
      });
    }
  }
}

if (!customElements.get("strung-racket-card")) {
  customElements.define("strung-racket-card", StrungRacketCard);
}
if (!customElements.get("strung-racket-card-editor")) {
  customElements.define("strung-racket-card-editor", StrungRacketCardEditor);
}
if (!customElements.get("strung-bag-card")) {
  customElements.define("strung-bag-card", StrungBagCard);
}
if (!customElements.get("strung-bag-card-editor")) {
  customElements.define("strung-bag-card-editor", StrungBagCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "strung-racket-card")) {
  window.customCards.push({
    type: "strung-racket-card",
    name: "Strung: Racket Card",
    description: "Zero-YAML card for a tennis racket with freshness gauge, calibration chart, and inline Log/Edit/Delete modals.",
    preview: true,
  });
}
if (!window.customCards.some((c) => c.type === "strung-bag-card")) {
  window.customCards.push({
    type: "strung-bag-card",
    name: "Strung: Bag Overview & String Showdown",
    description: "Cross-racket readiness ranking, bag KPIs, and string setup comparison table.",
    preview: true,
  });
}
