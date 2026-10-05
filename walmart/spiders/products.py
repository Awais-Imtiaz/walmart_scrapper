"""Products spider: search listing -> PDPs, plus zip-steered store lists.

Flow (all requests through Zyte API browserHtml):

  1. start(): one listing request (search page, first zip's session pool)
     AND one steered finder request per zip (its own session pool).
  2. parse_listing(): product entries -> one PDP request per product.
  3. parse_product(): full product fields; emit one WalmartZipProduct per
     configured zip whose stores are already cached. Products seen before
     their zip's stores arrive are stashed; parse_stores() flushes them.
  4. parse_stores(): steered finder response -> Store list for that zip
     (replaces any default-location cards); flushes stashed products.

Zip mechanics: Walmart resolves prices/fulfillment from the session IP
(pinned server-side to the ACID cookie) — per-zip PRICES are not
attainable without an authenticated location pin (EXPLANATION.md § "The
zip pinning investigation"). The zip dimension here is the store list:
each zip's finder page is steered to that zip, yielding the real Walmart
stores serving it.
"""

import re
from collections import defaultdict

from scrapy import Spider

from walmart.mixins import ZipCodeCrawlMixin
from walmart.items import WalmartProduct, WalmartZipProduct
from walmart.page_objects.listing_page import ListingPage
from walmart.page_objects.product_page import ProductPage
from walmart.page_objects.stores_page import StoresPage
from walmart.steering import TYPED_OK, type_zip_script

FINDER_URL = "https://www.walmart.com/store/finder?distance={distance}"

# Listing tiles lazy-load prices -> render + scroll. PDPs render fully on
# load (no scroll needed); the finder page needs a pause after steering.
LISTING_PARAMS = {"browserHtml": True, "actions": [{"action": "scrollBottom"}]}
PDP_PARAMS = {"browserHtml": True}
STEER_WAITS = [{"action": "waitForTimeout"}] * 4


class ProductsSpider(ZipCodeCrawlMixin, Spider):
    name = "products"

    search_urls = ["https://www.walmart.com/search?q=milk"]
    zip_codes = ["10001", "90210"]
    page_limit = 1
    item_limit = 5          # per listing page; keep browserHtml costs sane
    finder_distance = 10

    def __init__(self, *args, zip_codes=None, item_limit=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._zips_from_cli = zip_codes is not None
        if zip_codes is not None:
            self._set_zip_codes(zip_codes)
        if item_limit is not None:
            self.item_limit = int(item_limit)
        # products parsed before a zip's stores arrived, per zip
        self._stash: dict[str, list[WalmartProduct]] = defaultdict(list)
        self._stores: dict[str, list] = {}
        self._pages_seen: dict[str, int] = defaultdict(int)

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        if not spider._zips_from_cli:
            spider._set_zip_codes(crawler.settings.getlist("ZIP_CODES") or cls.zip_codes)
        return spider

    def _set_zip_codes(self, zip_codes):
        zips = zip_codes if isinstance(zip_codes, list) else zip_codes.split(",")
        bad = [z for z in zips if not re.fullmatch(r"\d{5}", z)]
        if bad:
            raise ValueError(f"zip codes must be 5 digits, got: {bad}")
        self.zip_codes = zips

    # ------------------------------------------------------------------ flow

    async def start(self):
        for url in self.search_urls:
            yield self.browser_request(url, self.zip_codes[0], self.parse_listing,
                                       LISTING_PARAMS)
        for zip_code in self.zip_codes:
            yield self.steer_request(zip_code)

    def browser_request(self, url, zip_code, callback, params, **kwargs):
        request = self.zip_follow(url, zip_code, callback, **kwargs)
        request.meta["zyte_api"] = dict(params)
        return request

    def steer_request(self, zip_code: str):
        """Finder page request whose actions type the zip into the combobox."""
        request = self.zip_follow(
            FINDER_URL.format(distance=self.finder_distance),
            zip_code,
            self.parse_stores,
        )
        request.meta["zyte_api"] = {
            "browserHtml": True,
            "actions": [
                {"action": "evaluate", "source": type_zip_script(zip_code)},
                *STEER_WAITS,
            ],
        }
        return request

    # -------------------------------------------------------------- parsers

    async def parse_listing(self, response, listing: ListingPage):
        self._pages_seen[response.meta["zip_code"]] += 1
        entries = listing.product_entries()[: self.item_limit]
        if not entries:
            self.logger.warning("listing parsed 0 entries: %s", response.url)
            return
        for entry in entries:
            yield self.browser_request(entry["url"], self.zip_codes[0],
                                       self.parse_product, PDP_PARAMS,
                                       cb_kwargs={"entry": entry})

        seen = self._pages_seen[response.meta["zip_code"]]
        if seen < self.page_limit and seen < listing.max_pages():
            sep = "&" if "?" in response.url else "?"
            next_url = f"{response.url}{sep}page={seen + 1}"
            yield self.browser_request(next_url, self.zip_codes[0],
                                       self.parse_listing, LISTING_PARAMS)

    async def parse_product(self, response, product: ProductPage, entry):
        if not product.is_valid():
            self.logger.warning("PDP without product data (shell?): %s", response.url)
            return
        item = await product.to_item()
        if not item.product_id:
            item.product_id = entry["product_id"]
        if not item.url:
            item.url = entry["url"]
        for zip_code in self.zip_codes:
            if zip_code in self._stores:
                yield self._zip_item(item, zip_code)
            else:
                self._stash[zip_code].append(item)

    async def parse_stores(self, response, stores_page: StoresPage):
        zip_code = response.meta["zip_code"]
        if TYPED_OK not in response.text:
            # Evaluate didn't run (page variant wiped it — experiment R15).
            # The cards on screen are the DEFAULT location's stores: caching
            # them would attribute wrong stores to this zip. Skip instead.
            self.logger.error(
                "steer script did not run for zip=%s — NOT caching default-"
                "location stores; %d products will miss this zip",
                zip_code, len(self._stash.get(zip_code, [])),
            )
            return
        stores = stores_page.stores()
        if not stores:
            self.logger.warning("no store cards parsed for zip=%s", zip_code)
            return
        self._stores[zip_code] = stores
        self.logger.info("zip=%s: %d stores", zip_code, len(stores))
        for product in self._stash.pop(zip_code, []):
            yield self._zip_item(product, zip_code)

    def close(self, reason: str):
        for zip_code, products in self._stash.items():
            if products:
                self.logger.error(
                    "zip=%s: %d products never got stores (steer failed?)",
                    zip_code, len(products),
                )

    def _zip_item(self, product: WalmartProduct, zip_code: str) -> WalmartZipProduct:
        return WalmartZipProduct(
            product=product, zip_code=zip_code, stores=list(self._stores[zip_code])
        )
