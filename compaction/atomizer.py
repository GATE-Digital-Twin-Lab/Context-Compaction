"""LLM atomizer: splits a run's transcript_clean.md (what the agent actually had in its context) into
atoms, one model call per turn, with no scoring. Writes next to the transcript:
    atoms.jsonl        one atom per line: id, turn, message, role, kind, text
    atoms.md           every message followed by its atoms, for reading
    atoms_calls.jsonl  one record per model call (usage, seconds, retries, errors)
    python -m compaction.atomizer RUN_DIR [--turns 1-10] [--thinking] [--temperature 0]"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from LLM.client import ChatClient
from utils import COMPACTION_ROLE, append_jsonl, transcript_blocks

ATOMIZE_PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "atomize.txt"
KINDS = ("goal", "observation", "state", "inference", "plan")
ATTEMPTS = 3
RETRY_TEMPERATURE = 0.7   # retries must sample: at temperature 0 a new seed gives the same reply
MIN_CHARS = 30            # a message at least this long ("Skipped." is not) must yield an atom


@dataclass(frozen=True)
class Message:
    index: int   # position among the run's messages, from 1
    turn: int
    role: str
    content: str


@dataclass(frozen=True)
class Atom:
    id: str
    turn: int
    message: int   # Message.index
    role: str      # who said it
    kind: str
    text: str


def read_messages(transcript: str) -> list[Message]:
    """The messages the agent saw (compaction markers are notes for the reader, not messages)."""
    blocks = [(t, r, c) for t, r, c in transcript_blocks(transcript) if r != COMPACTION_ROLE]
    return [Message(i, t, r, c) for i, (t, r, c) in enumerate(blocks, 1)]


def _render(messages: list[Message], numbered: bool) -> str:
    return "\n\n".join(
        (f"[{n}] " if numbered else "") + f"{m.role} (turn {m.turn}):\n{m.content}"
        for n, m in enumerate(messages, 1)
    )


def request(instructions: str, agent_prompt: str, context: list[Message], target: list[Message]) -> list[dict]:
    """The atomizer instructions, the agent's own instructions as reference, then the earlier messages
    as context and the numbered messages of the turn to split (the shared prefix stays cacheable)."""
    parts = [f"The agent's instructions, for reference only (do not split them):\n<instructions>\n{agent_prompt}\n</instructions>"]
    if context:
        parts.append(f"Earlier messages, as context only (do not split them):\n<context>\n{_render(context, False)}\n</context>")
    parts.append(f"Split these messages into atoms:\n<messages>\n{_render(target, True)}\n</messages>")
    return [{"role": "system", "content": instructions}, {"role": "user", "content": "\n\n".join(parts)}]


def parse_atoms(content: str, count: int) -> list[tuple[int, str, str]]:
    """(message number, kind, text) of every atom in the reply; ValueError if the reply is malformed."""
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the reply")
    data = json.loads(content[start:end + 1])
    if not isinstance(data, dict) or not isinstance(data.get("atoms"), list):
        raise ValueError('the reply has no "atoms" list')
    atoms = []
    for item in data["atoms"]:
        if not isinstance(item, dict):
            raise ValueError(f"not an atom: {item!r}")
        number, kind, text = item.get("message"), item.get("kind"), item.get("text")
        if not isinstance(number, int) or not 1 <= number <= count:
            raise ValueError(f"message number out of range: {item!r}")
        if kind not in KINDS:
            raise ValueError(f"unknown kind: {item!r}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"empty atom: {item!r}")
        atoms.append((number, kind, text.strip()))
    return atoms


def uncovered(target: list[Message], parsed: list[tuple[int, str, str]]) -> list[int]:
    """Numbers of the messages the atoms do not cover: a message with content (at least MIN_CHARS
    characters) needs an atom, and a list needs at least one atom per bulleted line."""
    counts = [0] * len(target)
    for number, _, _ in parsed:
        counts[number - 1] += 1
    needed = [max(len(m.content.strip()) >= MIN_CHARS, m.content.count("\n- ") + m.content.startswith("- "))
              for m in target]
    return [n for n, (have, need) in enumerate(zip(counts, needed), 1) if have < need]


def atomize_turn(client: ChatClient, instructions: str, agent_prompt: str, context: list[Message],
                 target: list[Message], seed: int, temperature: float = 0.0,
                 retry_temperature: float = RETRY_TEMPERATURE) -> tuple[list[tuple[Message, str, str]], dict]:
    """Atoms of one turn's messages and the call record. The first attempt decodes at `temperature`;
    a malformed or incomplete reply is retried with the next seed at `retry_temperature`. If no attempt
    covers every message, the most complete valid one is kept and the gaps are recorded."""
    messages = request(instructions, agent_prompt, context, target)
    record = {"turn": target[0].turn, "messages": [m.index for m in target], "attempts": []}
    best: tuple[list[int], list[tuple[int, str, str]]] | None = None
    for attempt in range(ATTEMPTS):
        client.temperature = temperature if attempt == 0 else retry_temperature
        done = client.complete(messages, seed=seed + attempt)
        log = {"seed": seed + attempt, "temperature": client.temperature, "usage": done.usage,
               "seconds": done.seconds, "finish_reason": done.finish_reason, "thinking_chars": len(done.reasoning)}
        try:
            parsed = parse_atoms(done.content, len(target))
        except ValueError as err:   # json.JSONDecodeError is a ValueError
            record["attempts"].append({**log, "error": str(err), "raw_content": done.content})
            continue
        gaps = uncovered(target, parsed)
        record["attempts"].append({**log, "uncovered": [target[n - 1].index for n in gaps]} if gaps else log)
        if best is None or len(gaps) < len(best[0]):
            best = (gaps, parsed)
        if not gaps:
            break
    if best is None:
        record["error"] = "no valid reply"
        return [], record
    if best[0]:
        record["incomplete"] = [target[n - 1].index for n in best[0]]
    return [(target[n - 1], kind, text) for n, kind, text in best[1]], record


def write_atoms_md(path: Path, title: str, messages: list[Message], atoms: list[Atom], failed: set[int],
                   incomplete: set[int]) -> None:
    by_message: dict[int, list[Atom]] = {}
    for atom in atoms:
        by_message.setdefault(atom.message, []).append(atom)
    lines, turn = [f"# Atoms — {title}", "", "Each message of the agent's context, followed by its atoms."], None
    for m in messages:
        if m.turn != turn:
            turn = m.turn
            lines += ["", f"## Turn {turn}" + (" (atomizer failed)" if turn in failed else "")]
        flag = " — not fully covered by its atoms" if m.index in incomplete else ""
        lines += ["", f"**{m.role}** (message {m.index}){flag}", "", "> " + m.content.replace("\n", "\n> "), ""]
        lines += [f"- `{a.id}` *{a.kind}*: {a.text}" for a in by_message.get(m.index, [])] or ["- (no atoms)"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_turns(spec: str | None) -> tuple[int, int] | None:
    if not spec:
        return None
    first, _, last = spec.partition("-")
    return int(first), int(last or first)


def atomize_run(run_dir: Path, turns: tuple[int, int] | None = None, thinking: bool = False,
                max_tokens: int = 16384, seed: int = 0, temperature: float = 0.0) -> list[Atom]:
    params = json.loads((run_dir / "params.json").read_text(encoding="utf-8"))
    client = ChatClient(params["llm_url"], params["llm_name"], max_tokens, thinking=thinking,
                        reasoning_effort=params.get("reasoning_effort") if thinking else None)
    instructions = ATOMIZE_PROMPT.read_text(encoding="utf-8").strip()
    messages = read_messages((run_dir / "transcript_clean.md").read_text(encoding="utf-8"))
    by_turn: dict[int, list[Message]] = {}
    for m in messages:
        by_turn.setdefault(m.turn, []).append(m)
    selected = [t for t in sorted(by_turn) if turns is None or turns[0] <= t <= turns[1]]

    calls = run_dir / "atoms_calls.jsonl"
    calls.write_text("", encoding="utf-8")
    append_jsonl(calls, {"settings": {"model": params["llm_name"], "thinking": thinking, "max_tokens": max_tokens,
                                      "seed": seed, "temperature": temperature, "retry_temperature": RETRY_TEMPERATURE,
                                      "min_chars": MIN_CHARS, "turns": turns, "prompt": instructions}})
    atoms: list[Atom] = []
    failed: set[int] = set()
    incomplete: set[int] = set()
    opening = messages[:1]   # the user's first message (the goal) stays in view as context
    for turn in selected:
        context = [m for m in opening if m.turn != turn] + by_turn.get(turn - 1, [])
        found, record = atomize_turn(client, instructions, params["system_prompt"], context, by_turn[turn],
                                     seed + turn, temperature)
        append_jsonl(calls, record)
        if "error" in record:
            failed.add(turn)
        incomplete.update(record.get("incomplete", []))
        for message, kind, text in found:
            atoms.append(Atom(f"a{len(atoms) + 1:04d}", turn, message.index, message.role, kind, text))
        gaps = f" (messages not covered: {record['incomplete']})" if "incomplete" in record else ""
        print(f"turn {turn}: {len(found)} atoms" + (" (failed)" if turn in failed else gaps), flush=True)

    with (run_dir / "atoms.jsonl").open("w", encoding="utf-8") as f:
        f.writelines(json.dumps(asdict(a), ensure_ascii=False) + "\n" for a in atoms)
    shown = [m for m in messages if m.turn in selected]
    write_atoms_md(run_dir / "atoms.md", run_dir.name, shown, atoms, failed, incomplete)
    return atoms


def main(argv: list[str] | None = None) -> list[Atom]:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--turns", help="only these turns, e.g. 1-10 or 7 (default: all)")
    parser.add_argument("--thinking", action="store_true", help="let the model think (slower; off by default)")
    parser.add_argument("--max-tokens", type=int, default=16384)
    parser.add_argument("--seed", type=int, default=0, help="turn t uses seed + t")
    parser.add_argument("--temperature", type=float, default=0.0,
                        help=f"first attempt (default 0, greedy); retries use {RETRY_TEMPERATURE}")
    args = parser.parse_args(argv)
    atoms = atomize_run(args.run_dir, parse_turns(args.turns), args.thinking, args.max_tokens, args.seed,
                        args.temperature)
    print(f"{len(atoms)} atoms: {args.run_dir / 'atoms.jsonl'}")
    return atoms


if __name__ == "__main__":
    sys.exit(0 if main() is not None else 1)
