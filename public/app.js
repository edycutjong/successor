// Successor board: streams /api/lookup (NDJSON) and renders the trace, lamps, verdict and receipt.
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const usd = (n) => n == null ? "—" : "$" + (n >= 100 ? n.toLocaleString("en-US", { maximumFractionDigits: 0 }) : n.toLocaleString("en-US", { maximumFractionDigits: 2 }));
const short = (a) => (a && a.length > 16 ? a.slice(0, 6) + "…" + a.slice(-4) : a);
const WORD = { SWAP: "SWAP", SELL_OLD: "SELL OLD", WRITE_OFF: "WRITE OFF", NOT_VERIFIABLE: "NOT VERIFIABLE", NOTHING_TO_DO: "NOTHING TO DO" };
const STEP = {
  resolve: "resolve coin (map)", notice: "read notice (info aux=notice)", reader: "agent", follow_link: "follow link",
  proposal: "agent proposes", successor: "verify successor (C2)", refute: "refute → back to the agent", repair: "repair",
  market_old: "old market (market-pairs, quotes)", market_new: "successor market", ratio: "ratio (C4)",
};
let state = { final: null, events: [], q: "CPOOL", id: 12573, ctrl: null, ticking: null };

function flaps(el, text, cls) {
  const chars = [...String(text || "").toUpperCase()].slice(0, 15);
  el.className = "flaps" + (cls ? " " + cls : "");
  el.innerHTML = "";
  chars.forEach((c, i) => {
    const t = document.createElement("span");
    t.className = "flap";
    t.textContent = c === " " ? " " : c;
    el.appendChild(t);
    setTimeout(() => t.classList.add("turn"), i * 45);
  });
}

function trace(t, text, cls = "") {
  const li = document.createElement("li");
  li.innerHTML = `<span class="t">${(t / 1000).toFixed(1)}s</span><span class="${cls}">${text}</span>`;
  $("trace").appendChild(li);
}

function markText(html, quote, cls, field) {
  // highlight the first occurrence of a quote in text segments only, never inside a tag
  const parts = html.split(/(<[^>]+>)/);
  for (let i = 0; i < parts.length; i += 2) {
    const k = parts[i].indexOf(quote);
    if (k >= 0) {
      parts[i] = parts[i].slice(0, k) + `<mark class="${cls}" title="${esc(field)}">${quote}</mark>` + parts[i].slice(k + quote.length);
      return parts.join("");
    }
  }
  return html;
}

function noticeHtml(notice, quotes, states) {
  let html = esc(notice).replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, (_m, label, url) => {
    let host = "link";
    try { host = new URL(url.replace(/&amp;/g, "&")).hostname.replace(/^www\./, ""); } catch { /* keep "link" */ }
    const cmc = (host === "coinmarketcap.com" || host.endsWith(".coinmarketcap.com")) && url.startsWith("https://");
    return cmc
      ? `<a href="${url}" target="_blank" rel="noopener">${label}</a>`
      : `${label} <span class="host">(${esc(host)})</span>`;
  });
  for (const [field, q] of Object.entries(quotes || {})) {
    const e = esc(q);
    if (e.length >= 3) html = markText(html, e, states[field] || "", field);
  }
  return html;
}

function endpointName(rowId) {
  const call = (state.final?.receipt?.calls || []).find((c) => c.id === rowId);
  const ep = call ? call.endpoint.split("/").filter(Boolean) : [];
  const name = { info: "info", map: "map", latest: ep.includes("market-pairs") ? "pairs" : "quotes", historical: "history" }[ep[ep.length - 1]] || rowId;
  return `${name} ${rowId}`;
}

function checkRow(c) {
  const rows = [...new Set(c.rows || [])].map((r) => `<button type="button" class="chip" data-row="${esc(r)}" title="open receipt row ${esc(r)}">${esc(endpointName(r))}</button>`).join(" ");
  return `<li class="check"><span class="lamp ${esc(c.state)}" role="img" aria-label="${esc(c.label)}: ${esc(c.state)}"></span>
    <span class="label">${esc(c.id)} · ${esc(c.label)}</span><span class="value">${esc(c.value)}</span><span class="rows">${rows}</span></li>`;
}

