# Strainforge

Cold forming load and energy calculator for tool design, with accounts and shared team history.

It covers ten processes: cut off, closed upset, open upset, setting to perform, pre-upsetting form, reduction, trap extrusion, backward extrusion, piercing and trimming. For each step it gives the press load F (kN), forming energy W (kJ), deformation grade φ and the tooling checks (buckling ratio, head cracking, area change, minimum bottom depth), plus every intermediate value, the equations and a ±30 % load sensitivity chart. Flow stress follows the Ludwik curve kf = C·φⁿ.

## Features

- **Calculator** (free, no account): all processes and product shapes, 34 standard materials.
- **Accounts**: personal or company sign-up. Saved calculations with search, notes and version history.
- **Teams**: everyone in a team workspace sees and edits the team's calculations. Saving checks for newer edits by colleagues (load theirs, overwrite, or save a copy), and open calculations refresh when a teammate saves.
- **Admin role**: invite links, roles, removing members, password reset links, renaming the workspace.
- **Materials**: admins add custom materials (C, n, Rm) and hide standard ones for their workspace.
- **Site owner**: accounts whose email is listed in the `SITE_ADMIN_EMAILS` environment variable (comma-separated) can add, edit and remove materials in the standard library that every account sees. The library lives in the database and is seeded from `strainforge/materials.json`.
- **Owner dashboard**: the site owner lands on `/`, a dashboard with projected monthly revenue at list price (billing is off), accounts, active users, teams and seats, saves, visits per day, process and material mix, recent activity and a CSV export of accounts. The calculator is at `/calculator` for everyone (and `/` for everyone else).
- **Extra calculators**: the site owner builds calculators from named inputs and formulas (`/admin/tools/new`). Formulas use Excel habits (`^`, `PI()`, `IF(c,a,b)`, `kf(phi)` with a material) and are evaluated by a whitelisted parser in `strainforge/formula.py`, never by `eval`. Live ones are listed at `/tools`.
- **Built-in tools** (`strainforge/builtin/`, page `templates/builtin_tool.html` + `static/builtin.js`): hand-coded tool-design calculators at `/tools/<slug>`, drawn to the entered sizes and checked against the source workbooks in `tests/test_builtin.py`. First one: die assembly with slotted sleeve (`/tools/slotted-sleeve-die`).
- **Units**: a Metric / Imperial switch in the top bar (remembered per browser; defaults to imperial for US English browsers). Calculations and saved calculations always use mm, N/mm², kN and kJ; `strainforge/static/units.js` converts what people see and type (in, in³, ksi, US tons, ft·lbf).
- **Pricing**: Personal $19.99/month or $219/year; Team $49.99/month or $549/year for 3 engineers incl. the admin, + $14.99/month or $164/year per extra engineer (yearly = one month free). Billing is not switched on yet; every workspace runs as early access.

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
