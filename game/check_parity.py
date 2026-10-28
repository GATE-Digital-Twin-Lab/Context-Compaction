"""Checks that the game's JS engine (game/js/engine.js) behaves exactly like the Python environment:
brewer results for every recipe with counts 1-6, growth times for many seeds, and whole random
episodes (every message and the final summary) played through the real turn loop. Needs node.

    python3 game/check_parity.py
"""

import json
import random
import subprocess
import sys
from itertools import combinations, product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.base import Agent, AgentReply  # noqa: E402
from environment.brewer import PLANTS, STAT_SETS, brew  # noqa: E402
from environment.garden import sample_growth_times  # noqa: E402
from environment.goals import validate_allergy  # noqa: E402
from environment.knowledge_base import LABELS  # noqa: E402
from environment.world import World  # noqa: E402
from input import parse_allergy, parse_goal  # noqa: E402
from ledger import Ledger  # noqa: E402
from LLM.episode import opening_message, play_turn  # noqa: E402
from output import summary  # noqa: E402
from tools.dispatcher import Dispatcher  # noqa: E402

ENGINE = ROOT / "game" / "js" / "engine.js"

JS_RUNNER = """
const PG = require(process.argv[1]);
const job = JSON.parse(require("fs").readFileSync(0, "utf8"));
const out = {};
if (job.recipes) out.brews = job.recipes.map((r) => PG.brew(r));
if (job.seeds) out.growth = job.seeds.map(([seed, a, b]) => {
  const rng = new PG.PyRandom(seed);
  return PG.PLANTS.map(() => rng.randint(a, b));
});
if (job.episodes) out.episodes = job.episodes.map((ep) => {
  const config = { ...ep.config, goals: ep.config.goals.split(",").map(PG.parseGoal) };
  config.allergy = PG.parseAllergy(ep.config.allergy, config.goals);
  const game = PG.Game.create(config);
  for (const call of ep.calls) game.call(call);
  return { messages: game.s.messages.map((m) => [m.turn, m.role, m.content]), summary: game.summary() };
});
process.stdout.write(JSON.stringify(out));
"""


def run_js(job: dict) -> dict:
    proc = subprocess.run(
        ["node", "-e", JS_RUNNER, str(ENGINE)], input=json.dumps(job), capture_output=True, text=True, check=True
    )
    return json.loads(proc.stdout)


# --- scripted episodes ---------------------------------------------------------------


class ScriptedAgent(Agent):
    """Makes random but mostly sensible calls from the true world state, and records them."""

    def __init__(self, world: World, rng: random.Random) -> None:
        super().__init__()
        self.world, self.rng, self.calls = world, rng, []

    def _reply(self) -> AgentReply:
        call = self._choose()
        self.calls.append(call)
        return AgentReply(call if isinstance(call, str) else json.dumps(call), call)

    def _choose(self):
        w, r = self.world, self.rng
        state = w.garden.state(w.turn)
        kind = r.choices(
            ["gather", "inventory", "lookup", "plant", "brew", "log", "skip", "bad"],
            weights=[4, 1, 2, 5, 5, 4, 1, 1],
        )[0]
        if kind == "gather":
            return {"tool": "gather"}
        if kind == "inventory":
            return {"tool": "inventory"}
        if kind == "lookup":
            plants = r.sample(PLANTS, r.randint(1, 3)) + (["lavender"] if r.random() < 0.1 else [])
            return {"tool": "kb_lookup", "plants": plants}
        if kind == "plant":
            plots = r.sample(state.free, r.randint(0, len(state.free))) if state.free else []
            if r.random() < 0.2:
                plots.append(r.choice([0, w.garden.size + 1, *[g.plot for g in state.growing], 1]))
            plots = sorted(set(plots))
            names = [*PLANTS, "lavender"] if r.random() < 0.1 else PLANTS
            return {"action": "plant", "plots": {str(p): r.choice(names) for p in plots}}
        if kind == "brew":
            recipes = [self._recipe() for _ in range(r.choices([1, 2, 3], weights=[5, 2, 1])[0])]
            return {"action": "brew", "recipe": recipes[0]} if len(recipes) == 1 and r.random() < 0.5 else {
                "action": "brew", "recipes": recipes}
        if kind == "log":
            call = {"action": "log"}
            if r.random() < 0.6:
                call["garden"] = True
            potions = w.inventory.potions
            entries = []
            for _ in range(r.randint(0, 3) if potions else 0):
                pid = r.randint(1, len(potions) + (1 if r.random() < 0.1 else 0))
                plants = list(potions[min(pid, len(potions)) - 1].recipe)
                if r.random() < 0.1:
                    plants.append(r.choice(PLANTS))
                labels = {p: r.choice([*LABELS, "maybe"] if r.random() < 0.05 else LABELS)
                          for p in r.sample(plants, r.randint(0, len(plants)))}
                entries.append({"id": pid, "labels": labels})
            if entries or r.random() < 0.5:
                call["potions"] = entries
            return call
        if kind == "skip":
            return {"action": "skip"}
        return r.choice(["{bad", "no json here", '{"action": "dance"}', '{"tool": "gather", "action": "skip"}',
                         "5", '{"action": "brew", "recipe": {"mint": 1, "sage": 1}}',
                         '{"action": "brew", "recipe": {"mint": 0, "sage": 1, "dill": 1}}',
                         '{"action": "log", "potions": [{"id": "x"}]}'])

    def _recipe(self) -> dict:
        w, r = self.world, self.rng
        if r.random() < 0.6:
            plants = list(r.choice(list(STAT_SETS.values())))
            if len(plants) == 3 and r.random() < 0.3:
                plants.append(r.choice([p for p in PLANTS if p not in plants]))
        else:
            plants = r.sample(PLANTS, r.randint(3, 4))
        r.shuffle(plants)
        return {p: max(1, min(w.inventory.plants[p], r.randint(1, 4))) if r.random() < 0.9 else r.randint(1, 6)
                for p in plants}


