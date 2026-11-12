"""The turn header the agent sees: day, turn and its view of the garden."""

from environment.view import GardenView
from environment.world import World
from tools.base import turns

TURNS_PER_DAY = 10


def day_of(turn: int) -> int:
    """Turns 1–10 are day 1, 11–20 day 2, ..."""
    return (turn - 1) // TURNS_PER_DAY + 1


def render_garden(view: GardenView) -> str:
    """E.g. 'free: 1, 6; growing: 2 (sage, yellow, 1 turn left), 3 (mint, black, planted turn 22);
    ready: 4 (nettle, brown, waiting 0); died: 5 (basil, yellow)'. The died part appears only while a
    dead plant waits to be cleared by gather."""
    growing = [
        f"{g.plot} ({g.plant}, {g.soil}, "
        + (f"{turns(g.turns_left)} left)" if g.turns_left is not None else f"planted turn {g.planted_turn})")
        for g in view.growing
    ]
    ready = [f"{r.plot} ({r.plant}, {r.soil}, waiting {r.waiting})" for r in view.ready]
    free = ", ".join(map(str, view.free)) or "none"
    text = f"free: {free}; growing: {', '.join(growing) or 'none'}; ready: {', '.join(ready) or 'none'}"
    if view.died:
        text += "; died: " + ", ".join(f"{d.plot} ({d.plant}, {d.soil})" for d in view.died)
    return text


def turn_header(world: World) -> str:
    return f"[Day {day_of(world.turn)}, turn {world.turn}]\nGarden: {render_garden(world.view())}\nChoose your action."
