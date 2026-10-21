# Potion Agent Demo — Specification

*Working spec for the demo described in `demo.md`. Everything (flowers, effects, rules) is fictional.*

## Purpose

An interactive demo to generate conversations between a user and a tool-using agent, so we can see how models behave and whether context compaction loses information the conversation still needs. The user is played by a human for now. The domain is artificial, but it follows a general agent pattern: perceive, update state, look things up, act, record the outcome, reuse it later.

## Components

### Tools available to the agent

| Tool | Input | Output | Side effects |
|---|---|---|---|
| `segment_image` | image | list of flowers with counts | adds the flowers to the inventory; triggers `search_corpus` for any flower not yet in the KB |
| `search_corpus` | flower name | 1–2 sentence description | description is saved to the KB |
| `kb_query` | flower name(s) | flower descriptions + all outcome statements involving those flowers (relational join) | none |
| `get_inventory` | – | current flowers and counts | none |
| `brew` | recipe `{flower: count}` | effects dictionary (see below), or an *infeasible* error | consumes the flowers; writes an outcome statement to the KB if the result is non-empty |

### Stores

- **Inventory:** flower → count. Increased by images, decreased by brewing.
- **Knowledge base (relational, written by the system, not the agent):**
  - `flowers(name, description)`
  - `outcomes(outcome_id, effects)`: which effects and their sign only, **no magnitudes**
  - `outcome_flowers(outcome_id, flower)`: which flowers were used, **no quantities**
  - Example statement: *"combining flowers 1, 2 and 5 gives a potion with +happiness"*

## Brewing rules

- A recipe uses **3 or 4 distinct flowers**, each with a quantity ≥ 1.
- **Infeasible brew:** the inventory lacks the flowers or the quantities. The agent must react appropriately (tell the user, suggest alternatives).
- Brewing **consumes** the flowers used.
- The brewer is a **hidden, fixed equation**. The agent sees only the result:
  ```
  {"positive": {"strength": 5}, "negative": {"happiness": 3}}
  ```
- **Cancellation:** if the same effect appears as both positive and negative, it is removed from both, whatever the magnitudes.
- **No effect:** both dictionaries are empty. This happens when the combination is incompatible or when all effects cancelled out. The agent cannot tell which.
- **Quantities matter and are non-monotone**, e.g. 2-1-1 → +2% strength, 3-1-1 → +5%, 4-1-1 → +10%, 5-1-1 → nothing.

## Users

There are several user profiles. Each profile has:
- a **goal** (e.g. "the strongest strength potion");
- an **allergy**: either to a single flower, or to a specific combination of flowers (each flower is fine on its own).

The goal and the allergy are stated **only in the conversation**. They are never written to the KB.

## Information placement

| Information | Lives in | Survives compaction? |
|---|---|---|
| Inventory | inventory store | yes (tool) |
| Flower descriptions | KB | yes (tool) |
| Qualitative outcome statements | KB | yes (tool) |
| User goal | conversation only | **at risk** |
| Allergy (flower or combination) | conversation only | **at risk** |
| Exact quantities and magnitudes of results (e.g. 4-1-1 → +10%) | conversation only | **at risk** |
| Best result so far (recipe + magnitude) | conversation only | **at risk** |
| Failed / no-effect attempts | conversation only | **at risk** |

## Example scenario

1. The user shows several images; the inventory and KB fill up.
2. The user asks for the strongest strength potion possible. The agent searches by trial and error, using the KB statements and its earlier attempts, with a limited inventory.
3. The agent finds the best strength potion so far (e.g. 4×A + 1×B + 1×C → +10%).
4. The user says they are allergic to that combination (or to one of its flowers).
5. The agent must now look for the best strength potion that **avoids the allergy**, aiming above the best allowed result found so far. If it finds nothing better, the best earlier allowed potion remains the answer, and that is also worth remembering.
6. **Compaction happens.** Later turns check whether the agent still:
   - respects the allergy;
   - remembers the exact best recipe and its magnitude;
   - avoids repeating attempts that failed or did nothing;
   - remembers the user's goal.

## Needed facts (for the compaction loss)

These are the facts in the conversation that later turns depend on: goal, allergy, best recipe with exact quantities and magnitude, and failed or no-effect recipes. Because the scenario is built by us, we know which turn introduced each fact. That gives the "needed facts" labels for free; we still need to judge whether each fact survives compaction.

## Open items

- [ ] The brewer equation (simple, fixed; makes "best" well-defined and reachable within the inventory)
- [ ] When compaction triggers (after N turns or N tokens) and which compactors to try
- [ ] Segmentation model, and how real flower/plant species map to fictional names
- [ ] The question distribution Q (which kinds of user turns, in what proportions)
- [ ] Which local LLM plays the agent
