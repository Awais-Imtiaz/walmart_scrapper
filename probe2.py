"""Phase 0b probe: HOW to pin walmart.com to a zip.

setLocation alone failed (probe.py: both zips -> Sacramento 95829, the
datacenter IP's default store). Walmart location = IP geo + cookies.

Experiments, cheapest first:
  R4/R5  raw HTTP stores-by-zip API      -> zip->store mapping, Akamai verdict
  R6-R9  store-finder bootstrap in a sticky session:
         browserHtml store/finder?zip=Z  -> hopefully sets location cookie
         browserHtml PDP  (same session) -> does it now report zip Z?

Run:  cd walmart && ../.venv/bin/python probe2.py
"""

import asyncio
import base64
import json
from pathlib import Path

from dotenv import load_dotenv
import os
from zyte_api import AsyncZyteAPI

from probe import DEBUG, ZIPS, find_next_data, walk

PDP_URL = (DEBUG / "probe_pdp_url.txt").read_text(encoding="utf-8").strip()
STORES_API = "https://www.walmart.com/api/store/v1/stores?zip={zip}&distance=10"
FINDER_URL = "https://www.walmart.com/store/finder?distance=10&zip={zip}"


async def raw_get(s, url, **extra):
    r = await s.get({"url": url, "httpResponseBody": True,
                     "httpResponseStatus": True, **extra})
    body = base64.b64decode(r.get("httpResponseBody", "")).decode(
        "utf-8", "replace"
    )
    return r.get("httpResponseStatus"), body


def loc_summary(nd: dict | None) -> dict:
    """Location + price fields from a PDP __NEXT_DATA__."""
    if not nd:
        return {}
    out = {}
    try:
        meta = nd["props"]["pageProps"]["initialData"]["data"]
        out["meta_location"] = meta["contentLayout"]["pageMetadata"]["location"]
    except (KeyError, TypeError):
        out["meta_location"] = None
    try:
        p = nd["props"]["pageProps"]["initialData"]["data"]["product"]
        out["price"] = p["priceInfo"]["currentPrice"].get("priceString")
        out["availability"] = p.get("availabilityStatus")
        out["product_location"] = p.get("location")
    except (KeyError, TypeError):
        pass
    return out


async def main():
    load_dotenv(Path(__file__).parent.parent / "ralphlauren" / ".env")
    client = AsyncZyteAPI(api_key=os.environ["ZYTE_API_KEY"])
    async with client.session() as s:
        # ---- R4/R5: raw stores API ----------------------------------------
        for z in ZIPS:
            print(f"[R4/5] raw GET stores API zip={z}")
            try:
                status, body = await raw_get(s, STORES_API.format(zip=z))
                print(f"  status={status} bytes={len(body)}")
                print(f"  head: {body[:200]!r}")
                (DEBUG / f"stores_api_{z}.json").write_text(body, encoding="utf-8")
            except Exception as e:  # noqa: BLE001 - probe reports, not raises
                print(f"  !! {type(e).__name__}: {e}")

        # ---- R6-R9: store-finder bootstrap + PDP, per zip ------------------
        for z in ZIPS:
            sid = f"wm-finder-{z}"
            print(f"\n[boot] session {sid}: GET {FINDER_URL.format(zip=z)}")
            try:
                r = await s.get(
                    {"url": FINDER_URL.format(zip=z), "browserHtml": True,
                     "responseCookies": True,
                     "session": {"id": sid}}
                )
                html = r["browserHtml"]
                (DEBUG / f"finder_{z}.html").write_text(html, encoding="utf-8")
                cookies = r.get("responseCookies") or []
                print(f"  bytes={len(html)} cookies={len(cookies)}")
                for c in cookies:
                    print(f"    cookie {c.get('name')}={c.get('value')!r}"
                          f" (domain={c.get('domain')})")
                fnd = find_next_data(html)
                if fnd:
                    (DEBUG / f"finder_{z}_next_data.json").write_text(
                        json.dumps(fnd, indent=1), encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                print(f"  !! finder failed: {type(e).__name__}: {e}")
                continue

            await asyncio.sleep(2)
            print(f"[pdp ] same session, GET PDP")
            r = await s.get(
                {"url": PDP_URL, "browserHtml": True,
                 "session": {"id": sid}}
            )
            html = r["browserHtml"]
            (DEBUG / f"pdp_after_finder_{z}.html").write_text(
                html, encoding="utf-8")
            nd = find_next_data(html)
            info = loc_summary(nd)
            meta_loc = info.get("meta_location") or {}
            print(f"  meta_location: zip={meta_loc.get('postalCode')}"
                  f" city={meta_loc.get('city')}"
                  f" store={meta_loc.get('storeId')}")
            print(f"  price={info.get('price')}"
                  f" availability={info.get('availability')}")
            pl = info.get("product_location") or {}
            if pl:
                print(f"  product_location: zip={pl.get('postalCode')}"
                      f" store={((pl.get('pickupLocation') or {}).get('storeId'))}")

    print("\nDone. Compare pdp_after_finder_10001 vs 90210 above.")


if __name__ == "__main__":
    asyncio.run(main())
