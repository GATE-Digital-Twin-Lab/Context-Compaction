# Potion Garden Agent Demo — Specification

*Working spec, superseding the first version in `demo.md`. Everything (plants, effects, rules) is fictional.*

## Purpose

A simulated environment for generating agent episodes, so we can study **what a tool-using agent forgets when its context is compacted**. The agent grows plants in a garden, learns the garden's properties, experiments with potions and pursues user goals under a time budget. The main measurement is information retention across compaction; potion quality is an auxiliary performance metric.

## World

- **Garden:** each user has a garden with **N plots** (an array of size N); N is given by the user at the start. Every garden has its own growth time per plant type (because of soil, location, etc.): at initialisation each plant's growth time is sampled independently from a discrete uniform **U(a, b)** turns (a, b to be decided). Growth times are fixed for a given garden and plant and unknown to the agent; it must learn them.
- **Seeds** are unlimited for every catalogue plant; the **inventory** has no size limit.
- **Plants:** a fixed catalogue of plant types, all available for planting. The knowledge base starts with the catalogue (names only).
- **Brewer:** a hidden, fixed equation that maps a recipe to effects (see Brewing rules).
- **Time:** discrete turns. Every action costs exactly **1 turn**. Thinking, planning and knowledge-base lookups cost **0 turns**.

## Actions (1 turn each, any number of items per action)

| Action | What it does |
|---|---|
| **Plant** | Plants any number of plants of any types in free plots |
| **Log** | Writes any number of facts to the knowledge base |
| **Brew** | Brews one potion from the inventory; consumes the plants used. An infeasible brew costs 0 turns |
| **Skip** | Does nothing; time passes |

Free (0-turn) tools: **Gather** (harvests **all** ready plots into the inventory, freeing them, so they can be replanted in the same turn), **KB lookup**, **inventory lookup**. Gather was an action in earlier versions; making it free removes a pure bookkeeping turn and simplifies planning for small models.

## Observations

Every turn starts with the **garden state**: free plots, growing plots and ready plots.
- **Ready plots** show how many turns they have been waiting since they became ready (starting at 0), e.g. *"ready: 11 (waiting 0), 17 (waiting 2)"*.
- If a plot's planting was **logged**, its plant is named: *"11 (elderberry, waiting 0)"*. A growing plot whose planting **and** growth time are both logged also shows turns remaining: *"3 (elderberry, 2 turns left)"*.
- If it was **not logged**, only plot numbers are given. The agent must remember what it planted where.
- With the waiting counter the agent can work out a growth time itself: growth time = turns since planting − turns waiting.

## Knowledge base

Written only through the **Log** action. The agent decides **when** to log and **what**; the environment fills in the factual content, so logged facts are never hallucinated. A single Log action (1 turn) can contain both parts below.

**Garden log** (all-or-nothing, filled in by the environment):
- **Growth times** of every plant type that is **ready, or was gathered this turn**, and whose growth time is not yet known (gathering is free, so "gather, then log" in one turn must still record the growth times). A growth time is a fixed property of the plant in this garden, so it is the true value no matter how long the plant waited. Several plots with the same plant give one entry.
- **Planting records** (plot → plant) for every **occupied** plot (growing **or** ready) not yet logged.
  - Planting records describe the **current** garden: a record is **removed when its plot is gathered**, so a later planting in the same plot starts unlogged. Growth times are permanent.

*Example:* 7 plots at turn 5, nothing logged; 1, 3, 6 free; 2 (elderberry) and 4 (sage, waiting 2) ready; 5 (chamomile) and 7 (basil) growing. A garden log adds growth elderberry and sage (true values) and plantings for plots 2, 4, 5, 7. If plot 5 becomes ready next turn, the agent sees `ready: 2 (elderberry, waiting 1), 4 (sage, waiting 3), 5 (chamomile, waiting 0)`. chamomile's growth time needs another garden log, and plots 2 and 4 waited one more turn because the agent did not gather them (gathering is free, so it could have gathered first and still logged both growth times).