class Capture:
    """Stands in for RunOutput: keeps the messages only."""

    def __init__(self) -> None:
        self.messages = []

    def log_message(self, turn, role, content):
        self.messages.append([turn, role, content])

    def log_call(self, *args):
        pass

    def log_llm_call(self, *args):
        pass

    def log_facts(self, *args):
        pass


def python_episode(config: dict, seed: int) -> tuple[list, dict, list]:
    goals = [parse_goal(g) for g in config["goals"].split(",")]
    world = World.create(config["garden_size"], (config["growth_min"], config["growth_max"]), goals,
                         parse_allergy(config["allergy"]), config["turn_cap"], config["env_seed"], lore=config["lore"])
    agent, out, ledger = ScriptedAgent(world, random.Random(seed)), Capture(), Ledger()
    dispatcher = Dispatcher(world)
    while not world.episode_over:
        play_turn(world, agent, dispatcher, out, ledger)
        if world.turn == 2:
            assert out.messages[0][2] == opening_message(world)
    return agent.calls, summary(world), out.messages


def normalise(data):
    """JSON round trip, so tuples and lists compare equal."""
    return json.loads(json.dumps(data))


def main() -> int:
    failures = 0

    recipes = [dict(zip(plants, counts))
               for n in (3, 4) for plants in combinations(PLANTS, n) for counts in product(range(1, 7), repeat=n)]
    seeds = [[s, a, b] for s in [*range(200), 2**31 - 1, 2**32 + 5, 987654321012] for a, b in [(2, 6), (1, 10), (3, 3)]]
    episodes = []
    rng = random.Random(1)
    for i in range(60):
        goals = rng.choice(["target:I:10", "target:I:5,time:S:8,target:D:2", "time:V:12,time:W:6", "target:D:20"])
        allergy = rng.choice(["none", "nettle+chamomile", "mint+dill", "basil+sage"])
        config = {"garden_size": rng.randint(1, 14), "growth_min": 1, "growth_max": rng.randint(1, 6),
                  "env_seed": rng.randrange(2**31), "goals": goals, "allergy": allergy,
                  "lore": rng.random() < 0.7, "turn_cap": rng.randint(5, 45)}
        try:
            validate_allergy(parse_allergy(allergy), [parse_goal(g) for g in goals.split(",")])
        except ValueError:
            config["allergy"] = "none"
        calls, summ, messages = python_episode(config, seed=i)
        episodes.append({"config": config, "calls": calls, "summary": summ, "messages": messages})

    js = run_js({"recipes": recipes, "seeds": seeds,
                 "episodes": [{"config": e["config"], "calls": e["calls"]} for e in episodes]})

    bad = [(r, js_b) for r, js_b in zip(recipes, js["brews"]) if brew(r).to_dict() != js_b]
    print(f"brewer: {len(recipes) - len(bad)}/{len(recipes)} recipes match")
    failures += len(bad)
    for r, js_b in bad[:5]:
        print("  MISMATCH", r, brew(r).to_dict(), js_b)

    bad = [(s, g) for s, g in zip(seeds, js["growth"])
           if list(sample_growth_times(PLANTS, s[1], s[2], random.Random(s[0])).values()) != g]
    print(f"growth times: {len(seeds) - len(bad)}/{len(seeds)} seeds match")
    failures += len(bad)

    for i, (ep, js_ep) in enumerate(zip(episodes, js["episodes"])):
        py_msgs, js_msgs = normalise(ep["messages"]), js_ep["messages"]
        if py_msgs != js_msgs:
            failures += 1
            k = next((j for j, (a, b) in enumerate(zip(py_msgs, js_msgs)) if a != b), min(len(py_msgs), len(js_msgs)))
            print(f"episode {i}: messages differ at {k}\n  python: {py_msgs[k:k + 1]}\n  js:     {js_msgs[k:k + 1]}")
            continue
        py_sum = normalise(ep["summary"])
        js_sum = js_ep["summary"]
        for g in js_sum["goals"]:
            if g["best_potion"]:
                g["best_potion"] = {k: g["best_potion"][k] for k in ("id", "turn", "recipe", "effect", "logged")}
        if py_sum != js_sum:
            failures += 1
            print(f"episode {i}: summaries differ\n  python: {py_sum}\n  js:     {js_sum}")
    n_msgs = sum(len(e["messages"]) for e in episodes)
    print(f"episodes: {len(episodes)} played, {n_msgs} messages compared")
    print("OK" if not failures else f"{failures} mismatches")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
