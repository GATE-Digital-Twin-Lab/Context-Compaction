"""Step through the agent's notes of a run, one reply at a time, for manual inspection (validation.ipynb).
Each reply is shown as the agent wrote it, next to how LLM/notes.py filed it, with its departures from the
schema; by default only the replies that do not follow the schema.
    from LLM.notes_review import browse
    browse("runs/<agent>/<run_id>")                      # Previous / Next buttons
"""

import html
import json
from dataclasses import dataclass
from pathlib import Path

from LLM.notes import SCHEMA, _BULLET, notes_text, write_notes
from utils import transcript_blocks


@dataclass
class Entry:
    turn: int
    reply: int      # the reply's number in the run (1 = first)
    before: str     # the message the agent replied to
    text: str       # the reply as kept in the context
    notes: dict     # its record in notes.jsonl


def load_entries(run_dir: str | Path, invalid_only: bool = True) -> list[Entry]:
    """The run's replies in order (only those that do not follow the schema, unless invalid_only is False).
    notes.jsonl is written first if the run does not have it yet."""
    run_dir = Path(run_dir)
    path = run_dir / "notes.jsonl"
    if not path.exists():
        write_notes(run_dir)
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    blocks = transcript_blocks((run_dir / "transcript_clean.md").read_text(encoding="utf-8"))
    entries, before = [], ""
    for turn, role, content in blocks:
        if role != "agent":
            before = content
            continue
        record = records[len(entries)]
        assert record["turn"] == turn, f"notes.jsonl does not match the transcript at turn {turn}"
        entries.append(Entry(turn, record["reply"], before, content, record))
    return [e for e in entries if not (invalid_only and e.notes["valid"])]


def _flagged(line: str, problems: list[str]) -> bool:
    """Whether a problem message quotes this line of the reply."""
    stripped = line.strip()
    bullet = _BULLET.match(stripped)
    texts = {stripped[:80], (bullet.group(1).strip() if bullet else stripped)[:80]}
    return any(repr(t) in p for t in texts for p in problems)


_STYLE = """<style>
.nr {font-family: var(--jp-ui-font-family, sans-serif); font-size: 13px; line-height: 1.45}
.nr h3 {margin: 4px 0 8px}
.nr .cols {display: flex; gap: 16px; align-items: flex-start; flex-wrap: wrap}
.nr .col {flex: 1 1 420px; min-width: 0}
.nr pre {white-space: pre-wrap; word-break: break-word; margin: 0; padding: 8px;
         border: 1px solid rgba(128,128,128,.35); border-radius: 4px}
.nr .flag {background: rgba(255,190,0,.35)}
.nr .bad {color: #d33}
.nr .muted {opacity: .6}
.nr table {border-collapse: collapse; width: 100%}
.nr td {border-top: 1px solid rgba(128,128,128,.25); padding: 3px 6px; vertical-align: top}
.nr td.sub {white-space: nowrap; width: 1%}
.nr ul {margin: 0; padding-left: 18px}
</style>"""


def render(entry: Entry, position: str = "") -> str:
    """One reply as HTML: problems, the reply with the quoted lines marked, and how it was filed."""
    notes = entry.notes
    esc = html.escape
    status = "follows the schema" if notes["valid"] else '<span class="bad">does not follow the schema</span>'
    out = [_STYLE, '<div class="nr">', f"<h3>Turn {entry.turn} · reply {entry.reply} · {status}"
           f'<span class="muted">{" · " + esc(position) if position else ""}</span></h3>']
    issues = [esc(p) for p in notes["problems"]] + [f"{esc(sub)} missing" for sub in notes["missing"]]
    if issues:
        out.append('<ul class="bad">' + "".join(f"<li>{i}</li>" for i in issues) + "</ul>")
    out.append(f'<details><summary class="muted">Message before the reply</summary><pre>{esc(entry.before)}</pre>'
               "</details>")

    notes_lines = len(notes_text(entry.text).split("\n"))   # the lines after these are the call
    lines = []
    for n, line in enumerate(entry.text.split("\n")):
        flagged = n < notes_lines and _flagged(line, notes["problems"])
        lines.append(f'<span class="flag">{esc(line)}</span>' if flagged else esc(line))
    reply = "\n".join(lines)

    filled = {p.split(" heading left out")[0] for p in notes["problems"] if " heading left out" in p}
    remarks: dict[str, list[str]] = {}
    for r in notes["remarks"]:
        remarks.setdefault(r["sub"], []).append(r["text"])
    items: dict[str, list[str]] = {}
    for i in notes["items"]:
        items.setdefault(i["sub"], []).append(i["text"])
    rows = []
    for section, subs in SCHEMA.items():
        rows.append(f'<tr><td colspan="2"><b>{section}</b></td></tr>')
        for sub in subs:
            if sub in items:
                cell = "<ul>" + "".join(f"<li>{esc(t)}</li>" for t in items[sub]) + "</ul>"
            elif sub in notes["empty"]:
                cell = '<span class="muted">none</span>' + "".join(
                    f'<div class="muted">{esc(t)}</div>' for t in remarks.get(sub, []))
            elif sub in notes["missing"]:
                cell = '<span class="bad">missing</span>'
            else:
                cell = '<span class="muted">(heading only)</span>'
            tag = ' <span class="flag">filled in</span>' if sub in filled else ""
            rows.append(f'<tr><td class="sub">{sub}{tag}</td><td>{cell}</td></tr>')

    out.append('<div class="cols">'
               f'<div class="col"><b>Reply</b><pre>{reply}</pre></div>'
               f'<div class="col"><b>Filed as</b><table>{"".join(rows)}</table></div>'
               "</div></div>")
    return "".join(out)


def browse(run_dir: str | Path, invalid_only: bool = True, start: int = 0):
    """A widget that shows the run's replies one at a time, with Previous / Next buttons."""
    import ipywidgets as widgets

    entries = load_entries(run_dir, invalid_only)
    if not entries:
        return widgets.HTML(f"<b>{html.escape(str(run_dir))}</b>: every reply follows the schema."
                            if invalid_only else "No replies in this run.")
    kind = "invalid replies" if invalid_only else "replies"
    state = {"i": min(max(start, 0), len(entries) - 1)}
    view = widgets.HTML()
    prev_button = widgets.Button(description="Previous", icon="arrow-left")
    next_button = widgets.Button(description="Next", icon="arrow-right")
    label = widgets.Label()

    def show() -> None:
        i = state["i"]
        label.value = f"{i + 1} of {len(entries)} {kind}"
        view.value = render(entries[i], f"{i + 1} of {len(entries)} {kind}")
        prev_button.disabled = i == 0
        next_button.disabled = i == len(entries) - 1

    def step(delta: int) -> None:
        state["i"] = min(max(state["i"] + delta, 0), len(entries) - 1)
        show()

    prev_button.on_click(lambda _: step(-1))
    next_button.on_click(lambda _: step(1))
    show()
    return widgets.VBox([widgets.HBox([prev_button, next_button, label]), view])
