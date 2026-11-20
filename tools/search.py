"""Counted tool: search the episode's sources.
  {"tool": "search", "queries": ["nettle mill pond", "Saint Brede's sprig"]}
Each query returns up to K sources, best first, each by its header only (id, title, author, kind); no
passages and no scores. The sources returned can be read whole with `read` in this turn only."""

from environment.world import World
from tools.base import ToolError, ToolResult

K = 5               # sources per query
MAX_QUERIES = 3     # per call


def run(world: World, args: dict) -> ToolResult:
    library = world.library
    if library is None:
        raise ToolError("There are no sources in this episode.")
    queries = args.get("queries")
    if isinstance(queries, str):
        queries = [queries]
    if not isinstance(queries, list) or not queries or not all(isinstance(q, str) and q.strip() for q in queries):
        raise ToolError(f'"queries" must be a list of 1 to {MAX_QUERIES} non-empty strings.')
    if len(queries) > MAX_QUERIES:
        raise ToolError(f"At most {MAX_QUERIES} queries per search.")
    blocks, found = [], []
    for query in queries:
        hits = library.search(query, K)
        if not hits:
            blocks.append(f'Search "{query}": no source matches.')
            continue
        blocks.append(f'Search "{query}":\n' + "\n".join(h.source.header() for h in hits))
        found += [h.source.id for h in hits if h.source.id not in found]
    library.mark_found(found, world.turn)
    tail = f"Readable whole this turn with read: {', '.join(found)}." if found else "Nothing to read."
    return ToolResult("\n\n".join(blocks) + "\n\n" + tail)