function figures() {
  const v = state.final;
  if (!v || v.type !== "verdict") return;
  const qty = Number($("qty").value || 0);
  const k = v.qty ? qty / v.qty : 0;
  const parts = [];
  // NOT VERIFIABLE has no verdict to act on: the old token's value is shown as a market figure, not as "sell old"
  if (v.value_sell_old_usd != null) parts.push(`${v.verdict === "NOT_VERIFIABLE" ? "market value, no verdict" : "sell old"}: <b>${usd(v.value_sell_old_usd * k)}</b>`);
  if (v.value_swap_usd != null) parts.push(`swap: <b>${usd(v.value_swap_usd * k)}</b>`);
  if (v.tracker_value_usd != null) parts.push(`<span class="tracker">tracker value (CMC price on a dead market): ${usd(v.tracker_value_usd * k)}</span>`);
  parts.push(`<span class="tracker">for ${qty.toLocaleString("en-US")} ${esc(v.holding?.symbol)} · window ${esc(v.swap_window || "not stated")}</span>`);
  $("figures").innerHTML = parts.join('<span class="sep">|</span>');
  const notes = ["excludes fees, gas and slippage"];
  const sell = v.value_sell_old_usd != null ? v.value_sell_old_usd * k : null;
  if (sell != null && v.old_volume_24h_usd && sell > 0.01 * v.old_volume_24h_usd) {
    notes.push(`size caveat: ${usd(sell)} is over 1% of the old token's 24 h volume (${usd(v.old_volume_24h_usd)}); the sell figure may not be achievable at that size`);
  }
  if (v.verdict === "SWAP" && !/open|until/i.test(v.swap_window || "")) notes.push("swap window not stated: SWAP holds only if the issuer's swap is still open");
  $("caveats").textContent = notes.join(" · ");
}