**Brew log** (per potion, chosen by the agent):
- Every successful brew, **including a no-effect brew** (a dud), is kept in the inventory as an item (`potion #3`), **without** its details. A dud can be logged with effect **none**, so failed combinations can be recorded.
- To log a potion the agent names it and provides its **own labels** for each plant from the restricted vocabulary **odd**, **even**, **higher is better**, **lower is better**, **present** (no information). The environment records the **plant set** and the **effect** (stat and sign).
- Exact quantities and magnitudes are **never** stored; they exist only in the conversation.
- Example entry: *"(higher is better) chamomile, even rosemary, even mint → +S"*. The vocabulary cannot express "exactly 2" or "mod 3", so the labels are the agent's approximate belief and can be wrong. For S, "even rosemary" also admits rosemary = 4, which gives nothing.
- **Entries are append-only:** existing statements are never updated. A new statement for the same plant set and effect is added alongside the old ones, so the KB keeps the history of the agent's beliefs as they develop. Only an **exact duplicate** (same plant set, same effect, same labels word for word) is dropped.

*Example:* at turn 20 the agent has brewed #1 (turn 8: mint=1, elderberry=1, dill=1 → no effect), #2 (turn 15: elderberry=1, sage=1, dill=1 → +I 2%) and #3 (turn 20: elderberry=2, sage=1, dill=1 → +I 5%). At turn 21 it logs all three with the labels it can justify:
- #1 → `mint, elderberry, dill → none`
- #2 → `elderberry, sage, dill → +I` (one data point, nothing to infer: all labels "present")
- #3 → `(higher) elderberry, sage, dill → +I` (1 → 2 elderberry raised 2% → 5%)

A later potion #4 that leads the agent to believe dill must be odd adds `(higher) elderberry, sage, (odd) dill → +I` as a fourth entry. Under the real rules dill has no effect, so this belief is wrong; labels are beliefs, not truths. Logging #3's labels again would be an exact duplicate and is dropped.

The quantities, the magnitudes and which potion is the best so far exist **only in the conversation**. After compaction the agent may still know "more elderberry helps I" from the KB, but not that 2 elderberry gave 5%.

**Consequence:** garden facts are **recoverable at a cost**. An agent that forgets what it planted can recover the planting map with one Log action, and growth times the next time a plant is ready. Forgetting garden facts therefore costs **time**, not information. Brew details, the allergy, goals and plans **cannot** be recovered.

