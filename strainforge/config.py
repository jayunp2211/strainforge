import os

# Set by the Neon integration on Vercel (Storage → neon-apricot-paddle, prefix DATABASE).
DATABASE_URL = (os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_POSTGRES_URL")
                or os.environ.get("POSTGRES_URL") or "")

SITE_URL = os.environ.get("SITE_URL", "https://strainforge.vercel.app").rstrip("/")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") != "0"

# Pricing (billing is not switched on yet; every workspace runs as early access).
PRICE_BASE_CENTS = 1500      # personal plan, and team base incl. the admin seat
PRICE_SEAT_CENTS = 1000      # each additional team seat
BILLING_ENABLED = False

# Site owners: may edit the standard material library everyone sees.
# Comma-separated account emails, set in Vercel → Settings → Environment Variables.
SITE_ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("SITE_ADMIN_EMAILS", "").split(",") if e.strip()}
