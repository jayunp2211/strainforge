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
