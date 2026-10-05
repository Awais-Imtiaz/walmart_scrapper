# Walmart Scraper — products & per-zip store lists

Scrapes `www.walmart.com` product data from search listings and PDPs, and
resolves **which Walmart stores serve each US zip code** — one steered
store-finder request per zip, sticky per-zip Zyte API sessions throughout.

Built with: Scrapy + scrapy-poet (Page Objects) + web-poet + scrapy-zyte-api
(sessions) — same stack and architecture as the sibling `../ralphlauren`
project; concepts are documented there, Walmart-specific decisions in
[EXPLANATION.md](EXPLANATION.md) and [docs/00-phase0-discovery.md](docs/00-phase0-discovery.md).

## Quickstart

```bash
cd "/home/awais/Scrapping practice"
source .venv/bin/activate
cd walmart

cp .env.example .env          # then paste your ZYTE_API_KEY into .env
scrapy crawl products                                 # zips from .env
scrapy crawl products -a zip_codes=10001,90210        # one-off override
scrapy crawl products -a item_limit=10                # more PDPs per run
python -m unittest discover -s tests -v               # offline tests
```

Output: one JSONL file per zip in `output/` (e.g. `output/10001.jsonl`) —
each line = one product for that zip, with the product fields plus
`stores` (Walmart stores near that zip) and `stores_count`.

**Live-verified (2026-10-05):** zip 10001 → 48 NYC-metro stores (NJ/NY/CT);
zip 90210 → 50 LA-metro stores (all CA); same product in both files with
real price/availability. All page-object fixtures are real captured HTML.

## What is zip-scoped — and what isn't

| Data | Zip-scoped? | Source |
|---|---|---|
| Store list (name/address/city/state/zip) | ✅ yes | steered `/store/finder` page |
| Product name/id/brand/rating/images | — (global) | `__NEXT_DATA__` on search + PDP |
| Price / availability / fulfillment | ❌ no — reflects the Zyte session IP's default store | PDP `__NEXT_DATA__` |

Walmart pins prices server-side to the session's IP location (bound to the
anonymous `ACID` cookie). Zyte's `setLocation` is ignored, raw APIs are
Akamai-blocked, and the "Make this my store" pin does not persist across
headless requests — the full investigation is in
[EXPLANATION.md § The zip pinning investigation](EXPLANATION.md). Getting
per-zip *prices* would require a logged-in session or authenticated API
access.

## File map

| File | Concept | Role |
|---|---|---|
| `walmart/spiders/products.py` | — | crawl flow: listing → PDPs; per-zip steered finder; stash-and-flush joins product × zip |
| `walmart/page_objects/listing_page.py` | **Page Objects** | search `__NEXT_DATA__` → product entries |
| `walmart/page_objects/product_page.py` | **Page Objects** | PDP `__NEXT_DATA__` → full product fields |
| `walmart/page_objects/stores_page.py` | **Page Objects** | steered finder → `Store` list from aria-labels |
| `walmart/page_objects/base.py` | **web-poet DI** | `NextDataPage(ItemPage)` — the `__NEXT_DATA__` unwrapper |
| `walmart/steering.py` | **browser actions** | the `evaluate` JS that types a zip into the finder combobox |
| `walmart/pipelines.py` | **Pipelines** | validation → dedupe → per-zip JSONL export |
| `walmart/middlewares.py` | **Middlewares** | challenge-shell detection (→ 503 retry) + per-zip stats |
| `walmart/mixins.py` | **Mixins** | per-zip Zyte session tagging |
| `walmart/session_configs.py` | **ZyteSessionConfig** | sticky session warm-up per zip pool |
| `walmart/items.py` | **Items** | `WalmartProduct`, `Store`, `WalmartZipProduct` (attrs) |
| `walmart/settings.py` | **Zyte API** | addons, sessions, politeness, robots decision |

## Documentation

- **[EXPLANATION.md](EXPLANATION.md)** — the full story: architecture,
  every Walmart-specific decision and its evidence, the zip-pinning
  investigation, honest limitations.
- **[docs/00-phase0-discovery.md](docs/00-phase0-discovery.md)** — the
  numbered experiment log (R1–R17) behind every mechanism, plus probe
  artifacts in `debug/`.
- `../ralphlauren/docs/` — deep-dives on the shared concepts (page
  objects, middlewares, pipelines, mixins, Zyte sessions).
