"""Phase 0 probe: does Zyte serve walmart.com, and does ZIP change the data?

Answers three questions with 3 browserHtml requests (pennies):
  R1  Is a search listing served (not a block page)? Shape of __NEXT_DATA__?
  R2  Same PDP fetched in a zip-10001 session (setLocation action): price + store?
  R3  Same PDP in a zip-90210 session: does anything differ?

Run:  cd walmart && ../.venv/bin/python probe.py
Reads ZYTE_API_KEY from ../ralphlauren/.env  (never printed).
Outputs land in walmart/debug/.
"""

import asyncio
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from zyte_api import AsyncZyteAPI

HERE = Path(__file__).parent
DEBUG = HERE / "debug"
DEBUG.mkdir(exist_ok=True)

SEARCH_URL = "https://www.walmart.com/search?q=milk"
ZIPS = ["10001", "90210"]

BLOCK_MARKERS = [
    "Pardon Our Interruption",
    "Robot or human",
    "Access Denied",
    "captcha-delivery",
    "px-captcha",
    "_abck",
    "denied access",
]

# Keys whose paths we report when walking PDP JSON (price + location evidence).
INTERESTING_KEYS = {
    "price", "currentPrice", "priceString", "displayPrice", "listPrice",
    "storeId", "storeName", "storeNumber", "zipCode", "postalCode",
    "city", "state", "fulfillmentType", "inStock", "availabilityStatus",
}


def find_next_data(html: str):
    # attribute order/extra attrs vary (nonce=...), so match by id only
    m = re.search(
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html,
        re.S,
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as e:
        print(f"  !! __NEXT_DATA__ found but unparseable: {e}")
        return None


def report_block(html: str, status_code) -> bool:
    hits = [m for m in BLOCK_MARKERS if m.lower() in html.lower()]
    print(f"  status={status_code} bytes={len(html)} block_markers={hits or 'NONE'}")
    return bool(hits)


def walk(node, path="", out=None, max_list=3):
    """Collect (path, value) for INTERESTING_KEYS, capping list expansion."""
    if out is None:
        out = []
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}"
            if k in INTERESTING_KEYS and isinstance(v, (str, int, float, bool)):
                out.append((p, v))
            walk(v, p, out, max_list)
    elif isinstance(node, list):
        for i, v in enumerate(node[:max_list]):
            walk(v, f"{path}[{i}]", out, max_list)
    return out


def extract_search_products(nd: dict) -> list[dict]:
    """Pull product candidates out of a search page's __NEXT_DATA__.

    Tries the known search-result paths first, then falls back to a generic
    walk for dicts carrying both a name-ish and an id-ish key.
    """
    for path in (
        ("props", "pageProps", "initialData", "searchResult", "itemStacks"),
        ("props", "pageProps", "initialData", "searchResult", "results"),
    ):
        node = nd
        ok = True
        for part in path:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                ok = False
                break
        if not ok:
            continue
        items = []
        stacks = node if isinstance(node, list) else [node]
        for stack in stacks:
            if not isinstance(stack, dict):
                continue
            for item in (stack.get("items") or stack.get("data") or []):
                if isinstance(item, dict):
                    items.append(item)
                elif isinstance(item, dict):  # noqa: unreachable guard
                    pass
        if items:
            return items

    # Generic fallback: any dict with productId/name keys.
    found = []

    def _walk(n):
        if isinstance(n, dict):
            if ("productId" in n or "usItemId" in n or "id" in n) and "name" in n:
                found.append(n)
                return
            for v in n.values():
                _walk(v)
        elif isinstance(n, list):
            for v in n:
                _walk(v)

    _walk(nd)
    return found


def product_url(item: dict) -> str | None:
    for k in ("canonicalUrl", "productPageUrl", "url", "clickUrl"):
        v = item.get(k)
        if isinstance(v, str) and v:
            return v if v.startswith("http") else f"https://www.walmart.com{v}"
    pid = item.get("productId") or item.get("usItemId") or item.get("id")
    return f"https://www.walmart.com/ip/{pid}" if pid else None


