// Potion Garden engine: a port of environment/, tools/ and the turn loop in LLM/episode.py.
// Every message the player sees is word for word what the Python environment sends the agent;
// game/check_parity.py checks this. All state is plain JSON, so a game can be saved and restored.

const PG = (() => {
  const D = typeof PG_DATA !== "undefined" ? PG_DATA : require("./data.js");
  const { PLANTS, STAT_SETS, STAT_NAMES, LEVELS, LABELS, MIN_PLANTS, MAX_PLANTS } = D;

  // --- Python compatibility ----------------------------------------------------

  /** Python's random.Random(seed) (MT19937), enough for randint: same seed, same growth times. */
  class PyRandom {
    constructor(seed) {
      this.mt = new Uint32Array(624);
      this.mti = 625;
      let n = Math.abs(Math.trunc(seed));
      const key = [];
      do {
        key.push(n % 2 ** 32);
        n = Math.floor(n / 2 ** 32);
      } while (n > 0);
      this.initByArray(key);
    }

    initGenrand(s) {
      const mt = this.mt;
      mt[0] = s >>> 0;
      for (let i = 1; i < 624; i++) {
        mt[i] = (Math.imul(1812433253, mt[i - 1] ^ (mt[i - 1] >>> 30)) + i) >>> 0;
      }
      this.mti = 624;
    }

    initByArray(key) {
      const mt = this.mt;
      this.initGenrand(19650218);
      let i = 1, j = 0;
      for (let k = Math.max(624, key.length); k; k--) {
        mt[i] = ((mt[i] ^ Math.imul(mt[i - 1] ^ (mt[i - 1] >>> 30), 1664525)) + key[j] + j) >>> 0;
        i++; j++;
        if (i >= 624) { mt[0] = mt[623]; i = 1; }
        if (j >= key.length) j = 0;
      }
      for (let k = 623; k; k--) {
        mt[i] = ((mt[i] ^ Math.imul(mt[i - 1] ^ (mt[i - 1] >>> 30), 1566083941)) - i) >>> 0;
        i++;
        if (i >= 624) { mt[0] = mt[623]; i = 1; }
      }
      mt[0] = 0x80000000;
    }

    uint32() {
      const mt = this.mt;
      if (this.mti >= 624) {
        const mix = (a, b) => (mt[a] & 0x80000000) | (mt[b] & 0x7fffffff);
        let kk = 0, y;
        for (; kk < 227; kk++) {
          y = mix(kk, kk + 1);
          mt[kk] = mt[kk + 397] ^ (y >>> 1) ^ (y & 1 ? 0x9908b0df : 0);
        }
        for (; kk < 623; kk++) {
          y = mix(kk, kk + 1);
          mt[kk] = mt[kk - 227] ^ (y >>> 1) ^ (y & 1 ? 0x9908b0df : 0);
        }
        y = mix(623, 0);
        mt[623] = mt[396] ^ (y >>> 1) ^ (y & 1 ? 0x9908b0df : 0);
        this.mti = 0;
      }
      let y = mt[this.mti++];
      y ^= y >>> 11;
      y ^= (y << 7) & 0x9d2c5680;
      y ^= (y << 15) & 0xefc60000;
      y ^= y >>> 18;
      return y >>> 0;
    }

    randint(a, b) {
      const n = b - a + 1;
      const k = n.toString(2).length;
      let r;
      do r = this.uint32() >>> (32 - k); while (r >= n);
      return a + r;
    }
  }

  /** Python repr() of a JSON value, for error messages. */
  function pyRepr(v) {
    if (v === null || v === undefined) return "None";
    if (v === true) return "True";
    if (v === false) return "False";
    if (typeof v === "number") return Number.isInteger(v) ? String(v) : String(v);
    if (typeof v === "string") return v.includes("'") && !v.includes('"') ? `"${v}"` : `'${v.replace(/'/g, "\\'")}'`;
    if (Array.isArray(v)) return `[${v.map(pyRepr).join(", ")}]`;
    return `{${Object.entries(v).map(([k, x]) => `${pyRepr(k)}: ${pyRepr(x)}`).join(", ")}}`;
  }

  /** Python str() of a JSON value. */
  const pyStr = (v) => (typeof v === "string" ? v : pyRepr(v));

  /** Python json.dumps() with its default separators and ensure_ascii. */
  function pyDumps(v) {
    if (v === null || v === undefined) return "null";
    if (typeof v === "string") {
      return JSON.stringify(v).replace(/[\u007f-￿]/g, (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
    }
    if (typeof v !== "object") return JSON.stringify(v);
    if (Array.isArray(v)) return `[${v.map(pyDumps).join(", ")}]`;
    return `{${Object.entries(v).map(([k, x]) => `${pyDumps(k)}: ${pyDumps(x)}`).join(", ")}}`;
  }

  const isDict = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  const byNumber = (a, b) => a - b;
  const sortedKeys = (obj) => Object.keys(obj).sort();
  const turns = (n) => (n === 1 ? `${n} turn` : `${n} turns`);

  class ToolError extends Error {}

  // --- brewer (environment/brewer.py) -------------------------------------------

  function intensity(score) {
    if (score <= 0) return 0;
    return LEVELS[Math.min(score, LEVELS.length) - 1];
  }

  // Each rule returns [positive score, negative score]; null means the condition fails.
  const RULES = {
    I: (n) => [n.sage % 2 === 1 ? n.elderberry : null, n.sage % 3 === 0 ? n.elderberry : null],
    S: (n) => [
      n.rosemary % 3 === 2 && n.mint === 2 ? n.chamomile : null,
      n.rosemary % 2 === 1 ? n.chamomile : null,
    ],
    V: (n) => [n.basil % 5 !== 0 && n.nettle % 2 === 0 ? n.basil : null, n.mint === 2 ? n.basil : null],
    D: (n) => [
      n.sage % 2 === 1 ? n.rosemary - n.sage + 1 : null,
      n.sage % 2 === 0 ? n.rosemary + n.sage - 2 : null,
    ],
    W: (n) => [
      n.elderberry === 2 && n.basil % 2 === 1 ? n.dill : null,
      n.basil % 2 === 1 && n.chamomile % 2 === 0 ? n.dill : null,
    ],
  };

  class RecipeError extends Error {}

  function validateRecipe(recipe) {
    for (const [plant, count] of Object.entries(recipe)) {
      if (!PLANTS.includes(plant)) throw new RecipeError(`Unknown plant ${plant}.`);
      if (typeof count !== "number" || !Number.isInteger(count) || count < 1) {
        throw new RecipeError(`Invalid count for ${plant}: ${pyRepr(count)}.`);
      }
    }
    const n = Object.keys(recipe).length;
    if (n < MIN_PLANTS || n > MAX_PLANTS) throw new RecipeError(`A recipe needs ${MIN_PLANTS}–${MAX_PLANTS} distinct plants.`);
  }

  function brew(recipe) {
    validateRecipe(recipe);
    const positive = {}, negative = {};
    for (const [stat, plants] of Object.entries(STAT_SETS)) {
      if (!plants.every((p) => p in recipe)) continue;
      const [ps, ns] = RULES[stat](recipe);
      const pos = ps !== null ? intensity(ps) : 0;
      const neg = ns !== null ? intensity(ns) : 0;
      if (pos && neg) continue; // both hold: they cancel, whatever the magnitudes
      if (pos) positive[stat] = pos;
      else if (neg) negative[stat] = neg;
    }
    return { positive, negative };
  }

  function effectLabel(effect) {
    const pos = Object.keys(effect.positive), neg = Object.keys(effect.negative);
    if (pos.length) return "+" + pos[0];
    if (neg.length) return "-" + neg[0];
    return "none";
  }

  // --- lore (environment/lore.py) -----------------------------------------------

  const pairKey = (a, b) => (a < b ? `${a}+${b}` : `${b}+${a}`);
  const LORE = new Map(D.LORE.map(([a, b, text]) => [pairKey(a, b), { a, b, text }]));

  function pairsAmong(plants) {
    const unique = [...new Set(plants)];
    const keys = [];
    for (let i = 0; i < unique.length; i++) {
      for (let j = i + 1; j < unique.length; j++) {
        const key = pairKey(unique[i], unique[j]);
        if (LORE.has(key)) keys.push(key);
      }
    }
    return keys.sort();
  }

  // --- goals (environment/goals.py) ---------------------------------------------

  function describeGoal(goal) {
    const name = `${STAT_NAMES[goal.stat]} (${goal.stat})`;
    if (goal.kind === "time") return `brew the best ${name} potion you can in ${goal.turns} turns`;
    const article = "aeiou".includes(name[0]) ? "an" : "a";
    return `brew ${article} ${name} potion of at least +${goal.target}% as fast as you can`;
  }

  /** 'time:S:30' or 'target:I:10' (input.py parse_goal). */
  function parseGoal(text) {
    const parts = text.trim().split(":");
    const usage = `Invalid goal "${text}": expected time:<stat>:<turns> or target:<stat>:<percent>.`;
    if (parts.length !== 3 || !/^\d+$/.test(parts[2])) throw new Error(usage);
    const kind = parts[0].toLowerCase(), stat = parts[1].toUpperCase(), value = parseInt(parts[2], 10);
    if (!(stat in STAT_SETS)) throw new Error(`Unknown stat ${stat}.`);
    if (kind === "time") {
      if (value < 1) throw new Error("A time goal needs turns >= 1 and no target.");
      return { kind, stat, turns: value, target: null };
    }
    if (kind === "target") {
      if (value <= 0) throw new Error("A target goal needs a target > 0 and no turn budget.");
      return { kind, stat, turns: null, target: value };
    }
    throw new Error(usage);
  }

  /** 'nettle+chamomile' or 'none' (input.py parse_allergy); returns sorted plants or null. */
  function parseAllergy(text, goals) {
    if (text.trim().toLowerCase() === "none") return null;
    const plants = [...new Set(text.split("+").map((p) => p.trim()))].sort();
    if (plants.length !== 2 || !plants.every((p) => PLANTS.includes(p))) {
      throw new Error(`An allergy needs two known plants, got [${plants.map(pyRepr).join(", ")}].`);
    }
    for (const goal of goals) {
      if (plants.every((p) => STAT_SETS[goal.stat].includes(p))) {
        throw new Error(`Allergy [${plants.map(pyRepr).join(", ")}] makes the ${goal.stat} goal impossible.`);
      }
    }
    return plants;
  }

  const violates = (allergy, recipe) => allergy !== null && allergy.every((p) => p in recipe);

  function scoreGoal(goal, potions, allergy, start, end) {
    let bestId = null, best = 0, violations = 0;
    for (const potion of potions) {
      if (!(start <= potion.turn && potion.turn <= end)) continue;
      if (violates(allergy, potion.recipe)) {
        violations++;
        continue;
      }
      const value = potion.effect.positive[goal.stat] || 0;
      if (value > best) [bestId, best] = [potion.id, value];
    }
    const success = goal.kind === "target" ? best >= goal.target : best > 0;
    return { goal, start_turn: start, end_turn: end, best_potion: bestId, best_intensity: best, success, allergy_violations: violations };
  }

  // --- world (environment/world.py, garden.py, inventory.py, knowledge_base.py) --

  function createWorld(config) {
    const rng = new PyRandom(config.env_seed);
    const growth = {};
    for (const plant of PLANTS) growth[plant] = rng.randint(config.growth_min, config.growth_max);
    return {
      size: config.garden_size,
      growth,
      plots: {}, // plot -> [plant, planted_turn, ready_turn]
      inventory: { plants: {}, potions: [] },
      kb: { growth: {}, plantings: {}, outcomes: [], lore: [] },
      goals: config.goals,
      allergy: config.allergy,
      turn_cap: config.turn_cap,
      lore: config.lore,
      turn: 1,
      goal_index: 0,
      goal_start: 1,
      results: [],
      target_reached: false,
      gathered_this_turn: [],
    };
  }

  const currentGoal = (w) => (w.goal_index < w.goals.length ? w.goals[w.goal_index] : null);
  const episodeOver = (w) => currentGoal(w) === null || w.turn > w.turn_cap;

  /** True garden state: free plots, growing [plot, plant, turns_left], ready [plot, plant, waiting]. */
  function gardenState(w) {
    const free = [], growing = [], ready = [];
    for (let plot = 1; plot <= w.size; plot++) {
      const slot = w.plots[plot];
      if (!slot) free.push(plot);
      else if (w.turn >= slot[2]) ready.push([plot, slot[0], w.turn - slot[2]]);
      else growing.push([plot, slot[0], slot[2] - w.turn]);
    }
    return { free, growing, ready };
  }

  /** The agent's view: names only where the planting is logged, turns left only if growth is too. */
  function gardenView(w) {
    const state = gardenState(w);
    const growing = state.growing.map(([plot, , left]) => {
      const plant = w.kb.plantings[plot] ?? null;
      const known = plant !== null && plant in w.kb.growth;
      return { plot, plant, turns_left: known ? left : null };
    });
    const ready = state.ready.map(([plot, , waiting]) => ({ plot, plant: w.kb.plantings[plot] ?? null, waiting }));
    return { free: state.free, growing, ready };
  }

  function renderGarden(view) {
    const growing = view.growing.map((g) => {
      const details = [g.plant, g.turns_left !== null ? `${turns(g.turns_left)} left` : null].filter(Boolean);
      return details.length ? `${g.plot} (${details.join(", ")})` : String(g.plot);
    });
    const ready = view.ready.map((r) => `${r.plot} (${r.plant ? r.plant + ", " : ""}waiting ${r.waiting})`);
    const free = view.free.join(", ") || "none";
    return `free: ${free}; growing: ${growing.join(", ") || "none"}; ready: ${ready.join(", ") || "none"}`;
  }

  const turnHeader = (w) => `[Turn ${w.turn}]\nGarden: ${renderGarden(gardenView(w))}\nChoose your action.`;

  function renderOutcome(o) {
    const parts = o.labels.map(([plant, label]) => (label === "present" ? plant : `(${label}) ${plant}`));
    return `${parts.join(", ")} → ${o.effect}`;
  }

  function shortages(w, total) {
    const out = [];
    for (const [p, n] of total) {
      const have = w.inventory.plants[p] || 0;
      if (have < n) out.push([p, n, have]);
    }
    return out;
  }

  function brewOne(w, recipe) {
    const inv = w.inventory.plants;
    for (const [p, n] of Object.entries(recipe)) {
      inv[p] -= n;
      if (inv[p] <= 0) delete inv[p];
    }
    const potion = { id: w.inventory.potions.length + 1, recipe: { ...recipe }, effect: brew(recipe), turn: w.turn, logged: false };
    w.inventory.potions.push(potion);
    const goal = currentGoal(w);
    if (goal && goal.kind === "target" && !violates(w.allergy, recipe) && (potion.effect.positive[goal.stat] || 0) >= goal.target) {
      w.target_reached = true;
    }
    return potion;
  }

  function logGarden(w) {
    const state = gardenState(w);
    const candidates = [...state.ready.map((r) => r[1]), ...w.gathered_this_turn];
    const growth = {};
    for (const plant of candidates) if (!(plant in w.kb.growth)) growth[plant] = w.growth[plant];
    const occupied = [...state.ready, ...state.growing].map(([plot, plant]) => [plot, plant]).sort((a, b) => a[0] - b[0]);
    const plantings = occupied.filter(([plot]) => !(plot in w.kb.plantings));
    const sortedGrowth = sortedKeys(growth).map((p) => [p, growth[p]]);
    for (const [p, t] of sortedGrowth) w.kb.growth[p] = t;
    for (const [plot, plant] of plantings) w.kb.plantings[plot] = plant;
    return { growth: sortedGrowth, plantings };
  }

  function endTurn(w) {
    const goal = currentGoal(w);
    let finished = null;
    if (goal !== null) {
      const deadline = goal.kind === "time" && w.turn >= w.goal_start + goal.turns - 1;
      if (w.target_reached || deadline || w.turn >= w.turn_cap) {
        finished = scoreGoal(goal, w.inventory.potions, w.allergy, w.goal_start, w.turn);
        w.results.push(finished);
        w.goal_index++;
        w.goal_start = w.turn + 1;
        w.target_reached = false;
      }
    }
    const over = currentGoal(w) === null || w.turn >= w.turn_cap;
    w.turn++;
    w.gathered_this_turn = [];
    const nextGoal = finished && !over ? currentGoal(w) : null;
    return { finished, next_goal: nextGoal, episode_over: over };
  }

  // --- tools (tools/*.py) ------------------------------------------------------------

  function requireDict(args, key) {
    const value = args[key];
    if (!isDict(value)) throw new ToolError(`"${key}" must be an object.`);
    return value;
  }

  function requireInt(value, what) {
    if (typeof value === "number" && Number.isInteger(value)) return value;
    if (typeof value === "string" && /^\s*[+-]?\d+(_\d+)*\s*$/.test(value)) return parseInt(value.replace(/_/g, ""), 10);
    throw new ToolError(`${what} must be a whole number, got ${pyRepr(value)}.`);
  }

  const result = (text, ends_turn = false, error = false) => ({ text, ends_turn, error });

  function toolPlant(w, args) {
    const raw = requireDict(args, "plots");
    const assignments = new Map();
    for (const [plot, plant] of Object.entries(raw)) {
      if (typeof plant !== "string") throw new ToolError(`Plant for plot ${plot} must be a name like "elderberry".`);
      assignments.set(requireInt(plot, "A plot number"), plant);
    }
    const planted = [], failed = [];
    for (const [plot, plant] of assignments) {
      if (!(plot >= 1 && plot <= w.size)) failed.push([plot, "does not exist"]);
      else if (!(plant in w.growth)) failed.push([plot, `unknown plant ${plant}`]);
      else if (w.plots[plot]) failed.push([plot, "occupied"]);
      else {
        w.plots[plot] = [plant, w.turn, w.turn + w.growth[plant]];
        planted.push([plot, plant]);
      }
    }
    let text = `Planted: ${planted.map(([p, plant]) => `plot ${p} (${plant})`).join(", ") || "nothing"}.`;
    if (failed.length) text += " Failed: " + failed.map(([p, why]) => `plot ${p} (${why})`).join(", ") + ".";
    return result(text, true);
  }

  function toolGather(w) {
    const ready = Object.keys(w.plots).map(Number).sort(byNumber).filter((p) => w.turn >= w.plots[p][2]);
    const counts = {};
    for (const plot of ready) {
      const plant = w.plots[plot][0];
      counts[plant] = (counts[plant] || 0) + 1;
      delete w.plots[plot];
      delete w.kb.plantings[plot];
    }
    const names = sortedKeys(counts);
    for (const plant of names) {
      if (!w.gathered_this_turn.includes(plant)) w.gathered_this_turn.push(plant);
      w.inventory.plants[plant] = (w.inventory.plants[plant] || 0) + counts[plant];
    }
    if (!names.length) return result("Gathered nothing.");
    const items = names.map((p) => `+${counts[p]} ${p}`).join(", ");
    return result(`Gathered: ${items}. Plots now free: ${ready.join(", ")}.`);
  }

  function toolInventory(w) {
    const inv = w.inventory;
    const plants = sortedKeys(inv.plants).map((p) => `${p}: ${inv.plants[p]}`).join(", ") || "none";
    const potions = inv.potions.map((p) => `#${p.id}` + (p.logged ? " (logged)" : "")).join(", ") || "none";
    return result(`plants: ${plants}; potions: ${potions}`);
  }

  function toolKbLookup(w, args) {
    const plants = args.plants;
    if (!Array.isArray(plants) || !plants.length) throw new ToolError('"plants" must be a non-empty list of plant names.');
    const unknown = plants.filter((p) => !PLANTS.includes(p));
    if (unknown.length) throw new ToolError(`Unknown plant ${pyStr(unknown[0])}.`);
    const asked = [...new Set(plants)];
    const grows = asked.map((p) => (p in w.kb.growth ? `${p} ${turns(w.kb.growth[p])}` : `${p} unknown`)).join(", ");
    const outcomes = w.kb.outcomes.filter((o) => o.labels.some(([p]) => asked.includes(p))).map(renderOutcome);
    const sections = [`Growth: ${grows}.`, listed("Interactions", outcomes, "none.")];
    if (w.lore) {
      const lore = w.kb.lore.filter(([a, b]) => asked.includes(a) || asked.includes(b)).map((l) => l[2]);
      sections.push(listed("Lore", lore, "none yet."));
    }
    return result(sections.join("\n"));
  }

  /** 'Title: none.' or the title followed by one '- item' line per item. */
  function listed(title, items, empty) {
    if (!items.length) return `${title}: ${empty}`;
    return [`${title}:`, ...items.map((item) => `- ${item}`)].join("\n");
  }

  function toolLog(w, args) {
    const garden = "garden" in args ? args.garden : false;
    if (typeof garden !== "boolean") throw new ToolError('"garden" must be true or false.');
    const raw = "potions" in args ? args.potions : [];
    if (!Array.isArray(raw)) throw new ToolError('"potions" must be a list.');
    if (!garden && !raw.length) throw new ToolError('Nothing to log: give "garden": true and/or "potions".');
    const potions = new Map();
    for (const entry of raw) {
      if (!isDict(entry) || !isDict("labels" in entry ? entry.labels : {})) {
        throw new ToolError('Each potion entry needs an "id" and an optional "labels" object.');
      }
      potions.set(requireInt("id" in entry ? entry.id : null, "A potion id"), "labels" in entry ? entry.labels : {});
    }
    // Validate everything before writing anything (world.log).
    const entries = [];
    for (const [pid, labels] of potions) {
      if (!(pid >= 1 && pid <= w.inventory.potions.length)) throw new ToolError(`Unknown potion #${pid}.`);
      const potion = w.inventory.potions[pid - 1];
      const extra = Object.keys(labels).filter((p) => !(p in potion.recipe)).sort();
      if (extra.length) throw new ToolError(`Potion #${pid} does not contain ${extra[0]}.`);
      const bad = [...new Set(Object.values(labels))].filter((l) => !LABELS.includes(l)).map(pyStr).sort();
      if (bad.length) throw new ToolError(`Invalid label "${bad[0]}" (allowed: ${LABELS.join(", ")}).`);
      const full = sortedKeys(potion.recipe).map((p) => [p, p in labels ? labels[p] : "present"]);
      entries.push([potion, full]);
    }
    const parts = [];
    if (garden) {
      const g = logGarden(w);
      if (g.growth.length) parts.push("growth " + g.growth.map(([p, t]) => `${p} = ${turns(t)}`).join(", "));
      if (g.plantings.length) parts.push("plantings: " + g.plantings.map(([n, p]) => `plot ${n} (${p})`).join(", "));
    }
    for (const [potion, labels] of entries) {
      const effect = effectLabel(potion.effect);
      const signature = effect + "|" + labels.map(([p, l]) => `${p}:${l}`).join(",");
      const isNew = !w.kb.outcomes.some((o) => o.signature === signature);
      const outcome = { signature, effect, labels, potion_id: potion.id, turn: w.turn };
      if (isNew) w.kb.outcomes.push(outcome);
      potion.logged = true;
      let unlocked = 0;
      if (w.lore) {
        for (const key of pairsAmong(Object.keys(potion.recipe))) {
          const { a, b, text } = LORE.get(key);
          const [pa, pb] = a < b ? [a, b] : [b, a];
          if (!w.kb.lore.some(([x, y]) => x === pa && y === pb)) {
            w.kb.lore.push([pa, pb, text, w.turn]);
            unlocked++;
          }
        }
      }
      let text = `potion #${potion.id}: ` + (isNew ? renderOutcome(outcome) : "already known");
      if (unlocked) text += " (the old herbals hold new lore about its plants: read it with kb_lookup)";
      parts.push(text);
    }
    return result("Logged: " + (parts.length ? parts.join("; ") : "nothing new") + ".", true);
  }

  function toolBrew(w, args) {
    if ("recipe" in args === "recipes" in args) throw new ToolError('Give either "recipe" (one potion) or "recipes" (a list of potions).');
    let recipes;
    if ("recipe" in args) recipes = [requireDict(args, "recipe")];
    else {
      recipes = args.recipes;
      if (!Array.isArray(recipes) || !recipes.length || !recipes.every(isDict)) {
        throw new ToolError('"recipes" must be a non-empty list of recipe objects.');
      }
    }
    recipes.forEach((recipe, i) => {
      try {
        validateRecipe(recipe);
      } catch (err) {
        throw new ToolError(recipes.length > 1 ? `Recipe ${i + 1}: ${err.message}` : err.message);
      }
    });
    const total = new Map();
    for (const recipe of recipes) for (const [p, n] of Object.entries(recipe)) total.set(p, (total.get(p) || 0) + n);
    const short = shortages(w, total);
    if (short.length) {
      const missing = short.map(([p, need, have]) => `need ${need} ${p}, have ${have}`).join("; ");
      const scope = recipes.length > 1 ? " for these recipes together" : "";
      throw new ToolError(`Not enough plants${scope}: ${missing}. Nothing was brewed.`);
    }
    const lines = recipes.map((r) => brewOne(w, r)).map((p) => `Brewed ${pyDumps(p.recipe)} → ${pyDumps(p.effect)} (potion #${p.id})`);
    return result(lines.join("\n"), true);
  }

  const ACTIONS = { plant: toolPlant, log: toolLog, brew: toolBrew, skip: () => result("Skipped.", true) };
  const FREE_TOOLS = { gather: toolGather, kb_lookup: toolKbLookup, inventory: toolInventory };

  function route(w, call) {
    if (typeof call === "string") {
      try {
        call = JSON.parse(call);
      } catch {
        if (!call.includes("{")) throw new ToolError("No JSON call found: end your reply with one JSON call.");
        throw new ToolError("Malformed JSON.");
      }
    }
    if (!isDict(call)) throw new ToolError("A call must be a JSON object.");
    if ("action" in call === "tool" in call) throw new ToolError('A call needs exactly one of "action" or "tool".');
    const [name, table, kind] = "action" in call ? [call.action, ACTIONS, "action"] : [call.tool, FREE_TOOLS, "tool"];
    if (typeof name !== "string" || !Object.hasOwn(table, name)) {
      throw new ToolError(`Unknown ${kind} ${pyRepr(name)} (allowed: ${Object.keys(table).join(", ")}).`);
    }
    return table[name](w, call);
  }

  // --- episode (LLM/episode.py) -----------------------------------------------------

  function openingMessage(w) {
    let allergy = "I have no allergies.";
    if (w.allergy !== null) {
      const [a, b] = w.allergy;
      allergy = `I am allergic to the combination of ${a} and ${b}: never brew a potion containing both.`;
    }
    return `My garden has ${w.size} plots. ${allergy} Goal 1: ${describeGoal(w.goals[0])}.`;
  }

  function goalMessage(end, w) {
    if (end.finished === null) return null;
    if (end.next_goal === null) return "Goal finished. That was the last goal.";
    return `Goal finished. Goal ${w.goal_index + 1}: ${describeGoal(end.next_goal)}.`;
  }

  /** One episode played by a human: the same turn loop as LLM/episode.py, one call at a time. */
  class Game {
    constructor(state) {
      this.s = state;
    }

    static create(config) {
      const world = createWorld(config);
      const game = new Game({ config, world, messages: [], actions: [], failures: 0, calls_this_turn: 0, started: new Date().toISOString() });
      game.say("user", openingMessage(world));
      game.say("environment", turnHeader(world));
      return game;
    }

    get world() {
      return this.s.world;
    }

    get over() {
      return episodeOver(this.s.world);
    }

    say(role, content, error = false) {
      this.s.messages.push({ turn: this.s.world.turn, role, content, ...(error && { error: true }) });
    }

    /** The agent's reply: notes, then one call (an object, or raw text from the console). */
    call(call, notes = "") {
      const w = this.s.world;
      const callText = typeof call === "string" ? call.trim() : pyDumps(call);
      this.say("agent", notes.trim() ? `${notes.trim()}\n${callText}` : callText);
      let res;
      try {
        res = route(w, call);
      } catch (err) {
        const message = err instanceof ToolError ? err.message : `Malformed call (${err.message}).`;
        this.s.failures++;
        res = this.s.failures >= D.MAX_FAILURES
          ? result(`${message} ${D.MAX_FAILURES} failed attempts: the turn is skipped.`, true, true)
          : result(message, false, true);
      }
      this.s.actions.push({ turn: w.turn, call, ...res });
      this.say("environment", res.text, res.error);
      this.s.calls_this_turn++;
      if (!res.ends_turn && this.s.calls_this_turn >= D.MAX_CALLS_PER_TURN) {
        this.say("environment", `${D.MAX_CALLS_PER_TURN} calls without an action: the turn is skipped.`);
        res = { ...res, ends_turn: true };
      }
      if (res.ends_turn) this.finishTurn();
      return res;
    }

    /** A note written between calls: it stays in the conversation, costs nothing and is not a call. */
    note(text) {
      this.s.messages.push({ turn: this.s.world.turn, role: "agent", content: text.trim(), note: true });
    }

    finishTurn() {
      const w = this.s.world;
      const turn = w.turn;
      const end = endTurn(w);
      const message = goalMessage(end, w);
      if (message) this.s.messages.push({ turn, role: "user", content: message });
      this.s.failures = 0;
      this.s.calls_this_turn = 0;
      if (!episodeOver(w)) this.say("environment", turnHeader(w));
    }

    /** output.py summary(): per-goal results with the best potion's details. */
    summary() {
      const w = this.s.world;
      const goals = w.results.map((r) => ({
        goal: r.goal,
        description: describeGoal(r.goal),
        start_turn: r.start_turn,
        end_turn: r.end_turn,
        turns_used: r.end_turn - r.start_turn + 1,
        success: r.success,
        best_intensity: r.best_intensity,
        best_potion: r.best_potion ? w.inventory.potions[r.best_potion - 1] : null,
        allergy_violations: r.allergy_violations,
      }));
      const inProgress = episodeOver(w) ? null : currentGoal(w);
      return {
        turns_played: w.turn - 1,
        episode_over: episodeOver(w),
        stop_reason: null,
        goals,
        goal_in_progress: inProgress,
        goals_not_started: w.goals.slice(w.results.length + (inProgress !== null ? 1 : 0)),
      };
    }

    /** transcript.md in the same format as output.py. */
    transcriptMarkdown(label = "human") {
      let text = `# Transcript — ${label} — ${this.s.started}\n`;
      let turn = null;
      for (const m of this.s.messages) {
        if (m.turn !== turn) {
          text += `\n## Turn ${m.turn}\n`;
          turn = m.turn;
        }
        text += `\n**${m.note ? "agent (note)" : m.role}**\n\n${m.content.trimEnd()}\n`;
      }
      return text;
    }
  }

  return {
    DATA: D, PLANTS, LABELS, STAT_NAMES, PyRandom, pyDumps, brew, describeGoal, parseGoal, parseAllergy,
    gardenState, gardenView, renderOutcome, currentGoal, Game,
  };
})();

if (typeof module !== "undefined") module.exports = PG;
