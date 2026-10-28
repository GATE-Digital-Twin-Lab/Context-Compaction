// Potion Garden UI: turns drags and clicks into the agent's JSON calls and shows the conversation.
// The board shows only what the agent can see (gardenView), never the true garden or potion details.

(() => {
  const { Game, PLANTS, LABELS, DATA, pyDumps, gardenView, describeGoal } = PG;
  const SAVE_KEY = "potion-garden/save-v1";
  const CONFIG_KEY = "potion-garden/config-v1";
  const $ = (id) => document.getElementById(id);

  let game = null;
  let dragging = null; // {kind: "seed" | "plant" | "potion", value}
  const ui = {
    staged: {},       // plot -> plant, sent with the next plant action
    seed: null,       // seed packet picked by click
    recipes: [{}],    // cauldron: plant -> count, one object per recipe
    active: 0,        // recipe that clicked plants go to
    logGarden: false,
    entries: [],      // log book: {id, labels: plant -> label}
    lookup: [],       // plants picked for kb_lookup
    rendered: 0,      // conversation messages already on screen
  };

  // --- plant glyphs ---------------------------------------------------------------

  const STEM = "#5b7f3e";
  const LOOK = {
    mint: { shape: "leaf", color: "#49b37f" },
    elderberry: { shape: "berry", color: "#5b3f8c" },
    nettle: { shape: "nettle", color: "#6f8f2a" },
    sage: { shape: "leaf", color: "#93ab9c" },
    chamomile: { shape: "flower", color: "#ffffff", center: "#f2c94c" },
    dill: { shape: "umbel", color: "#c9c84a" },
    basil: { shape: "round", color: "#2e8b3e" },
    rosemary: { shape: "sprig", color: "#4f7d6b", center: "#8aa4e0" },
  };

  function glyph(plant, cls = "") {
    const L = LOOK[plant];
    const c = L.color;
    const stem = `<path d="M16 30V13" stroke="${STEM}" stroke-width="2" stroke-linecap="round"/>`;
    let art;
    switch (L.shape) {
      case "leaf":
        art = `${stem}<path d="M16 17C8 16 4.5 10 5.5 4.5c6.5-.2 11.4 4.2 10.5 12.5z" fill="${c}"/>
          <path d="M16 21c7.5.2 11.4-5 10.6-10.6-6.4.2-11 4.4-10.6 10.6z" fill="${c}" opacity=".8"/>`;
        break;
      case "round":
        art = `${stem}<ellipse cx="10.5" cy="13" rx="6" ry="7.5" transform="rotate(-30 10.5 13)" fill="${c}"/>
          <ellipse cx="21.5" cy="15.5" rx="6" ry="7.5" transform="rotate(30 21.5 15.5)" fill="${c}" opacity=".85"/>`;
        break;
      case "nettle":
        art = `${stem}<path d="M16 18 9 16l2-2-4-1 3-2-3-2 4-1-1-3 4 2 1-4 2 5z" fill="${c}"/>
          <path d="M16 22l7-2-2-2 4-1-3-2 3-2-4-1 1-3-4 2-1-3-1 6z" fill="${c}" opacity=".8"/>`;
        break;
      case "berry":
        art = `<path d="M16 30V18M16 18l-5-6M16 18l5-5M16 18v-9" stroke="${STEM}" stroke-width="1.8" fill="none" stroke-linecap="round"/>
          <circle cx="10" cy="12" r="3.4" fill="${c}"/><circle cx="21.5" cy="12.5" r="3.4" fill="${c}"/>
          <circle cx="16" cy="8" r="3.4" fill="${c}"/><circle cx="13" cy="16" r="3" fill="${c}" opacity=".85"/>
          <circle cx="19" cy="16.5" r="3" fill="${c}" opacity=".85"/>`;
        break;
      case "flower": {
        const petals = [0, 60, 120, 180, 240, 300]
          .map((a) => `<ellipse cx="16" cy="6.5" rx="3" ry="5" transform="rotate(${a} 16 12)" fill="${c}" stroke="#d8d2c0" stroke-width=".6"/>`)
          .join("");
        art = `<path d="M16 30V16" stroke="${STEM}" stroke-width="2" stroke-linecap="round"/>${petals}<circle cx="16" cy="12" r="3.6" fill="${L.center}"/>`;
        break;
      }
      case "umbel": {
        const rays = [-50, -25, 0, 25, 50]
          .map((a) => `<path d="M16 16 16 6" transform="rotate(${a} 16 16)" stroke="${STEM}" stroke-width="1.2"/>`)
          .join("");
        const dots = [-50, -25, 0, 25, 50]
          .map((a) => `<circle cx="16" cy="5.5" r="2.4" transform="rotate(${a} 16 16)" fill="${c}"/>`)
          .join("");
        art = `<path d="M16 30V16" stroke="${STEM}" stroke-width="2" stroke-linecap="round"/>${rays}${dots}`;
        break;
      }
      default: { // sprig
        const needles = [6, 10, 14, 18, 22]
          .map((y) => `<path d="M16 ${y + 2}l-6-3M16 ${y + 2}l6-3" stroke="${c}" stroke-width="2.2" stroke-linecap="round"/>`)
          .join("");
        art = `<path d="M16 30V4" stroke="${STEM}" stroke-width="2" stroke-linecap="round"/>${needles}
          <circle cx="16" cy="4" r="2" fill="${L.center}"/>`;
      }
    }
    return `<svg viewBox="0 0 32 32" class="${cls}" aria-hidden="true">${art}</svg>`;
  }

  // Plots whose planting is not logged: the agent sees only that something grows.
  const SPROUT = `<svg viewBox="0 0 32 32" class="glyph" aria-hidden="true"><path d="M16 30V18" stroke="${STEM}" stroke-width="2" stroke-linecap="round"/>
    <path d="M16 20c-5 0-8-3-8-7 4 0 8 2 8 7zM16 19c5 0 8-3 8-7-4 0-8 2-8 7z" fill="#9bbf7a"/></svg>`;
  const BUD = `<svg viewBox="0 0 32 32" class="glyph" aria-hidden="true"><path d="M16 30V16" stroke="${STEM}" stroke-width="2" stroke-linecap="round"/>
    <path d="M16 20c-4 0-6-2-6-5M16 20c4 0 6-2 6-5" stroke="#9bbf7a" stroke-width="2" fill="none"/>
    <ellipse cx="16" cy="10" rx="6" ry="8" fill="#e9c46a"/><text x="16" y="14" text-anchor="middle" font-size="10" font-weight="700" fill="#6d5139">?</text></svg>`;

  // --- helpers --------------------------------------------------------------------

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const nonEmpty = (r) => Object.keys(r).length > 0;
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  let toastTimer;
  function toast(text) {
    const el = $("toast");
    el.textContent = text;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
  }

  function save() {
    try {
      localStorage.setItem(SAVE_KEY, JSON.stringify({ state: game.s, drafts: { ...ui, seed: null, rendered: 0 } }));
    } catch { /* storage unavailable: the game still works, it just won't survive a reload */ }
  }

  function load() {
    try {
      const data = JSON.parse(localStorage.getItem(SAVE_KEY));
      if (!data || !data.state || !data.state.world) return false;
      game = new Game(data.state);
      Object.assign(ui, data.drafts || {}, { seed: null, rendered: 0 });
      return true;
    } catch {
      return false;
    }
  }

  // --- sending calls ----------------------------------------------------------------

  function send(call) {
    if (!game || game.over) return null;
    const res = game.call(call, $("notes").value);
    $("notes").value = "";
    if (res.error) toast(res.text);
    save();
    render();
    if (game.over) setTimeout(showResults, 400);
    return res;
  }

  function plantAction() {
    const plots = Object.keys(ui.staged).map(Number).sort((a, b) => a - b);
    if (!plots.length) return;
    const call = { action: "plant", plots: Object.fromEntries(plots.map((p) => [String(p), ui.staged[p]])) };
    if (send(call)) ui.staged = {};
    render();
  }

  function brewAction() {
    const recipes = ui.recipes.filter(nonEmpty);
    if (!recipes.length) return;
    const call = recipes.length === 1 ? { action: "brew", recipe: recipes[0] } : { action: "brew", recipes };
    const res = send(call);
    if (res && !res.error) {
      ui.recipes = [{}];
      ui.active = 0;
      render();
    }
  }

  function logAction() {
    const call = { action: "log" };
    if (ui.logGarden) call.garden = true;
    if (ui.entries.length) call.potions = ui.entries.map((e) => ({ id: e.id, labels: e.labels }));
    if (!call.garden && !call.potions) return;
    const res = send(call);
    if (res && !res.error) {
      ui.logGarden = false;
      ui.entries = [];
      render();
    }
  }

  function lookupAction() {
    if (!ui.lookup.length) return toast("Pick one or more plants to look up.");
    const plants = PLANTS.filter((p) => ui.lookup.includes(p));
    if (send({ tool: "kb_lookup", plants })) ui.lookup = [];
    render();
  }

  function rawAction() {
    const text = $("rawCall").value.trim();
    if (!text) return;
    if (send(text)) $("rawCall").value = "";
  }

  // --- drafts -------------------------------------------------------------------------

  function stage(plot, plant) {
    ui.staged[plot] = plant;
    render();
  }

  function addToRecipe(plant, index = ui.active) {
    const recipe = ui.recipes[index];
    recipe[plant] = (recipe[plant] || 0) + 1;
    ui.active = index;
    render();
  }

  function addEntry(id) {
    if (!ui.entries.some((e) => e.id === id)) ui.entries.push({ id, labels: {} });
    render();
  }

  const CYCLE = ["higher", "lower", "odd", "even", "present", null];
  function cycleLabel(entry, plant) {
    const next = CYCLE[(CYCLE.indexOf(entry.labels[plant] ?? null) + 1) % CYCLE.length];
    if (next === null) delete entry.labels[plant];
    else entry.labels[plant] = next;
    render();
  }

  // --- rendering ------------------------------------------------------------------------

  function render() {
    if (!game) return;
    const w = game.world;
    const over = game.over;
    $("turnBadge").textContent = over ? `Episode over · ${plural(w.turn - 1, "turn")}` : `Turn ${w.turn}`;
    $("btnResults").hidden = !over;
    renderSeeds();
    renderGarden();
    renderInventory();
    renderRecipes();
    renderLog();
    renderLookup();
    renderConvo();
    $("btnPlant").disabled = over || !Object.keys(ui.staged).length;
    $("btnPlant").innerHTML = `Plant${Object.keys(ui.staged).length ? " " + Object.keys(ui.staged).length : ""} <span class="cost">1 turn</span>`;
    $("btnClearStaged").disabled = !Object.keys(ui.staged).length;
    const n = ui.recipes.filter(nonEmpty).length;
    $("btnBrew").disabled = over || !n;
    $("btnBrew").innerHTML = `Brew${n > 1 ? " " + n + " potions" : ""} <span class="cost">1 turn</span>`;
    $("btnLog").disabled = over || (!ui.logGarden && !ui.entries.length);
    for (const id of ["btnGather", "btnInventory", "btnLookup", "btnSkip", "btnRaw", "btnAddRecipe"]) $(id).disabled = over;
    $("logGarden").checked = ui.logGarden;
  }

  function renderSeeds() {
    $("seedShelf").innerHTML = PLANTS.map((p) =>
      `<div class="seed${ui.seed === p ? " selected" : ""}" draggable="true" data-seed="${p}" title="Seeds: ${p}">${glyph(p)}${p}</div>`
    ).join("");
  }

  function renderGarden() {
    const view = gardenView(game.world);
    const cells = {};
    for (const plot of view.free) {
      const plant = ui.staged[plot];
      cells[plot] = plant
        ? `<div class="plot staged" data-plot="${plot}" title="Click to unstage"><span class="num">${plot}</span>${glyph(plant, "glyph")}
            <div class="label">${plant}</div><div class="meta">to plant</div></div>`
        : `<div class="plot free" data-plot="${plot}"><span class="num">${plot}</span><div class="meta">free</div></div>`;
    }
    for (const g of view.growing) {
      const left = g.turns_left !== null ? plural(g.turns_left, "turn") + " left" : "growing";
      cells[g.plot] = `<div class="plot growing"><span class="num">${g.plot}</span>${g.plant ? glyph(g.plant, "glyph") : SPROUT}
        ${g.plant ? `<div class="label">${g.plant}</div>` : ""}<div class="meta">${left}</div></div>`;
    }
    for (const r of view.ready) {
      cells[r.plot] = `<div class="plot ready"><span class="num">${r.plot}</span>${r.plant ? glyph(r.plant, "glyph") : BUD}
        ${r.plant ? `<div class="label">${r.plant}</div>` : ""}<div class="meta">ready · waiting ${r.waiting}</div></div>`;
    }
    $("garden").innerHTML = Object.keys(cells).map(Number).sort((a, b) => a - b).map((p) => cells[p]).join("");
  }

  function renderInventory() {
    const inv = game.world.inventory;
    const plants = Object.keys(inv.plants).sort();
    $("invPlants").innerHTML = plants.length
      ? plants.map((p) => `<span class="chip" draggable="true" data-plant="${p}" title="Click or drag into the cauldron">${glyph(p)}${p} <span class="count">${inv.plants[p]}</span></span>`).join("")
      : `<span class="empty">No plants. Gather ready plots.</span>`;
    $("invPotions").innerHTML = inv.potions.length
      ? inv.potions.map((p) => `<span class="chip potion${p.logged ? " logged" : ""}" draggable="true" data-potion="${p.id}" title="Click or drag into the log book"><span class="dot"></span>#${p.id}</span>`).join("")
      : `<span class="empty">No potions yet.</span>`;
  }

  function recipeTotals() {
    const total = {};
    for (const r of ui.recipes) for (const [p, n] of Object.entries(r)) total[p] = (total[p] || 0) + n;
    return total;
  }

  function renderRecipes() {
    const have = game.world.inventory.plants;
    const total = recipeTotals();
    $("recipes").innerHTML = ui.recipes.map((recipe, i) => {
      const plants = Object.keys(recipe);
      const rows = plants.map((p) => {
        const short = total[p] > (have[p] || 0);
        return `<div class="ing">${glyph(p)}<span class="name">${p}</span>
          <span class="hint" style="${short ? "color:var(--warn)" : ""}">have ${have[p] || 0}</span>
          <span class="stepper"><button data-dec="${i}:${p}">−</button><span class="n">${recipe[p]}</span><button data-inc="${i}:${p}">+</button></span></div>`;
      }).join("");
      const count = plants.length;
      const status = count === 0 ? "drop plants here" : count < 3 ? `${count} plant${count > 1 ? "s" : ""}, need 3–4` : count > 4 ? `${count} plants, max 4` : `${count} plants`;
      return `<div class="recipe${i === ui.active ? " active" : ""}" data-recipe="${i}">
        <div class="recipe-head">Recipe ${i + 1} · ${status}${ui.recipes.length > 1 || count ? `<button class="x" data-del-recipe="${i}" title="Remove">×</button>` : ""}</div>
        ${rows}</div>`;
    }).join("");
  }

  function renderLog() {
    $("logEntries").innerHTML = ui.entries.length
      ? ui.entries.map((e, i) => {
        const labs = PLANTS.map((p) => {
          const l = e.labels[p];
          return `<button class="lab${l ? " set" : ""}" data-entry="${i}" data-lab="${p}">${l ? `<b>${l}</b> ` : ""}${p}</button>`;
        }).join("");
        return `<div class="entry"><div class="entry-head"><span class="dot"></span>Potion #${e.id}
          <button class="x" data-del-entry="${i}" title="Remove">×</button></div><div class="labels">${labs}</div></div>`;
      }).join("")
      : `<span class="empty">Drop potions here. Label only plants the potion contains (${LABELS.join(", ")}); unlabelled ones count as present.</span>`;
  }

  function renderLookup() {
    $("lookupPlants").innerHTML = PLANTS.map((p) => `<span class="chip${ui.lookup.includes(p) ? " on" : ""}" data-look="${p}">${p}</span>`).join("");
  }

  function renderConvo() {
    const box = $("convo");
    const messages = game.s.messages;
    if (ui.rendered === 0 || ui.rendered > messages.length) {
      box.innerHTML = `<div class="msg system"><div class="who" title="Click to expand">System prompt ▸</div><div class="body">${promptHtml()}</div></div>`;
      ui.rendered = 0;
      ui.lastTurn = null;
    }
    const roles = { user: "User", environment: "Environment", agent: "You" };
    let html = "";
    for (const m of messages.slice(ui.rendered)) {
      if (m.turn !== ui.lastTurn) {
        html += `<div class="turn-sep">turn ${m.turn}</div>`;
        ui.lastTurn = m.turn;
      }
      html += `<div class="msg ${m.role}${m.error ? " failed" : ""}"><div class="who">${roles[m.role] || m.role}</div><div class="body">${esc(m.content)}</div></div>`;
    }
    if (html) {
      box.insertAdjacentHTML("beforeend", html);
      box.scrollTop = box.scrollHeight;
    }
    ui.rendered = messages.length;
  }

  // The system prompt as a small subset of Markdown: headings, lists, examples.
  function promptHtml() {
    const inline = (s) => esc(s).replace(/(\{(?:[^{}]|\{[^{}]*\})*\})/g, "<code>$1</code>");
    const isExample = (s) => /^(\[Turn|Garden:|New facts:|Plan:|\{)/.test(s);
    let html = "", list = null;
    const close = () => { if (list) { html += `</${list}>`; list = null; } };
    for (const line of DATA.SYSTEM_PROMPT.split("\n")) {
      if (!line.trim()) { close(); continue; }
      let m;
      if ((m = line.match(/^# (.*)/))) { close(); html += `<h3>${esc(m[1])}</h3>`; }
      else if ((m = line.match(/^- (.*)/))) { if (list !== "ul") { close(); html += "<ul>"; list = "ul"; } html += `<li>${inline(m[1])}</li>`; }
      else if ((m = line.match(/^\d+\. (.*)/))) { if (list !== "ol") { close(); html += "<ol>"; list = "ol"; } html += `<li>${inline(m[1])}</li>`; }
      else if (isExample(line)) { close(); html += `<pre>${esc(line)}</pre>`; }
      else { close(); html += `<p>${inline(line)}</p>`; }
    }
    close();
    return html.replace(/<\/pre><pre>/g, "\n");
  }

  // --- results ------------------------------------------------------------------------------

  function recipeText(r) {
    return Object.entries(r).map(([p, n]) => `${p} ${n}`).join(", ");
  }

  function effectText(e) {
    const [pos] = Object.entries(e.positive), [neg] = Object.entries(e.negative);
    if (pos) return `+${pos[0]} ${pos[1]}%`;
    if (neg) return `−${neg[0]} ${neg[1]}%`;
    return "no effect";
  }

  function showResults() {
    const s = game.summary();
    const w = game.world;
    const actions = game.s.actions;
    const kinds = {};
    for (const a of actions) {
      if (a.error) continue;
      const name = typeof a.call === "object" && a.call ? a.call.action || a.call.tool : "raw";
      kinds[name] = (kinds[name] || 0) + 1;
    }
    const errors = actions.filter((a) => a.error).length;
    $("resultsTitle").textContent = game.over ? "Episode over" : "Results so far";
    const goals = s.goals.map((g) => `<div class="goal-card"><span class="badge ${g.success ? "ok" : "fail"}">${g.success ? "Success" : "Failed"}</span>
      <div class="desc"><b>${esc(g.description)}</b><div class="hint">turns ${g.start_turn}–${g.end_turn} (${plural(g.turns_used, "turn")})
      · best ${g.best_potion ? `#${g.best_potion.id} ${recipeText(g.best_potion.recipe)} → +${g.best_intensity}%` : "none"}
      ${g.allergy_violations ? ` · <span style="color:var(--warn)">${plural(g.allergy_violations, "allergy violation")}</span>` : ""}</div></div></div>`).join("");
    const pending = [s.goal_in_progress, ...s.goals_not_started].filter(Boolean)
      .map((g) => `<div class="goal-card"><span class="badge fail">Open</span><div class="desc">${esc(describeGoal(g))}</div></div>`).join("");
    const stat = (v, k) => `<div class="stat"><div class="v">${v}</div><div class="k">${k}</div></div>`;
    const potions = w.inventory.potions.map((p) => `<tr><td>#${p.id}</td><td class="num">${p.turn}</td><td>${recipeText(p.recipe)}</td>
      <td>${effectText(p.effect)}${w.allergy && w.allergy.every((a) => a in p.recipe) ? ` <span style="color:var(--warn)">(allergy)</span>` : ""}</td><td>${p.logged ? "yes" : ""}</td></tr>`).join("");
    const growth = PLANTS.map((p) => `<tr><td>${glyph(p)} ${p}</td><td class="num">${plural(w.growth[p], "turn")}</td><td>${p in w.kb.growth ? "logged" : ""}</td></tr>`).join("");
    $("resultsBody").innerHTML = `
      ${goals}${pending}
      <div class="stats">${stat(s.turns_played, "turns played")}${stat(w.inventory.potions.length, "potions")}${stat(kinds.plant || 0, "plant actions")}
        ${stat(kinds.log || 0, "logs")}${stat(kinds.skip || 0, "skips")}${stat(errors, "errors")}</div>
      <h3>Potions brewed</h3>
      ${potions ? `<table class="res"><tr><th>Potion</th><th class="num">Turn</th><th>Recipe</th><th>Effect</th><th>Logged</th></tr>${potions}</table>` : `<p class="muted">None.</p>`}
      <details><summary>Hidden growth times in this garden (seed ${game.s.config.env_seed})</summary>
        <table class="res"><tr><th>Plant</th><th class="num">Growth</th><th>In KB</th></tr>${growth}</table></details>`;
    for (const svg of $("resultsBody").querySelectorAll("td svg")) Object.assign(svg.style, { width: "18px", height: "18px", verticalAlign: "middle" });
    $("dlgResults").showModal();
  }

  function download(name, text, type) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type }));
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  function runFiles() {
    const c = game.s.config;
    const params = {
      run_id: game.s.started, agent: "human", garden_size: c.garden_size, growth_min: c.growth_min, growth_max: c.growth_max,
      env_seed: c.env_seed, goals: c.goals, allergy: c.allergy, lore: c.lore, turn_cap: c.turn_cap, compactor: "none",
      growth_times: game.world.growth,
    };
    return { params, summary: game.summary(), actions: game.s.actions, final_state: game.world, transcript: game.transcriptMarkdown() };
  }

  // --- setup and briefing ----------------------------------------------------------------------

  function openSetup() {
    let last = {};
    try { last = JSON.parse(localStorage.getItem(CONFIG_KEY)) || {}; } catch { /* first game */ }
    const d = { ...DATA.DEFAULTS, ...last };
    const f = $("setupForm");
    for (const key of ["garden_size", "turn_cap", "growth_min", "growth_max", "goals", "allergy"]) f.elements[key].value = d[key];
    f.elements.env_seed.value = "";
    f.elements.lore.checked = d.lore;
    $("setupError").textContent = "";
    $("btnSetupCancel").hidden = !game;
    $("dlgSetup").showModal();
  }

  function startFromForm(event) {
    event.preventDefault();
    const f = $("setupForm").elements;
    const num = (k) => parseInt(f[k].value, 10);
    try {
      const raw = {
        garden_size: num("garden_size"), turn_cap: num("turn_cap"), growth_min: num("growth_min"), growth_max: num("growth_max"),
        goals: f.goals.value.trim(), allergy: f.allergy.value.trim() || "none", lore: f.lore.checked,
      };
      if (!(raw.garden_size >= 1)) throw new Error("Garden size must be at least 1.");
      if (!(raw.turn_cap >= 1)) throw new Error("Turn cap must be at least 1.");
      if (!(raw.growth_min >= 1 && raw.growth_min <= raw.growth_max)) throw new Error("Need 1 ≤ growth min ≤ growth max.");
      const goals = raw.goals.split(",").filter((g) => g.trim()).map(PG.parseGoal);
      if (!goals.length) throw new Error("At least one goal is required.");
      const allergy = PG.parseAllergy(raw.allergy, goals);
      const seedText = f.env_seed.value.trim();
      if (seedText && !/^\d+$/.test(seedText)) throw new Error("The seed must be a whole number (or empty for random).");
      const env_seed = seedText ? Number(seedText) : Math.floor(Math.random() * 2 ** 31);
      try { localStorage.setItem(CONFIG_KEY, JSON.stringify(raw)); } catch { /* not saved */ }
      game = Game.create({ ...raw, goals, allergy, env_seed });
    } catch (err) {
      $("setupError").textContent = err.message;
      return;
    }
    Object.assign(ui, { staged: {}, seed: null, recipes: [{}], active: 0, logGarden: false, entries: [], lookup: [], rendered: 0 });
    $("notes").value = "";
    $("dlgSetup").close();
    save();
    render();
    openBriefing();
  }

  function openBriefing(tab = "howto") {
    $("tabPrompt").innerHTML = promptHtml();
    showTab(tab);
    $("dlgBriefing").showModal();
  }

  function showTab(tab) {
    for (const b of document.querySelectorAll(".tab")) b.classList.toggle("active", b.dataset.tab === tab);
    $("tabHowto").hidden = tab !== "howto";
    $("tabPrompt").hidden = tab !== "prompt";
  }

  // --- events --------------------------------------------------------------------------------

  function wire() {
    $("btnPlant").onclick = plantAction;
    $("btnClearStaged").onclick = () => { ui.staged = {}; render(); };
    $("btnBrew").onclick = brewAction;
    $("btnLog").onclick = logAction;
    $("btnLookup").onclick = lookupAction;
    $("btnGather").onclick = () => send({ tool: "gather" });
    $("btnInventory").onclick = () => send({ tool: "inventory" });
    $("btnSkip").onclick = () => send({ action: "skip" });
    $("btnRaw").onclick = rawAction;
    $("rawCall").onkeydown = (e) => { if (e.key === "Enter") rawAction(); };
    $("notes").onkeydown = (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("notes").blur(); };
    $("btnAddRecipe").onclick = () => { ui.recipes.push({}); ui.active = ui.recipes.length - 1; render(); };
    $("logGarden").onchange = (e) => { ui.logGarden = e.target.checked; render(); };
    $("btnNew").onclick = openSetup;
    $("btnBriefing").onclick = () => openBriefing();
    $("btnBriefingClose").onclick = () => $("dlgBriefing").close();
    $("btnResults").onclick = showResults;
    $("btnResultsClose").onclick = () => $("dlgResults").close();
    $("btnResultsNew").onclick = () => { $("dlgResults").close(); openSetup(); };
    $("btnSetupCancel").onclick = () => $("dlgSetup").close();
    $("setupForm").onsubmit = startFromForm;
    $("dlgSetup").oncancel = (e) => { if (!game) e.preventDefault(); };
    $("btnDlTranscript").onclick = () => download("transcript.md", game.transcriptMarkdown(), "text/markdown");
    $("btnDlRun").onclick = () => download("run.json", JSON.stringify(runFiles(), null, 2), "application/json");
    for (const b of document.querySelectorAll(".tab")) b.onclick = () => showTab(b.dataset.tab);

    // Clicks (also the touch-friendly path for everything you can drag).
    document.addEventListener("click", (e) => {
      const t = e.target.closest("[data-seed],[data-plot],[data-plant],[data-potion],[data-inc],[data-dec],[data-del-recipe],[data-recipe],[data-lab],[data-del-entry],[data-look],.msg.system .who");
      if (!t || !game) return;
      const d = t.dataset;
      if (d.seed) { ui.seed = ui.seed === d.seed ? null : d.seed; render(); }
      else if (d.plot) {
        const plot = Number(d.plot);
        if (ui.staged[plot] && (!ui.seed || ui.seed === ui.staged[plot])) { delete ui.staged[plot]; render(); }
        else if (ui.seed) stage(plot, ui.seed);
        else toast("Pick a seed packet first, or drag one here.");
      }
      else if (d.plant) addToRecipe(d.plant);
      else if (d.potion) addEntry(Number(d.potion));
      else if (d.inc || d.dec) {
        const [i, p] = (d.inc || d.dec).split(":");
        const r = ui.recipes[i];
        r[p] += d.inc ? 1 : -1;
        if (r[p] < 1) delete r[p];
        ui.active = Number(i);
        render();
      }
      else if (d.delRecipe !== undefined) {
        e.stopPropagation();
        ui.recipes.splice(Number(d.delRecipe), 1);
        if (!ui.recipes.length) ui.recipes.push({});
        ui.active = Math.min(ui.active, ui.recipes.length - 1);
        render();
      }
      else if (d.recipe !== undefined) { ui.active = Number(d.recipe); render(); }
      else if (d.lab) cycleLabel(ui.entries[d.entry], d.lab);
      else if (d.delEntry !== undefined) { ui.entries.splice(Number(d.delEntry), 1); render(); }
      else if (d.look) {
        ui.lookup = ui.lookup.includes(d.look) ? ui.lookup.filter((p) => p !== d.look) : [...ui.lookup, d.look];
        render();
      }
      else if (t.matches(".msg.system .who")) {
        const msg = t.parentElement;
        msg.classList.toggle("open");
        t.textContent = msg.classList.contains("open") ? "System prompt ▾" : "System prompt ▸";
      }
    });

    // Drag and drop.
    document.addEventListener("dragstart", (e) => {
      const t = e.target.closest?.("[data-seed],[data-plant],[data-potion]");
      if (!t) return;
      const d = t.dataset;
      dragging = d.seed ? { kind: "seed", value: d.seed } : d.plant ? { kind: "plant", value: d.plant } : { kind: "potion", value: Number(d.potion) };
      e.dataTransfer.setData("text/plain", String(dragging.value));
      e.dataTransfer.effectAllowed = "copy";
    });
    document.addEventListener("dragend", () => {
      dragging = null;
      for (const el of document.querySelectorAll(".drop-ok")) el.classList.remove("drop-ok");
    });
    const target = (e) => {
      if (!dragging) return null;
      if (dragging.kind === "seed") return e.target.closest(".plot.free,.plot.staged");
      if (dragging.kind === "plant") return e.target.closest(".recipe") || e.target.closest("#recipes");
      return e.target.closest("#logEntries");
    };
    document.addEventListener("dragover", (e) => {
      const t = target(e);
      for (const el of document.querySelectorAll(".drop-ok")) if (el !== t) el.classList.remove("drop-ok");
      if (!t) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      t.classList.add("drop-ok");
    });
    document.addEventListener("drop", (e) => {
      const t = target(e);
      if (!t) return;
      e.preventDefault();
      const { kind, value } = dragging;
      dragging = null;
      if (kind === "seed") stage(Number(t.dataset.plot), value);
      else if (kind === "plant") addToRecipe(value, t.dataset.recipe !== undefined ? Number(t.dataset.recipe) : ui.active);
      else addEntry(value);
    });
  }

  wire();
  if (load()) {
    render();
    if (game.over) showResults();
  } else {
    openSetup();
  }
})();