function onEvent(ev) {
  state.events.push(ev);
  const t = ev.t_ms || 0;
  if (ev.type === "step") {
    const s = ev.step;
    if (s === "resolve" && ev.chosen) { flaps($("f-old"), ev.chosen.symbol); trace(t, `${STEP[s]}: ${esc(ev.chosen.symbol)} · ${esc(ev.chosen.name || "")} · CMC id ${ev.chosen.id}`); }
    else if (s === "resolve") trace(t, `${STEP[s]}: ${esc(ev.reason)}`);
    else if (s === "notice") { $("notice").innerHTML = ev.notice ? noticeHtml(ev.notice, {}, {}) : ""; trace(t, `${STEP[s]}: ${ev.has_notice ? "notice found" : "no notice"}`); }
    else if (s === "reader") {
      if (ev.cache === "hit") trace(t, `agent: recorded extraction of this exact notice (${esc(ev.model)}, ${ev.llm_calls} call(s), ${esc(String(ev.recorded_at || "").slice(0, 10))})`, "agent");
      else { trace(t, `agent reading the notice live (${esc(ev.model)}), about 20 s on a cold notice <span id="tick">0 s</span>`, "agent"); startTick(); }
    } else if (s === "follow_link") {
      const when = ev.recorded ? ` · read ${esc(String(ev.fetched_at || "").slice(0, 10))}` : "";
      trace(t, ev.ok ? `agent follows link ${esc(ev.host)} (allow-listed: a domain in CMC's urls) · ${ev.chars} chars${when}` : `agent link refused: ${esc(ev.error)} (${esc(ev.url)})`, ev.ok ? "agent" : "err");
    }
    else if (s === "proposal") {
      stopTick();
      const f = ev.fields || {};
      const bits = Object.entries(f).map(([k, v]) => `${k}=${esc(k.includes("contract") ? short(String(v)) : v)}`);
      trace(t, `agent proposal #${ev.n}: ${bits.join(" · ") || "no fields"}${Object.keys(ev.dropped || {}).length ? ` · dropped by C3: ${esc(Object.keys(ev.dropped).join(", "))}` : ""}`, "agent");
      for (const [k, src] of Object.entries(ev.sources || {})) {
        if (src === "announcement") trace(t, `quoted from the linked page (${esc(k)}): “${esc(ev.quotes[k])}”`, "agent");
      }
      state.quotes = ev.quotes; state.qstates = {};
      const n = state.events.find((e) => e.step === "notice");
      if (n?.notice) $("notice").innerHTML = noticeHtml(n.notice, ev.quotes, {});
    } else if (s === "successor") {
      trace(t, `${STEP[s]}: ${esc(ev.state)} · ${esc(ev.reason)}`, ev.state === "verified" ? "ok" : "err");
      if (ev.successor) flaps($("f-new"), ev.successor.symbol);
    } else if (s === "refute") trace(t, `refute sent to the agent: ${esc(ev.reason)}`, "err");
    else if (s === "market_old" || s === "market_new") trace(t, `${STEP[s]} ${esc(ev.coin)}: ${esc(ev.state)} · ${esc(ev.reason)}`, ev.state === "alive" ? "ok" : "");
    else if (s === "ratio") trace(t, `${STEP[s]}: ${esc(ev.state)} · ${esc(ev.reason)}${ev.event_day ? ` · event day ${esc(ev.event_day)} (${esc(ev.event_day_source)})` : ""}`, ev.state === "P" ? "ok" : "");
    else trace(t, esc(s));
  } else if (ev.type === "verdict") {
    stopTick();
    state.final = ev;
    flaps($("f-verdict"), WORD[ev.verdict] || ev.verdict, "verdict " + ev.verdict);
    if (!ev.successor) flaps($("f-new"), "—");
    $("reason").textContent = `${ev.rule_id}: ${ev.reason}`;
    $("checks").innerHTML = (ev.checks || []).map(checkRow).join("");
    const okFields = {};
    for (const c of ev.checks || []) {
      if (c.id === "C2") ["successor_symbol", "successor_name", "new_contract", "new_chain"].forEach((f) => (okFields[f] = c.state === "verified" ? "ok" : c.state === "refuted" ? "bad" : ""));
      if (c.id === "C4") okFields.ratio_new_per_old = c.value.startsWith("P") ? "ok" : "";
    }
    const n = state.events.find((e) => e.step === "notice");
    if (n?.notice) $("notice").innerHTML = noticeHtml(n.notice, state.quotes || {}, okFields);
    figures();
    trace(t, `verdict ${esc(WORD[ev.verdict])} (${esc(ev.rule_id)}) · ${ev.credits_used ?? 0} CMC credits`, "ok");
    $("captured").textContent = `captured ${ev.captured_at || ""} · ${ev.receipt?.llm_source || ""}`;
    $("receipt-btn").disabled = false; $("reread").disabled = false;
  } else if (ev.type === "outcome") {
    stopTick();
    state.final = ev;
    if (ev.outcome === "no_notice") { flaps($("f-verdict"), "NO NOTICE", "verdict NOT_VERIFIABLE"); $("reason").textContent = ev.message; }
    else {
      $("reason").textContent = ev.message;
      const pick = $("pick"); pick.hidden = !(ev.candidates || []).length;
      pick.innerHTML = (ev.candidates || []).map((c) => `<button type="button" data-q="${esc(c.symbol)}" data-id="${c.id}">${esc(c.symbol)} · ${esc(c.name)} · id ${c.id}${c.is_active === 0 ? " (inactive)" : ""}</button>`).join("");
    }
    trace(t, esc(ev.message));
  } else if (ev.type === "error") {
    stopTick();
    state.final = ev;
    flaps($("f-verdict"), "NO VERDICT", "verdict NOT_VERIFIABLE");
    $("reason").textContent = `Error at ${ev.step}${ev.http_status ? ` (HTTP ${ev.http_status})` : ""}: ${ev.error}. No verdict is shown. `;
    const rp = document.createElement("a"); rp.href = "/about#demo"; rp.textContent = "See a captured run (labelled replay)";
    $("reason").append(rp);
    trace(t, `error at ${esc(ev.step)}: ${esc(ev.error)}`, "err");
  }
}

