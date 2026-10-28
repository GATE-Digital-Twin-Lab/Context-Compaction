"""Command-line arguments, validation, and the experiment configuration."""

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from environment.goals import Allergy, Goal, GoalKind, validate_allergy
from utils import new_seed, slugify

AGENTS = ("llm", "random", "oracle")
COMPACTORS = ("none",)  # compactors are added later


@dataclass(frozen=True)
class ExperimentConfig:
    # agent
    agent: str
    llm_name: str | None
    llm_url: str
    thinking: bool
    temperature: float | None   # None: the model's recommended default (as served)
    top_p: float | None         # None: the model's recommended default (as served)
    max_tokens: int             # per reply, thinking included
    llm_seed: int
    # garden
    garden_size: int
    growth_min: int
    growth_max: int
    env_seed: int
    # user
    goals: tuple[Goal, ...]
    allergy: Allergy | None
    # episode
    turn_cap: int
    prompt_file: Path
    # compaction (checked only between turns)
    compactor: str
    context_window: int | None   # model's context size in tokens
    compaction_trigger: float    # compact once the context passes this fraction of the window
    # output
    runs_dir: Path
    temp_dir: Path

    @property
    def agent_label(self) -> str:
        """Folder name under runs/ and temp/: the LLM name or the agent type."""
        return slugify(self.llm_name) if self.agent == "llm" else self.agent

    def to_dict(self) -> dict:
        data = asdict(self)
        data["goals"] = [g.to_dict() for g in self.goals]
        data["allergy"] = sorted(self.allergy.plants) if self.allergy else None
        for key in ("prompt_file", "runs_dir", "temp_dir"):
            data[key] = str(data[key])
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ExperimentConfig":
        """Rebuild from params.json (extra keys such as run_id are ignored)."""
        values = {k: data[k] for k in cls.__dataclass_fields__}
        values["goals"] = tuple(Goal.from_dict(g) for g in data["goals"])
        values["allergy"] = Allergy(frozenset(data["allergy"])) if data["allergy"] else None
        for key in ("prompt_file", "runs_dir", "temp_dir"):
            values[key] = Path(values[key])
        return cls(**values)


def load_config(run_dir: Path) -> ExperimentConfig:
    params = run_dir / "params.json"
    if not params.is_file():
        raise ValueError(f"No params.json in {run_dir}.")
    return ExperimentConfig.from_dict(json.loads(params.read_text(encoding="utf-8")))


def parse_goal(text: str) -> Goal:
    """'time:S:30' or 'target:I:10'."""
    parts = text.strip().split(":")
    usage = f'Invalid goal "{text}": expected time:<stat>:<turns> or target:<stat>:<percent>.'
    if len(parts) != 3 or not parts[2].isdigit():
        raise ValueError(usage)
    kind, stat, value = parts[0].lower(), parts[1].upper(), int(parts[2])
    if kind == GoalKind.TIME:
        return Goal(GoalKind.TIME, stat, turns=value)
    if kind == GoalKind.TARGET:
        return Goal(GoalKind.TARGET, stat, target=value)
    raise ValueError(usage)


