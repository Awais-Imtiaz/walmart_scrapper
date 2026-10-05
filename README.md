# Walmart Scraper — products & per-zip store lists

Scrapes `www.walmart.com` product data from search listings and PDPs, and
resolves **which Walmart stores serve each US zip code** — one steered
store-finder request per zip, sticky per-zip Zyte API sessions throughout.

Built with: Scrapy + scrapy-poet (Page Objects) + web-poet + scrapy-zyte-api
(sessions).

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then paste your ZYTE_API_KEY into .env
scrapy crawl products                                 # zips from .env
scrapy crawl products -a zip_codes=10001,90210        # one-off override
scrapy crawl products -a item_limit=10                # more PDPs per run
```

Output: one JSONL file per zip in `output/` (e.g. `output/10001.jsonl`) —
each line = one product for that zip, with the product fields plus
`stores` (Walmart stores near that zip) and `stores_count`.

## What is zip-scoped — and what isn't

| Data | Zip-scoped? | Source |
|---|---|---|
| Store list (name/address/city/state/zip) | ✅ yes | steered `/store/finder` page |
| Product name/id/brand/rating/images | — (global) | `__NEXT_DATA__` on search + PDP |
| Price / availability / fulfillment | ❌ no — reflects the Zyte session IP's default store | PDP `__NEXT_DATA__` |

Walmart pins prices server-side to the session IP's location (bound to the
anonymous `ACID` cookie). Zyte's `setLocation` geolocation override is
silently ignored, Walmart's internal APIs are Akamai-blocked to
non-browser callers, and headless "Make this my store" clicks do not
persist across requests — so per-zip *prices* would require an
authenticated session. The store lists, however, are genuinely per-zip.

## How it works

```
search listing (browserHtml + scrollBottom)
  └─ product entries from __NEXT_DATA__ -> one PDP per product (browserHtml)
       └─ full product fields; stashed per zip until that zip's stores arrive

per zip: steered /store/finder request (browserHtml + evaluate action)
  └─ the action types the zip into the page's combobox (React native-setter
     + input event); Walmart's own authenticated search re-renders the
     store cards for that zip; parsed from
     aria-label="Make this my store, <name>, <street>, <city>, ST ZIP"
       └─ flush stashed products -> output/<zip>.jsonl
```

All extraction is JSON-walking of the `__NEXT_DATA__` script blob (CSS
class names on walmart.com are hashed and unstable; the JSON paths are
not). Challenge "shell" pages (~500KB, no `<title>`, HTTP 200) are
detected by a downloader middleware and rewritten to 503 so Scrapy
retries them — except session-init requests, which the Zyte addon owns.

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

## Status

**Live-verified** (2026-10-05): zip 10001 → 48 NYC-metro stores (NJ/NY/CT);
zip 90210 → 50 LA-metro stores (all CA); same product in both files with
real price/availability.

Every request is `browserHtml` (~30s mean). Requests per run =
1 listing (+ extra pages via `page_limit`) + `item_limit` PDPs + one
steered finder per zip — e.g. 2 zips × 3 products = 9 requests.

## Note on robots.txt

`ROBOTSTXT_OBEY = False`: Walmart's robots.txt itself is served as raw
HTTP, which Walmart's anti-bot layer blocks for Zyte API requests (503).
The crawl only touches public SEO pages (`/search`, `/ip/*`,
`/store/finder`). Review Walmart's Terms of Use before running this at
scale.
