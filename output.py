"""Writes a run's outputs to runs/<agent>/<run_id>/ (working data in temp/<agent>/<run_id>/)."""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from environment.inventory import Potion
from environment.world import World
from input import ExperimentConfig
from ledger import Fact
from tools.base import ToolResult
from utils import append_jsonl, append_text, run_id, write_json


def potion_dict(potion: Potion) -> dict:
    return {
        "id": potion.id,
        "turn": potion.turn,
        "recipe": potion.recipe,
        "effect": potion.effect.to_dict(),
        "logged": potion.logged,
    }


def world_state(world: World) -> dict:
    """Full true state: garden, inventory and knowledge base."""
    state = world.garden.state(world.turn)
    return {
        "turn": world.turn,
        "garden": {
            "size": world.garden.size,
            "growth_times": world.garden.growth_times,
            "plantings": {
                str(plot): {"plant": plant, "planted_turn": turn}
                for plot, (plant, turn) in world.garden.plantings().items()
            },
            "free": state.free,
            "growing": [g._asdict() for g in state.growing],
            "ready": [r._asdict() for r in state.ready],
        },
        "inventory": {
            "plants": dict(sorted(world.inventory.plants.items())),
            "potions": [potion_dict(p) for p in world.inventory.potions],
        },
        "knowledge_base": {
            "growth_times": world.kb.growth_times(),
            "plantings": {str(k): v for k, v in world.kb.plantings().items()},
            "outcomes": [{"labels": o.labels, "effect": o.effect, "text": o.render()} for o in world.kb.outcomes()],
        },
    }


def summary(world: World) -> dict:
    """Per-goal results, including the best potion's details."""
    goals = []
    for result in world.results:
        best = world.inventory.potions[result.best_potion - 1] if result.best_potion else None
        goals.append({
            "goal": result.goal.to_dict(),
            "description": result.goal.describe(),
            "start_turn": result.start_turn,
            "end_turn": result.end_turn,
            "turns_used": result.turns_used,
            "success": result.success,
            "best_intensity": result.best_intensity,
            "best_potion": potion_dict(best) if best else None,
            "allergy_violations": result.allergy_violations,
        })
    in_progress = None if world.episode_over else world.current_goal
    not_started = world.goals[len(world.results) + (in_progress is not None):]
    return {
        "turns_played": world.turn - 1,
        "episode_over": world.episode_over,
        "goals": goals,
        "goal_in_progress": in_progress.to_dict() if in_progress else None,
        "goals_not_started": [g.to_dict() for g in not_started],
    }


class RunOutput:
    """Creates the run folders and writes each output file."""

    def __init__(self, config: ExperimentConfig, rid: str | None = None) -> None:
        self.run_id = rid or run_id()
        self.dir = config.runs_dir / config.agent_label / self.run_id
        self.temp = config.temp_dir / config.agent_label / self.run_id
        (self.dir / "compactions").mkdir(parents=True, exist_ok=False)
        self.temp.mkdir(parents=True, exist_ok=False)
        self._transcript_turn: int | None = None
        append_text(self.dir / "transcript.md", f"# Transcript — {config.agent_label} — {self.run_id}\n")

    @classmethod
    def reopen(cls, config: ExperimentConfig, run_dir: Path) -> "RunOutput":
        """Attach to an existing run folder (for --resume)."""
        out = cls.__new__(cls)
        out.run_id = run_dir.name
        out.dir = run_dir
        out.temp = config.temp_dir / config.agent_label / run_dir.name
        if not out.temp.is_dir():
            raise FileNotFoundError(f"No working folder {out.temp} for this run.")
        out._transcript_turn = None
        return out

    @property
    def kb_path(self) -> Path:
        return self.temp / "knowledge_base.sqlite"

    def write_params(self, config: ExperimentConfig, extra: dict[str, Any]) -> None:
        """All inputs, plus values only known after setup (growth times, prompt text)."""
        write_json(self.dir / "params.json", {"run_id": self.run_id, **config.to_dict(), **extra})

    def log_message(self, turn: int, role: str, content: str) -> None:
        """Append one message to the human-readable transcript."""
        text = ""
        if turn != self._transcript_turn:
            text += f"\n## Turn {turn}\n"
            self._transcript_turn = turn
        append_text(self.dir / "transcript.md", text + f"\n**{role}**\n\n{content.rstrip()}\n")

    def log_call(self, turn: int, call: Any, result: ToolResult) -> None:
        append_jsonl(self.dir / "actions.jsonl", {"turn": turn, "call": call, **asdict(result)})

    def log_facts(self, facts: list[Fact]) -> None:
        for fact in facts:
            append_jsonl(self.dir / "ledger.jsonl", {**asdict(fact), "recoverable": fact.recoverable})

    def write_compaction(self, index: int, data: dict[str, Any]) -> None:
        """Context before/after, token counts, turn and ledger snapshot of one compaction."""
        write_json(self.dir / "compactions" / f"{index:03d}.json", data)

    def write_final(self, world: World) -> None:
        write_json(self.dir / "final_state.json", world_state(world))
        write_json(self.dir / "summary.json", summary(world))
