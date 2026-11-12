# Potion Garden Agent Demo — Specification (version 3)

*Working spec for the redesign on branch `dev2`, built from the ideas in `demo.md`. It replaces version 2 (the world with lore lines, garden logging and labelled potion logs), which is in the git history up to commit `cae0dea`. Everything (plants, effects, sources, people) is fictional.*

Marked **(default)**: a choice made while writing the spec that the design discussion did not settle explicitly; change it freely. Marked **(content)**: hidden content still to be written.

## Purpose

A simulated environment in which a **language** agent is actually needed, used to study **what the agent forgets when its context is compacted**. The previous version was black-box optimisation over structured data, which a scripted search solves better than an LLM. In this version the agent:
- turns a client's request, written in plain language, into a measurable goal;
- searches and reads a corpus of old texts of uneven reliability, which imply facts but never state numbers;
- runs experiments (growing plants in soils, brewing, mixing) to find exact values;
- records evidence and claims in a structured notebook, and checks its beliefs against the data with a validator;
- delivers one potion that satisfies the request.

**Retention target.** The observations are recorded automatically and an expert can verify them. What cannot be verified afterwards is the agent's **thought process**: how it translated the request, interpreted the sources, formed and tested hypotheses, and decided. That chain is what compaction must preserve (see *Information and retention*). Accuracy is secondary: the goal is to keep the agent's information state, including wrong beliefs.

## World

### Plants, garden, soils

- **Plants:** the same 8 as before: mint, elderberry, nettle, sage, chamomile, dill, basil, rosemary. Seeds are unlimited.
- **Garden:** N plots (given by the episode), one plant per plot. Each episode starts with an empty garden and an empty inventory.
- **Soils:** black, brown, yellow, unlimited. The agent chooses the soil for every planting. Soil affects **growing only**, never brewing:
  - **growth time** is a fixed property of each (plant, soil) pair;
  - **death:** a few (plant, soil) pairs never survive, and rarely a pair survives only with some probability. Most pairs always survive.
  - A plant that dies is reported when it would have become ready: the garden line shows it as died, its plot becomes free, and the growth table records it.
- **Time:** discrete turns; **a day is 10 turns**. Every action costs exactly 1 turn; thinking and free tools cost nothing (within the free-call budget, see *Tools*).
- **One fixed world:** the stat rules, the secondary pairs, the growth times per soil, the death probabilities and the corpus are written together and do not change between episodes. The env seed only drives random deaths. Variation comes from the requests and the LLM seed.

### Primary effects (unchanged rules)

The five stats and their hidden rules stay as in version 2 (`environment/brewer.py`):

| Stat | Plant set |
|---|---|
| I (intelligence) | elderberry, sage, dill |
| S (strength) | mint, chamomile, rosemary |
| V (vitality) | mint, nettle, basil |
| D (dexterity) | nettle, sage, rosemary |
| W (wisdom) | elderberry, chamomile, dill, basil |

- A stat is active only if every plant of its set is present. Its positive and negative conditions depend on counts (e.g. S positive needs exactly 2 mint and rosemary % 3 = 2); if both hold, they cancel, whatever the magnitudes.
- Base intensity levels: 2, 5, 10, 20%. **The base never exceeds 20%**, so any request above +20% needs secondary effects.
- With at most 4 plants, at most one stat can be active. Mixing (below) can exceed 4 plants, so a mixed potion can carry **several primary effects**.

### Secondary effects

Secondary effects come from **pairs of plants**. A pair counts if both plants are present in the recipe, **whatever their counts**. Each listed pair contributes its modifier; two different pairs with the same label both count. Which pairs give which label is hidden **(content)**.

| Label | Modifier | How a source might describe it |
|---|---|---|
| fragrant | +25% | "the brew smelled of a spring meadow" |
| warming | +50% | "a warmth spread through his chest" |
| sweet | +100% | "tasted of honey" |
| bitter | −25% | "bitter on the tongue; he barely felt it" |
| murky | −50% | "cloudy, and the effect faded by noon" |
| toxic | −100% | "the goat that drank it never rose again" |

