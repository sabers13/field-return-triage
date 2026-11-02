/* Field Return Triage — renders the committed page data. No dependencies, no network.
   Every value below is read from #page-data, which `make page-data` writes from
   results/. Nothing is fetched, and the demo buttons keep their state in memory only. */

(() => {
  "use strict";

  const DATA = JSON.parse(document.getElementById("page-data").textContent);
  const $ = (selector, root = document) => root.querySelector(selector);

  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[character]);

  const fmt = {
    dec(value, digits = 3) {
      return value === null || value === undefined ? "—" : Number(value).toFixed(digits);
    },
    pct(value, digits = 1) {
      return value === null || value === undefined ? "—" : `${(Number(value) * 100).toFixed(digits)}%`;
    },
    money(value) {
      return value === null || value === undefined ? "—" : `$${Number(value).toFixed(4)}`;
    },
    int(value) {
      return value === null || value === undefined ? "—" : Number(value).toLocaleString("en-US");
    },
  };

  const PRIORITY = {
    1: { label: "Priority 1", sub: "Safety first" },
    2: { label: "Priority 2", sub: "Clear clues" },
    3: { label: "Priority 3", sub: "Needs human reading" },
  };

  const FIELD_LABEL = {
    safety: "Safety clue",
    symptoms: "Symptom",
    conditions: "Condition",
    fault_codes: "Fault code",
    mileage: "Mileage",
  };

  /* ---------------------------------------------------------- theme */

  const root = document.documentElement;
  const themeButton = $("#theme-toggle");
  let explicitTheme = false;

  function applyTheme(theme) {
    root.dataset.theme = theme;
    themeButton.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    themeButton.setAttribute(
      "aria-label",
      theme === "dark" ? "Switch to light appearance" : "Switch to dark appearance",
    );
  }

  try {
    const stored = localStorage.getItem("frt-theme");
    if (stored === "light" || stored === "dark") {
      explicitTheme = true;
      applyTheme(stored);
    }
  } catch (error) {
    /* file:// or a privacy mode can refuse storage; the page still works. */
  }

  const scheme = window.matchMedia("(prefers-color-scheme: dark)");
  if (!explicitTheme) applyTheme(scheme.matches ? "dark" : "light");

  themeButton.addEventListener("click", () => {
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    explicitTheme = true;
    applyTheme(next);
    try {
      localStorage.setItem("frt-theme", next);
    } catch (error) {
      /* no storage, no problem */
    }
  });

  if (typeof scheme.addEventListener === "function") {
    scheme.addEventListener("change", (event) => {
      if (!explicitTheme) applyTheme(event.matches ? "dark" : "light");
    });
  }

  /* ---------------------------------------------------------- hero */

  const baselineCount = ["group", "safety", "conditions"].filter(
    (key) => DATA.results.baselines[key] && DATA.results.baselines[key].available,
  ).length;

  const heroStats = [
    [fmt.int(DATA.run.item_count), "complaints evaluated"],
    [String(DATA.results.models.length), "extraction models"],
    [String(baselineCount), "free baselines"],
    [fmt.int(DATA.trend.backtest.alerts.total), "spike alerts backtested"],
  ];

  $("#hero-stats").innerHTML = heroStats
    .map(
      ([value, label]) =>
        `<div class="hero-stat"><dt>${esc(value)}</dt><dd>${esc(label)}</dd></div>`,
    )
    .join("");

  /* ---------------------------------------------------------- queue */

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

  function priorityPill(card) {
    const priority = PRIORITY[card.priority] || { label: "Priority", sub: "" };
    return `<span class="priority-pill">${esc(priority.label)} <span>${esc(priority.sub)}</span></span>`;
  }

  function priorityPillText(card) {
    const priority = PRIORITY[card.priority] || { label: "Priority", sub: "" };
    return `${priority.label}, ${priority.sub}`;
  }

  function cardMeta(card) {
    const vehicle = [card.vehicle.make, card.vehicle.model, card.vehicle.model_year]
      .filter(Boolean)
      .join(" ");
    const pieces = [];
    if (vehicle) pieces.push(`<span>${esc(vehicle)}</span>`);
    if (card.received) pieces.push(`<span>received ${esc(card.received)}</span>`);
    return pieces.join("");
  }

  function neighboursBlock(card) {
    const items = card.neighbours
      .map((neighbour) => {
        const sameGroup = neighbour.group === card.group;
        const groupNote = sameGroup
          ? '<span class="same-group">same group</span>'
          : '<span class="other-group">different group</span>';
        const safety = neighbour.safety_relevant
          ? '<span><span class="safety-dot"></span>safety-relevant</span>'
          : "";
        return `<article class="neighbour">
          <div class="neighbour-top">
            <span class="neighbour-id">#${esc(neighbour.complaint_id)}</span>
            <span class="neighbour-score">${fmt.dec(neighbour.score, 4)}</span>
          </div>
          <div class="neighbour-meta">
            <span>${esc(String(neighbour.group).replace(/_/g, " "))}</span>
            ${groupNote}
            <span>${esc(neighbour.received)}</span>
            ${safety}
          </div>
          <p class="neighbour-excerpt">${esc(neighbour.excerpt)}</p>
        </article>`;
      })
      .join("");
    return `<section class="neighbours" aria-label="Nearest past cases">
      <div class="neighbours-head">
        <h3>${card.neighbours.length} nearest past cases</h3>
        <p>Cosine similarity, four decimals; ties break by complaint id.</p>
      </div>
      <div class="nearest-grid">${items}</div>
    </section>`;
  }

  function reasonsList(reasons) {
    if (!reasons.length) return "";
    return `<ul class="reasons">${reasons
      .map((reason) => {
        const quotes = reason.quotes.length
          ? `<p class="reason-quotes">${reason.quotes
              .map((quote) => `“${esc(quote)}”`)
              .join(" · ")}</p>`
          : "";
        return `<li><p class="reason-text">${esc(reason.text).replace(/_/g, " ")}</p>${quotes}</li>`;
      })
      .join("")}</ul>`;
  }

  function demoBlock(card) {
    return `<div class="demo" data-card-id="${esc(card.card_id)}" data-state="idle" data-priority="${esc(card.priority)}">
      <button class="btn btn-primary" type="button" data-demo="accept">Accept</button>
      <button class="btn" type="button" data-demo="change">Change…</button>
      <span class="demo-note">Demo only · stores nothing</span>
    </div>`;
  }

  function cardHTML(card) {
    const chips = [
      `<span class="chip">${esc(String(card.group).replace(/_/g, " "))}</span>`,
      card.needs_human_review && card.priority !== 3
        ? '<span class="chip chip-human">needs human reading</span>'
        : "",
      card.coded_safety
        ? `<span class="chip chip-safety">coded ${esc(card.coded_flags.join(" / "))}</span>`
        : "",
    ].join("");

    const suggestion = card.suggestion;
    const testChips = suggestion.tests.length
      ? `<div class="test-chips">${suggestion.tests
          .map((test) => `<span class="test-chip">${esc(test)}</span>`)
          .join("")}</div>`
      : "";

    const inspect = suggestion.inspect.length
      ? `<div class="test-block"><p class="block-label">Inspect</p><p class="reason-text">${suggestion.inspect
          .map(esc)
          .join("; ")}</p></div>`
      : "";

    const request = suggestion.request.length
      ? `<div class="test-block"><p class="block-label">Ask for</p><ul class="ask-list">${suggestion.request
          .map((item) => `<li>${esc(item)}</li>`)
          .join("")}</ul></div>`
      : "";

    const routing = card.reasons.length
      ? `<div class="routing"><p class="block-label">Card routing</p>${reasonsList(card.reasons)}</div>`
      : "";

    const noClues = card.clues.length
      ? ""
      : `<p class="no-clues"><strong>No highlighted clues.</strong> ${
          card.needs_human_review
            ? "No quote passed the verbatim check, so the hard rules send this card to human reading."
            : "No quote passed the verbatim check, so the rulebook falls back to the standard test."
        }</p>`;

    const versions = card.versions;
    return `<article class="card" data-priority="${esc(card.priority)}" aria-label="Complaint ${esc(
      card.complaint_id,
    )}, ${esc(priorityPillText(card))}">
      <header class="card-head">
        ${priorityPill(card)}
        <span class="card-id">#${esc(card.complaint_id)}</span>
        ${chips}
        <div class="card-meta">${cardMeta(card)}</div>
      </header>
      <div class="card-body">
        <div class="card-col">
          <p class="col-label">Complaint narrative <span class="quiet">${
            card.clues.length
          } highlighted ${card.clues.length === 1 ? "clue" : "clues"}</span></p>
          <p class="narrative">${highlight(card.narrative, card.clues)}</p>
          ${clueLegend(card.clues)}
          ${noClues}
          ${routing}
        </div>
        <div class="card-col">
          <p class="col-label">Suggested next step <span class="quiet">rulebook</span></p>
          <div class="test-block"><p class="block-label">Test</p>${testChips}</div>
          ${inspect}
          <div class="test-block"><p class="block-label">Why this test</p>${reasonsList(
            suggestion.reasons,
          )}</div>
          ${request}
        </div>
      </div>
      ${neighboursBlock(card)}
      <footer class="card-foot">
        <p class="versions" aria-label="Versions">
          <span>model ${esc(versions.model)}</span>
          <span>prompt ${esc(versions.prompt)}</span>
          <span>rulebook ${esc(versions.rulebook)}</span>
          <span>hard rules ${esc(versions.hard_rules)}</span>
          <span>schema ${esc(versions.schema)}</span>
          <span>quotes ${esc(card.quote_check.passed)}/${esc(card.quote_check.checked)} passed</span>
        </p>
        ${demoBlock(card)}
      </footer>
    </article>`;
  }

  $("#queue-rule").innerHTML = `<strong>Selection rule.</strong> ${esc(DATA.queue.rule)} Cards from <code>${esc(
    DATA.queue.model_id,
  )}</code>.`;

  const counts = DATA.queue.counts;
  const filterOptions = [
    ["all", `All ${DATA.queue.cards.length}`],
    ["1", `${PRIORITY[1].label} ${counts["1"] || 0}`],
    ["2", `${PRIORITY[2].label} ${counts["2"] || 0}`],
    ["3", `${PRIORITY[3].label} ${counts["3"] || 0}`],
  ];

  $("#queue-filters").innerHTML = filterOptions
    .map(
      ([value, label], index) =>
        `<button class="filter" type="button" data-filter="${value}" aria-pressed="${
          index === 0 ? "true" : "false"
        }">${esc(label.replace(/ \d+$/, ""))} <span class="count">${esc(
          label.match(/\d+$/)?.[0] || "",
        )}</span></button>`,
    )
    .join("");

  $("#queue-list").innerHTML = DATA.queue.cards.map(cardHTML).join("");

  const cards = Array.from(document.querySelectorAll("#queue-list .card"));
  $("#queue-filters").addEventListener("click", (event) => {
    const button = event.target.closest("[data-filter]");
    if (!button) return;
    const value = button.dataset.filter;
    for (const other of document.querySelectorAll("#queue-filters .filter")) {
      other.setAttribute("aria-pressed", other === button ? "true" : "false");
    }
    for (const card of cards) {
      card.hidden = value !== "all" && card.dataset.priority !== value;
    }
  });

  /* ---------------------------------------------------------- demo decisions */

  const demoDefaults = new Map();
  for (const demo of document.querySelectorAll(".demo")) {
    demoDefaults.set(demo.dataset.cardId, demo.innerHTML);
  }

  function finishDemo(demo, message) {
    demo.dataset.state = "done";
    demo.innerHTML = `<span class="demo-status">${esc(message)}</span>
      <button class="btn btn-quiet" type="button" data-demo="reset">Reset</button>`;
  }

  function resetDemo(demo) {
    demo.dataset.state = "idle";
    demo.innerHTML = demoDefaults.get(demo.dataset.cardId) || "";
  }

  $("#queue-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-demo]");
    if (!button) return;
    const demo = button.closest(".demo");
    if (!demo) return;

    if (button.dataset.demo === "accept") {
      finishDemo(demo, "Accepted in this demo — nothing was stored.");
    } else if (button.dataset.demo === "reset") {
      resetDemo(demo);
    } else if (button.dataset.demo === "cancel") {
      resetDemo(demo);
    } else if (button.dataset.demo === "change") {
      const selectId = `reason-${demo.dataset.cardId.replace(/[^a-z0-9]+/gi, "-")}`;
      demo.innerHTML = `<form class="change-form">
        <label for="${esc(selectId)}">Reason (not stored)</label>
        <select id="${esc(selectId)}" name="reason">
          <option>Different test is needed</option>
          <option>Wrong component group</option>
          <option>More information is needed</option>
          <option>Other</option>
        </select>
        <button class="btn btn-primary" type="submit">Note change</button>
        <button class="btn btn-quiet" type="button" data-demo="cancel">Cancel</button>
      </form>`;
    }
  });

  $("#queue-list").addEventListener("submit", (event) => {
    if (!event.target.matches(".change-form")) return;
    event.preventDefault();
    const demo = event.target.closest(".demo");
    if (!demo) return;
    finishDemo(demo, "Change noted in this demo — nothing was stored.");
  });

  /* ---------------------------------------------------------- results */

  function withCI(metric, formatter) {
    if (!metric || metric.value === null || metric.value === undefined) {
      return '<span class="value muted-value">—</span>';
    }
    const main = `<span class="value">${esc(formatter(metric.value))}</span>`;
    if (metric.ci_low === null || metric.ci_high === null) return main;
    return `${main}<span class="ci">${esc(formatter(metric.ci_low))}–${esc(
      formatter(metric.ci_high),
    )}</span>`;
  }

  const run = DATA.run;
  $("#run-meta").innerHTML = [
    `run ${esc(run.id)}`,
    esc(run.mode),
    `${fmt.int(run.item_count)} items`,
    `cost ${fmt.money(run.cost_usd)}`,
    `sample sha256 ${esc(String(run.sample_hash).slice(0, 12))}…`,
  ]
    .map((piece) => `<span>${piece}</span>`)
    .join("");

  const models = DATA.results.models;
  $("#models-table-body").innerHTML = models
    .map((model) => {
      const metrics = model.metrics;
      const items = fmt.int(model.items_evaluated);
      const reduced = model.reduced
        ? `<span class="badge">budget cut to ${items} of ${fmt.int(model.items_available)}</span>`
        : "";
      const needsHuman = metrics.routing.needs_human_share;
      return `<tr>
        <td>
          <span class="system-name">${esc(model.model_id)}</span>
          <span class="system-sub">${esc(model.role)} · ${items} items ${reduced}</span>
        </td>
        <td data-label="Macro-F1">${withCI(metrics.group.macro_f1, (value) => fmt.dec(value, 3))}</td>
        <td data-label="Safety recall">${withCI(metrics.safety.final_recall, (value) => fmt.dec(value, 3))}</td>
        <td data-label="Safety precision">${withCI(metrics.safety.final_precision, (value) => fmt.dec(value, 3))}</td>
        <td data-label="Quote grounding">${withCI(metrics.quote_grounding, (value) => fmt.pct(value, 1))}</td>
        <td data-label="Needs human">${withCI(needsHuman, (value) => fmt.pct(value, 1))}</td>
        <td data-label="Cost / 1,000">${withCI(metrics.cost.per_1000_usd, (value) => fmt.money(value))}</td>
      </tr>`;
    })
    .join("");

  const reducedModels = models.filter((model) => model.reduced);
  const cutNote = reducedModels.length
    ? ` ${reducedModels
        .map((model) => `${model.model_id} ran ${fmt.int(model.items_evaluated)} of ${fmt.int(
          model.items_available,
        )} items after the budget cut, so its intervals are wider.`)
        .join(" ")}`
    : "";
  const recallText = models
    .map((model) => fmt.dec(model.metrics.safety.final_recall?.value, 3))
    .join(" / ");
  const precisionText = models
    .map((model) => fmt.dec(model.metrics.safety.final_precision?.value, 3))
    .join(" / ");
  $("#models-note").textContent =
    `Safety is the final hard-rule decision against the coded crash, fire and injury fields. ` +
    `Final recall is ${recallText}; final precision is ${precisionText}. Recall counts the coded ` +
    `safety cases the hard rules caught; precision counts how many flagged cases were coded. ` +
    `Lower precision means a longer reading queue, not a missed safety case.${cutNote}`;

  function barRow(label, kind, value) {
    const width = value === null || value === undefined ? 0 : Math.max(0, Math.min(1, value)) * 100;
    return `<div class="bar-row" data-kind="${esc(kind)}">
      <span class="bar-label">${esc(label)}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${width.toFixed(2)}%"></span></span>
      <span class="bar-value">${fmt.dec(value, 3)}</span>
    </div>`;
  }

  const primary = models.find((model) => model.role === "primary");
  const comparison = models.find((model) => model.role === "comparison");
  const groupBaseline = DATA.results.baselines.group;
  const safetyBaseline = DATA.results.baselines.safety;

  const roleLabel = { primary: "Primary", comparison: "Comparison" };
  $("#glance-group").innerHTML = [
    primary ? barRow(roleLabel.primary, "primary", primary.metrics.group.macro_f1?.value) : "",
    comparison
      ? barRow(roleLabel.comparison, "comparison", comparison.metrics.group.macro_f1?.value)
      : "",
    barRow("TF-IDF baseline", "baseline", groupBaseline.macro_f1?.value),
  ].join("");

  $("#glance-safety").innerHTML = [
    primary
      ? barRow("Primary · recall", "recall", primary.metrics.safety.final_recall?.value)
      : "",
    primary
      ? barRow("Primary · precision", "precision", primary.metrics.safety.final_precision?.value)
      : "",
    comparison
      ? barRow("Comparison · recall", "recall", comparison.metrics.safety.final_recall?.value)
      : "",
    comparison
      ? barRow(
          "Comparison · precision",
          "precision",
          comparison.metrics.safety.final_precision?.value,
        )
      : "",
    barRow("Keyword · recall", "baseline", safetyBaseline.recall?.value),
    barRow("Keyword · precision", "precision-baseline", safetyBaseline.precision?.value),
  ].join("");

  function baselineRow(name, method, score, detail, note) {
    return `<tr>
      <td data-label="Baseline"><span class="baseline-name">${esc(name)}</span><span class="baseline-method">${esc(
        method,
      )}</span></td>
      <td data-label="Metric">${score}</td>
      <td data-label="Detail"><span class="baseline-note">${detail}</span></td>
      <td data-label="Note"><span class="baseline-note">${note}</span></td>
    </tr>`;
  }

  const conditionsBaseline = DATA.results.baselines.conditions;
  $("#baselines-table-body").innerHTML = [
    baselineRow(
      "Component group",
      `${groupBaseline.method}`,
      `<span class="baseline-result">macro-F1 ${fmt.dec(groupBaseline.macro_f1?.value, 3)} (${fmt.dec(
        groupBaseline.macro_f1?.ci_low,
        3,
      )}–${fmt.dec(groupBaseline.macro_f1?.ci_high, 3)})</span>`,
      `Accuracy ${fmt.dec(groupBaseline.accuracy?.value, 3)} (${fmt.dec(
        groupBaseline.accuracy?.ci_low,
        3,
      )}–${fmt.dec(groupBaseline.accuracy?.ci_high, 3)}); coverage ${fmt.dec(
        groupBaseline.coverage?.value,
        3,
      )}.`,
      `Trained on ${fmt.int(groupBaseline.training_items)} past cases. Cost $0.`,
    ),
    baselineRow(
      "Safety",
      `${safetyBaseline.method}`,
      `<span class="baseline-result">recall ${fmt.dec(safetyBaseline.recall?.value, 3)} (${fmt.dec(
        safetyBaseline.recall?.ci_low,
        3,
      )}–${fmt.dec(safetyBaseline.recall?.ci_high, 3)}); precision ${fmt.dec(
        safetyBaseline.precision?.value,
        3,
      )} (${fmt.dec(safetyBaseline.precision?.ci_low, 3)}–${fmt.dec(
        safetyBaseline.precision?.ci_high,
        3,
      )})</span>`,
      `Flagged ${fmt.int(safetyBaseline.predicted_safety_items)} of ${fmt.int(
        safetyBaseline.evaluation_items,
      )} items; ${fmt.int(safetyBaseline.coded_safety_items)} were coded safety-relevant.`,
      "No model call. Cost $0.",
    ),
    baselineRow(
      "Conditions",
      `${conditionsBaseline.method}`,
      `<span class="baseline-result">any condition ${fmt.pct(
        conditionsBaseline.any_condition_share?.value,
        1,
      )} (${fmt.pct(conditionsBaseline.any_condition_share?.ci_low, 1)}–${fmt.pct(
        conditionsBaseline.any_condition_share?.ci_high,
        1,
      )})</span>`,
      `${fmt.int(conditionsBaseline.items_with_any_condition)} of ${fmt.int(
        conditionsBaseline.evaluation_items,
      )} items carry at least one condition.`,
      `<span class="agreement-tag">agreement, not accuracy</span>`,
    ),
  ].join("");

  const source = DATA.results.source;
  const sourceFacts = (model) => {
    const rows = [];
    rows.push(["items", fmt.int(model.items_evaluated)]);
    if (source.card) rows.push(["card", `${source.repo || "which-ai-model"}/${source.card}`]);
    if (source.commit) rows.push(["commit", source.commit]);
    rows.push(["pick", model.picked_on_the_card || model.pick]);
    return rows
      .map(
        ([key, value]) =>
          `<div><dt>${esc(key)}</dt><dd>${esc(value)}</dd></div>`,
      )
      .join("");
  };

  const sourceWhy = (model) => {
    if (model.role === "primary") {
      return `The defect card's <strong>cheapest good-enough</strong> model: the lowest-cost pick that still meets the card's safety floor.`;
    }
    return `The defect card's <strong>most accurate</strong> model on its primary metric.`;
  };

  $("#source-cards").innerHTML = models
    .map(
      (model) => `<article class="source-card">
        <span class="source-role">${esc(roleLabel[model.role] || model.role)} · ${esc(model.pick)}</span>
        <h4>${esc(model.model_id)}</h4>
        <p class="source-why">${sourceWhy(model)}</p>
        <dl class="source-facts">${sourceFacts(model)}</dl>
      </article>`,
    )
    .join("");

  if (source.picker_rule) {
    $("#source-cards").insertAdjacentHTML(
      "afterend",
      `<p class="method-note">Card rule: ${esc(source.picker_rule)} ${
        source.no_model_meets_floor
          ? "The card says no model meets the floor, so safety rests on the hard rules."
          : ""
      }</p>`,
    );
  }

  /* ---------------------------------------------------------- trend */

  const trend = DATA.trend;
  const example = trend.example;
  const weeks = example.weeks;
  const countsByWeek = weeks.map((week) => (typeof week.count === "number" ? week.count : 0));
  const maxCount = Math.max(1, ...countsByWeek);
  const totalWeeks = Math.max(1, weeks.length);

  $("#chart-title").textContent = `${example.series_label} · ${example.group_label.replace(
    /_/g,
    " ",
  )} · ${fmt.int(example.total_complaints)} complaints`;

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

  const alertIndex = weeks.findIndex((week) => week.week === example.alert.week);
  const recallDate = example.recall.report_date;
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

  $("#legend-alert").textContent = `${example.alert.week} · ${fmt.int(
    example.alert.count,
  )} complaints`;
  $("#legend-recall").textContent = `${example.recall.report_date} · +${fmt.int(
    example.recall.lead_days,
  )} days`;
  $("#example-reading").textContent = example.reading;

  const backtest = trend.backtest;
  const base = backtest.base_rate;
  $("#trend-stats").innerHTML = [
    [
      fmt.pct(backtest.alerts.share),
      `alerts followed by a recall (${fmt.int(backtest.alerts.preceding_recall)} of ${fmt.int(
        backtest.alerts.total,
      )})`,
    ],
    [
      fmt.pct(base.share),
      `random same-series weeks (base rate) <span class="ci">${fmt.pct(
        base.ci_low,
      )}–${fmt.pct(base.ci_high)}</span>`,
    ],
    [
      `${fmt.dec(backtest.alerts.median_lead_days, 0)} days`,
      "median lead time from the alert week to the recall",
    ],
  ]
    .map(
      ([value, label]) => `<dl class="stat"><dt>${esc(value)}</dt><dd>${label}</dd></dl>`,
    )
    .join("");

  $("#trend-reading").textContent = backtest.reading;
  $("#trend-method").textContent = `Rule: ${trend.backtest.method.rule}. Backtest: ${
    trend.backtest.method.base_rate
  }, ${fmt.int(trend.backtest.method.recall_window_days)}-day window.`;
})();