def parse_allergy(text: str) -> Allergy | None:
    """'p3+p5' or 'none'."""
    if text.strip().lower() == "none":
        return None
    return Allergy(frozenset(p.strip() for p in text.split("+")))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run one Potion Garden episode.")
    a = p.add_argument_group("agent")
    a.add_argument("--agent", choices=AGENTS, default="random")
    a.add_argument("--llm-name", help="model name (required for --agent llm)")
    a.add_argument("--llm-url", default="http://127.0.0.1:8080", help="OpenAI-compatible server (scripts/serve_llm.sh)")
    a.add_argument("--thinking", choices=("on", "off"), default="on",
                   help="model thinking; it is discarded after every reply either way")
    a.add_argument("--temperature", type=float, help="default: the model's recommended value")
    a.add_argument("--top-p", type=float, help="default: the model's recommended value")
    a.add_argument("--max-tokens", type=int, default=32768, help="per reply, thinking included")
    a.add_argument("--llm-seed", type=int, help="default: random, recorded in params.json")
    g = p.add_argument_group("garden")
    g.add_argument("--garden-size", type=int, default=10)
    g.add_argument("--growth-min", type=int, default=2)
    g.add_argument("--growth-max", type=int, default=6)
    g.add_argument("--env-seed", type=int, help="default: random, recorded in params.json")
    u = p.add_argument_group("user")
    u.add_argument("--goals", default="target:I:10,time:S:40,target:D:10",
                   help="comma-separated, e.g. 'time:S:30,target:I:10'")
    u.add_argument("--allergy", default="none", help="two plants, e.g. 'p3+p5', or 'none'")
    e = p.add_argument_group("episode")
    e.add_argument("--turn-cap", type=int, default=150)
    e.add_argument("--prompt-file", type=Path, default=Path("prompts/system.txt"))
    c = p.add_argument_group("compaction (checked only between turns)")
    c.add_argument("--compactor", choices=COMPACTORS, default="none")
    c.add_argument("--context-window", type=int, help="model context size in tokens; required unless --compactor none")
    c.add_argument("--compaction-trigger", type=float, default=0.8,
                   help="compact once the context passes this fraction of the window (default 0.8)")
    o = p.add_argument_group("output")
    o.add_argument("--runs-dir", type=Path, default=Path("runs"))
    o.add_argument("--temp-dir", type=Path, default=Path("temp"))
    r = p.add_argument_group("resume")
    r.add_argument("--resume", type=Path, metavar="RUN_DIR",
                   help="continue an interrupted run from its last checkpoint; takes no other options")
    return p


def parse_command(argv: list[str] | None = None) -> tuple[ExperimentConfig, Path | None]:
    """A new run's config, or (saved config, run folder) for --resume."""
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.resume is None:
        return parse_args(argv), None
    if len(argv) != 2:
        parser.error("--resume takes no other options: the run continues with its saved parameters.")
    try:
        return load_config(args.resume), args.resume
    except (ValueError, KeyError) as err:
        parser.error(f"Cannot resume {args.resume}: {err}")


def parse_args(argv: list[str] | None = None) -> ExperimentConfig:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        goals = tuple(parse_goal(t) for t in args.goals.split(",") if t.strip())
        if not goals:
            raise ValueError("At least one goal is required.")
        allergy = parse_allergy(args.allergy)
        validate_allergy(allergy, goals)
        _check(args)
    except ValueError as err:
        parser.error(str(err))
    return ExperimentConfig(
        agent=args.agent,
        llm_name=args.llm_name,
        llm_url=args.llm_url,
        thinking=args.thinking == "on",
        temperature=args.temperature,
        top_p=args.top_p,
        max_tokens=args.max_tokens,
        llm_seed=args.llm_seed if args.llm_seed is not None else new_seed(),
        garden_size=args.garden_size,
        growth_min=args.growth_min,
        growth_max=args.growth_max,
        env_seed=args.env_seed if args.env_seed is not None else new_seed(),
        goals=goals,
        allergy=allergy,
        turn_cap=args.turn_cap,
        prompt_file=args.prompt_file,
        compactor=args.compactor,
        context_window=args.context_window,
        compaction_trigger=args.compaction_trigger,
        runs_dir=args.runs_dir,
        temp_dir=args.temp_dir,
    )


def _check(args: argparse.Namespace) -> None:
    """Range checks; raise ValueError with a readable message."""
    if args.agent == "llm":
        if not args.llm_name:
            raise ValueError("--llm-name is required for --agent llm.")
        if not args.prompt_file.is_file():
            raise ValueError(f"Prompt file not found: {args.prompt_file}.")
    if args.garden_size < 1:
        raise ValueError("--garden-size must be >= 1.")
    if not 1 <= args.growth_min <= args.growth_max:
        raise ValueError("Need 1 <= --growth-min <= --growth-max.")
    if args.turn_cap < 1:
        raise ValueError("--turn-cap must be >= 1.")
    if args.temperature is not None and args.temperature < 0:
        raise ValueError("--temperature must be >= 0.")
    if args.top_p is not None and not 0 < args.top_p <= 1:
        raise ValueError("--top-p must be in (0, 1].")
    if args.max_tokens < 1:
        raise ValueError("--max-tokens must be >= 1.")
    if not 0 < args.compaction_trigger <= 1:
        raise ValueError("--compaction-trigger must be in (0, 1].")
    if args.context_window is not None and args.context_window < 1:
        raise ValueError("--context-window must be >= 1.")
    if args.compactor != "none" and args.context_window is None:
        raise ValueError("--context-window is required when a compactor is used.")
