"""Free tool: whole sources, only those returned by a search in the current turn.
  {"tool": "read", "sources": ["S12", "S40"]}"""

from environment.world import World
from tools.base import ToolError, ToolResult


def run(world: World, args: dict) -> ToolResult:
    library = world.library
    if library is None:
        raise ToolError("There are no sources in this episode.")
    ids = args.get("sources")
    if isinstance(ids, str):
        ids = [ids]
    if not isinstance(ids, list) or not ids or not all(isinstance(s, str) for s in ids):
        raise ToolError('"sources" must be a list of source ids such as ["S12"].')
    if unknown := [s for s in ids if s not in library.sources]:
        raise ToolError(f"Unknown source {unknown[0]}.")
    if unread := [s for s in ids if not library.readable(s, world.turn)]:
        raise ToolError(f"{', '.join(unread)} {'was' if len(unread) == 1 else 'were'} not returned by a search "
                        "this turn: search for it again to read it.")
    parts = []
    for sid in dict.fromkeys(ids):
        src = library.sources[sid]
        parts.append(f"{src.header()}\n\n{src.body}")
    return ToolResult("\n\n---\n\n".join(parts))
