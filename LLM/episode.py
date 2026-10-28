"""The turn loop: compaction check → turn → end of turn → checkpoint."""

import checkpoint
from agents.base import Agent, ContextFull
from environment.world import TurnEnd, World
from input import ExperimentConfig
from ledger import Ledger
from output import RunOutput
from tools.dispatcher import Dispatcher
from tools.observation import turn_header

MAX_CALLS_PER_TURN = 20  # stops an agent that only uses free tools


def opening_message(world: World) -> str:
    allergy = "I have no allergies."
    if world.allergy is not None:
        a, b = sorted(world.allergy.plants)
        allergy = f"I am allergic to the combination of {a} and {b}: never brew a potion containing both."
    return f"My garden has {world.garden.size} plots. {allergy} Goal 1: {world.goals[0].describe()}."


def goal_message(end: TurnEnd, world: World) -> str | None:
    if end.finished is None:
        return None
    if end.next_goal is None:
        return "Goal finished. That was the last goal."
    return f"Goal finished. Goal {world.goal_index + 1}: {end.next_goal.describe()}."


def maybe_compact(config: ExperimentConfig, agent: Agent, compactions: int) -> int:
    """Compact between turns once the context passes the trigger. No compactors exist yet."""
    if config.compactor == "none":
        return compactions
    raise NotImplementedError(f"Compactor {config.compactor!r} is not implemented yet.")


def play_turn(world: World, agent: Agent, dispatcher: Dispatcher, out: RunOutput, ledger: Ledger) -> None:
    turn = world.turn
    if turn == 1:
        opening = opening_message(world)
        agent.observe(opening)
        out.log_message(turn, "user", opening)
    header = turn_header(world)
    agent.observe(header)
    out.log_message(turn, "environment", header)

    for _ in range(MAX_CALLS_PER_TURN):
        reply = agent.respond()
        if reply.thinking:
            out.log_message(turn, "agent (thinking, discarded)", reply.thinking)
        out.log_message(turn, "agent", reply.text)
        if reply.meta:
            out.log_llm_call(turn, reply.meta)
        result = dispatcher.handle(reply.call)
        out.log_call(turn, reply.call, result)
        agent.observe(result.text)
        out.log_message(turn, "environment", result.text)
        if result.ends_turn:
            break
    else:
        world.skip()
        note = f"{MAX_CALLS_PER_TURN} calls without an action: the turn is skipped."
        agent.observe(note)
        out.log_message(turn, "environment", note)

    end = world.end_turn()
    if message := goal_message(end, world):
        agent.observe(message)
        out.log_message(turn, "user", message)
    out.log_facts(ledger.observe(world))


def run_episode(
    config: ExperimentConfig, world: World, agent: Agent, out: RunOutput, ledger: Ledger, compactions: int = 0
) -> None:
    """Play until the episode ends (or the context is full); a checkpoint is saved after every completed turn."""
    dispatcher = Dispatcher(world)
    stop_reason = None
    while not world.episode_over:
        compactions = maybe_compact(config, agent, compactions)
        try:
            play_turn(world, agent, dispatcher, out, ledger)
        except ContextFull as err:
            stop_reason = "context full"
            out.log_message(world.turn, "environment", f"Episode stopped: the context is full ({err}).")
            break
        checkpoint.save(out.temp, out.dir, world, ledger, agent.state(), compactions)
    out.write_final(world, stop_reason)
