# Strainforge

Cold forming load and energy calculator for tool design, with accounts and shared team history.

It covers ten processes: cut off, closed upset, open upset, setting to perform, pre-upsetting form, reduction, trap extrusion, backward extrusion, piercing and trimming. For each step it gives the press load F (kN), forming energy W (kJ), deformation grade φ and the tooling checks (buckling ratio, head cracking, area change, minimum bottom depth), plus every intermediate value, the equations and a ±30 % load sensitivity chart. Flow stress follows the Ludwik curve kf = C·φⁿ.

## Features

- **Calculator** (free, no account): all processes and product shapes, 34 standard materials.
- **Accounts**: personal or company sign-up. Saved calculations with search, notes and version history.
- **Teams**: everyone in a team workspace sees and edits the team's calculations. Saving checks for newer edits by colleagues (load theirs, overwrite, or save a copy), and open calculations refresh when a teammate saves.
- **Admin role**: invite links, roles, removing members, password reset links, renaming the workspace.
- **Materials**: admins add custom materials (C, n, Rm) and hide standard ones for their workspace.
- **Pricing**: Personal $15/month; Team $15/month incl. the admin + $10/month per extra seat. Billing is not switched on yet; every workspace runs as early access.

## Stack

- Python 3.12, FastAPI, Jinja2 templates, vanilla JS (`strainforge/static/calc.js`).
- `strainforge/xlengine.py` evaluates the workbook's own formulas (`model.json`); `calc.py` maps inputs and outputs.
- `strainforge/drawings.py` generates the SVG tooling and product drawings.
- Postgres (Neon, through Vercel Storage). The schema is created automatically on first use (`strainforge/db.py`).
- Deployed on Vercel with the Python runtime (`api/index.py`, `vercel.json`).

## Run locally

```
pip install -r requirements.txt uvicorn
export DATABASE_URL=postgresql://user:pass@localhost/strainforge
export COOKIE_SECURE=0
uvicorn api.index:app --reload
```

Tests: `python tests/test_calc.py`
