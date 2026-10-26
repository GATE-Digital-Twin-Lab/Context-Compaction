# Reliable Context Compaction — Potion Garden Environment

This repository contains the research notes and the experimental environment for a study on **reliable context compaction** for LLM agents: when an agent's context is compacted (summarised, truncated or pruned), how much of the information it still needs is lost, and can that loss be bounded with a statistical guarantee (Learn-then-Test + Prediction-Powered Inference)?

The experiments run in the **Potion Garden**, a small fictional world in which an agent grows plants, learns how its garden behaves, brews potions and pursues user goals under a time budget. The environment is designed so that some needed facts exist **only in the agent's context**, and compaction can destroy them. The full design is in [demo_spec.md](demo_spec.md).

## Repository structure

```
README.md
requirements.txt
scripts/                    shell scripts that launch runs; every parameter set here or overridden on the command line
main.py                     entry point: builds all components from the inputs and runs one episode
input.py                    command-line arguments, validation, and everything related to experiment input
utils.py                    generic helpers not tied to a specific concept
output.py                   writes the final outputs to runs/<agent>/<timestamp>/
LLM/
  init.py                   model setup, prompting, calls to the model, parsing of its replies
  episode.py                the turn loop: garden state → agent → action → result → (compaction) → next turn
environment/                the hidden world: garden and growth timers, brewer rules, knowledge base, inventory, goals, turn clock
tools/                      one file per agent-facing tool (plant, gather, log, brew, skip, kb_lookup, inventory); thin wrappers around environment/
compaction/                 compactors and the token-threshold trigger (empty for now; approach not settled yet)
ledger.py                   records every needed fact when it appears; snapshots them at each compaction
agents/                     non-LLM agents for testing, parameter tuning and baselines (random, scripted oracle)
prompts/                    system prompt and user-message templates as text files
tests/                      unit tests (brewer rules, garden timing, logging edge cases)
runs/                       results (see below)
temp/                       working data during a run (see below)
Papers/                     literature review (papers.xlsx)
idea.md, conversation.md    research idea and notes from early discussions
demo.md, demo_spec.md       first demo idea and the current environment specification
```

**Design principles**

- **The hidden rules stay hidden.** The brewer equation and the growth times live in `environment/` and are never imported by agent-facing code, so they cannot leak into a prompt.
- **Agents are interchangeable.** The turn loop talks to an agent through one interface ("here is the context, give me your response"). The LLM agent is one implementation; the random and oracle agents in `agents/` are others.
- *Note:* `episode.py` sits in `LLM/` for now, but the non-LLM agents use the same loop. It can move to the top level if that turns out cleaner.

## Running experiments

All runs are started from shell scripts in `scripts/`. Each script lists every parameter with its default value, and any parameter can be overridden on the command line. The script calls `main.py`, which does the work.

Parameters (planned):

| Group | Parameters |
|---|---|
| Agent | agent type (LLM / random / oracle), LLM name, sampling parameters (temperature, max tokens, …), LLM seed |
| Garden | garden size N, growth-time range a–b, environment seed |
| User | goals (type, stat, deadline or target), allergy (two-plant combination or none) |
| Episode | global turn cap, prompt file |
| Compaction | compactor, token threshold (to be added) |

## Outputs

### `runs/<agent>/<timestamp>/`

One folder per run. `<agent>` is the LLM name (e.g. `qwen3-8b`) or the non-LLM agent name (`random`, `oracle`). `<timestamp>` includes a short run ID or the seed, so parallel runs cannot collide.

| File | Contents |
|---|---|
| `params.json` | all experiment inputs: initial prompt, garden size, sampled growth times, LLM parameters, turn cap, goals, allergy, seeds, compaction settings |
| `transcript.md` | the agent's full thought process: every reasoning step and message, in order |
| `actions.jsonl` | one line per turn: turn number, action, result, errors |
| `final_state.json` | final inventory, garden and knowledge base |
| `summary.json` | per-goal results: best potion brewed, turns used, success or failure, allergy violations |
| `ledger.jsonl` | every needed fact with the turn it appeared |
| `compactions/` | per compaction: context before and after, token counts, turn, and the ledger snapshot of facts the agent should still know |

### `temp/<agent>/<timestamp>/`

Working data needed while the run is in progress: the knowledge base (a small SQLite database), inventory and garden tables, and other intermediate files. Whether `temp/` is cleaned up after a successful run is *to be decided*.

## Status

- [x] Environment specification ([demo_spec.md](demo_spec.md))
- [ ] Project setup (this README, folder structure, `requirements.txt`)
- [ ] Environment implementation and tests
- [ ] Non-LLM agents (random, oracle) and parameter tuning (a, b, N, goal budgets)
- [ ] LLM agent; how the local model is served is *to be decided* (e.g. Ollama, vLLM, llama.cpp or Transformers)
- [ ] Compaction methods
- [ ] Evaluation plan
