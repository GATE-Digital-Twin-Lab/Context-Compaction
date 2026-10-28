import re

from environment.brewer import PLANTS
from environment.lore import LORE, complementary_pairs, pairs_among

# words that would hint at a stat (affinity only: lore never says what a pair is good for)
STAT_HINTS = r"strength|strong|might|vigou?r|vital|life|health|heal|dexter|nimble|agile|quick|swift|" \
             r"intellig|clever|mind|thought|wis(e|dom)|insight"


def test_one_line_for_every_complementary_pair_and_no_other():
    assert set(LORE) == complementary_pairs() and len(LORE) == 17


def test_lines_name_both_plants_and_no_stat():
    for (a, b), text in LORE.items():
        assert a in text.lower() and b in text.lower(), text
        words = re.sub(r"\bsage\b", "", text.lower())  # the plant, not the word
        assert not re.search(rf"\b({STAT_HINTS.lower()})", words), text
        assert not {p for p in PLANTS if p in text.lower()} - {a, b}, text


def test_pairs_among_a_recipe():
    assert pairs_among({"mint": 1, "elderberry": 1, "dill": 1}) == [("dill", "elderberry")]
    assert pairs_among(["elderberry", "chamomile", "dill", "basil"]) == sorted(
        [("chamomile", "elderberry"), ("dill", "elderberry"), ("basil", "elderberry"),
         ("chamomile", "dill"), ("basil", "chamomile"), ("basil", "dill")]
    )
