# Potion Garden — the game

A browser version of the Potion Garden environment, played by a human instead of an LLM. You play the agent: you get the same system prompt, the same opening message from the user and the same environment replies, and every button or drag sends the same JSON call the agent would send. There is no LLM and no compaction: the whole conversation stays on screen.

## Playing

Open `game/index.html` in a browser (double-click works, no server or build step). The setup dialog takes the same parameters as `scripts/run_experiment.sh`; the same env seed gives the same hidden growth times as a Python run, so a human can play the exact garden an agent played. Its defaults are the parameters of the most recent LLM run (read from `runs/*/*/params.json` by `export_data.py`, seed included; the script defaults if there is no LLM run). Run `python3 game/export_data.py` after a new LLM run to update them.

| Control | Call it sends | Cost |
|---|---|---|
| Drag seed packets onto plots (or click a packet, then plots), then **Plant** | `{"action": "plant", "plots": {...}}` | 1 turn |
| Drag plants into the cauldron (several recipes = one batch), then **Brew** | `{"action": "brew", "recipe(s)": ...}` | 1 turn |
| Garden switch and/or potions dragged into the log book with labels, then **Log** | `{"action": "log", ...}` | 1 turn |
| **Skip** | `{"action": "skip"}` | 1 turn |
| **Gather**, knowledge base **Look up**, inventory **Ask** | `{"tool": "gather" / "kb_lookup" / "inventory"}` | free |

The notes box is the agent's visible notes: it is sent with your next call and stays in the conversation. The conversation is shown in a readable form (coloured by kind: garden, planting, harvest, cauldron, knowledge base); hover a message to see the exact text the agent gets, which is also what the downloaded `transcript.md` contains.

The board shows only what the agent can see: a plot shows its plant only once its planting is logged, turns left only once the growth time is logged too, and potions never show their recipe or effect. The goal, the allergy and brew results appear only in the conversation. Errors cost no turn; 3 failed attempts in a turn skip it; 20 calls without an action skip it.

The game is saved in the browser (localStorage) after every call, so a reload continues where you were. At the end, the results dialog shows the per-goal scores (as in `summary.json`), every potion brewed and the hidden growth times, and offers `transcript.md` (same format as a run's) and `run.json` (params, summary, actions, final state) for comparison with agent runs.

## Files

```
index.html, style.css   the page
js/data.js              generated: plants, stat sets, lore, labels, system prompt (do not edit)
js/engine.js            port of environment/, tools/ and the turn loop; all state is plain JSON
js/ui.js                drag and drop, rendering, saving, results
export_data.py          regenerates js/data.js from the Python sources
check_parity.py         checks the JS engine against the Python environment (needs node)
```

## Keeping it in sync with the Python environment

The hidden rules exist twice: in `environment/` and in `js/engine.js`. After changing the environment:

```
python3 game/export_data.py     # plants, stat sets, lore, labels, system prompt, defaults
python3 game/check_parity.py    # brewer for all 102,816 recipes with counts 1–6, growth times for 600+ seeds,
                                # and 60 random episodes through the real turn loop, message by message
```

Rule changes in `environment/brewer.py` (`_RULES`) and message wording in `tools/` have to be ported by hand to `js/engine.js`; `check_parity.py` reports any difference. The engine still accepts calls as raw text (the parity check sends malformed ones), but the game itself only sends calls built by its controls.
