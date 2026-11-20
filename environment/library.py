"""The episode's sources: a sample of the corpus pool, searched with BM25 over passages, ranked as sources.

Sources get episode ids S1, S2, ... in the sample's shuffled order, so an id tells nothing about the
source's kind or plant. The agent sees a source's title, author and kind (as its header gives it: the
trial ledgers show as apothecary transcripts).

Passages: a text's paragraphs (blank-line separated) are merged in order while a passage stays within
PASSAGE_WORDS; a paragraph longer than that is cut at sentence lines; a short heading ("Monday.",
"II. Of growing") always joins the paragraph after it. Each title is indexed once, as its source's
passage 0.

Ranking a query (demo_spec.md, Retrieval): BM25 scores every passage; the top CANDIDATES passages are
normalised by the best score; a source scores the sum of its candidate passages' scores, sorted
descending and halved at each step (s1 + s2/2 + s3/4 + ...: several matches raise a source, but never
above twice its best, so long texts do not win by length); the top k sources are returned. The kind's
reliability does not enter the ranking: weighing sources is the agent's job."""

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from corpus.sampler import SIZE, sample
from corpus.texts import path_of, split

PASSAGE_WORDS = 80
CANDIDATES = 20     # passages pooled per query before they are grouped by source
DECAY = 0.5         # weight of a source's next-best candidate passage
HEADING_WORDS = 8
K1, B = 1.5, 0.75
STOPWORDS = frozenset(
    "a an and are as at be but by for from had has have he her his i if in into is it its me my of on or "
    "our she so that the their them then there they this to was we were what when which who will with you".split())


@dataclass(frozen=True)
class Source:
    id: str          # S1, S2, ... (what the agent sees)
    sheet: str       # the pool's sheet id (hidden)
    title: str
    author: str
    kind: str        # as shown: "apothecary transcript", "folk tale", ...
    body: str

    def header(self) -> str:
        author = self.author if self.author.startswith("as told") else f"by {self.author}"
        return f'{self.id}: "{self.title}", {author} ({self.kind})'


@dataclass(frozen=True)
class Passage:
    source: Source
    number: int      # 1-based within its source; 0 is the title
    of: int
    text: str


@dataclass(frozen=True)
class Hit:
    source: Source
    score: float                 # normalised: the best passage of the query scores 1
    passages: tuple[int, ...]    # its candidate passages, best first (0: the title)


def tokens(text: str) -> list[str]:
    """Lower-case words without stopwords; possessive 's and plural -s are dropped ("nettles" = "nettle")."""
    out = []
    for word in re.findall(r"[a-z]+(?:'[a-z]+)?", text.lower()):
        word = re.sub(r"'s$|'$", "", word).replace("'", "")
        if word.endswith("ies") and len(word) > 4:
            word = word[:-3] + "y"
        elif word.endswith("s") and not word.endswith("ss") and len(word) > 3:
            word = word[:-1]
        if len(word) > 1 and word not in STOPWORDS:
            out.append(word)
    return out


def passages_of(body: str, limit: int = PASSAGE_WORDS) -> list[str]:
    pieces: list[str] = []
    for para in (p.strip() for p in body.split("\n\n")):
        if not para:
            continue
        if len(para.split()) <= limit:
            pieces.append(para)
            continue
        chunk: list[str] = []
        for line in para.splitlines():
            if chunk and len(" ".join(chunk + [line]).split()) > limit:
                pieces.append("\n".join(chunk))
                chunk = []
            chunk.append(line)
        pieces.append("\n".join(chunk))
    out: list[str] = []
    heading = False   # the last passage ends in a heading that must join the next piece
    for piece in pieces:
        n = len(piece.split())
        if out and (heading or len((out[-1] + " " + piece).split()) <= limit):
            out[-1] += "\n\n" + piece
        else:
            out.append(piece)
        heading = n < HEADING_WORDS
    return out


@dataclass
class Library:
    sources: dict[str, Source]
    found: dict[str, int] = field(default_factory=dict)   # source id -> last turn a search returned it
    _passages: list[Passage] = field(init=False, repr=False)
    _tf: list[Counter] = field(init=False, repr=False)
    _df: Counter = field(init=False, repr=False)
    _avg: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._passages = []
        for src in self.sources.values():
            texts = passages_of(src.body)
            self._passages.append(Passage(src, 0, len(texts), src.title))
            self._passages += [Passage(src, i, len(texts), t) for i, t in enumerate(texts, start=1)]
        self._tf = [Counter(tokens(p.text)) for p in self._passages]
        self._df = Counter(t for tf in self._tf for t in tf)
        self._avg = sum(sum(tf.values()) for tf in self._tf) / max(len(self._tf), 1)

    @classmethod
    def from_sheets(cls, sheet_ids: Sequence[str], found: Mapping[str, int] | None = None) -> "Library":
        sources = {}
        for i, sheet in enumerate(sheet_ids, start=1):
            head, body = split(path_of(sheet).read_text(encoding="utf-8"))
            sid = f"S{i}"
            sources[sid] = Source(sid, sheet, head["Title"], head["Author"], head["Kind"], body.strip())
        return cls(sources, dict(found or {}))

    @classmethod
    def create(cls, seed: int, size: int = SIZE) -> "Library":
        return cls.from_sheets(sample(seed, size))

    def to_dict(self) -> dict:
        return {"sheets": [s.sheet for s in self.sources.values()], "found": dict(self.found)}

    @classmethod
    def from_dict(cls, data: Mapping) -> "Library":
        return cls.from_sheets(data["sheets"], data["found"])

    @property
    def passages(self) -> list[Passage]:
        """The body passages (titles left out)."""
        return [p for p in self._passages if p.number]

    def search(self, query: str, k: int, candidates: int = CANDIDATES, decay: float = DECAY) -> list[Hit]:
        """The top k sources for the query (k or fewer: only sources with a candidate passage)."""
        top = self.passage_scores(query)[:candidates]
        if not top:
            return []
        best = top[0][0]
        grouped: dict[str, list[tuple[float, int]]] = {}
        for score, i in top:   # already sorted best first
            grouped.setdefault(self._passages[i].source.id, []).append((score / best, self._passages[i].number))
        hits = [Hit(self.sources[sid], sum(s * decay ** j for j, (s, _) in enumerate(ps)), tuple(n for _, n in ps))
                for sid, ps in grouped.items()]
        hits.sort(key=lambda h: (-h.score, int(h.source.id[1:])))
        return hits[:k]

    def passage_scores(self, query: str) -> list[tuple[float, int]]:
        """BM25 (score, passage index) of every passage matching the query, best first."""
        terms = set(tokens(query))
        n = len(self._passages)
        scored = []
        for i, tf in enumerate(self._tf):
            length = sum(tf.values())
            score = 0.0
            for t in terms:
                if f := tf.get(t):
                    idf = math.log(1 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5))
                    score += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * length / self._avg))
            if score > 0:
                scored.append((score, i))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return scored

    def mark_found(self, ids, turn: int) -> None:
        for sid in ids:
            self.found[sid] = turn

    def readable(self, sid: str, turn: int) -> bool:
        return self.found.get(sid) == turn
