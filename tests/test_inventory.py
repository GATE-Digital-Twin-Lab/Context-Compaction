import pytest

from environment.brewer import Effect
from environment.inventory import Inventory


def test_add_and_shortages():
    inv = Inventory()
    inv.add_plants({"p2": 2, "p4": 1})
    assert inv.shortages({"p2": 2, "p4": 1, "p6": 1}) == {"p6": (1, 0)}
    assert inv.shortages({"p2": 4, "p4": 1}) == {"p2": (4, 2)}
    assert inv.shortages({"p2": 1, "p4": 1}) == {}


def test_consume():
    inv = Inventory()
    inv.add_plants({"p2": 3, "p4": 1, "p6": 1})
    inv.consume({"p2": 2, "p4": 1, "p6": 1})
    assert dict(inv.plants) == {"p2": 1}
    with pytest.raises(ValueError):
        inv.consume({"p2": 2})


def test_potions_get_sequential_ids():
    inv = Inventory()
    first = inv.add_potion({"p1": 1, "p2": 1, "p6": 1}, Effect(), turn=8)
    second = inv.add_potion({"p2": 1, "p4": 1, "p6": 1}, Effect({"I": 2}, {}), turn=15)
    assert (first.id, second.id) == (1, 2)
    assert not first.logged
    assert inv.potions[-1].effect == Effect({"I": 2}, {})
