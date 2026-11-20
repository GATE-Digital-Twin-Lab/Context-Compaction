"""Layer 4: one source text, written piece by piece and assembled by code.

A text is never written in one call. For a sheet:
  1. header: one call invents the title, the author and a small cast (people, a setting) that every piece
     shares, so the pieces read as one text;
  2. pieces: one call per claim of the brief (F1, F2, ...), answered between <piece> and </piece>. An
     instruction and a few sample images per label keep the images varied (no "honey" in every sweet brew);
     light repetition across texts is accepted;
  3. padding: separate calls for the everyday passages, so the claims and the padding never mix;
  4. assembly: code builds the text in the kind's layout (a book's numbered sections, a ledger's dated
     entries, a tale's padding with the claims among it, a pamphlet's bullets), so header, order and layout
     always hold;
  5. checks: every piece is checked by code (no name the sheet does not use) and read alone by
     the blind reader; only a failing piece is written again, with its problems as feedback. Then the whole
     text is read once more; a claim it gets wrong sends that piece back, a claim it finds that the brief
     does not make is traced to the padding that made it.
Length is not checked: the padding is sized from the sheet's target, and the pieces are as long as they are.
"""

import json
import re
from dataclasses import dataclass, field

from corpus.briefs import compare, items, stray_names
from corpus.texts import KIND_NAMES, one_sentence_per_line

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
ENTRIES = ("pair", "triple", "mix", "trial")             # a ledger's dated entries
SECTIONS = (("alias", "group"), ("soil",), ("pair",), ("triple",), ("mix", "identity"))
SECTION_TITLES = ("Of its names and where it grows", "Of its growing", "Of {focus} brewed with one other",
                  "Of {focus} brewed with two others", "Of mixtures")
NUMERALS = ("I", "II", "III", "IV", "V", "VI")
PAD_TOPICS = ("the author's morning and the work of the house", "the weather and the season",
              "trade at the market and what things cost", "a neighbour and the talk of the village",
              "repairs to the house, the roof, the cellar or the yard", "the family and the animals",
              "a journey on the road and who was met there", "a feast day and how it was kept")


# --- the pieces of one claim ------------------------------------------------------------------------


@dataclass
class Piece:
    item: dict
    text: str = ""
    problems: list[str] = field(default_factory=list)
    attempts: int = 0
    done: bool = False


def parse_piece(raw: str) -> str:
    """The text between <piece> and </piece>; ValueError if there is none."""
    m = re.search(r"<piece>\s*(.*?)\s*</piece>", raw, re.S)
    if not m or not m.group(1).strip():
        raise ValueError("the answer lacks <piece>...</piece>")
    return m.group(1).strip()


def labels_of(item: dict) -> list[str]:
    """The secondary labels a claim shows (stats are shown as a change in the drinker, toxic as harm)."""
    value = item["value"]
    effects = value["second_alone"] + value["mixed"] if item["type"] == "mix" else \
        value["effects"] if item["type"] == "trial" else item.get("cues", [])
    return list(dict.fromkeys(e for e in effects if e not in "SDVIW"))


# --- prompts ------------------------------------------------------------------------------------------


def system_prompt(sheet: dict, header: dict, style: str, glossary: str, example: str | None) -> str:
    """Shared by every writing call of a sheet, so the server can reuse it from its cache."""
    kind = KIND_NAMES[sheet["kind"]]
    article = "an" if kind[0] in "aeiou" else "a"
    example_part = (f"\n\nA text of this kind, for its voice only (its claims and images are not yours, never reuse "
                    f"them):\n<example>\n{example}</example>") if example else ""
    return f"""You write one source text, piece by piece, for a game set in a medieval village where people brew potions from eight garden plants. A player will read the finished text and must work out, from your descriptions alone, what it claims.

The text is {article} {kind}: {style}
Its title: {header['title']}. Its author: {header['author']}. People who may appear in it: {header['people']}. Its setting: {header['setting']}. Write every piece in this voice, with these people where people are needed.

Rules for every piece:
1. Say only what the piece asks for. Never add another claim, true or not: what a folk name means, where a plant grows wild, how a plant grows in an earth (black, brown, yellow), what a brew, a mix of brews or a trial does.
2. Show every effect in your own way, and vary it as much as you can from piece to piece: name it plainly at times, more often show it through what people saw, tasted, smelled, or how they fared. Never lean on one word or one image for an effect. A label is noticed in the potion itself while drinking (its smell, taste or look); a stat is a change in what the drinker can do afterwards, a gain or a loss.
3. Never give amounts, counts or proportions of plants: a brew is just the plants "together". The only numbers about a potion's effect are a trial's two counts of work, used exactly.
4. Use plant names, folk names and places exactly as the piece gives them; given a folk name or "a plant of <place>", never reveal which plant it is. Name no other plant, folk name or place.
5. Think only briefly, to plan; write the piece once, in your answer.

Glossary (the player has it):
{glossary}{example_part}"""