function startTick() { const t0 = Date.now(); if (state.ticking) clearInterval(state.ticking); state.ticking = setInterval(() => { const el = $("tick"); if (el) el.textContent = `${Math.round((Date.now() - t0) / 1000)} s`; }, 1000); }
function stopTick() { if (state.ticking) clearInterval(state.ticking); state.ticking = null; const el = $("tick"); if (el) el.removeAttribute("id"); }

function reset(q) {
  stopTick();  // a superseded lookup's tick must not keep running
  state.events = []; state.final = null; state.quotes = {};
  flaps($("f-old"), q); flaps($("f-new"), ""); flaps($("f-verdict"), "", "verdict");
  ["figures", "caveats", "reason", "notice", "checks", "trace", "captured"].forEach((id) => ($(id).innerHTML = ""));
  $("pick").hidden = true; $("receipt-btn").disabled = true; $("reread").disabled = true;
}

async function lookup(q, id, fresh = false) {
  if (state.ctrl) state.ctrl.abort();
  const ctrl = new AbortController();
  state.ctrl = ctrl;
  // only the newest lookup may touch the board (a2a r03: an aborted stream could re-enable Go or land late events)
  const mine = () => state.ctrl === ctrl;
  const emit = (line) => {
    if (!mine()) return;
    let ev;
    try { ev = JSON.parse(line); } catch { ev = { type: "error", step: "stream", error: "unreadable line from the server", t_ms: 0 }; }
    onEvent(ev);
  };
  state.q = q; state.id = id;
  reset(q);
  $("go").disabled = true;
  const p = new URLSearchParams({ q, qty: $("qty").value || "1" });
  if (id) p.set("id", id);
  if (fresh) p.set("fresh", "1");
  history.replaceState(null, "", `/?q=${encodeURIComponent(q)}${id ? `&id=${id}` : ""}`);
  try {
    const r = await fetch(`/api/lookup?${p}`, { headers: { Accept: "application/x-ndjson" }, signal: ctrl.signal });
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
        if (line) emit(line);
      }
    }
    if (buf.trim()) emit(buf);
    if (mine() && !state.final) onEvent({ type: "error", step: "stream", error: "the stream ended without a verdict", t_ms: 0 });
  } catch (e) {
    if (e.name !== "AbortError" && mine()) onEvent({ type: "error", step: "network", error: String(e.message || e), t_ms: 0 });
  } finally { if (mine()) $("go").disabled = false; }
}

function receiptHtml(v) {
  const r = v.receipt || {};
  const calls = (r.calls || []).map((c) => `<tr id="row-${esc(c.id)}"><td>${esc(c.id)}</td><td>GET ${esc(c.endpoint)}</td><td>${esc(JSON.stringify(c.params))}</td><td>${c.http_status}</td><td>${c.latency_ms} ms</td><td>${c.credit_count}</td><td>${esc(c.ts)}</td></tr>`).join("");
  const rows = (r.calls || []).map((c) => `<details id="data-${esc(c.id)}"><summary>${esc(c.id)} · ${esc(c.endpoint)} · verbatim response</summary><pre>${esc(JSON.stringify(c.data, null, 1))}</pre></details>`).join("");
  const llm = (r.llm || []).map((l, i) => `<details><summary>call ${i + 1} · ${esc(l.model)} · ${esc(l.prompt_version)} · HTTP ${l.http_status} · ${l.latency_ms} ms · ${esc(l.captured_at)}</summary><pre>${esc(JSON.stringify({ messages: l.request_messages, response: l.response }, null, 1))}</pre></details>`).join("");
  const pages = (r.pages || []).map((p) => `<li>${esc(p.label)}: ${esc(p.url)} · sha256 ${esc(p.sha256)}</li>`).join("");
  return `<h3>1 · Endpoints called (${(r.calls || []).length}, ${r.credits_used ?? 0} credits)</h3><table><tr><th>row</th><th>call</th><th>params</th><th>HTTP</th><th>latency</th><th>credits</th><th>time</th></tr>${calls}</table>
  <h3>2 · Verbatim CMC rows</h3>${rows}
  <h3>3 · The agent (${esc(r.llm_source)})</h3>${llm || "<p>no LLM call</p>"}${pages ? `<p>Pages the agent read:</p><ul>${pages}</ul>` : ""}
  <h3>4 · Reproduce</h3><pre>${esc((r.curl || []).join("\n"))}</pre>
  <h3>5 · Rule that fired</h3><pre>${esc(JSON.stringify({ verdict: v.verdict, rule_id: v.rule_id, reason: v.reason, checks: v.checks, proposal: v.proposal }, null, 1))}</pre>`;
}

