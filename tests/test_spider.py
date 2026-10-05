"""Offline spider tests: zip validation, stash-flush, request building.

No network — parse callbacks are exercised with fabricated responses that
carry the same meta the real flow sets (scrapy-poet injection is bypassed
by calling the callback's inner logic through fake pages).
"""

import asyncio
import unittest
from pathlib import Path


from scrapy.http import HtmlResponse, Request
from scrapy.utils.test import get_crawler

from walmart.items import WalmartProduct
from walmart.spiders.products import ProductsSpider

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://www.walmart.com"


def _collect(agen):
    async def run():
        return [item async for item in agen]
    return asyncio.run(run())


def _html_response(url, filename=None, meta=None, body=None):
    if body is None:
        body = (FIXTURES / filename).read_bytes() if filename else b"<html></html>"
    return HtmlResponse(
        url,
        body=body,
        encoding="utf-8",
        request=Request(url, meta=meta or {}),
    )


def _product(name="Milk", pid="1"):
    return WalmartProduct(name=name, url=f"{BASE}/ip/x/{pid}", product_id=pid)


class ZipValidationTest(unittest.TestCase):
    def _spider(self, **kwargs):
        crawler = get_crawler()
        return ProductsSpider.from_crawler(crawler, **kwargs)

    def test_cli_zips_win(self):
        spider = self._spider(zip_codes=["11111", "22222"])
        self.assertEqual(spider.zip_codes, ["11111", "22222"])

    def test_comma_string(self):
        spider = self._spider(zip_codes="11111,22222")
        self.assertEqual(spider.zip_codes, ["11111", "22222"])

    def test_rejects_bad_zips(self):
        with self.assertRaises(ValueError):
            self._spider(zip_codes=["abc"])


class StashFlushTest(unittest.TestCase):
    """Products scraped before their zip's stores arrive must flush later."""

    def _spider(self):
        crawler = get_crawler()
        return ProductsSpider.from_crawler(crawler, zip_codes=["90210"])

    def test_product_before_stores_is_stashed_then_flushed(self):
        spider = self._spider()

        # parse_product with no stores cached -> stash, no items
        from walmart.page_objects.product_page import ProductPage
        from web_poet import HttpResponse
        pdp_html = (FIXTURES / "pdp_fragment.html").read_text()
        page = ProductPage(response=HttpResponse(
            f"{BASE}/ip/milk/46942839", body=pdp_html.encode()))
        entry = {"product_id": "46942839", "name": "milk",
                 "url": f"{BASE}/ip/milk/46942839", "brand": "", "rating": None}
        out = _collect(spider.parse_product(
            _html_response(f"{BASE}/ip/milk/46942839", meta={"zip_code": "90210"}),
            page, entry))
        self.assertEqual(out, [])
        self.assertEqual(len(spider._stash["90210"]), 1)

        # parse_stores with a confirmed steer -> flushes the stashed product
        from walmart.page_objects.stores_page import StoresPage
        finder_html = (FIXTURES / "finder_cards_fragment.html").read_text()
        stores_page = StoresPage(response=HttpResponse(
            f"{BASE}/store/finder", body=finder_html.encode()))
        resp = _html_response(f"{BASE}/store/finder?distance=10",
                              meta={"zip_code": "90210"},
                              body=finder_html + "<div id='x'>TYPED</div>")
        items = _collect(spider.parse_stores(resp, stores_page))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].zip_code, "90210")
        self.assertGreater(items[0].stores_count, 0)
        self.assertNotIn("90210", spider._stash)  # popped by the flush

    def test_unconfirmed_steer_does_not_cache(self):
        spider = self._spider()
        spider._stash["90210"].append(_product())
        from walmart.page_objects.stores_page import StoresPage
        from web_poet import HttpResponse
        finder_html = (FIXTURES / "finder_cards_fragment.html").read_text()
        stores_page = StoresPage(response=HttpResponse(
            f"{BASE}/store/finder", body=finder_html.encode()))
        resp = _html_response(f"{BASE}/store/finder", meta={"zip_code": "90210"},
                              body=finder_html)  # no TYPED marker
        items = _collect(spider.parse_stores(resp, stores_page))
        self.assertEqual(items, [])
        self.assertNotIn("90210", spider._stores)
        self.assertEqual(len(spider._stash["90210"]), 1)  # untouched


class RequestBuildingTest(unittest.TestCase):
    def test_start_builds_listing_and_steers(self):
        crawler = get_crawler()
        spider = ProductsSpider.from_crawler(crawler, zip_codes=["10001", "90210"])

        async def collect():
            return [r async for r in spider.start()]

        starts = asyncio.run(collect())
        self.assertEqual(len(starts), 3)  # 1 listing + 2 steered finders
        steer = [r for r in starts if "/store/finder" in r.url]
        self.assertEqual(len(steer), 2)
        actions = steer[0].meta["zyte_api"]["actions"]
        self.assertEqual(actions[0]["action"], "evaluate")
        self.assertIn("10001", actions[0]["source"])
        zip_meta = steer[0].meta
        self.assertTrue(zip_meta["zyte_api_session_enabled"])
        self.assertEqual(zip_meta["zyte_api_session_location"]["postalCode"], "10001")


if __name__ == "__main__":
    unittest.main()