**Combination:**
- Same-sign modifiers add up, with no cap: all three positives give +175%.
- If positive and negative modifiers are both present, they **cancel completely**: no modifier at all (as with clashing primary conditions). This is the intended "antidote": a positive pair makes a toxic brew drinkable.
- **Final intensity** = base × (1 + sum of modifiers), clamped at 0, rounded half away from zero (2.5 → 3, −2.5 → −3). A modifier applies to **every** primary effect of the potion, whatever its sign: sweet turns −S 20 into −S 40.
- **Toxic** (or any net modifier ≤ −100%) removes the effect: the potion is undrinkable, and delivering it fails.
- A **2-plant recipe** gives only a secondary effect (no stat set has 2 plants). It is a cheap probe of one pair.

### Brewing and mixing

- **Brew:** a recipe uses **2–4 distinct plants**, each with count ≥ 1. Several recipes can be brewed in one action, all or nothing.
- **Mix:** combines potions from the inventory into one new potion. It is the same as brewing the **summed recipe** of the inputs: e.g. {sage 1, chamomile 1, nettle 1} + {nettle 1, mint 1, elderberry 1} = {nettle 2, sage 1, chamomile 1, mint 1, elderberry 1}. Primary and secondary effects are recomputed from the summed recipe, so new pairs across the inputs can create new secondary effects, and added plants can break a primary condition. There is **no plant limit**. The input potions are used up (their records stay in the notebook). Mixing costs 1 turn like brewing, and several mixes can go in one action.
- Every potion is a **finite resource**: it is used up by mixing or by delivery.
- **Output** (tool results keep the structured style): `Brewed {"mint": 2, "chamomile": 4, "rosemary": 2} → {"positive": {"S": 25}, "negative": {}, "secondary": ["fragrant"]} (potion #4)`. Only the final intensity is shown, not the base or the modifier values; the agent works the modifiers out by comparing potions.

### Plant names and groups (content)

The corpus refers to plants by **folk names** ("the grey-leaved herb of the abbey wall" = sage) and **groups** ("pond plants", "hearth herbs"). A hidden table of names and groups is written first; the corpus and the requests are written from it.

## Sources

- **Corpus:** one fixed set of short texts (herbals, records, notes, tales, pamphlets), plus distractor texts about unrelated things. Each source shows its **title, author and kind**. **(content)**
- **Claims are implied, never numeric.** A source tells what happened ("my boy could suddenly carry two full buckets instead of one"); the agent infers the relation (a doubling: sweet, or a stronger base) and finds the exact values by experiment. Sources cover combinations, secondary effects, soils and plant groups. Some facts appear in no source and can only be found by experiment.
- **Contradictions:** several sources may support a claim and one deny it.
- **Reliability:** the kinds have a **known order**, stated in the system prompt, tied to the chance that a source of that kind is wrong. From most to least reliable, e.g. learned herbals > monastery records > healers' notes > village tales > merchants' pamphlets. The probabilities themselves are hidden **(content)**.
- **Generation:** every source is written from a structured hidden claim (plants, relation, true or false, kind). This gives the answer key for each source.
- **Retrieval:** BM25 over passages. `search` takes queries and returns the top-k passages with their source's title, author and kind. `read` returns whole sources, but only those returned by a `search` **in the current turn**; to read again in a later turn, the agent must search again.

## Requests

- **One request per episode** while testing, written in plain language, e.g. *"I am a stonecutter … I need to pack 10 oxen with stone, but I can barely pack 8. In a week we need to gather enough stone …"*. The request is part of the system prompt, so it is never compacted.
- **Translation rules** the agent must apply:
  - **Ratios:** from 8 to 10 oxen means at least +25%; from 5 to 7 means at least +40% (more is fine, less is not).
  - **Glossary:** the system prompt maps symptoms and uses to stats, as a doctor maps symptoms to a disease. **(content)**
  - **Deadlines** in days: "a week" means deliver by the end of day 7, i.e. turn 70. Requests without a deadline have a turn cap.
  - **Vague constraints:** e.g. a client reacts badly to "the pond plants". Sources name the group's members. The request is designed so that one member is **required** for the goal (nettle for D) and the others must be avoided. The allergy itself cannot be observed by experiment; it is inferred from the request and the sources.
