import re
from importlib import resources
from pathlib import Path

import yaml

DEMO_SUFFIX = re.compile(r" \(demo\)$")


def _compile(patterns, key):
    out = []
    for p in patterns or []:
        try:
            out.append(re.compile(p, re.IGNORECASE))
        except re.error as e:
            raise ValueError(f"bad pattern {p!r} in group {key!r}: {e}") from e
    return out


def load(cfg=None):
    with resources.files("simsar_forever").joinpath("data/groups.yaml").open(encoding="utf-8") as f:
        spec = yaml.safe_load(f)["groups"]
    if cfg:
        user_file = Path(cfg["_base_dir"]) / "groups.yaml"
        if user_file.exists():
            with open(user_file, encoding="utf-8") as f:
                spec.update((yaml.safe_load(f) or {}).get("groups", {}))
    groups = []
    for key, g in spec.items():
        groups.append({
            "key": key,
            "title": g.get("title", key),
            "profession": g.get("profession", key),
            "role": g.get("role", "craft"),
            "color": g.get("color", "#888888"),
            "patterns": _compile(g.get("patterns"), key),
            "exclude": _compile(g.get("exclude"), key),
            "ids": {int(i) for i in g.get("ids", [])},
        })
    return groups


def public(groups):
    return [{k: g[k] for k in ("key", "title", "profession", "role", "color")} for g in groups]


def assign(names, groups, recipe_items=None):
    """names: {item_id: name}; recipe_items: {profession: set(item_id)}.
    Returns {item_id: [group keys]} for items that belong to at least one group."""
    recipe_items = {k.lower(): v for k, v in (recipe_items or {}).items()}
    out = {}
    for item_id, name in names.items():
        name = DEMO_SUFFIX.sub("", name or "")
        hits = []
        for g in groups:
            # Recipes pull their products and reagents into crafting groups only; a gathering
            # profession's own recipes (Forever gives Skinning some) would drag in bars and the like.
            from_recipes = g["role"] == "craft" and item_id in recipe_items.get(g["profession"].lower(), ())
            if item_id in g["ids"] or from_recipes:
                hits.append(g["key"])
            elif name and any(p.search(name) for p in g["patterns"]) and not any(p.search(name) for p in g["exclude"]):
                hits.append(g["key"])
        if hits:
            out[item_id] = hits
    return out