def fmt_price(item: dict):
    price = (
        item.get("priceDisplayCodes", {}).get("currentPrice")
        if isinstance(item.get("priceDisplayCodes"), dict)
        else None
    )
    for k in ("displayPrice", "priceString", "currentPrice"):
        v = item.get(k)
        if isinstance(v, (int, float, str)):
            return v
        if isinstance(v, dict) and isinstance(v.get("price"), (int, float)):
            return v["price"]
    return price


async def main():
    load_dotenv(HERE.parent / "ralphlauren" / ".env")
    api_key = os.environ.get("ZYTE_API_KEY")
    if not api_key:
        raise SystemExit("ZYTE_API_KEY missing (expected in ../ralphlauren/.env)")

    client = AsyncZyteAPI(api_key=api_key)  # retries on by default in 0.11
    async with client.session() as s:
        # ---- R1: search listing, no session --------------------------------
        cached = DEBUG / "search_milk.html"
        if cached.exists():
            print("[R1] using cached debug/search_milk.html")
            html = cached.read_text(encoding="utf-8")
            r1 = {"statusCode": "cached"}
        else:
            print(f"[R1] GET {SEARCH_URL}")
            r1 = await s.get(
                {"url": SEARCH_URL, "browserHtml": True,
                 "actions": [{"action": "scrollBottom"}]}
            )
            html = r1["browserHtml"]
            cached.write_text(html, encoding="utf-8")
        blocked = report_block(html, r1.get("statusCode"))
        nd = find_next_data(html)
        products: list[dict] = []
        if nd:
            (DEBUG / "search_milk_next_data.json").write_text(
                json.dumps(nd, indent=1), encoding="utf-8"
            )
            products = extract_search_products(nd)
            print(f"  __NEXT_DATA__ OK, product candidates: {len(products)}")
        else:
            print("  !! no __NEXT_DATA__ in response")
        if blocked or not products:
            print("  -> probe stops here: listing unusable (blocked or no products)")
            return

        first = products[0]
        pdp_url = product_url(first)
        print(f"  first product: {first.get('name', '?')!r} -> {pdp_url}")
        (DEBUG / "probe_pdp_url.txt").write_text(pdp_url, encoding="utf-8")

        # ---- R2/R3: same PDP inside one zip session each -------------------
        for z in ZIPS:
            await asyncio.sleep(2)  # politeness between browser requests
            print(f"\n[R?] PDP in zip session {z}")
            r = await s.get(
                {
                    "url": pdp_url,
                    "browserHtml": True,
                    "actions": [
                        {
                            "action": "setLocation",
                            "address": {
                                "addressCountry": "US",
                                "postalCode": z,
                            },
                        }
                    ],
                    "session": {"id": f"wm-probe-{z}"},
                }
            )
            html = r["browserHtml"]
            (DEBUG / f"pdp_{z}.html").write_text(html, encoding="utf-8")
            report_block(html, r.get("statusCode"))
            for a in r.get("actions", []):
                print(f"  action {a.get('action')}: status={a.get('status')}"
                      f"{' err=' + str(a.get('error')) if a.get('error') else ''}")
            pdp_nd = find_next_data(html)
            if not pdp_nd:
                print("  !! no __NEXT_DATA__ on PDP")
                continue
            (DEBUG / f"pdp_{z}_next_data.json").write_text(
                json.dumps(pdp_nd, indent=1), encoding="utf-8"
            )
            hits = walk(pdp_nd)
            print(f"  interesting fields ({len(hits)}):")
            for p, v in hits[:40]:
                print(f"    {p} = {v!r}")
            if len(hits) > 40:
                print(f"    ... and {len(hits) - 40} more")

    print("\nProbe done. Artifacts in walmart/debug/ — compare pdp_10001 vs pdp_90210.")


if __name__ == "__main__":
    asyncio.run(main())
