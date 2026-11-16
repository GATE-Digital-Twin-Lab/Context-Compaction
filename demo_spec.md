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
  - A plant that dies is reported when it would have become ready: the garden line shows it as died, the growth table records it, and the dead plant occupies its plot until `gather` clears it.
  - Every planting in a pair with a survival chance rolls independently (env seed).
- **Time:** discrete turns; **a day is 10 turns**. Every action costs exactly 1 turn; thinking and free tools cost nothing (within the free-call budget, see *Tools*).
- **One fixed world:** the stat rules, the secondary pairs, the growth times per soil, the death probabilities and the corpus are written together and do not change between episodes. The env seed only drives random deaths. Variation comes from the requests and the LLM seed.

**Soil table (hidden).** Growth time in turns; "dies" = never survives (the death is reported after the growth time); a percentage = survival chance.

| Plant | black | brown | yellow |
|---|---|---|---|
| mint | 6 | 2 | 5 |
| elderberry | 5 | 2, dies | 3, dies |
| nettle | 4, dies | 6, dies | 5 |
| sage | 4, dies | 5 | 2 |
| chamomile | 4 | 5 | 3 |
| dill | 3 | 2, **75%** | 3, dies |
| basil | 6, dies | 6 | 3 |
| rosemary | 4 | 4 | 6 |

Sampled once with seed 17, then hand-edited (nettle brown 3 → 6, nettle yellow 6 → 5, dill brown 3 → 2 and 86% → 75%) and frozen; the corpus is written from it. Sampling rules:
- growth time per (plant, soil) uniform in 2–6 turns (equal times allowed);
- 6–8 dying (plant, soil) pairs in total, at most 3 per soil, and every plant keeps at least one soil with 100% survival;
- 1–2 of the dying pairs get a survival chance uniform in 10–90% (whole percent); their growth time becomes 2 turns if the chance is below 50%, else 3.

Here: 8 dying pairs, one with a chance (dill in brown, 75%). Nettle, elderberry and dill each have a single safe soil (yellow 5, black 5, black 3).

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

Secondary effects come from **pairs of plants**. A pair counts if both plants are present in the recipe, **whatever their counts**. Each listed pair contributes its modifier; two different pairs with the same label both count. Which pairs give which label is hidden.

| Label | Modifier | Pairs (hidden) | How a source might describe it |
|---|---|---|---|
| fragrant | +25% | mint + sage; basil + rosemary | "the brew smelled of a spring meadow" |
| warming | +50% | chamomile + nettle; basil + sage | "a warmth spread through his chest" |
| sweet | +100% | dill + mint; chamomile + sage | "tasted of honey" |
| bitter | −25% | elderberry + mint; dill + rosemary | "bitter on the tongue; he barely felt it" |
| murky | −50% | elderberry + rosemary; dill + nettle | "cloudy, and the effect faded by noon" |
| toxic | −100% | elderberry + nettle | "the goat that drank it never rose again" |

**How the pairs were chosen:**
- **No pair lies inside a stat set**, so the minimal recipe of a stat (exactly its set) never carries a secondary effect. Of the 28 pairs, 17 lie inside a stat set, which leaves **11**; all 11 are used. Two pairs per label would need 12, so **toxic has a single pair**: the one deadly pairing.
- **Each pair gives one label**, and **a label's two pairs share no plant**: excluding one plant never removes both ways to make a label.
- Each of I, S, V, D, extended with a 4th plant, has at least one boost and at least one drawback, and the best boosts differ (I +100%, S +125%, V +75%, D +150%).

**Consequences:**
- **W** already has 4 plants, so a W brew has no secondary effect; W can be boosted only by mixing.
- Every pair outside a stat set carries a label, so a 2-plant probe of a pair inside a stat set always returns nothing.

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

The corpus refers to plants by **folk names** ("Hesketh" = sage) and **groups**. A group is a place where plants grow naturally ("the plants of the mill pond", "what grows at Coldharbour"), so a plant's origin and its groups are the same fact. A hidden table of names and groups is written first; the corpus and the requests are written from it.