function openReceipt(row) {
  if (!state.final || state.final.type !== "verdict") return;
  $("receipt").innerHTML = receiptHtml(state.final);
  $("drawer").hidden = false;
  if (row) { const d = $("data-" + row); if (d) { d.open = true; d.scrollIntoView({ block: "center" }); d.classList.add("hl"); } }
  $("close").focus();
}

async function health() {
  const el = $("health");
  try {
    const h = await (await fetch("/api/health")).json();
    const ok = h.cmc?.ok;
    el.classList.add(ok ? "ok" : "bad");
    el.querySelector(".health-text").textContent = ok ? "live" : "degraded";
    el.title = `CMC ok: ${ok} · credits left ${h.cmc?.credits_left ?? "?"} · model ${h.llm?.model} · build ${h.build_sha}`;
    el.setAttribute("aria-label", (ok ? "live" : "degraded") + " · API health: " + el.title);
  } catch { el.classList.add("bad"); }
}

$("form").addEventListener("submit", (e) => { e.preventDefault(); const q = $("q").value.trim(); if (q) lookup(q, null); });
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-q]");
  if (b) {
    if (b.closest("#ctable")) window.scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    lookup(b.dataset.q, b.dataset.id ? Number(b.dataset.id) : null);
    return;
  }
  const c = e.target.closest(".chip[data-row]");
  if (c) openReceipt(c.dataset.row);
});
$("qty").addEventListener("input", figures);
$("receipt-btn").addEventListener("click", () => openReceipt());
$("close").addEventListener("click", () => { $("drawer").hidden = true; $("receipt-btn").focus(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("drawer").hidden) $("close").click(); });
$("copy").addEventListener("click", async () => { await navigator.clipboard.writeText(JSON.stringify(state.final, null, 1)); $("copy").textContent = "Copied"; setTimeout(() => ($("copy").textContent = "Copy JSON"), 1200); });
$("reread").addEventListener("click", () => lookup(state.q, state.id, true));


// ---- census screen -------------------------------------------------------------------------------
const VLABEL = { SWAP: "Swap", SELL_OLD: "Sell old", WRITE_OFF: "Write off", NOT_VERIFIABLE: "Not verifiable", NOTHING_TO_DO: "Nothing to do" };
let census = { rows: [], f: "all" };

function censusRows() {
  const f = census.f;
  const keep = (r) => f === "all" || (f === "migration" && r.type === "migration") || (f === "prose" && r.prose_only) || r.verdict === f;
  $("cbody").innerHTML = census.rows.filter(keep).map((r) => {
    const flags = [r.prose_only ? "prose only" : "names a contract", r.names_ratio ? "ratio named" : "no ratio", r.only_unfetchable_hosts ? "links not fetchable" : ""].filter(Boolean).join(" · ");
    const v = r.verdict && r.verdict !== "ERROR" ? `<span class="vd ${esc(r.verdict)}">${esc(VLABEL[r.verdict] || r.verdict)}</span>` : `<span class="vd none">not read yet</span>`;
    const when = r.verdict_captured_at ? `<span class="why when">${esc(r.rule_id || "")} · read ${esc(r.verdict_captured_at.replace("T", " ").replace("Z", " UTC"))}</span>` : "";
    const why = r.reason ? `<span class="why block">${esc(r.reason)}</span>` : "";
    return `<tr><td class="num">${r.featured ? "★" : esc(r.rank)}</td><td><span class="sym">${esc(r.symbol)}</span> <span class="why">${esc(r.name)}${r.featured ? " · demo coin, listed apart from the counts" : ""}</span><span class="why block show-s">${esc(r.type)} · ${esc(flags)}</span></td><td class="why hide-s">${esc(r.type)} · ${esc(flags)}</td><td>${v}${when}${why}</td><td><button type="button" data-q="${esc(r.symbol)}" data-id="${esc(r.id)}" aria-label="Look up ${esc(r.symbol)} live">Look up</button></td></tr>`;
  }).join("") || `<tr><td colspan="5" class="why">no coins match this filter</td></tr>`;
}

