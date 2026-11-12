import pytest

from simsar_forever import groups

GROUPS = groups.load()


@pytest.mark.parametrize("name, expected", [
    ("Light Leather", ["skinning"]),
    ("Heavy Hide", ["skinning"]),
    ("Pristine Hide", ["skinning"]),
    ("Cured Heavy Hide", ["leatherworking"]),
    ("Forceful Medium Armor Kit", ["leatherworking"]),
    ("Linen Cloth", ["tailoring"]),
    ("Bolt of Silk Cloth", ["tailoring"]),
    ("Cerulean Dye", ["tailoring"]),
    ("Strange Dust", ["enchanting"]),
    ("Enchanted Leather", ["enchanting"]),
    ("Raw Rockscale Cod", ["fishing"]),
    ("Stonescale Eel", ["fishing"]),
    ("Pattern: Forceful Medium Armor Kit", ["recipes"]),
    ("Formula: Minor Wizard Oil", ["recipes"]),
])
def test_patterns(name, expected):
    assert groups.assign({1: name}, GROUPS).get(1) == expected


@pytest.mark.parametrize("name", [
    "Ceremonial Leather Loincloth", "Craftsman's Writ: Heavy Quiver", "Un'Goro Soil", "Raw Black Truffle",
    "Green Hills of Stranglethorn - Page 1",
])
def test_non_matches(name):
    assert 1 not in groups.assign({1: name}, GROUPS)


def test_recipe_membership_adds_items():
    out = groups.assign({7: "Some New Forever Thing"}, GROUPS, {"Leatherworking": {7}})
    assert out[7] == ["leatherworking"]


@pytest.mark.parametrize("name, expected", [
    ("Peacebloom", ["herbalism"]),
    ("Copper Ore", ["mining"]),
    ("Thorium Bar", ["mining"]),
    ("Raw Rainbow Fin Albacore", ["fishing"]),
    ("Elixir of Wisdom", ["alchemy"]),
    ("Heavy Sharpening Stone", ["blacksmithing"]),
    ("Mithril Frag Bomb", ["engineering"]),
    ("Chunk of Boar Meat", ["cooking"]),
    ("Heavy Runecloth Bandage", ["first_aid"]),
    ("Plans: Iron Shield Spike", ["recipes"]),
    ("Recipe: Smoked Sagefish", ["recipes"]),
    ("Cured Ham Steak", ["cooking"]),
    ("Fish Oil", ["fishing", "alchemy"]),
])
def test_all_professions(name, expected):
    assert groups.assign({1: name}, GROUPS).get(1) == expected


def test_gathering_recipes_do_not_pull_in_reagents():
    out = groups.assign({7: "Iron Bar", 8: "Some Forever Thing"}, GROUPS, {"Skinning": {7, 8}})
    assert 8 not in out and out[7] == ["mining"]