- **Aliases:** 3 folk names per plant (24 in all), each belonging to **exactly one** plant. Confusion comes only from myths (a source saying a name means another plant). Aliases are **opaque**: people's and saints' names or invented words, never a description or a real folk etymology, so they can be resolved only from sources, not from the model's own knowledge.
- **Groups:** **8 groups of 3 plants**, every plant in **3 groups**.
  - **Two plants share at most one group**, so any two of a plant's groups identify it ("grows both by the mill pond and at Ludding").
  - **No group equals a stat set**, so a group never gives away a recipe.
  - The pond group is **nettle, mint, elderberry** (the maiden request).
  - Places are **named locations** ("Coldharbour"), so the model cannot guess their plants from its own knowledge; only the mill pond keeps a descriptive name, because the maiden request refers to it.

**Names and groups (hidden, `content/plants.json`).** The group layout was drawn with seed 17 from the 62 layouts that satisfy the rules.

| Plant | Aliases | Groups |
|---|---|---|
| mint | Wenna's sprig, Ferrow, Saint Aldhelm's herb | mill pond, Ashby Row, Brackley |
| elderberry | Old Gilly's herb, Brannock, Saint Osric's leaf | mill pond, Harrow's End, Wendle Cross |
| nettle | Tobin's wort, Quellock, Saint Brede's sprig | mill pond, Ludding, Kettlebury |
| sage | Prior Anselm's leaf, Hesketh, Saint Cuthwin's wort | Coldharbour, Brackley, Kettlebury |
| chamomile | Mother Hale's herb, Pellow, Saint Ermengild's sprig | Harrow's End, Brackley, Ludding |
| dill | Corbin's leaf, Thrale, Saint Wulfric's herb | Wendle Cross, Ashby Row, Kettlebury |
| basil | Ysolde's sprig, Gammock, Saint Edith's wort | Coldharbour, Harrow's End, Ashby Row |
| rosemary | Remy's herb, Morrick, Saint Hild's leaf | Coldharbour, Wendle Cross, Ludding |

Pairs that share no group: mint–rosemary, elderberry–sage, basil–nettle, chamomile–dill.

## Sources

- **Corpus:** a large fixed **pool** of texts of five kinds, plus distractor texts about unrelated things. Each episode gets a **sample** of the pool, drawn with `corpus_seed` (separate from the garden seed). Each source shows its **title, author and kind**. **(content)**
- **One focus plant per source.** Other plants appear in it only as co-ingredients of its brews and mixes, possibly under folk names.
- **Kinds**, from most to least reliable:

| Kind | Fact correct | In the pool | In a sample | Length | What it tells |
|---|---|---|---|---|---|
| Monastery books | 100% | one per plant | rare | long | everything about its plant: names, groups, soil hints, brews with primary and secondary effects, some mixes |
| Apothecary transcripts | 80% | many | frequent | medium, often table-like | experimental results: brews and mixes with their effects, plants under their official names; rarely names or groups |
| Herbal lady tales | 70% | many | frequent | long, mostly padding | names, groups, hints about the plant; rarely a brew |
| Merchant pamphlets | 60% | lots | very frequent | short, some padding | a few facts of any kind |
| Folk tales | 40% | lots | very frequent | short, some padding | a few facts of any kind, vaguely: a primary effect is hard to tell from a secondary one |

- **Experimental and non-experimental facts:**

| Fact | Experimental | How the agent checks it |
|---|---|---|
| alias (a folk name = a plant) | no | sources only |
| group (a plant grows in a place) | no | sources only |
| soil hint (how a plant grows in a soil: dies, sometimes fails, fast, slow) | yes | plant it (costs turns and plants) |
| brew (plants → a primary stat through the glossary, or a secondary label, `toxic` included) | yes | brew it |
| mix (two brews → an effect) | yes | mix it |

  Not facts: the glossary (it is in the system prompt), undrinkability (never shown; inferred from `toxic` and the intensities) and pure lore ("the monks first grew sage"), which is padding.
