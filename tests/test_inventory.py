import pytest

from environment.brewer import Effect
from environment.inventory import Inventory


def test_add_and_shortages():
    inv = Inventory()
    inv.add_plants({"elderberry": 2, "sage": 1})
    assert inv.shortages({"elderberry": 2, "sage": 1, "dill": 1}) == {"dill": (1, 0)}
    assert inv.shortages({"elderberry": 4, "sage": 1}) == {"elderberry": (4, 2)}
    assert inv.shortages({"elderberry": 1, "sage": 1}) == {}


def test_consume():
    inv = Inventory()
    inv.add_plants({"elderberry": 3, "sage": 1, "dill": 1})
    inv.consume({"elderberry": 2, "sage": 1, "dill": 1})
    assert dict(inv.plants) == {"elderberry": 1}
    with pytest.raises(ValueError):
        inv.consume({"elderberry": 2})


def test_potions_get_sequential_ids():
    inv = Inventory()
    first = inv.add_potion({"mint": 1, "elderberry": 1, "dill": 1}, Effect(), turn=8)
    second = inv.add_potion({"elderberry": 1, "sage": 1, "dill": 1}, Effect({"I": 2}, {}), turn=15)
    assert (first.id, second.id) == (1, 2)
    assert not first.logged
    assert inv.potions[-1].effect == Effect({"I": 2}, {})