User goals and the allergy are **not** loggable in this version; the agent must remember them. Making the allergy loggable (so protecting it becomes the agent's choice) is a possible later variant.

Lookups are free and return, per plant, its growth time (if logged) and all logged outcome statements involving it (a relational join).

## The logging trade-off (core mechanic)

Logging is safe but costs a turn. Keeping facts in the conversation is free but at risk of compaction.
- Batching saves time: an agent that remembers two growth times can log both in one action.
- Bad timing costs plots: e.g. gather (free) → log → plant at turns K, K, K+1 leaves the freed plots idle for a turn instead of growing something new.

So a good agent will deliberately keep some facts unlogged in its context. Those are exactly the facts compaction can destroy.

## Brewing rules

### General

- A recipe uses **3 or 4 distinct plants**, each with quantity ≥ 1, written as `{plant: count}`.
- **Infeasible brew:** not enough plants in the inventory. It costs **no turn** (nothing is consumed), and the agent must react appropriately.
- Output: `{"positive": {"S": 5}, "negative": {}}`. A potion has **at most one effect**, positive or negative.
- **Cancellation:** if a stat's positive and negative conditions both hold, they cancel, whatever the magnitudes.
- **No effect:** both dictionaries are empty. This happens when no stat's plant set is complete, when neither condition holds, or when they cancel. The agent cannot tell which.
- The agent does **not** know the intensity cap. It works in an open environment, aims for the maximum, and after reaching it can only refine what not to do.

### Plants and stats

8 plants and 5 stats. The plants are named for immersion: mint, elderberry, nettle, sage, chamomile, dill, basil, rosemary (in that order; internally the catalogue order is fixed, so a seed gives the same growth times as before the renaming). A stat is active only if **every** plant in its set is present (≥ 1).

| Stat | Plant set |
|---|---|
| I (intelligence) | elderberry, sage, dill |
| S (strength) | mint, chamomile, rosemary |
| V (vitality) | mint, nettle, basil |
| D (dexterity) | nettle, sage, rosemary |
| W (wisdom) | elderberry, chamomile, dill, basil |

Any two sets together need ≥ 5 distinct plants, so with at most 4 per recipe **at most one stat can be active**.

### Conditions and intensity

Notation: N(p) = count of p; **!** = higher is better; **@** = lower is better (minimum 1). Plants not named in a rule do not affect intensity (they only need to be present).

| Stat | Positive (+) | Negative (−) |
|---|---|---|
| I | N(elderberry)!, N(sage) % 2 = 1 | N(elderberry)!, N(sage) % 3 = 0 |
| S | N(chamomile)!, N(rosemary) % 3 = 2, N(mint) = 2 | N(chamomile)!, N(rosemary) % 2 = 1 |
| V | N(basil)!, N(basil) % 5 ≠ 0, N(nettle) % 2 = 0 | N(mint) = 2, N(basil)! |
| D | N(rosemary)!, N(sage)@, N(sage) % 2 = 1 | N(rosemary)!, N(sage)!, N(sage) % 2 = 0 |
| W | N(elderberry) = 2, N(dill)!, N(basil) % 2 = 1 | N(dill)!, N(basil) % 2 = 1, N(chamomile) % 2 = 0 |

**Intensity levels:** 2, 5, 10, 20% (positive and negative alike). The driver score maps to a level: score 1 → 2%, 2 → 5%, 3 → 10%, ≥ 4 → 20%; score ≤ 0 → no effect.
- Single driver (!): score = N(driver).
- D positive (rosemary!, sage@): score = N(rosemary) − N(sage) + 1 (the larger the difference, the stronger).
- D negative (rosemary!, sage!): score = N(rosemary) + N(sage) − 2.

### Properties (brute-force check, counts 1–6 per plant)

| Stat | All-1s recipe gives | Share of recipes that are positive | Cheapest +20% recipe | Difficulty |
|---|---|---|---|---|
| I | +2% | 72 / 216 | elderberry=4, sage=1, dill=1 | easy |
| S | −2% | **6 / 216** | mint=2, chamomile=4, rosemary=2 | hard (two exact conditions) |
| V | nothing | 75 / 216 | mint=1, nettle=2, basil=4 | medium |
| D | +2% | 72 / 216 | nettle=1, sage=1, rosemary=4 | easy |
| W | nothing | 54 / 1,296 | elderberry=2, chamomile=1, dill=4, basil=1 | hard |

Traps: V with basil = 5 gives nothing; S with rosemary = 5 cancels. For S and W blind search is hopeless, so the agent must reason from the exact results it remembers.

## Users

Users are **independent and isolated**: each episode starts with an empty garden, an empty inventory and a KB holding only the plant catalogue. Nothing carries over between users, which keeps episodes i.i.d. as LTT/PPI calibration requires.

The user sets the **initial conditions** and the **goals**:
- **Garden size** N.
- **Allergy** (optional; some users have none): to a **combination of two plants**. Any recipe containing both is forbidden, and a potion that violates it counts as a failure for the goal.
  - It is stated **at the start, as an initial condition** (users know their allergies). This makes it the oldest fact in the conversation, so it is the most exposed to compaction.
  - The allergy **never makes a goal impossible**: the pair is never two plants that are both required for one of the user's goals. It can be **one required plant + one non-required plant**, e.g. chamomile + nettle for a strength goal.
  - The agent knows only that a recipe needs 3–4 distinct plants, not which ones are required. It may therefore include a non-required 4th plant while exploring (e.g. find its best strength potion as {mint, chamomile, rosemary, nettle}). If that plant forms the allergic pair, the agent must discover that the potion also works without it.
  - The allergy binds only if the agent's recipes actually include the non-required plant, so whether it matters depends on the agent's trajectory.
  - For a W goal (4 required plants, no room for another plant) the allergy can never apply.
- **Goals** (about 3 per episode, pursued one after another), each of one of two types:
  - **Time-limited:** *"brew the best strength potion you can in 30 turns"*. Ends at the deadline; the score is the strongest valid potion of that stat brewed within the window.
  - **Target:** *"brew a strength potion of at least +10% as fast as you can"*. Ends when a valid potion reaches the target; the score is the number of turns used. A global turn cap ends it as failed if the target is never reached.
  - Since the agent does not know the intensity cap, an open-ended "brew the best" goal without a deadline would never end; both goal types avoid this.
  - The garden, the inventory and the KB **carry over** between goals within an episode.

## Compaction

- Triggered when the context passes a **fraction of the model's context window** (`--compaction-trigger`, default 0.8, of `--context-window` tokens). The check runs **only between turns**, after an action and its response are complete, so compaction never cuts an action in half.
- **Informed but blind by default:** the system prompt tells the agent that older parts of the conversation may be summarised without notice, but it is never told how full its context is or when compaction will happen, just as a person knows they forget but not when. Logging is therefore insurance. An *uninformed* variant (compaction is never mentioned) is a possible ablation. A *warned* variant (the agent sees its context usage and can log just before compaction) is an optional later experiment.
- With about 3 goals per episode, at least one compaction happens.
- The same garden can be run with **0, 1, …, k compactions** for comparison.

## Facts worth remembering

| Fact | Where it lives unless logged |
|---|---|
| Current goal, which goals are done | conversation only (cannot be logged) |
| Allergy (two-plant combination) | conversation only (cannot be logged) |
| Exact quantities and magnitudes of brews | conversation only (KB statements use only odd / even / higher / lower labels) |
| Best result so far | conversation only |
| Failed / no-effect recipes | conversation only |
| Planting map (what is planted where) | conversation, **unless logged**; recoverable with one garden log |
| Observed growth times | conversation, **unless logged**; recoverable when the plant is next ready |
| The agent's plan / schedule | conversation only |

The inventory, logged facts and the plant catalogue are always available through free lookups.

## Measurement

- **Main (retention):** at each compaction point, the simulator log gives the set of goal-relevant facts known so far. The loss is the **fraction of those facts lost** in the compacted context. Defining the facts at the compaction point keeps the loss independent of what the agent does afterwards, since its later actions change after compaction.
- **Which facts count:** the retention loss focuses on **unrecoverable** facts (brew quantities and magnitudes, best result so far, failed recipes, allergy, current goal, plan). Garden facts (planting map, growth times) are recoverable at a turn cost, so forgetting them shows up in the performance metrics as wasted turns.
- **Auxiliary (performance):** best potion achieved per goal, turns used, goals completed, idle plots, infeasible brews, allergy violations. Needs several runs per garden, because LLM strategy and randomness add noise.

## Planning

Planning is free (0 turns) and is **not** given a dedicated tool or notepad: the agent writes its plan in its visible notes (thinking is discarded after each reply), so the plan is another fact compaction can destroy. Recommended agent loop: **plan → execute → re-plan** when an observation contradicts the plan.

## Interaction format

### Turn structure

Every turn has four steps:

1. **Garden state** (environment):
   ```
   [Turn 14]
   Garden: free: 1, 2, 6; growing: 3 (elderberry, 2 turns left), 4, 5; ready: 7 (waiting 2), 8 (chamomile, waiting 0)
   Choose your action.
   ```
2. **Agent:** thinks privately, then writes a reply of **visible notes** (whatever it wants to keep) followed by **one call**. It may call **free tools** any number of times (one per reply), then submits **exactly one action**:
   ```
   (thinking: discarded after the reply)
   Notes: I = elderberry+sage+dill; elderberry drives intensity (1→2%, 2→5%). Plan: check the KB on chamomile, rosemary first.
   {"tool": "kb_lookup", "plants": ["chamomile", "rosemary"]}               ← optional, free, repeatable
   ```
   ```
   Notes: ...
   {"action": "brew", "recipe": {"mint": 2, "chamomile": 4, "rosemary": 2}}   ← exactly one per turn
   ```
3. **Action result** (environment):
   ```
   Brewed {"mint": 2, "chamomile": 4, "rosemary": 2} → {"positive": {"S": 20}, "negative": {}}  (potion #4)
   ```
4. **Time advances** to the next turn, and the loop repeats from step 1.

**Thinking and notes.** The agent is a reasoning model and thinks before every reply. Its thinking is **never sent back**: the environment builds the history itself and keeps only the visible reply, cut after the first call (anything the model writes after the call, such as an invented result, is dropped). The thinking is kept in `transcript.md` for analysis only. Information therefore lives in three tiers:

| Tier | Cost | Lasts |
|---|---|---|
| Thinking | free | the current reply only |
| Visible notes (and the environment's replies) | free, but they fill the context | until compaction removes or summarises them |
| Knowledge base | 1 turn per Log | permanent, but coarse (labels only) |

Derived knowledge (growth times worked out from the waiting counters, the best potion so far, hypotheses about the rules, the plan) survives the reply only if the agent writes it into its notes.

**Guidance for small models.** A first run with a small model showed notes holding only plans, no logging at all (skipping instead), and long, indecisive thinking. The system prompt therefore:
- explains why logging matters, with a worked example on made-up plants (A, B, C, stat X) so no hidden rule is leaked, and says a log costs the same as a skip, so the agent should never skip while something useful is unlogged;
- lists the facts worth tracking (goal and constraints, which cannot be logged; plantings and growth times; every brew with exact numbers; the best potion so far; hypotheses and plan);
- suggests a short notes format, `New facts: …` (with exact numbers) then `Plan: …`, written when a fact is learned. It does **not** ask the agent to restate its whole state every reply; an agent that does so keeps it in the newest message, at the price of a faster-filling context, and that choice is part of what is observed;
- gives a four-step decision routine (new, known, at most three options, decide) and asks for decisive play: decide once, a no-effect brew is information, keep every plot growing, plant several plots of a plant to vary quantities.

For Qwen3.8, `--reasoning-effort medium` is used: its template's default (`xhigh`) adds an instruction to "consider plausible alternatives", which works against the decision routine; `medium` adds nothing.

Thinking is dropped from **every** reply, including replies within one turn (e.g. kb_lookup → brew); anything needed for the next call goes in the notes. *Possible variant:* keep thinking until the turn's action and drop it at the turn's end (depends on how each chat template treats old thinking). A thinking-off variant, where all reasoning is visible text, is kept as a comparison.

The garden state and action results **deliberately omit** the current goal, its deadline or turns remaining, the allergy, past results and the best result so far. Repeating any of these every turn would protect them from compaction and defeat the test.

### Actions (cost 1 turn)

| Action | Syntax |
|---|---|
| Plant | `{"action": "plant", "plots": {"3": "elderberry", "4": "elderberry", "5": "basil"}}` |
| Log | `{"action": "log", "garden": true, "potions": [{"id": 3, "labels": {"chamomile": "higher", "rosemary": "even", "mint": "even"}}]}` (either part optional) |
| Brew | `{"action": "brew", "recipe": {"mint": 2, "chamomile": 4, "rosemary": 2}}` |
| Skip | `{"action": "skip"}` |

**Log parts** (see Knowledge base): `"garden": true` logs growth times of ready plants and planting records of all occupied plots, filled in by the environment. `"potions"` logs chosen potions with the agent's labels (`odd`, `even`, `higher`, `lower`, `present`); the environment adds the plant set and effect.

### Free tools (cost 0 turns)

| Tool | Syntax | Returns |
|---|---|---|
| Gather | `{"tool": "gather"}` | collects all ready plots; they are free at once |
| KB lookup | `{"tool": "kb_lookup", "plants": ["chamomile"]}` | all KB entries involving these plants |
| Inventory | `{"tool": "inventory"}` | plant → count; potions by ID only (no details), marked logged / unlogged |

A separate garden-view tool is not needed: the garden state is shown at the start of every turn, and the only free tool that changes it (gather) reports which plots it freed.

### Environment responses

| Action / tool | Response | Notes |
|---|---|---|
| Plant | `Planted: plot 3 (elderberry), plot 4 (elderberry). Failed: plot 5 (occupied), plot 12 (does not exist), plot 6 (unknown plant lavender).` | **Partial success:** valid plots are planted, the others are reported with the reason. Costs the turn. |
| Gather | `Gathered: +2 elderberry, +1 basil. Plots now free: 3, 4, 7.` (or `Gathered nothing.`) | **Free, never fails.** Collects **all** ready plots (counts only, not per plot), updates the inventory, and removes the planting records of the gathered plots. |
| Brew | `Brewed {"mint": 2, "chamomile": 4, "rosemary": 2} → {"positive": {"S": 20}, "negative": {}} (potion #4)` | Failures (`Not enough plants: need 4 chamomile, have 2.` · `A recipe needs 3–4 distinct plants.`) cost 0 turns; 3 failures → forced Skip. |
| Skip | `Skipped.` | – |
| Log | `Logged: growth elderberry = 4 turns, basil = 3 turns; plantings: plot 3 (elderberry), plot 5 (basil); potion #3: (higher) chamomile, even rosemary, even mint → +S.` | **All-or-nothing:** if any potion entry is invalid (unknown potion ID, a label for a plant the potion does not contain, or a label outside the vocabulary), nothing is logged, including the garden part. A failed Log costs **0 turns** and counts toward the 3-failure limit. Plants the agent leaves unlabelled default to `present`. The garden part alone never fails (it may log nothing new). An exact duplicate (same plant set, effect and labels) is reported as `potion #3: already known` and the potion is marked logged. |
| KB lookup | `chamomile: grows in 4 turns. Interactions: (higher) chamomile, even rosemary, even mint → +S; …` | All known info for the plant: growth time (if logged) and all logged outcome statements involving it, **in the order they were logged** (the last one is the agent's latest belief). |
| Inventory | `plants: elderberry: 3, chamomile: 1, basil: 1; potions: #1 (logged), #2, #3` | Potion details are never shown here; they live only in the conversation. |

- **Errors** (malformed JSON, failed brews, failed logs) cost **0 turns**. After **3 failed attempts** in one turn the environment forces a Skip.
- **Allergy violations are not flagged.** A brew containing the allergic pair succeeds normally (plants consumed, effect shown) but counts as a failure in scoring. A warning would re-insert the allergy into the context and undo the effect of compaction.

### Episode flow

1. **Initialisation:** sample each plant's growth time from U(a, b); empty garden of N plots; empty inventory; KB holds the plant catalogue (names only).
2. **System prompt:** the visible rules of the world: actions and their costs, free tools, 3–4 distinct plants per recipe, the effects dictionary, the log label vocabulary, that time is limited, the reply format (notes, then one JSON call), and how its memory works (thinking is discarded after each reply; the conversation may be summarised without notice; only the knowledge base is permanent). The hidden brewing rules and growth times are **not** included.
3. **User opening message:** garden size, allergy (if any), first goal.
4. **Turn loop** (turn t):
   1. The environment shows `[Turn t]` with the garden state and asks for an action.
   2. The agent reasons, uses free tools, and submits one action.
   3. The environment applies the action and returns the result (or forces a Skip after 3 failed attempts).
   4. The environment checks the goal. A target goal reached by a valid brew ends now; a time-limited goal ends when its deadline passes.
   5. Time advances to t + 1. A plant planted in turn t with growth time g becomes **ready at the start of turn t + g** and stays ready until gathered.
   6. If the context has passed the compaction trigger, **compaction** runs (blind: the agent is not told).
   7. A **checkpoint** of the complete state is saved (see Checkpointing).
5. **Goal end:** the user sends *"Goal finished."* together with the next goal, without reporting the result.
6. **Episode end:** after the last goal, or at the global turn cap.

### Checkpointing

Protects long runs against crashes (connection loss, out of memory, context overflow). It is prevention, not logging.
- **After every completed turn** the complete state is saved to `temp/<agent>/<run_id>/checkpoint.json`: world (garden, inventory, goals, turn), knowledge base contents, ledger, agent state (conversation, random state), the byte sizes of the log files, and the number of compactions so far.
- Only the **latest** checkpoint is kept. It is written to a temporary file and then renamed, so a crash while saving keeps the previous one.
- **Resume** with `--resume runs/<agent>/<run_id>`. All parameters come from that run's `params.json` (no other options are accepted). The log files are cut back to their checkpointed sizes, later compaction files are removed, and the knowledge base is rebuilt from the checkpoint, so nothing from the interrupted turn remains.
- The interrupted turn is **replayed from its start**; at most one turn is lost. The resumed run first re-checks compaction, so a crash caused by a full context compacts before retrying.

### Evaluation and comparisons (parked)

To be designed later. Notes so far:
- Performance metrics per goal type (best intensity within the deadline; turns to reach the target).
- Comparisons: different LLMs; different compaction thresholds (context sizes); different compactors.
- Non-LLM baselines: a random agent, a heuristic search agent, and a scripted oracle that knows the hidden rules (upper bound).

## Open items

- [x] Brewer rules (see Brewing rules)
- [x] Observation format and action syntax (see Interaction format)
- [x] Environment responses and episode flow
- [ ] Evaluation plan and baselines (parked)
- [ ] Concrete allergy list (one required + one non-required plant for the user's goals)
- [ ] Values of a, b for growth times; range of garden sizes N; time budgets per goal
- [ ] Compaction trigger value and context window per model, and which compactors to try
- [ ] Which local LLM plays the agent
- [ ] Optional: a scripted reference planner that knows the hidden rules (upper bound for the auxiliary metric)