def piece_prompt(piece: Piece, samples: dict[str, list[str]]) -> str:
    """One claim to write; samples: a few ways of showing each label (the cue bank), never to be copied."""
    item = piece.item
    lines = [f"Piece {item['n']}: {item['brief']}"]
    labels = labels_of(item)
    if labels:
        lines.append("Show each label in its own way. Do not keep reaching for the obvious image (honey for sweet, "
                     "flowers for fragrant, mud for murky), and do not repeat a way you have already used in this text. "
                     "Some of the many ways it can be shown (find your own):")
        lines += [f"- {label}: {'; '.join(samples.get(label, [])[:3])}" for label in labels]
    if item["type"] in BREWS:
        lines.append("Name every plant of the brew (and of any brew poured in) in the piece itself, as given: "
                     "a reader sees this piece without the brief.")
    lines.append("Write one to four sentences in the text's voice, between <piece> and </piece>, and nothing else.")
    if piece.problems:
        lines.append("Your previous answer was rejected. Fix these problems:\n"
                     + "\n".join(f"- {p}" for p in piece.problems))
    return "\n".join(lines)


def header_prompt(sheet: dict, style: str, places: list[str], problems: list[str]) -> str:
    kind = KIND_NAMES[sheet["kind"]]
    subject = (f"trials of one kind of potion, the one made of {', '.join(sorted(set(sheet['facts'][0]['base'])))}"
               if sheet["kind"] == "trials" else f"the plant {sheet['focus']}")
    text = (f"Invent the title and the author of {('an' if kind[0] in 'aeiou' else 'a')} {kind} from a medieval "
            f"village ({style}), whose subject is {subject}. Also name three people of the village who may appear "
            f"in it, and its setting (a house, a shop, an inn or the like). "
            f"Never use these place names: {', '.join(places)}.\n"
            "Answer in exactly this form:\nTITLE: <title>\nAUTHOR: <a name and a role>\n"
            "PEOPLE: <three names, each with a word on who they are>\nSETTING: <the setting>")
    if problems:
        text += "\nYour previous answer was rejected. Fix these problems:\n" + "\n".join(f"- {p}" for p in problems)
    return text


def pad_prompt(words: int, topic: str, role: str, problems: list[str]) -> str:
    text = (f"Write {role} of the text: a passage of about {words} words about {topic}. It makes no claim and "
            "hints at no effect: it names no plant, folk name or place of growing, and tells of no taste, smell, "
            "warmth or cold, no illness, tiredness or recovery, no change in anyone's body, mind or skill. "
            "Answer with the passage only, between <pad> and </pad>.")
    if problems:
        text += "\nYour previous answer was rejected. Fix these problems:\n" + "\n".join(f"- {p}" for p in problems)
    return text


def parse_header(raw: str) -> dict:
    out = {}
    for key in ("title", "author", "people", "setting"):
        m = re.search(rf"^\s*{key.upper()}:\s*(.+?)\s*$", raw, re.M)
        if not m:
            raise ValueError(f"the answer lacks {key.upper()}:")
        out[key] = m.group(1).strip()
    return out


def parse_pad(raw: str) -> str:
    m = re.search(r"<pad>\s*(.*?)\s*</pad>", raw, re.S)
    if not m or not m.group(1).strip():
        raise ValueError("the answer lacks <pad>...</pad>")
    return m.group(1).strip()


