"""Entry point: builds all components from the inputs and runs (or resumes) one episode."""

import sys

import checkpoint
from agents.base import Agent
from agents.random_agent import RandomAgent
from environment.world import World
from input import ExperimentConfig, parse_command
from LLM.agent import LLMAgent
from LLM.client import ChatClient
from LLM.episode import run_episode
from ledger import Ledger
from output import RunOutput


def make_agent(config: ExperimentConfig) -> Agent:
    if config.agent == "random":
        return RandomAgent(seed=config.llm_seed)
    if config.agent == "llm":
        client = ChatClient(config.llm_url, config.llm_name, config.max_tokens,
                            config.temperature, config.top_p, config.thinking, config.reasoning_effort)
        return LLMAgent(client, config.prompt_file.read_text(encoding="utf-8"), seed=config.llm_seed)
    raise NotImplementedError(f"The {config.agent!r} agent is not implemented yet.")


def start(config: ExperimentConfig) -> RunOutput:
    out = RunOutput(config)
    world = World.create(
        config.garden_size, (config.growth_min, config.growth_max), list(config.goals),
        config.allergy, config.turn_cap, config.env_seed, kb_path=str(out.kb_path),
    )
    agent, ledger = make_agent(config), Ledger()
    out.write_params(config, {"growth_times": world.garden.growth_times, **agent.info()})
    out.log_facts(ledger.observe(world))
    checkpoint.save(out.temp, out.dir, world, ledger, agent.state(), compactions=0)
    run_episode(config, world, agent, out, ledger)
    world.kb.close()
    return out


def resume(config: ExperimentConfig, run_dir) -> RunOutput:
    out = RunOutput.reopen(config, run_dir)
    cp = checkpoint.load(out.temp)
    if cp is None:
        raise FileNotFoundError(f"No checkpoint in {out.temp}; start a new run instead.")
    world, ledger = checkpoint.restore(cp, out.dir, out.kb_path)
    agent = make_agent(config)
    agent.load_state(cp.agent)
    run_episode(config, world, agent, out, ledger, cp.compactions)
    world.kb.close()
    return out


def main(argv: list[str] | None = None) -> RunOutput:
    config, run_dir = parse_command(argv)
    out = resume(config, run_dir) if run_dir else start(config)
    print(f"Run finished: {out.dir}")
    return out


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
