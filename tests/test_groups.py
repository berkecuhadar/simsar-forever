import pytest

from simsar import groups

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
    "Ceremonial Leather Loincloth", "Cured Ham Steak", "Craftsman's Writ: Heavy Quiver",
    "Un'Goro Soil", "Raw Black Truffle", "Recipe: Smoked Sagefish", "Smoked Sagefish",
])
def test_non_matches(name):
    assert 1 not in groups.assign({1: name}, GROUPS)


def test_recipe_membership_adds_items():
    out = groups.assign({7: "Some New Forever Thing"}, GROUPS, {"Leatherworking": {7}})
    assert out[7] == ["leatherworking"]
