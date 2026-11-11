# Reliable Context Compaction — Potion Garden Environment

This repository contains the research notes and the experimental environment for a study on **reliable context compaction** for LLM agents: when an agent's context is compacted (summarised, truncated or pruned), how much of the information it still needs is lost, and can that loss be bounded with a statistical guarantee (Learn-then-Test + Prediction-Powered Inference)?

The experiments run in the **Potion Garden**, a small fictional world in which an agent grows plants, learns how its garden behaves, brews potions and pursues user goals under a time budget. The environment is designed so that some needed facts exist **only in the agent's context**, and compaction can destroy them. The full design is in [demo_spec.md](demo_spec.md).

## Repository structure

```
README.md
requirements.txt
scripts/                    shell scripts that launch runs and the model server; every parameter set here or overridden on the command line
main.py                     entry point: builds all components from the inputs and runs one episode
input.py                    command-line arguments, validation, and everything related to experiment input
utils.py                    generic helpers not tied to a specific concept, incl. the clean transcript (also a command for older runs)
output.py                   writes the final outputs to runs/<agent>/<timestamp>/
LLM/
  client.py                 chat client for an OpenAI-compatible server (llama-server, vLLM, Ollama)
  parsing.py                finds the one JSON call in a reply and cuts off anything written after it
  agent.py                  the LLM agent: thinking is discarded after every reply, only notes + call are kept
  notes.py                  parses every reply into the reply schema (notes.jsonl)
  notes_review.py           steps through a run's replies for manual inspection (used in validation.ipynb)
  episode.py                the turn loop: garden state → agent → action → result → (compaction) → next turn
environment/                the hidden world: garden and growth timers, brewer rules, knowledge base, inventory, goals, turn clock
tools/                      one file per agent-facing tool (plant, gather, log, brew, skip, kb_lookup, inventory); thin wrappers around environment/
compaction/                 compactors: summary.py (the model summarises its own context); fork.py (replay a run to a turn, compact, continue); atomizer.py (split a run's context into atoms)
ledger.py                   records every needed fact when it appears; snapshots them at each compaction
checkpoint.py               per-turn checkpoints: saves the full state, restores it after a crash (--resume)
agents/                     non-LLM agents for testing, parameter tuning and baselines (random, replay of a recorded run, scripted oracle)
prompts/                    system prompt and user-message templates as text files
tests/                      unit tests (brewer rules, garden timing, logging edge cases)
game/                       browser game: a human plays the agent with the same messages and calls (no LLM, no compaction); see game/README.md
runs/                       results (see below)
temp/                       working data during a run (see below)
Papers/                     literature review (papers.xlsx)
validation.ipynb            manual inspection of the replies that do not follow the reply schema (Previous / Next)
idea.md, conversation.md    research idea and notes from early discussions
demo.md, demo_spec.md       first demo idea and the current environment specification
```

**Design principles**

- **The hidden rules stay hidden.** The brewer equation and the growth times live in `environment/` and are never imported by agent-facing code, so they cannot leak into a prompt.
- **Agents are interchangeable.** The turn loop talks to an agent through one interface ("here is the context, give me your response"). The LLM agent is one implementation; the random and oracle agents in `agents/` are others.
- *Note:* `episode.py` sits in `LLM/` for now, but the non-LLM agents use the same loop. It can move to the top level if that turns out cleaner.

## Running experiments

All runs are started from shell scripts in `scripts/`. Each script lists every parameter with its default value, and any parameter can be overridden on the command line. The script calls `main.py`, which does the work.

Parameters (`python -c "from input import build_parser; build_parser().print_help()"` lists them all):

| Group | Parameters |
|---|---|
| Agent | `--agent` (llm / random / oracle), `--llm-name`, `--llm-url`, `--thinking` (on / off), `--reasoning-effort`, `--temperature`, `--top-p`, `--max-tokens` (per reply, thinking included), `--llm-seed` |
| Garden | `--garden-size`, `--growth-min`, `--growth-max`, `--env-seed` |
| User | `--goals` (e.g. `time:S:30,target:I:10`), `--allergy` (e.g. `nettle+chamomile` or `none`), `--lore` (on / off: logging a potion unlocks herbal lore, read with kb_lookup) |
| Episode | `--turn-cap`, `--prompt-file` |
| Compaction | `--compactor`, `--context-window` (tokens), `--compaction-trigger` (fraction of the window, default 0.8; checked only between turns) |
| Output | `--runs-dir`, `--temp-dir` |

Seeds that are not given are drawn at random and recorded in `params.json`, so every run can be repeated. Temperature and top-p that are not given are left to the model's recommended values, which the server reads from the GGUF; `params.json` records what the server reports (`llm_server.default_sampling`).

### LLM agent

The model is served by llama-server with an OpenAI-compatible API. Start it first, then run with `--agent llm`:

```
scripts/serve_llm.sh                                   # preset qwen3.8-27b: Qwen3.8-27B Q8_0 on GPUs 0 and 1, 256k context
scripts/run_experiment.sh --agent llm --llm-name qwen3.8-27b-q8
```

Presets (`scripts/serve_llm.sh <preset>`): `qwen3.8-27b` (default), `qwen3.6-27b`, `nemotron-3-nano`. Each sets the model file, the name to pass as `--llm-name`, and the model card's recommended sampling as the server default. `run_experiment.sh` passes `--reasoning-effort medium`: Qwen3.8's default (`xhigh`) adds "consider plausible alternatives" to the system prompt, which works against the decisive play the prompt asks for.

