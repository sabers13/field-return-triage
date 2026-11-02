/* All evidence comes from the committed results embedded by make page.
   No requests or model calls. Review decisions live in memory only. */
(() => {
  "use strict";
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const root = document.documentElement;
  const scheme = matchMedia("(prefers-color-scheme: dark)");
  let manualTheme = new URLSearchParams(location.search).has("theme");
  try { manualTheme ||= ["light", "dark"].includes(localStorage.getItem("frt-theme")); } catch (_) {}
  function applyTheme(theme) {
    root.dataset.theme = theme;
    $$('[data-theme-set]').forEach(button => button.setAttribute("aria-pressed", String(button.dataset.themeSet === theme)));
    $('meta[name="theme-color"]').content = theme === "dark" ? "#030712" : "#f9fafb";
  }
  applyTheme(root.dataset.theme);
  $$('[data-theme-set]').forEach(button => button.addEventListener("click", () => {
    manualTheme = true;
    const url = new URL(location.href);
    if (url.searchParams.has("theme")) { url.searchParams.delete("theme"); history.replaceState(null, "", url); }
    applyTheme(button.dataset.themeSet);
    try { localStorage.setItem("frt-theme", button.dataset.themeSet); } catch (_) {}
  }));
  scheme.addEventListener("change", event => { if (!manualTheme) applyTheme(event.matches ? "dark" : "light"); });

  const navLinks = $$('.nav a, .rail-nav a');
  const sections = ["overview", "queue", "results", "method"].map(id => document.getElementById(id));
  let navTicking = false;
  let requestedSection = sections.find(section => `#${section.id}` === location.hash);
  function selectNavigation(section) {
    navLinks.forEach(link => {
      if (link.hash === `#${section.id}`) link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    });
  }
  function updateNavigation() {
    const top = parseFloat(getComputedStyle(root).scrollPaddingTop) || 0;
    const atBottom = scrollY > 0 && Math.ceil(scrollY + innerHeight) >= root.scrollHeight - 2;
    const requestedReached = requestedSection && (
      Math.abs(requestedSection.getBoundingClientRect().top - top) <= 2 ||
      (requestedSection === sections[0] && scrollY <= 1) ||
      (requestedSection === sections.at(-1) && atBottom)
    );
    if (requestedReached) requestedSection = null;
    let current = sections[0];
    for (const section of sections) if (section.getBoundingClientRect().top <= top + 2) current = section;
    if (atBottom) current = sections.at(-1);
    selectNavigation(requestedSection || current);
    navTicking = false;
  }
  navLinks.forEach(link => link.addEventListener("click", event => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    requestedSection = sections.find(section => `#${section.id}` === link.hash);
    if (requestedSection) selectNavigation(requestedSection);
  }));
  const resumeScrollNavigation = () => { requestedSection = null; };
  addEventListener("wheel", resumeScrollNavigation, { passive: true });
  addEventListener("touchstart", resumeScrollNavigation, { passive: true });
  addEventListener("keydown", event => {
    if (["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "].includes(event.key)) resumeScrollNavigation();
  });
  addEventListener("hashchange", () => {
    requestedSection = sections.find(section => `#${section.id}` === location.hash);
    updateNavigation();
  });
  addEventListener("scrollend", () => { requestedSection = null; updateNavigation(); });
  addEventListener("scroll", () => { if (!navTicking) { requestAnimationFrame(updateNavigation); navTicking = true; } }, { passive: true });
  addEventListener("resize", updateNavigation);
  addEventListener("load", updateNavigation);
  updateNavigation();

  let DATA;
  try {
    DATA = JSON.parse($("#page-data").textContent);
    if (!DATA.queue.cards.length || !DATA.results.models.length || !DATA.trend.example.weeks.length) throw new Error("Missing evidence");
  } catch (_) { $("#data-error").hidden = false; return; }
  const esc = value => String(value ?? "").replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  const fmt = {
    dec: (value, digits = 3) => value == null ? "—" : Number(value).toFixed(digits),
    pct: (value, digits = 1) => value == null ? "—" : `${(Number(value) * 100).toFixed(digits)}%`,
    money: value => value == null ? "—" : `$${Number(value).toFixed(4)}`,
    int: value => value == null ? "—" : Number(value).toLocaleString("en-US"),
  };
  const FIELD_LABEL = { safety: "Safety clue", symptoms: "Symptom", conditions: "Condition", fault_codes: "Fault code", mileage: "Mileage" };
  const PRIORITY = { 1: "Safety first", 2: "Clear clues", 3: "Needs human reading" };
  const groupName = group => ({ power_windows_locks_switches: "Windows, locks and switches", airbags: "Airbags", electrical_system: "Electrical system", lighting: "Lighting", electronic_stability_control: "Stability control", steering: "Steering", brakes: "Brakes", power_train: "Powertrain", unclear: "Component unclear" })[group] || group.replaceAll("_", " ");
  const vehicleName = card => [card.vehicle.model_year, card.vehicle.make, card.vehicle.model].filter(Boolean).join(" ");
  const date = value => new Intl.DateTimeFormat("en", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
  const icon = id => `<svg aria-hidden="true"><use href="#i-${id}"/></svg>`;
  const ci = (metric, format = fmt.dec) => `${format(metric?.value)} <span class="ci">95% CI ${format(metric?.ci_low)}–${format(metric?.ci_high)}</span>`;

  function escapeRegExp(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function quotePattern(quote) {
    const parts = quote.trim().split(/\s+/).map(escapeRegExp);
    return parts.length ? new RegExp(parts.join("\\s+"), "i") : null;
  }

  const CLUE_ORDER = { symptoms: 0, conditions: 1, fault_codes: 2, mileage: 3, safety: 4 };

  function subtract(range, cut) {
    if (cut.end <= range.start || cut.start >= range.end) return [range];
    const pieces = [];
    if (range.start < cut.start) pieces.push({ start: range.start, end: cut.start });
    if (cut.end < range.end) pieces.push({ start: cut.end, end: range.end });
    return pieces;
  }

  function highlight(narrative, clues) {
    const found = [];
    for (const clue of clues) {
      if (!clue.text) continue;
      const pattern = quotePattern(clue.text);
      if (!pattern) continue;
      const match = pattern.exec(narrative);
      if (!match) continue;
      found.push({
        start: match.index,
        end: match.index + match[0].length,
        field: clue.field,
        kind: clue.kind,
      });
    }

    /* Nested quotes are common: a safety sentence often contains the symptom and the
       condition. Claim the specific clues first, then fill the gaps of the long safety
       quote, so every clue is visible with its own colour. */
    found.sort(
      (left, right) =>
        (CLUE_ORDER[left.field] ?? 9) - (CLUE_ORDER[right.field] ?? 9) ||
        left.end - left.start - (right.end - right.start) ||
        left.start - right.start,
    );

    const covered = [];
    const pieces = [];
    for (const range of found) {
      let remaining = [{ start: range.start, end: range.end }];
      for (const cut of covered) {
        remaining = remaining.flatMap((piece) => subtract(piece, cut));
        if (!remaining.length) break;
      }
      for (const piece of remaining) {
        pieces.push({ ...piece, field: range.field, kind: range.kind });
      }
      covered.push({ start: range.start, end: range.end });
    }

    pieces.sort((left, right) => left.start - right.start);
    const merged = [];
    for (const piece of pieces) {
      const previous = merged[merged.length - 1];
      if (previous && previous.end === piece.start && previous.field === piece.field) {
        previous.end = piece.end;
      } else {
        merged.push({ ...piece });
      }
    }

    let html = "";
    let position = 0;
    for (const range of merged) {
      const label = `${FIELD_LABEL[range.field] || "Clue"} · ${String(range.kind).replace(/_/g, " ")}`;
      html += esc(narrative.slice(position, range.start));
      html += `<mark class="clue clue-${esc(range.field)}" title="${esc(label)}">${esc(
        narrative.slice(range.start, range.end),
      )}</mark>`;
      position = range.end;
    }
    return html + esc(narrative.slice(position));
  }

  function clueLegend(clues) {
    const fields = new Set(clues.map((clue) => clue.field));
    const items = [];
    if (fields.has("safety")) items.push(["clue-safety", "safety clue"]);
    if (fields.has("symptoms")) items.push(["clue-symptoms", "symptom"]);
    if (fields.has("conditions")) items.push(["clue-conditions", "condition"]);
    if (fields.has("fault_codes") || fields.has("mileage")) {
      items.push(["clue-fault_codes", "code / mileage"]);
    }
    if (!items.length) return "";
    return `<p class="clue-legend">${items
      .map(
        ([className, label]) =>
          `<span><i class="${className}"></i>${esc(label)}</span>`,
      )
      .join("")}</p>`;
  }


  const cards = DATA.queue.cards;
  const example = cards.find(card => card.priority === 2) || cards[0];
  const condition = example.clues.find(clue => clue.field === "conditions");
  const symptom = example.clues.find(clue => clue.field === "symptoms");
  $("#hero-example").innerHTML = `<div class="quote-preview"><p class="block-label">In complaint #${esc(example.complaint_id)}</p><blockquote>“${esc(symptom?.text || example.narrative)}”<br>in <mark>${esc(condition?.text || "the reported conditions")}</mark></blockquote><p class="quote-context">${esc(vehicleName(example))}</p></div>
    <div class="preview-connection">${icon("check")}<span>Exact words checked against the original</span></div>
    <div class="suggestion-preview"><p class="block-label">Suggested test</p><p>${esc(example.suggestion.tests[0] || "Ask for more information")}</p></div>`;
  $("#queue-rule").textContent = `${DATA.queue.rule} Cards come from ${DATA.queue.model_id}. The opening example is the first clear-clue case in that fixed selection, with every selected case available below.`;

  function reasonsList(reasons) {
    return reasons.length ? `<ul class="reasons">${reasons.map(reason => `<li><p>${esc(reason.text.replaceAll("_", " "))}</p>${reason.quotes.length ? `<p class="reason-quotes">${reason.quotes.map(quote => `“${esc(quote)}”`).join(" · ")}</p>` : ""}</li>`).join("")}</ul>` : "<p>No specific reason was recorded.</p>";
  }
  function neighboursBlock(card) {
    return `<div class="nearest-grid">${card.neighbours.map(neighbour => `<article class="neighbour"><div class="neighbour-top"><strong>#${esc(neighbour.complaint_id)}</strong><span>Similarity ${fmt.dec(neighbour.score, 4)}</span></div><p class="neighbour-meta"><span>${esc(groupName(neighbour.group))}</span><span class="${neighbour.group === card.group ? "same-group" : "other-group"}">${neighbour.group === card.group ? "Same component group" : "Different component group"}</span><span>${esc(date(neighbour.received))}</span>${neighbour.safety_relevant ? "<span>Safety-relevant</span>" : ""}</p><p class="neighbour-excerpt">${esc(neighbour.excerpt)}…</p></article>`).join("")}</div>`;
  }
  function cardHTML(card) {
    const s = card.suggestion;
    return `<article class="card" id="case-${esc(card.complaint_id)}" data-priority="${card.priority}" aria-label="Complaint ${esc(card.complaint_id)}" hidden>
      <header class="card-head"><span class="priority-pill" data-priority="${card.priority}">Priority ${card.priority} · ${PRIORITY[card.priority]}</span><span class="card-id">#${esc(card.complaint_id)} · ${esc(date(card.received))}</span><h3 class="card-vehicle">${esc(vehicleName(card))}</h3><span class="chip">${esc(groupName(card.group))}</span>${card.coded_safety ? `<span class="chip">Coded ${esc(card.coded_flags.join(" / "))}</span>` : ""}</header>
      <div class="card-body"><div class="card-col"><h4 class="col-label">Original complaint</h4><p class="narrative">${highlight(card.narrative, card.clues)}</p>${clueLegend(card.clues)}${!card.clues.length ? '<p class="no-clues">No clue passed the quote check. A person needs to read this complaint.</p>' : ""}<p class="routing-note">${card.priority === 1 ? "Safety takes priority. A person must review this case." : card.priority === 3 ? "The evidence is unclear. This case needs human reading." : "Clear clues survived the quote check. A technician still makes the decision."}</p></div>
      <div class="card-col"><h4 class="col-label">Suggested next step</h4><ul class="test-list">${s.tests.map(test => `<li>${esc(test)}</li>`).join("") || "<li>Standard test; ask for more information</li>"}</ul><div class="test-block"><p class="block-label">Why this test</p>${reasonsList(s.reasons)}</div>${s.inspect.length ? `<div class="test-block"><p class="block-label">Inspect</p><p>${s.inspect.map(esc).join("; ")}</p></div>` : ""}${s.request.length ? `<div class="test-block"><p class="block-label">Ask the customer for</p><ul class="ask-list">${s.request.map(item => `<li>${esc(item)}</li>`).join("")}</ul></div>` : ""}</div></div>
      <div class="record-details"><details><summary>The nearest past cases</summary><div class="technical-body"><p class="detail-intro">The pipeline searches for five cases; this preview shows the nearest three. Similarity measures text closeness, not the likelihood of the same fault. A different component group is labelled explicitly.</p>${neighboursBlock(card)}</div></details><details><summary>Routing, quote checks and versions</summary><div class="technical-body">${reasonsList(card.reasons)}<dl class="versions">${Object.entries(card.versions).map(([key,value]) => `<div><dt>${esc(key.replaceAll("_", " "))}</dt><dd>${esc(value)}</dd></div>`).join("")}<div><dt>Quote check</dt><dd>${card.quote_check.passed} / ${card.quote_check.checked} passed; ${card.quote_check.dropped} dropped</dd></div></dl></div></details></div>
      <footer class="card-foot"><div class="demo" data-card-id="${esc(card.card_id)}" data-priority="${card.priority}" role="group" aria-label="Demo review for complaint ${esc(card.complaint_id)}"><div class="demo-actions"><button class="btn btn-primary" type="button" data-demo="accept">Accept suggestion</button><button class="btn" type="button" data-demo="change">Change with a reason</button><span class="demo-note">Demo only · nothing saved</span></div></div></footer>
    </article>`;
  }
  $("#example-browser").innerHTML = `<div class="queue-toolbar"><div class="filter-group" role="group" aria-label="Filter examples by priority">${[["all","All cases"],["1","Safety"],["2","Clear clues"],["3","Human reading"]].map(([value,label]) => `<button type="button" data-filter="${value}" aria-pressed="${value === "all"}">${label}</button>`).join("")}</div><span class="queue-count" id="queue-count" role="status"></span></div><label class="case-mobile" for="case-select">Choose a recorded complaint<select name="recorded-case" id="case-select"></select></label><div class="queue-workspace"><div class="case-list" role="group" aria-label="Recorded complaints">${cards.map(card => `<button class="case-choice" data-case="${esc(card.complaint_id)}" type="button" aria-pressed="false" aria-controls="case-${esc(card.complaint_id)}"><strong>#${esc(card.complaint_id)} · ${PRIORITY[card.priority]}</strong><small>${esc(vehicleName(card))}</small><span class="case-group">${esc(groupName(card.group))}</span></button>`).join("")}</div><div class="case-panels">${cards.map(cardHTML).join("")}</div></div>`;
  let filter = "all";
  let selected = example.complaint_id;
  function selectionFromURL() {
    const query = new URLSearchParams(location.search);
    filter = ["1", "2", "3"].includes(query.get("priority")) ? query.get("priority") : "all";
    const available = cards.filter(card => filter === "all" || String(card.priority) === filter);
    selected = available.find(card => card.complaint_id === query.get("case"))?.complaint_id || (filter === "all" ? example.complaint_id : available[0].complaint_id);
  }
  function renderSelection(writeURL = false) {
    const available = cards.filter(card => filter === "all" || String(card.priority) === filter);
    $$("[data-filter]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.filter === filter)));
    $$(".case-choice").forEach(button => {
      button.hidden = !available.some(card => card.complaint_id === button.dataset.case);
      button.setAttribute("aria-pressed", String(button.dataset.case === selected));
    });
    $$(".card").forEach(card => { card.hidden = card.id !== `case-${selected}`; });
    $("#case-select").innerHTML = available.map(card => `<option value="${esc(card.complaint_id)}"${card.complaint_id === selected ? " selected" : ""}>#${esc(card.complaint_id)} — ${esc(vehicleName(card))} — ${PRIORITY[card.priority]}</option>`).join("");
    $("#queue-count").textContent = `${available.length} recorded cases · showing #${selected}`;
    if (writeURL) {
      const url = new URL(location.href);
      url.searchParams.set("case", selected);
      if (filter === "all") url.searchParams.delete("priority"); else url.searchParams.set("priority", filter);
      history.pushState(null, "", url);
    }
  }
  selectionFromURL(); renderSelection();
  $("#example-browser").addEventListener("click", event => {
    const choice = event.target.closest("[data-case]");
    const priority = event.target.closest("[data-filter]");
    if (choice) { selected = choice.dataset.case; renderSelection(true); }
    if (priority) {
      filter = priority.dataset.filter;
      const available = cards.filter(card => filter === "all" || String(card.priority) === filter);
      if (!available.some(card => card.complaint_id === selected)) selected = available[0].complaint_id;
      renderSelection(true);
    }
  });
  $("#case-select").addEventListener("change", event => { selected = event.target.value; renderSelection(true); });
  addEventListener("popstate", () => { selectionFromURL(); renderSelection(); });

  // Review is a local demonstration. Only the appearance preference uses storage.
  const initialDemos = new Map($$(".demo").map(demo => [demo.dataset.cardId, demo.innerHTML]));
  function resetDemo(demo) { demo.innerHTML = initialDemos.get(demo.dataset.cardId); $("button", demo).focus(); }
  function showDecision(demo, text) {
    demo.innerHTML = `<p class="demo-status" role="status"></p><div class="demo-actions"><button type="button" class="btn" data-demo="reset">Reset demo</button><span class="demo-note">Nothing was saved or sent.</span></div>`;
    $(".demo-status", demo).textContent = text;
    $("button", demo).focus();
  }
  $("#example-browser").addEventListener("click", event => {
    const button = event.target.closest("[data-demo]");
    if (!button) return;
    const demo = button.closest(".demo");
    if (button.dataset.demo === "accept") showDecision(demo, "Suggestion accepted in this demonstration. A real technician would still decide the case.");
    if (button.dataset.demo === "reset" || button.dataset.demo === "cancel") resetDemo(demo);
    if (button.dataset.demo === "change") {
      const reasonID = `reason-${demo.closest(".card").id}`;
      demo.innerHTML = `<form class="change-form"><label for="${reasonID}">Why would you change this suggestion?<textarea id="${reasonID}" name="review-reason" required maxlength="2000" autocomplete="off" placeholder="For example, run the voltage check before temperature cycling…"></textarea></label><p class="demo-note">The original safety priority stays in place. No decision is saved.</p><div class="demo-actions"><button class="btn btn-primary" type="submit">Apply demo change</button><button class="btn" type="button" data-demo="cancel">Cancel</button></div></form>`;
      $("textarea", demo).focus();
    }
  });
  $("#example-browser").addEventListener("submit", event => {
    if (!event.target.matches(".change-form")) return;
    event.preventDefault();
    const textarea = $("textarea", event.target);
    const reason = textarea.value.trim();
    if (!reason) { textarea.setCustomValidity("Enter a reason to try the change."); textarea.reportValidity(); return; }
    showDecision(event.target.closest(".demo"), `Demo change applied. Reason: ${reason}. The original priority is unchanged.`);
  });
  $("#example-browser").addEventListener("input", event => { if (event.target.matches("textarea")) event.target.setCustomValidity(""); });

  const models = DATA.results.models;
  const primary = models.find(model => model.role === "primary");
  const comparison = models.find(model => model.role === "comparison");
  const m = primary.metrics;
  $("#evaluation-intro").textContent = `Primary model: ${fmt.int(primary.items_evaluated)} complaints. Comparison: ${fmt.int(comparison.items_evaluated)} after a budget cut. These results describe this sample, not real returned parts.`;
  $("#evidence-strip").innerHTML = [
    [fmt.int(primary.items_evaluated), "Complaints evaluated", "One held-out snapshot"],
    [fmt.pct(m.quote_grounding.value), "Clues quote the original", `95% CI ${fmt.pct(m.quote_grounding.ci_low)}–${fmt.pct(m.quote_grounding.ci_high)}`],
    [fmt.pct(m.routing.needs_human_share.value), "Need human reading", `95% CI ${fmt.pct(m.routing.needs_human_share.ci_low)}–${fmt.pct(m.routing.needs_human_share.ci_high)}`],
    [fmt.money(m.cost.per_1000_usd.value), "Model cost / 1,000 complaints", `95% CI ${fmt.money(m.cost.per_1000_usd.ci_low)}–${fmt.money(m.cost.per_1000_usd.ci_high)}`],
  ].map(([value,label,note]) => `<dl class="evidence-stat"><dt>${value}</dt><dd>${label}<span class="ci">${note}</span></dd></dl>`).join("");
  function barRow(label, kind, value) {
    return `<div class="bar-row" data-kind="${kind}"><span>${label}</span><span class="bar-track"><span class="bar-fill" style="width:${Math.min(100,Math.max(0,value*100))}%"></span></span><span class="bar-value">${fmt.dec(value)}</span></div>`;
  }
  $("#glance-group").innerHTML = [barRow("Primary", "primary", m.group.macro_f1.value), barRow("Comparison", "comparison", comparison.metrics.group.macro_f1.value), barRow("Free classifier", "baseline", DATA.results.baselines.group.macro_f1.value)].join("");
  $("#safety-summary").innerHTML = `<div class="safety-pair"><dl><dt>${fmt.dec(m.safety.final_recall.value)}</dt><dd>Safety recall<span class="ci">95% CI ${fmt.dec(m.safety.final_recall.ci_low)}–${fmt.dec(m.safety.final_recall.ci_high)}</span><p class="fine">Share of coded safety cases caught.</p></dd></dl><dl><dt>${fmt.dec(m.safety.final_precision.value)}</dt><dd>Safety precision<span class="ci">95% CI ${fmt.dec(m.safety.final_precision.ci_low)}–${fmt.dec(m.safety.final_precision.ci_high)}</span><p class="fine">Share of flags that matched a coded safety case.</p></dd></dl></div>`;
  const metricRows = [
    ["Component group", "Macro-F1", metric => metric.group.macro_f1, fmt.dec],
    ["Safety recall", "Final hard-rule decision", metric => metric.safety.final_recall, fmt.dec],
    ["Safety precision", "Final hard-rule decision", metric => metric.safety.final_precision, fmt.dec],
    ["Quote grounding", "Clues quote the original", metric => metric.quote_grounding, fmt.pct],
    ["Needs human reading", "Share of all evaluated cases", metric => metric.routing.needs_human_share, fmt.pct],
    ["Safety priority", "Share routed to priority 1", metric => metric.routing.priority_1_share, fmt.pct],
    ["Similar-case precision@5", "Past cases sharing the group", metric => metric.similar_precision_at_5, fmt.dec],
    ["Condition agreement", "Agreement, not accuracy", metric => metric.condition_agreement, fmt.dec],
    ["Cost / 1,000", "Model calls, USD", metric => metric.cost.per_1000_usd, fmt.money],
  ];
  $("#model-scorecard").innerHTML = `<table class="scorecard"><caption>Recorded model results with 95% confidence intervals</caption><thead><tr><th scope="col">Measure</th>${models.map(model => `<th scope="col">${model.role === "primary" ? "Primary" : "Comparison"}<span class="metric-definition">${fmt.int(model.items_evaluated)} complaints</span></th>`).join("")}</tr></thead><tbody>${metricRows.map(([label,definition,get,format]) => `<tr><th scope="row">${label}<span class="metric-definition">${definition}</span></th>${models.map(model => `<td>${ci(get(model.metrics), format)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  const b = DATA.results.baselines;
  $("#baseline-scorecard").innerHTML = `<table class="baseline-table"><caption>Methods with no model-call cost</caption><thead><tr><th scope="col">Method</th><th scope="col">Result and uncertainty</th><th scope="col">Context</th></tr></thead><tbody>
    <tr><th scope="row">${esc(b.group.method)}</th><td>Macro-F1 ${ci(b.group.macro_f1)}</td><td>Trained on ${fmt.int(b.group.training_items)} past cases. Accuracy ${ci(b.group.accuracy)}.</td></tr>
    <tr><th scope="row">Safety keywords</th><td>Recall ${ci(b.safety.recall)}<br>Precision ${ci(b.safety.precision)}</td><td>${fmt.int(b.safety.predicted_safety_items)} flags / ${fmt.int(b.safety.evaluation_items)} complaints; ${fmt.int(b.safety.coded_safety_items)} coded safety cases.</td></tr>
    <tr><th scope="row">Condition keywords</th><td>Any condition ${ci(b.conditions.any_condition_share,fmt.pct)}</td><td>${fmt.int(b.conditions.items_with_any_condition)} / ${fmt.int(b.conditions.evaluation_items)} complaints. Coverage only; agreement with a model is not accuracy.</td></tr></tbody></table>`;
  const source = DATA.results.source;
  $("#source-cards").innerHTML = models.map(model => `<article class="source-card"><span class="block-label">${esc(model.role)}</span><h4>${esc(model.model_id)}</h4><p>${model.role === "primary" ? "Lowest-cost model meeting the pinned card’s quality floor." : "Highest-scoring model on the pinned card’s primary metric."}</p><dl class="versions"><div><dt>Evaluated</dt><dd>${fmt.int(model.items_evaluated)} / ${fmt.int(model.items_available)} available${model.reduced ? " · reduced by the budget cap" : ""}</dd></div><div><dt>Source card</dt><dd>${esc(source.repo)}/${esc(source.card)}</dd></div><div><dt>Commit</dt><dd>${esc(source.commit)}</dd></div><div><dt>Card pick</dt><dd>${esc(model.picked_on_the_card)}</dd></div></dl></article>`).join("");
  $("#run-meta").textContent = `Run ${DATA.run.id} · ${DATA.run.mode} · ${fmt.int(DATA.run.item_count)} complaints · evaluation cost ${fmt.money(DATA.run.cost_usd)} · sample ${DATA.run.sample_hash}`;

  const trend = DATA.trend;
  const backtest = trend.backtest;
  $("#trend-comparison").innerHTML = [
    ["Spike alerts followed by a recall", backtest.alerts.share, `${backtest.alerts.preceding_recall} of ${backtest.alerts.total} alerts`, ""],
    ["Random weeks in the same series", backtest.base_rate.share, `Base rate · 95% CI ${fmt.pct(backtest.base_rate.ci_low)}–${fmt.pct(backtest.base_rate.ci_high)}`, "baseline"],
  ].map(([label,value,note,kind]) => `<article class="trend-result ${kind}"><h4>${label}</h4><strong>${fmt.pct(value)}</strong><div class="bar-track"><span class="bar-fill" style="width:${value*100}%"></span></div><p>${note}</p></article>`).join("");
  $("#trend-reading").textContent = backtest.reading;

  const series = trend.example;
  const weeks = series.weeks;
  const countsByWeek = weeks.map((week) => (typeof week.count === "number" ? week.count : 0));
  const maxCount = Math.max(1, ...countsByWeek);
  const totalWeeks = Math.max(1, weeks.length);

  $("#chart-title").textContent = `${series.series_label} · ${series.group_label.replace(
    /_/g,
    " ",
  )} · ${fmt.int(series.total_complaints)} complaints`;

  const tickStep = Math.max(1, Math.ceil(maxCount / 4));
  const ticks = [];
  for (let value = 0; value <= maxCount; value += tickStep) ticks.push(value);
  if (ticks[ticks.length - 1] !== maxCount) ticks.push(maxCount);

  $("#chart-y").innerHTML = ticks
    .map((value) => {
      const bottom = (value / maxCount) * 100;
      return `<span style="bottom:${bottom}%">${esc(value)}</span>`;
    })
    .join("");
  $("#chart-grid").innerHTML = ticks
    .map((value) => {
      const bottom = (value / maxCount) * 100;
      return `<span class="gridline" style="bottom:${bottom}%"></span>`;
    })
    .join("");

  const alertIndex = weeks.findIndex((week) => week.week === series.alert.week);
  const recallDate = series.recall.report_date;
  let recallIndex = weeks.findIndex((week) => week.week >= recallDate);
  if (recallIndex < 0) recallIndex = weeks.length - 1;

  $("#chart-bars").innerHTML = countsByWeek
    .map((count, index) => {
      const height = (count / maxCount) * 100;
      const isAlert = index === alertIndex ? " is-alert" : "";
      return `<span class="bar${isAlert}" style="height:${height.toFixed(2)}%"></span>`;
    })
    .join("");

  if (alertIndex >= 0) {
    $("#marker-alert").style.left = `${((alertIndex + 0.5) / totalWeeks) * 100}%`;
    const windowWeeks = Math.round(Number(trend.backtest.method.recall_window_days || 365) / 7);
    const end = Math.min(alertIndex + windowWeeks, totalWeeks - 1);
    const windowBox = $("#chart-window");
    windowBox.style.left = `${(alertIndex / totalWeeks) * 100}%`;
    windowBox.style.width = `${((end - alertIndex + 1) / totalWeeks) * 100}%`;
  } else {
    $("#marker-alert").style.display = "none";
    $("#chart-window").style.display = "none";
  }
  if (recallIndex >= 0) {
    $("#marker-recall").style.left = `${((recallIndex + 0.5) / totalWeeks) * 100}%`;
  } else {
    $("#marker-recall").style.display = "none";
  }

  const years = new Map();
  weeks.forEach((week, index) => {
    const year = String(week.week).slice(0, 4);
    if (year && !years.has(year)) years.set(year, index);
  });
  $("#chart-x").innerHTML = Array.from(years.entries())
    .map(([year, index]) => {
      const left = (index / totalWeeks) * 100;
      return `<span class="year-label" style="left:${left}%">${esc(year)}</span>`;
    })
    .join("");

  $("#legend-alert").textContent = `${series.alert.week} · ${fmt.int(
    series.alert.count,
  )} complaints`;
  $("#legend-recall").textContent = `${series.recall.report_date} · +${fmt.int(
    series.recall.lead_days,
  )} days`;
  $("#example-reading").textContent = series.reading;

  $("#weekly-data").innerHTML = weeks.map(week => `<tr><th scope="row">${esc(week.week)}</th><td>${fmt.int(week.count)}</td><td>${week.week === series.alert.week ? "Alert week" : week.week === weeks[recallIndex]?.week ? `Recall ${esc(series.recall.report_date)}` : "—"}</td></tr>`).join("");
  $("#trend-method").textContent = `Rule: ${backtest.method.rule}. Backtest: ${backtest.method.base_rate}; ${fmt.int(backtest.method.recall_window_days)}-day window. Median lead time for alerts preceding a recall: ${fmt.int(backtest.alerts.median_lead_days)} days. The trend signal is weak and does not establish an early-warning system.`;
  const download = $("#download-evidence");
  const blobURL = URL.createObjectURL(new Blob([JSON.stringify(DATA, null, 2)], { type: "application/json" }));
  download.href = blobURL;
  download.hidden = false;
  addEventListener("pagehide", event => { if (!event.persisted) URL.revokeObjectURL(blobURL); });
})();