# --- code checks ------------------------------------------------------------------------------------


def check_names(text: str, sheet: dict) -> list[str]:
    """Plants, folk names and places the sheet does not use would be claims the source must not make. (No
    word is banned: a source may name an effect plainly; the prompts ask for variety instead.)"""
    if stray := stray_names(text, sheet):
        return [f"names that this text must not use: {stray}"]
    return []


BREWS = ("pair", "triple", "mix", "trial")


def brew_names(item: dict) -> list[str]:
    """The plants, folk names and places a brew, mix or trial claim must name (from its key); [] otherwise."""
    if item["type"] not in BREWS:
        return []
    found: list[str] = []

    def walk(node):
        if isinstance(node, tuple) and len(node) == 2 and node[0] in ("plant", "alias", "group") \
                and isinstance(node[1], str):
            found.append(node[1])
        elif isinstance(node, tuple):
            for child in node:
                walk(child)

    for part in item["key"][1:]:
        walk(part)
    return list(dict.fromkeys(found))


def check_brew_names(text: str, item: dict) -> list[str]:
    """A piece must name its brew's plants itself: the reader (and the player) read it without the brief."""
    plain = text.lower().replace("’", "'")
    if missing := [n for n in brew_names(item) if n not in plain]:
        return [f"{item['n']}: the piece never names {', '.join(missing)}; name every plant of the brew, "
                "exactly as the piece gives it, in the piece itself"]
    return []


# --- assembly -----------------------------------------------------------------------------------------


def layout(sheet: dict) -> list[tuple[str, object]]:
    """The text's parts in order: ("pad", index), ("piece", item index), ("heading", text), ("bullet", index)."""
    kind, sheet_items = sheet["kind"], items(sheet)
    parts: list[tuple[str, object]] = []
    if kind == "book":
        parts.append(("pad", 0))
        pad = 1
        for (types, title), numeral in zip(zip(SECTIONS, SECTION_TITLES), NUMERALS):
            members = [i for i, it in enumerate(sheet_items) if it["type"] in types]
            if not members:
                continue
            parts.append(("heading", f"{numeral}. {title.format(focus=sheet['focus'])}"))
            parts += [("piece", i) for i in members]
            parts.append(("pad", pad))
            pad += 1
    elif kind in ("transcript", "trials"):
        parts.append(("pad", 0))
        day = 0
        for i, it in enumerate(sheet_items):
            if it["type"] in ENTRIES:
                parts.append(("heading", f"{WEEKDAYS[day % len(WEEKDAYS)]}."))
                day += 1
            parts.append(("piece", i))
        parts.append(("pad", 1))
    elif kind == "pamphlet":
        parts = [("pad", 0)] + [("bullet", i) for i in range(len(sheet_items))] + [("pad", 1)]
    else:                                               # herbal and folk: the claims among the padding
        parts.append(("pad", 0))
        for i in range(len(sheet_items)):
            parts += [("piece", i), ("pad", i + 1)]
    return parts


def pad_plan(sheet: dict) -> list[int]:
    """How many words each padding passage gets: the sheet's padding share of its target, spread evenly."""
    count = sum(1 for kind, _ in layout(sheet) if kind == "pad")
    total = round(sheet["words"] * sheet["padding"])
    return [max(15, total // count)] * count


def assemble(sheet: dict, header: dict, pieces: list[Piece], pads: list[str]) -> str:
    blocks = []
    for kind, value in layout(sheet):
        if kind == "pad":
            blocks.append(pads[value])
        elif kind == "heading":
            blocks.append(value)
        elif kind == "bullet":
            blocks.append("* " + pieces[value].text)
        else:
            blocks.append(pieces[value].text)
    body = "\n\n".join(b for b in blocks if b)
    return (f"Title: {header['title']}\nAuthor: {header['author']}\nKind: {KIND_NAMES[sheet['kind']]}\n\n"
            + one_sentence_per_line(body))


def piece_of(problem: str) -> str | None:
    """The claim number a reader's problem is about, if any (F3: ...)."""
    m = re.match(r"(F\d+)[: ]", problem)
    return m.group(1) if m else None