- **Facts.** Every source is written from a hidden **source sheet**: its kind, focus plant, facts (each true or false) and amount of padding; the sheets are the answer key. A fact may name only some of the plants ("nettle and chamomile, among two others").
- **Truth is per fact**, not per source, and is drawn **when the pool is built**, at the kind's rate; one text can mix true and false facts. Monastery books are always true.
- **Shared myths:** a false fact is not a random error. A **myth pool** is drawn before any text is written: each fact has **one fixed wrong version per kind**, so all the folk tales that get a fact wrong tell the same myth, and cheap sources can agree with each other and still be wrong. E.g. an apothecary transcript tells of a messenger who drank a potion with nettle and chamomile among two other plants and fell ill (toxic); the truth is a D potion with warming.
  - **The myth pool** (`python -m corpus.myths` → `content/myths.json`, seed 17): every catalogue fact has one myth for each fallible kind (transcript, herbal tale, pamphlet, folk tale), **different across the kinds** and never the truth. A myth is **one change** from the truth:

| Fact | Myth |
|---|---|
| alias | the name means another plant that **shares a group** with the true one (a local confusion) |
| group | the plant grows at a place it is **not** in (a plant is moved, never denied where it grows) |
| soil hint | another category |
| 2-plant brew | another label, or nothing (a nothing pair gets a label) |
| 3-plant brew | swap, drop or add a label; name the wrong stat, claim a stat where there is none, or deny the stat |
| mix | one **revealed effect** is wrong (the stat, the secondary, or the second brew's own effect); the plants and how they are named stay true |

  - **References stay true:** an alias or group used inside a brew or mix always means its true plant, and a text never states a false alias and also uses that alias.
- **Mixes** are reported only by monastery books and apothecary transcripts, and only simple ones: two brews of 2 + 2 or 3 + 2 plants (see *Mixes* below).
- **Claims are implied, never numeric.** A source tells what happened ("my boy could suddenly carry two full buckets instead of one"); the agent infers the relation (a doubling: sweet, or a stronger base) and finds the exact values and quantities by experiment. **No source hints at quantities**: counts are found only by experiment. Some facts appear in no source and can only be found by experiment.
- **Vagueness is separate from falsity:** a true fact can be told vaguely (folk tales especially), and a false one clearly.
- **Contradictions:** several sources may support a fact and others deny it.
- **Reliability:** the system prompt states the **order** of the kinds only; the probabilities are hidden.
- **Padding:** besides the distractor texts, sources carry meaningless detail ("I describe my morning before going out to gather herbs"), the herbal lady tales most of all. Padding states no facts.
- **The fact catalogue:** one master table per fact type, with every possible fact and its true value. A source with focus plant X draws its facts from the rows that involve X (43 rows per plant: 3 aliases, 3 groups, 3 soils, 7 pairs, 21 triples, 6 mixes). Built by `python -m corpus.catalogue` into `content/catalogue.json` (204 rows).

| Table | Rows | True values |
|---|---|---|
| alias | 24 | the plant |
| group | 24 (8 groups × 3 members) | the group's members |
| soil hint | 24 (8 plants × 3 soils) | dies; sometimes fails (dill in brown); fast (2–3 turns); slow (5–6 turns); ordinary (4 turns) |
| 2-plant brew | 28 | a secondary label (11) or nothing (17) |
| 3-plant brew | 56 | the stat, for the 4 stat triples (I, S, V, D); 0, 1 or 2 secondary labels (10 / 26 / 20 triples) |
| mix | 48 (6 per focus plant) | the stats whose sets are present, the labels, drinkable; plus what the source reveals |

- **How a fact names its plants:** the official name, an alias (the agent must find what it means) or a group ("nettle with one of the pond plants"). A group reference is a hint only: it does not identify the pair or triple, so it never counts as the true source for it.
- **A brew's primary effect names the stat only.** Whether a stat triple gives +, − or nothing depends on the counts, which no source gives; a primary fact means "these plants together act on S", and its myth names the wrong stat or says nothing happens. The direction is left to experiment.
- **Mixes** (`corpus/catalogue.py`, `mixes()`): a mix is told as a story about two brews.
  - **No counts:** sources never give quantities, so a mix is judged on its **plants** only. A primary "acts on S" when S's set is present (direction left to experiment, as for brews); the labels depend on presence alone.
  - **The named brew** `{X, y}`, X the focus plant: told by official names, **without its effect**.
  - **2 + 2:** the second brew `{u, v}` is any two plants (X included; not the named brew itself), named in one of three styles: **two aliases**, **an alias and a group**, or **two groups** ("a plant of the mill pond and one of Kettlebury"). When a group is used, the second brew's **own effect** is revealed too (if it has one). The source reveals **one effect** of the mix.
  - **3 + 2:** the second brew is **a whole group** ("all three plants of Coldharbour"), any group. The source reveals **one stat** (if any) and **one secondary** (if any) of the mix.
  - **What a drinker notices:** a secondary is revealed only if it acts: mixed-sign modifiers cancel, so then none is revealed; otherwise a label of the net's sign. An undrinkable mix (toxic, or net ≤ −100%) shows no stat, only its poison.
  - **Selection** (seed 17): **6 per focus plant**, 3 of 2 + 2 (one per naming style) and 3 of 3 + 2, each with something to reveal. **W:** every plant gets **1 W mix** (a 3 + 2 whose plants contain W's set, e.g. `{X, dill}` + Harrow's End), with W the revealed stat; no other mix reaches W. No source describes a 4-plant brew, so these are the only written evidence for W.
  - With up to 5 plants a mix can act on two stats (one in the current selection); only one is revealed.
- **Guarantees:**
  - **in the pool:** every 2-plant brew, 3-plant brew and soil hint has at least one true source that names its plants (name or alias);
  - **in the sample:** every alias and group has at least one true source (the repair rule below). The books cover most of the rest.
- **Building the pool**, in layers:
  1. the catalogue of true facts, classified as above;
  2. the myth pool;
  3. the source sheets;
  4. the texts, generated from the sheets, each **checked** against its sheet: every fact stated with its intended truth, nothing else;
  5. the sampler.
- **Sampling:** the sampler draws texts per kind with `corpus_seed` (books rarely). Then, for every non-experimental fact with **no true source** in the sample, it adds one from the pool, starting with the least reliable kind: a folk tale stating the truth, if none a pamphlet, then a herbal tale, a transcript, and last the plant's book. This keeps the guarantee from becoming "a book for every plant that matters".
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

| Record | Fields | Status |
|---|---|---|
| `claim` (c#) | `source` (id), `quote` (the passage), `says` (a validator statement, or a name: `{"name": "pond plant", "plant": "nettle"}`), `trust` (high / medium / low); optional `why` | none: a claim reports what a source says, as the agent understands it |
| `belief` (b#) | `statement` (validator grammar), `why` (**required**: why the agent believes it); optional `from` (claim ids) | set **only by the validator**, recomputed against the data at every lookup |
| `requirement` (r#) | `phrase` (from the request); `means` (any of `stat`, `at_least`, `deadline_turn`, `avoid`) and/or `open` (a question still to answer); optional `from`, `why` | none |

- Records are told apart by **origin**: claims cite a source, beliefs are the agent's own and are judged by data, and requirements come from the request. Claims and beliefs share the validator's grammar, so a claim can be turned into a belief and tested.
- **Groups are name claims**: a source naming the pond plants gives one name claim per member, written in one batched call; a lookup by name returns them all, and a disagreeing source is a separate claim per member.
- **Requirements are refined over time**: at the start the agent knows only part of the request's meaning (e.g. the stat, and an open question "which plants are the pond plants?"); it replaces the requirement when sources answer it. An unanswered `open` question is part of the thought process to retain.
- **Corrections:** a new record with `replaces: <id>` (same type); the old one stays, marked as replaced, and lookups hide it unless asked. Every record gets an id and the turn it was written.
- `kb_lookup` filters on record type and fields (potions: effect, intensity, secondary, pattern; growth: plant, soil; claims: source, name, plant, trust; beliefs: status, plant; requirements: open). The more fields are given, the narrower the answer; broad lookups return many rows and fill the context. At most 30 rows per lookup, with the total count shown.

## Validator

A free tool that checks statements against the notebook's **automatic records** (potions and growth), never against the hidden rules. It answers in three states, with the evidence:

```
{"status": "true" | "false" | "unknown", "for": [6, 18], "against": [], "tested": 7}
```

| Kind | Example | True | False | Unknown |
|---|---|---|---|---|
| sufficiency: every potion matching P has E | sage + chamomile → sweet | no counterexample among the n matching potions | one matching potion without E | no matching potion |
| necessity: every potion with E matches P | +D needs nettle | a witness with E, and no potion outside P (n of them) has E | one potion outside P has E | no witness, or nothing outside P tried |
| relation: a higher count of plant X never lowers (increases) / never raises (decreases) the intensity of a stat | more chamomile → S never decreases | ≥ 1 qualifying pair, none disagreeing | one pair disagrees | no qualifying pair |
| soil: always dies / always survives / growth time / survival ≥ p or ≤ p | dill in brown survives ≥ 60% | no counterexample; for a rate, the 95% Wilson interval lies above (≤: below) p | a counterexample; the interval lies on the wrong side | nothing finished; the interval contains p |

- **Patterns** (shared with `kb_lookup`): each plant gets an exact count, `any` (present), `odd`, `even` or `absent`; `only: true` forbids other plants, so a pattern can be an exact recipe. A list of patterns means any of them.
- **Effects**: a stat with its sign (`+S`, `-I`) with an optional minimum (`at_least`), `none` (no stat effect), or a secondary label; `not: true` negates. **Drinkability is not an effect**: it is never shown, so the validator must not reveal it; the agent reasons from the labels (`toxic`) and the intensities.
- **Qualifying pairs** for a relation differ **only** in the count of the plant (0 allowed, so adding a plant is a relation). The intensity is that of the signed stat, 0 when the potion lacks it. "Increases" means never decreases: unchanged pairs are reported as `flat` and do not refute. Pairs that also differ elsewhere are counted as `confounded` and ignored.
- **Left to `kb_lookup`**: "this exact recipe gives X" and "some recipe gives X" are lookups (a pattern with `only: true`; any row), so they are not validator statements.
- Evidence lists are cut at 10 entries; `tested` is the full count. Answers are only from data: `true` means "no counterexample in n", not proof.
- A `belief` record is a stored validator statement. Its status is the validator's answer at lookup time, so a belief in the notebook is never out of date.

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
| `gather` | collects all ready plots and clears dead plants; those plots are free at once | free |

- **Budget:** `search`, `record` and `validate` together are limited to **5 calls per turn**. Every operation can be batched. A batched call counts as one call; a call that fails (malformed) does not count. The budget resets every turn, and every counted answer ends with how many calls are left.
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

- Every plot shows its plant and soil. **(default)** A growing plot shows the turns left once its (plant, soil) growth time is in the notebook, and otherwise the turn it was planted. A ready plot shows how long it has waited. A dead plant is shown under died until `gather` clears it.
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

- [x] **(content)** The pairs that give secondary effects (see *Secondary effects*)
- [x] **(content)** Growth times and deaths per (plant, soil) (see *Plants, garden, soils*)
- [x] **(content)** Source kinds, their correct rates and what they tell (see *Sources*)
- [x] **(content)** The corpus structure: a pool sampled per episode, experimental and non-experimental facts (see *Sources*)
- [x] **(content)** The fact catalogue's tables, guarantees and the rules for names and groups (see *Plant names and groups*, *Sources*)
- [x] **(content)** The myth pool (see *Sources*)
- [ ] **(content)** The glossary; the source sheets and texts; pool and sample sizes per kind; 5–10 requests with their translations and success checks
- [x] The validator's grammar (see *Validator*)
- [x] The record fields of claims, beliefs and requirements (see *Notebook*)
- [ ] `search` k and passage length (the `kb_lookup` row limit is 30)
- [ ] The new reply schema (the thought process)
- [ ] Defining and labelling the retention target; compaction method and guarantee (parked)
- [ ] Multi-agent variant (parked idea)