Context shift is disabled in the server, so it never drops old tokens on its own. If the conversation no longer fits, the episode stops with `stop_reason: "context full"` in `summary.json`.

### Resuming an interrupted run

A checkpoint is saved after every completed turn. To continue a run that crashed or was stopped:

```
scripts/resume.sh runs/<agent>/<run_id>      # same as: python main.py --resume runs/<agent>/<run_id>
```

The run continues with exactly its saved parameters and state; at most the interrupted turn is replayed.

### Compacting a recorded run (fork)

```
python -m compaction.fork runs/<agent>/<run_id> --at 50 [--keep-turns 5]
```

Replays the run up to the end of turn 50 without model calls (and checks that the replay reproduces its transcript exactly), lets the model summarise its context except the last k turns (`--keep-turns`, default 5) with `prompts/summary.txt`, replaces the summarised part with the summary (`prompts/summary_continue.txt`) followed by the last k turns verbatim and lets the agent continue to the turn cap. The fork is written to `runs/<agent>/<run_id>/compactions/t050_summary/` with the usual run files; `compaction_summary.md` holds the summary, `compactions/001.json` the context before and after, and the transcripts mark the compaction point with a **compaction** entry. The model server must serve the run's model.

### Inspecting the notes

`validation.ipynb` steps through the replies of a run (`RUN`) that do not follow the reply schema, one per click: the reply as the agent wrote it, with the lines a problem names marked, next to how `LLM/notes.py` filed it. `browse(RUN, invalid_only=False)` steps through every reply. The notebook needs `ipykernel` and `ipywidgets` in the kernel's environment.

### Splitting a run into atoms

```
python -m compaction.atomizer runs/<agent>/<run_id> [--turns 1-10] [--thinking]
```

Splits `transcript_clean.md` (what the agent had in its context) into atoms with the run's model: one call per turn, with the agent's instructions, the opening message and the previous turn as context, using `prompts/atomize.txt`. An atom is one self-contained statement with the role of its speaker and a kind (goal, observation, state, inference, plan); there is no scoring. Thinking is off unless `--thinking` is given, and the first attempt decodes greedily (`--temperature`, default 0). A reply that is malformed, or leaves a message with content (or a bulleted line) without an atom, is retried with the next seed at temperature 0.7; if no attempt covers everything, the most complete one is kept and the uncovered messages are recorded and flagged in `atoms.md`. Writes `atoms.jsonl`, `atoms.md` (every message followed by its atoms) and `atoms_calls.jsonl` into the run folder.

## Outputs

### `runs/<agent>/<timestamp>/`

One folder per run. `<agent>` is the LLM name (e.g. `qwen3-8b`) or the non-LLM agent name (`random`, `oracle`). `<timestamp>` includes a short run ID or the seed, so parallel runs cannot collide.

| File | Contents |
|---|---|
| `params.json` | all experiment inputs: initial prompt, garden size, sampled growth times, LLM parameters, turn cap, goals, allergy, seeds, compaction settings |
| `transcript.md` | the agent's full thought process: every message in order, including the discarded thinking (marked as such) |
| `transcript_clean.md` | the same without the thinking: only what stays in the agent's context. Written at the end of the run; for older runs, `python utils.py [RUN_DIR ...]` (default: every run under `runs/`) |
| `notes.jsonl` | LLM agent only: the notes of every reply parsed into the reply schema (sections, sub-sections, one item per line; a "- none" with a comment counts as empty and its comment is kept as a remark; a line whose sub-section heading was left out is filed under the next sub-section in the schema order, and the reply is marked invalid for inspection), with departures from the schema. Written at the end of the run; for older runs, `python -m LLM.notes RUN_DIR ...` |
| `actions.jsonl` | one line per turn: turn number, action, result, errors |
| `final_state.json` | final inventory, garden and knowledge base |
| `summary.json` | per-goal results: best potion brewed, turns used, success or failure, allergy violations; why the episode stopped early, if it did |
| `ledger.jsonl` | every needed fact with the turn it appeared |
| `llm_calls.jsonl` | LLM agent only: one line per model call with token counts, finish reason, timing and the raw reply (before cutting) |
| `compactions/` | per compaction: context before and after, token counts, turn, and the ledger snapshot of facts the agent should still know; forks of the run (`t<turn>_summary/`, see above) |
| `atoms.jsonl`, `atoms.md`, `atoms_calls.jsonl` | only after running the atomizer: the atoms of the clean transcript, a readable version, and the model calls |

### `temp/<agent>/<timestamp>/`

Working data needed while the run is in progress: the knowledge base (`knowledge_base.sqlite`) and the latest checkpoint (`checkpoint.json`). Whether `temp/` is cleaned up after a successful run is *to be decided*.

## Status

- [x] Environment specification ([demo_spec.md](demo_spec.md))
- [x] Project setup (this README, folder structure, `requirements.txt`)
- [x] Environment implementation and tests (`python -m pytest`)
- [x] Turn loop, checkpointing and resume, random agent, `scripts/run_experiment.sh`
- [ ] Oracle agent and parameter tuning (a, b, N, goal budgets)
- [x] LLM agent served by llama-server (`scripts/serve_llm.sh`); thinking on and discarded after every reply
- [ ] Compaction methods
- [ ] Evaluation plan
