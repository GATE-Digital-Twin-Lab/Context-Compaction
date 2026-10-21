# Potion Garden Agent Demo — Specification

*Working spec, superseding the first version in `demo.md`. Everything (plants, effects, rules) is fictional.*

## Purpose

A simulated environment for generating agent episodes, so we can study **what a tool-using agent forgets when its context is compacted**. The agent grows plants in a garden, learns the garden's properties, experiments with potions and pursues user goals under a time budget. The main measurement is information retention across compaction; potion quality is an auxiliary performance metric.

## World

- **Garden:** each user has a garden with **N plots**. Every garden has its own growth time per plant type (because of soil, location, etc.). Growth times are fixed for a given garden and plant and unknown to the agent; it must learn them.
- **Seeds** are unlimited for every catalogue plant; the **inventory** has no size limit.
- **Plants:** a fixed catalogue of plant types, all available for planting. The knowledge base starts with the catalogue (names only).
- **Brewer:** a hidden, fixed equation that maps a recipe to effects (see Brewing rules).
- **Time:** discrete turns. Every action costs exactly **1 turn**. Thinking, planning and knowledge-base lookups cost **0 turns**.

## Actions (1 turn each, any number of items per action)

| Action | What it does |
|---|---|
| **Plant** | Plants any number of plants of any types in free plots |
| **Gather** | Harvests any number of ready plots into the inventory, freeing those plots |
| **Log** | Writes any number of facts to the knowledge base |
| **Brew** | Brews one potion from the inventory; consumes the plants used. An infeasible brew costs 0 turns |
| **Skip** | Does nothing; time passes |

Free (0-turn) tools: **KB lookup**, **inventory lookup**.

## Observations

Each turn the agent is told which plots have become ready, e.g. *"plots 11 and 17 are ready"*.
- If the planting of those plots was **logged**, the message names the plants: *"plot 11 (flower_2) and plot 17 (flower_5) are ready"*.
- If it was **not logged**, only plot numbers are given. The agent must remember what it planted where.

## Knowledge base

Written only through the **Log** action. It can hold:
- **Planting records:** which plant is in which plot (turns observations into named ones)
- **Growth times:** "flower_2 grows in 4 turns in this garden"
- **Qualitative outcome statements:** "flower_1 + flower_2 + flower_5 → +happiness" (no quantities, no magnitudes)

User goals and the allergy are **not** loggable in this version; the agent must remember them. Making the allergy loggable (so protecting it becomes the agent's choice) is a possible later variant.

Lookups are free and retrieve all statements involving given plants (a relational join).

## The logging trade-off (core mechanic)

Logging is safe but costs a turn. Keeping facts in the conversation is free but at risk of compaction.
- Batching saves time: an agent that remembers two growth times can log both in one action.
- Bad timing costs plots: e.g. gather → log → brew at turns K, K+1, K+2 while another plant became ready at K+1 means that plot sits idle instead of growing something new.

So a good agent will deliberately keep some facts unlogged in its context. Those are exactly the facts compaction can destroy.

## Brewing rules

- A recipe uses **3 or 4 distinct plants**, each with quantity ≥ 1, written as `{plant: count}`.
- **Infeasible brew:** not enough plants in the inventory. It costs **no turn** (nothing is consumed), and the agent must react appropriately.
- Output: `{"positive": {"strength": 5}, "negative": {"happiness": 3}}`
- **Cancellation:** an effect appearing as both positive and negative is removed from both, whatever the magnitudes.
- **No effect:** both dictionaries are empty (an incompatible combination, or everything cancelled out). The agent cannot tell which.
- **Quantities matter and are non-monotone**, e.g. 2-1-1 → +2%, 3-1-1 → +5%, 4-1-1 → +10%, 5-1-1 → nothing.

## Users

Users are **independent and isolated**: each episode starts with an empty garden, an empty inventory and a KB holding only the plant catalogue. Nothing carries over between users, which keeps episodes i.i.d. as LTT/PPI calibration requires.

The user sets the **initial conditions** and the **goals**:
- **Garden size** N.
- **Allergy** (optional; some users have none): always to a **combination of two plants**. Any recipe containing both is forbidden; each plant is fine on its own or with others. Single-plant allergies are excluded, because the agent would simply never plant that plant.
- **Goals** (about 3 per episode, pursued one after another), each constrained by time, by magnitude, or both, e.g. *"the best strength potion within 30 turns"*, *"a strength potion of at least +10%"*, *"at least +10% strength within 30 turns"*.

## Compaction

- Triggered when the context exceeds **N tokens** (independent of turns).
- With about 3 goals per episode, at least one compaction happens.
- The same garden can be run with **0, 1, …, k compactions** for comparison.

## Facts worth remembering

| Fact | Where it lives unless logged |
|---|---|
| Current goal, which goals are done | conversation only (cannot be logged) |
| Allergy (two-plant combination) | conversation only (cannot be logged) |
| Exact quantities and magnitudes of brews | conversation only (KB keeps only qualitative statements) |
| Best result so far | conversation only |
| Failed / no-effect recipes | conversation only |
| Planting map (what is planted where) | conversation, **unless logged** |
| Observed growth times | conversation, **unless logged** |
| The agent's plan / schedule | conversation only |

The inventory, logged facts and the plant catalogue are always available through free lookups.

## Measurement

- **Main (retention):** at each compaction point, the simulator log gives the set of goal-relevant facts known so far. The loss is the **fraction of those facts lost** in the compacted context. Defining the facts at the compaction point keeps the loss independent of what the agent does afterwards, since its later actions change after compaction.
- **Auxiliary (performance):** best potion achieved per goal, turns used, goals completed, idle plots, infeasible brews, allergy violations. Needs several runs per garden, because LLM strategy and randomness add noise.

## Planning

Planning is free (0 turns) and is **not** given a dedicated tool or notepad: the agent writes its plan in its own reasoning, so the plan is another fact compaction can destroy. Recommended agent loop: **plan → execute → re-plan** when an observation contradicts the plan.

## Open items

- [ ] Brewer equation (simple, fixed; makes "best" well-defined and reachable)
- [ ] Growth-time distribution across gardens; number of plant types; garden sizes
- [ ] Token threshold for compaction, and which compactors to try
- [ ] Prompt format of the per-turn observation and the action syntax
- [ ] Which local LLM plays the agent
- [ ] Optional: a scripted reference planner that knows the hidden rules (upper bound for the auxiliary metric)