- **Success** is judged on the delivered potion only:
  - its intensity for the requested stat, after modifiers, meets the threshold (any positive intensity if none is given);
  - other primary effects are ignored;
  - it is drinkable (not toxic);
  - its summed recipe contains no excluded plant;
  - it is delivered before the deadline.
- `deliver` **ends the goal**, as a success or a failure. There is one delivery and no feedback.

## Notebook

The notebook replaces the knowledge base. It holds typed records, indexed for exact lookups. Recording is **free** (within the free-call budget), all records are **append-only**, and every record has an id.

**Written automatically by the environment:**

| Record | Key and fields | When |
|---|---|---|
| `potion` (#k) | recipe (summed for mixes), origin (brew, or mix of #a + #b), primary effects, secondary labels, turn | at every brew or mix |
| `growth` | key (plant, soil); growth time; counts planted, grew, died | updated when a plot becomes ready or its plant dies |

The garden itself is not recorded: the garden line shows it every turn.

**Written by the agent:**

| Record | Required fields | Status |
|---|---|---|
| `claim` (c#) | the source id, plants, relation, value, the agent's trust | none: a claim reports what a source says, as the agent understands it |
| `belief` (b#) | a statement in the validator's grammar | set **only by the validator**, recomputed against the data at every lookup |
| `requirement` (r#) | the request phrase it comes from, and what it means (stat, threshold, deadline, excluded plants) | none |

- Records are told apart by **origin**: claims cite a source, beliefs are the agent's own and are judged by data, and requirements come from the request. Claims and beliefs share one vocabulary of relations (pair → secondary label, recipe → effect, (plant, soil) → growth or survival), so a claim can be turned into a belief and tested.
- **Corrections:** a new record with `replaces: <id>`; the old one stays, marked as replaced.
- `kb_lookup` filters on record type and fields (e.g. potions with primary S; growth rows for sage). The more fields are given, the narrower the answer; broad lookups return many rows and fill the context. **(default)** At most 30 rows per lookup, with the total count shown.

## Validator

A free tool that checks statements against the notebook's **automatic records** (potions and growth), never against the hidden rules. It answers in three states, with the evidence:

```
{"status": "true" | "false" | "unknown", "for": [6, 18], "against": [], "tested": 7}
```

| Kind | True | False | Unknown |
|---|---|---|---|
| exact recipe gives X | that recipe was brewed with result X | it was brewed with another result | not brewed |
| exists (some recipe containing F gives X) | one witness | never (the space is infinite with quantities) | no witness yet; reports how many were tested |
| all / none (every recipe containing F gives / does not give X) | no counterexample in n tests (consistent, not proven; n is reported) | one counterexample | nothing tested |
| relation (more P increases / decreases X) | ≥ 1 qualifying pair, and all such pairs agree | one pair disagrees | no qualifying pair |
| rate ((plant, soil) survives with rate ≥ p) | the 95% binomial interval lies above p | it lies below p | otherwise |

- **Qualifying pairs** for a relation differ **only** in the count of P and give the same stat. Pairs that also differ elsewhere are confounded and reported separately, never counted.
- A `belief` record is a stored validator statement. Its status is the validator's answer at lookup time, so a belief in the notebook is never out of date.
- The exact JSON grammar is fixed in the implementation.

## Tools and actions

### Free tools (0 turns)

| Tool | Does | Budget |
|---|---|---|
| `search` | queries → top-k passages with source, title, author, kind | **counted** |
| `record` | writes one or more claims, beliefs and requirements | **counted** |
| `validate` | checks one or more statements | **counted** |
| `read` | whole texts of sources returned by a search this turn | free |
| `kb_lookup` | notebook records matching filters | free |
| `inventory` | plant counts; potions by id | free |
| `gather` | collects all ready plots; they are free at once | free |

- **Budget:** `search`, `record` and `validate` together are limited to **5 calls per turn**. Every operation can be batched. **(default)** A batched call counts as one call. The budget resets every turn.
- **Running out:** a 6th counted call costs no turn; the agent is told the budget is used up and that only reads, lookups, inventory, gather or an action remain this turn.

### Actions (1 turn each, exactly one per turn)

| Action | Syntax (sketch) |
|---|---|
| plant | `{"action": "plant", "plots": {"3": {"plant": "sage", "soil": "yellow"}, "4": {"plant": "mint", "soil": "black"}}}` |
| brew | `{"action": "brew", "recipes": [{"mint": 1, "basil": 1}, {"sage": 1, "dill": 1, "elderberry": 2}]}` |
| mix | `{"action": "mix", "mixes": [[4, 9], [5, 6, 7]]}` |
| deliver | `{"action": "deliver", "potion": 12}` |
| skip | `{"action": "skip"}` |

- Plant reports what was planted where (and in which soil); partial success as before.
- Brew and mix are all or nothing; an infeasible brew or mix costs no turn.
- Errors (malformed calls, infeasible brews or mixes, invalid records) cost no turn; after 3 failed attempts in one turn, the turn is skipped.

## Observations

Every turn starts with the day, the turn and the garden:

```
[Day 3, turn 24]
Garden: free: 1, 6; growing: 2 (sage, yellow, 1 turn left), 3 (mint, black, planted turn 22); ready: 4 (nettle, brown, waiting 0); died: 5 (basil, yellow)
```

- Every plot shows its plant and soil. **(default)** A growing plot shows the turns left once its (plant, soil) growth time is in the notebook, and otherwise the turn it was planted. A ready plot shows how long it has waited. A plant that died is shown once.
- The garden line deliberately omits the request, the deadline and any results.

## The agent's memory and reply format

- The agent is a reasoning model. Its **thinking is discarded** after every reply: it is long and tied to the current turn. Only the visible reply stays in the context.
- The agent writes **structured notes** before its call, as in version 2. The schema will change: since observations are recorded automatically, the notes should carry the **thought process**, not repeat results:
  - pointers to new records;
  - interpretations of sources and of the request, with claim ids;
  - beliefs with the validator's status;
  - decisions with their reasons, citing ids.

  The schema is designed once the tools exist.

## Information and retention

| Class | Examples | Recoverable by | Retention priority |
|---|---|---|---|
| Recorded observations | potions, growth rows, validator results | an exact `kb_lookup` or `validate` | low: the cost is a lookup, plus knowing it exists |
| Read texts | passages and sources read | `search` again, if the agent remembers what to ask | medium: needs a pointer |
| Context only | unrecorded interpretations, derived requirements, hypotheses being tested, why each plot was planted, the plan, what was searched and found useless | nothing | **high: what compaction must protect** |

Observations are **recoverable by design**; this is a deliberate change from version 2, where exact results existed only in the context. The retention study targets reasoning, not observations. How to define and label the retention target is open.

## Kept from version 2

The turn loop, the LLM client and agent (thinking discarded, cut after the first call), checkpointing and `--resume`, the run outputs (`params.json`, transcripts, `actions.jsonl`, `llm_calls.jsonl`, `summary.json`), and the primary brewing rules.

**Removed:** the log action, garden logging, the potion label vocabulary, lore lines, the two-plant allergy, and the time-limited "brew the best" goals.

**Frozen:** the browser game (`game/`) and the oracle agent, which follow version 2. The compaction code (summary, fork, atomizer, notes) stays as it is until the new schema exists.

## Open items

- [ ] **(content)** Plant names and groups; the glossary; the pairs that give secondary effects; growth times and deaths per (plant, soil); the false-information chance per source kind; the corpus; 5–10 requests with their translations and success checks
- [ ] The validator's exact grammar; the record fields and the relation vocabulary
- [ ] `search` k and passage length; the `kb_lookup` row limit
- [ ] The new reply schema (the thought process)
- [ ] Defining and labelling the retention target; compaction method and guarantee (parked)
- [ ] Multi-agent variant (parked idea)
