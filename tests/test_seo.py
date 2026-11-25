"""Search engine basics: what Google sees on the public pages, and that preview deploys stay out of results."""
import importlib
import json
import re

from fastapi.testclient import TestClient


def client(monkeypatch, **env):
    for k in ("VERCEL_ENV", "GOOGLE_SITE_VERIFICATION", "DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from strainforge import config
    importlib.reload(config)
    from strainforge import app as appmod
    return TestClient(appmod.app)


def jsonld(html):
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def test_home_is_indexable_with_brand_and_site_data(monkeypatch):
    r = client(monkeypatch).get("/")
    assert r.status_code == 200 and "X-Robots-Tag" not in r.headers
    assert '<meta name="robots" content="index">' in r.text
    assert re.search(r"<title>Strainforge", r.text)
    assert '<link rel="canonical" href="https://strainforge.vercel.app/">' in r.text
    types = {n["@type"] for d in jsonld(r.text) for n in d["@graph"]}
    assert types == {"WebSite", "Organization"}


def test_calculators_have_web_application_data(monkeypatch):
    c = client(monkeypatch)
    for path in ("/calculator", "/calculator/slotted-sleeve-die", "/calculator/disc-spring"):
        r = c.get(path)
        assert r.status_code == 200, path
        (d,) = jsonld(r.text)
        assert d["@type"] == "WebApplication" and d["url"].endswith(path)


def test_robots_and_sitemap_on_production(monkeypatch):
    c = client(monkeypatch, VERCEL_ENV="production")
    robots = c.get("/robots.txt").text
    assert "Disallow: /history" in robots and "Sitemap: https://strainforge.vercel.app/sitemap.xml" in robots
    sm = c.get("/sitemap.xml").text
    assert "<loc>https://strainforge.vercel.app/</loc>" in sm and "/calculator/disc-spring" in sm


def test_preview_deploys_are_not_indexed(monkeypatch):
    c = client(monkeypatch, VERCEL_ENV="preview")
    assert c.get("/robots.txt").text == "User-agent: *\nDisallow: /\n"
    assert c.get("/").headers["X-Robots-Tag"] == "noindex, nofollow"


def test_google_verification_tag(monkeypatch):
    r = client(monkeypatch, GOOGLE_SITE_VERIFICATION="abc123").get("/pricing")
    assert '<meta name="google-site-verification" content="abc123">' in r.text
    assert "google-site-verification" not in client(monkeypatch).get("/pricing").text
