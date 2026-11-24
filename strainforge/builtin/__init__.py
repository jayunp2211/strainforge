"""Built-in engineering tools (hand-coded, unlike the owner-built formula calculators).

Each module exposes TOOL: a dict with slug, title, summary, inputs (the form spec),
example (default values), calculate(values) -> result dict, and notes (method notes).
The generic page (templates/builtin_tool.html + static/builtin.js) renders any of them.
"""
from . import sleeve

TOOLS = {t["slug"]: t for t in (sleeve.TOOL,)}


def get(slug: str):
    return TOOLS.get(slug)


def public_spec(t: dict) -> dict:
    """What the browser needs to build the form (no Python callables)."""
    return {k: t[k] for k in ("slug", "title", "inputs", "example", "groups", "figures")}
