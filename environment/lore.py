"""Hidden herbal lore: one line per pair of plants that share a stat's plant set. Never import from
agent-facing code. The lines name the affinity only, never the stat; logging a potion unlocks the
lines for the pairs among its plants, and kb_lookup shows the unlocked ones."""

from collections.abc import Iterable
from itertools import combinations

from environment.brewer import STAT_SETS


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


LORE: dict[tuple[str, str], str] = {
    _pair("nettle", "rosemary"): "Nettle and rosemary were planted side by side along the old abbey wall, "
                                 "and the monks would never cut one without the other.",
    _pair("nettle", "sage"): "The hedge-folk say: where nettle stings, sage soothes; in the brewer's pot "
                             "the two are fast friends.",
    _pair("rosemary", "sage"): "Rosemary and sage grow best in the same stony bed, and the old herbals "
                               "call them sisters of the hearth.",
    _pair("dill", "sage"): "The village brewers keep dill and sage in a single jar, for each, they say, "
                           "wakes something in the other.",
    _pair("elderberry", "sage"): "Elderberry and sage appear together in the oldest recipe books, as if "
                                 "one were never written down without the other.",
    _pair("dill", "elderberry"): "Dill and elderberry share an old kinship, and the herbwives gather them "
                                 "on the same morning.",
    _pair("chamomile", "mint"): "Chamomile and mint are steeped together in every tavern from here to the "
                                "coast; neither tastes quite right alone.",
    _pair("chamomile", "rosemary"): "A pedlar's rhyme: chamomile for the cup, rosemary for the pot, and "
                                    "both together or none at all.",
    _pair("mint", "rosemary"): "Mint and rosemary are tied in one bundle at the market, and the old "
                               "brewers swear the bundle should never be untied.",
    _pair("basil", "mint"): "Basil and mint were sown in one furrow by the first gardeners, and the "
                            "herbals still name them companions.",
    _pair("basil", "nettle"): "Nettle and basil, the old gardeners say, keep each other's company in pot "
                              "and plot alike.",
    _pair("mint", "nettle"): "The hedge-witches gathered mint and nettle in the same basket, for one "
                             "without the other made a poor brew.",
    _pair("basil", "chamomile"): "Basil and chamomile are old companions; the herbwives of the valley "
                                 "always bundle them together.",
    _pair("basil", "dill"): "Basil and dill hang from the same rafter in every brewer's loft and are "
                            "taken down together.",
    _pair("basil", "elderberry"): "Elderberry and basil, the chroniclers write, were the twin gifts of "
                                  "the summer fair.",
    _pair("chamomile", "dill"): "Chamomile and dill lie pressed between the same pages of the old "
                                "herbals, as if the scribes knew them inseparable.",
    _pair("chamomile", "elderberry"): "Elderberry wine is never poured without a sprig of chamomile, by "
                                      "a custom older than anyone remembers.",
}


def complementary_pairs() -> set[tuple[str, str]]:
    """Pairs of plants that appear together in at least one stat's plant set."""
    return {_pair(a, b) for plants in STAT_SETS.values() for a, b in combinations(plants, 2)}


def pairs_among(plants: Iterable[str]) -> list[tuple[str, str]]:
    """The complementary pairs among some plants (sorted), i.e. the lore a potion unlocks."""
    return sorted(p for p in (_pair(a, b) for a, b in combinations(set(plants), 2)) if p in LORE)
