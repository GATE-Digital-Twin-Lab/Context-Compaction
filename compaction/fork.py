"""Fork a recorded run at a turn: replay it (no model calls) up to the end of that turn, compact the
context with a summary, and let the LLM agent continue from there. Everything goes to
<run>/compactions/t<turn>_summary/: the usual run files plus compaction_summary.md.
    python -m compaction.fork RUN_DIR --at 50 [--keep-turns 5] [--name NAME]"""

import argparse
import json
import sys
from pathlib import Path

import checkpoint
from agents.replay_agent import ReplayAgent, recorded_replies
from compaction.summary import SUMMARY_PROMPT, summarise
from environment.world import World
from input import ExperimentConfig
from ledger import Ledger
from LLM.agent import LLMAgent
from LLM.client import ChatClient
from LLM.episode import play_turn, run_episode
from output import RunOutput
from tools.dispatcher import Dispatcher
from utils import COMPACTION_ROLE


def make_client(config: ExperimentConfig) -> ChatClient:
    return ChatClient(config.llm_url, config.llm_name, config.max_tokens,
                      config.temperature, config.top_p, config.thinking, config.reasoning_effort)


def _after_title(text: str, turn: int) -> str:
    """The transcript up to the end of a turn, without its title line (which names the run)."""
    return text.split("\n", 1)[1].split(f"\n## Turn {turn + 1}\n")[0]


def replay(
    run_dir: Path, at: int, out: RunOutput, config: ExperimentConfig
) -> tuple[World, Ledger, ReplayAgent, dict[int, int]]:
    """Rebuild the run's world, ledger and conversation at the end of turn `at`; check that the replay
    reproduced the recorded transcript exactly. Also returns where each turn starts in the conversation."""
    original = (run_dir / "transcript.md").read_text(encoding="utf-8")
    world = World.create(
        config.garden_size, (config.growth_min, config.growth_max), list(config.goals),
        config.allergy, config.turn_cap, config.env_seed, kb_path=str(out.kb_path), lore=config.lore,
    )
    agent, ledger, dispatcher = ReplayAgent(recorded_replies(original)), Ledger(), Dispatcher(world)
    out.log_facts(ledger.observe(world))
    starts = {}
    while world.turn <= at:
        if world.episode_over:
            raise ValueError(f"The run ended before turn {at}.")
        starts[world.turn] = len(agent.messages)
        play_turn(world, agent, dispatcher, out, ledger)
    if _after_title((out.dir / "transcript.md").read_text(encoding="utf-8"), at) != _after_title(original, at):
        raise RuntimeError(f"The replay does not reproduce {run_dir / 'transcript.md'} up to turn {at}.")
    return world, ledger, agent, starts


def fork(run_dir: Path, at: int, keep_turns: int = 5, name: str | None = None) -> RunOutput:
    if not 0 <= keep_turns < at:
        raise ValueError(f"--keep-turns must be in [0, {at}).")
    params = json.loads((run_dir / "params.json").read_text(encoding="utf-8"))
    config = ExperimentConfig.from_dict(params)
    name = name or f"t{at:03d}_summary"
    out = RunOutput(config, rid=f"{run_dir.name}/{name}", run_dir=run_dir / "compactions" / name,
                    temp_dir=config.temp_dir / config.agent_label / run_dir.name / name)
    system_prompt = params["system_prompt"]
    fork_info = {"parent": str(run_dir), "at_turn": at, "compactor": "summary", "keep_turns": keep_turns}
    out.write_params(config, {"growth_times": params["growth_times"], "system_prompt": system_prompt, "fork": fork_info})

    world, ledger, replayed, starts = replay(run_dir, at, out, config)
    client = make_client(config)
    keep_last = len(replayed.messages) - starts[at - keep_turns + 1] if keep_turns else 0
    result = summarise(client, system_prompt, replayed.messages, seed=config.llm_seed + replayed.replayed,
                       keep_last=keep_last)
    done = result.completion
    out.write_compaction(1, {
        "turn": at, **fork_info, "prompt": SUMMARY_PROMPT.read_text(encoding="utf-8"),
        "usage": done.usage, "finish_reason": done.finish_reason, "seconds": done.seconds,
        "summary": result.summary, "thinking": done.reasoning,
        "context_before": replayed.messages, "summarised": result.summarised, "context_after": result.after,
        "ledger": ledger.snapshot(world),
    })
    (out.dir / "compaction_summary.md").write_text(result.summary + "\n", encoding="utf-8")
    last = at - keep_turns
    summarised = "turn 1" if last == 1 else f"turns 1–{last}"
    kept = f" Turns {last + 1}–{at} stay in the context verbatim, after the summary." if keep_turns else ""
    out.log_message(at, COMPACTION_ROLE, (
        f"Context compacted after turn {at}: the {len(result.summarised)} messages of {summarised} above "
        f"({done.usage.get('prompt_tokens', '?')} tokens with the summary request) left the agent's context and "
        f"were replaced by the message below ({len(result.summary)}-character summary).{kept}"
    ))
    out.log_message(at, "user", result.after[0]["content"])

    agent = LLMAgent(client, system_prompt, seed=config.llm_seed)
    agent.load_state({"messages": result.after, "system_prompt": system_prompt, "calls": replayed.replayed})
    checkpoint.save(out.temp, out.dir, world, ledger, agent.state(), compactions=1)
    run_episode(config, world, agent, out, ledger, compactions=1)
    world.kb.close()
    return out


def main(argv: list[str] | None = None) -> RunOutput:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--at", type=int, required=True, help="compact after this turn")
    parser.add_argument("--keep-turns", type=int, default=5, help="last turns kept verbatim after the summary (default 5)")
    parser.add_argument("--name", help="folder name under compactions/ (default: t<turn>_summary)")
    args = parser.parse_args(argv)
    out = fork(args.run_dir, args.at, args.keep_turns, args.name)
    print(f"Fork finished: {out.dir}")
    return out


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
