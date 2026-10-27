"""The turn header the agent sees: turn number and its view of the garden."""

from environment.view import GardenView
from environment.world import World
from tools.base import turns


def render_garden(view: GardenView) -> str:
    """E.g. 'free: 1, 6; growing: 3 (p2, 2 turns left), 5; ready: 7 (waiting 2)'."""
    growing = []
    for g in view.growing:
        details = [d for d in (g.plant, f"{turns(g.turns_left)} left" if g.turns_left is not None else None) if d]
        growing.append(f"{g.plot} ({', '.join(details)})" if details else str(g.plot))
    ready = [f"{r.plot} ({r.plant + ', ' if r.plant else ''}waiting {r.waiting})" for r in view.ready]
    free = ", ".join(map(str, view.free)) or "none"
    return f"free: {free}; growing: {', '.join(growing) or 'none'}; ready: {', '.join(ready) or 'none'}"


def turn_header(world: World) -> str:
    return f"[Turn {world.turn}]\nGarden: {render_garden(world.view())}\nChoose your action."
