"""Random agent: plays only from what it is shown; used to stress-test the environment."""

import json
import random
import re

from agents.base import Agent, AgentReply
from environment.brewer import PLANTS
from environment.knowledge_base import LABELS


def _numbers(text: str, field: str) -> list[int]:
    """Plot numbers listed under a field of the latest garden line, e.g. 'free: 1, 3'."""
    match = re.search(rf"{field}: ([^;\n]*)", text)
    return [int(n) for n in re.findall(r"(?<![\w(])(\d+)(?= \(|,|$)", match.group(1))] if match else []


class RandomAgent(Agent):
    def __init__(self, seed: int, error_rate: float = 0.05) -> None:
        super().__init__()
        self.rng = random.Random(seed)
        self.error_rate = error_rate

    def _reply(self) -> AgentReply:
        last = self.messages[-1]["content"] if self.messages else ""
        if last.startswith("plants:"):
            return self._after_inventory(last)
        if self.rng.random() < self.error_rate:
            return self._say("{not valid json")
        garden = next((m["content"] for m in reversed(self.messages) if "Garden: " in m["content"]), "")
        free, ready = _numbers(garden, "free"), _numbers(garden, "ready")
        options = ["inventory", "skip", "log_garden"] + ["plant"] * 3 * bool(free) + ["gather"] * 3 * bool(ready)
        choice = self.rng.choice(options)
        if choice == "plant":
            plots = self.rng.sample(free, self.rng.randint(1, len(free)))
            return self._say({"action": "plant", "plots": {str(p): self.rng.choice(PLANTS) for p in plots}})
        if choice == "gather":
            return self._say({"tool": "gather"})
        if choice == "inventory":
            return self._say({"tool": "inventory"})
        if choice == "log_garden":
            return self._say({"action": "log", "garden": True})
        return self._say({"action": "skip"})

    def _after_inventory(self, text: str) -> AgentReply:
        """Brew from what is available, or log a potion, or skip."""
        plants = {p: int(n) for p, n in re.findall(r"([a-z]+): (\d+)", text)}
        potions = [int(n) for n in re.findall(r"#(\d+)", text)]
        if potions and self.rng.random() < 0.3:
            pid = self.rng.choice(potions)
            labels = {p: self.rng.choice(LABELS) for p in self.rng.sample(PLANTS, 2)}
            return self._say({"action": "log", "potions": [{"id": pid, "labels": labels}]})
        if len(plants) >= 3:
            chosen = self.rng.sample(sorted(plants), self.rng.randint(3, min(4, len(plants))))
            extra = int(self.rng.random() < 0.1)  # sometimes infeasible on purpose
            recipe = {p: self.rng.randint(1, plants[p]) + extra for p in chosen}
            return self._say({"action": "brew", "recipe": recipe})
        return self._say({"action": "skip"})

    def _say(self, call: str | dict) -> AgentReply:
        text = call if isinstance(call, str) else json.dumps(call)
        return AgentReply(f"(random choice)\n{text}", call)

    def state(self) -> dict:
        version, internal, gauss = self.rng.getstate()
        return {**super().state(), "rng": [version, list(internal), gauss]}

    def load_state(self, data: dict) -> None:
        super().load_state(data)
        version, internal, gauss = data["rng"]
        self.rng.setstate((version, tuple(internal), gauss))
