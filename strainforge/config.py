import os

# Set by the Neon integration on Vercel (Storage → neon-apricot-paddle, prefix DATABASE).
DATABASE_URL = (os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_POSTGRES_URL")
                or os.environ.get("POSTGRES_URL") or "")

# Changes on every Vercel deploy, so browsers and the CDN fetch fresh CSS/JS after each release.
ASSET_VERSION = (os.environ.get("VERCEL_GIT_COMMIT_SHA") or os.environ.get("VERCEL_DEPLOYMENT_ID") or "dev")[:12]

SITE_URL = os.environ.get("SITE_URL", "https://strainforge.vercel.app").rstrip("/")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") != "0"

# Pricing (billing is not switched on yet; every workspace runs as early access).
# Yearly prices are one month free (11 x monthly, rounded down).
PRICE_PERSONAL_CENTS = 1999          # Personal, per month
PRICE_PERSONAL_YEAR_CENTS = 21900    # Personal, per year
PRICE_TEAM_CENTS = 4999              # Team, per month, includes TEAM_INCLUDED_SEATS engineers (admin counts)
PRICE_TEAM_YEAR_CENTS = 54900        # Team, per year
TEAM_INCLUDED_SEATS = 3
PRICE_SEAT_CENTS = 1499              # each engineer beyond the included seats, per month
PRICE_SEAT_YEAR_CENTS = 16400        # each extra engineer, per year


def team_price_cents(seats: int, yearly: bool = False) -> int:
    """List price of a team workspace with this many members."""
    extra = max(0, seats - TEAM_INCLUDED_SEATS)
    if yearly:
        return PRICE_TEAM_YEAR_CENTS + extra * PRICE_SEAT_YEAR_CENTS
    return PRICE_TEAM_CENTS + extra * PRICE_SEAT_CENTS

BILLING_ENABLED = False

# Site owners: may edit the standard material library everyone sees.
# Comma-separated account emails, set in Vercel → Settings → Environment Variables.
SITE_ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("SITE_ADMIN_EMAILS", "").split(",") if e.strip()}