async function loadCensus() {
  try {
    const [c, n] = await Promise.all([fetch("/api/census").then((r) => r.json()), fetch("/api/notices").then((r) => r.json())]);
    census.rows = n.notices;
    const tile = (b, t) => `<div class="tile"><b>${esc(b)}</b><span>${esc(t)}</span></div>`;
    $("census-meta").textContent = `Captured ${c.captured_at} · ${c.scope} · ${c.method}`;
    $("tiles").innerHTML = [
      tile(c.notices, `coins carry a notice (of ${c.coins_scanned} scanned)`),
      tile(`${c.prose_only} / ${c.migration_type}`, "migration-type notices state the successor only in prose"),
      tile(`${c.no_ratio_named} / ${c.migration_type}`, "migration-type notices name no swap ratio"),
      tile(`${c.only_unfetchable_hosts} / ${c.migration_type}`, "link only to hosts the agent cannot fetch (x.com, t.me, …)"),
      tile(`${c.old_zero_volume} / ${c.market_checked}`, "old tokens CMC still prices on $0 24 h volume (of lookups that reached the market check)"),
      tile(`${c.verdicts.NOT_VERIFIABLE} / ${c.verdicts_total}`, `verdicts are Not verifiable (read ${c.verdicts_captured || "n/a"})`),
    ].join("");
    $("reasons").innerHTML = `<b>Why ${c.verdicts.NOT_VERIFIABLE} are Not verifiable:</b> ` + Object.entries(c.not_verifiable_reasons).map(([k, v]) => `${esc(v)} · ${esc(k)}`).join(" | ") + `. Not verifiable means CMC's data cannot support a verdict, not that the page failed to load.`;
    $("census-note").textContent = `${census.rows.length} rows listed = ${c.notices} counted + ${census.rows.length - c.notices} starred demo coins (CPOOL, AGIX, RZUSD, BIT) that sit outside the active top 2000. Each verdict is one run of the live flow at the time shown on its row; market-sensitive verdicts can differ on a later run.`;
    const tot = Math.max(c.verdicts_total, 1);
    $("dist").innerHTML = Object.entries(c.verdicts).filter(([, k]) => k).map(([k, v]) => `<i class="${esc(k)}" style="width:${(v / tot) * 100}%" title="${esc(VLABEL[k])}: ${v}"></i>`).join("");
    $("dist").setAttribute("aria-label", "Verdict distribution: " + Object.entries(c.verdicts).map(([k, v]) => `${VLABEL[k]} ${v}`).join(", "));
    $("dist").insertAdjacentHTML("afterend", `<p class="legend">${Object.entries(c.verdicts).map(([k, v]) => `${esc(VLABEL[k])} ${v}`).join(" · ")} · Reader opened or tried a link while reading: ${c.reader_opened_link}</p>`);
    censusRows();
  } catch { $("census-meta").textContent = "Census unavailable right now."; }
}
$("filters").addEventListener("click", (e) => {
  const b = e.target.closest(".filt");
  if (!b) return;
  census.f = b.dataset.f;
  document.querySelectorAll(".filt").forEach((x) => x.classList.toggle("on", x === b));
  censusRows();
});

const params = new URLSearchParams(location.search);
health();
loadCensus();
lookup(params.get("q") || "CPOOL", params.get("id") ? Number(params.get("id")) : params.get("q") ? null : 12573);
