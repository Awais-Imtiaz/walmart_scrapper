import asyncio
import unittest
from pathlib import Path

from web_poet import HttpResponse

from walmart.items import WalmartProduct, WalmartZipProduct
from walmart.page_objects.listing_page import ListingPage
from walmart.page_objects.product_page import ProductPage
from walmart.page_objects.stores_page import StoresPage
from walmart.steering import TYPED_OK, type_zip_script

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://www.walmart.com"


def _page(cls, filename: str, url: str):
    html = (FIXTURES / filename).read_text()
    return cls(response=HttpResponse(url, body=html.encode()))


class ListingPageTest(unittest.TestCase):
    def test_entries_from_live_fixture(self):
        listing = _page(ListingPage, "search_fragment.html",
                        f"{BASE}/search?q=milk")
        entries = listing.product_entries()
        self.assertEqual(len(entries), 3)
        first = entries[0]
        self.assertEqual(first["product_id"], "46942839")
        self.assertTrue(first["name"].startswith("Crystal Creamery"))
        self.assertTrue(first["url"].startswith(f"{BASE}/ip/"))
        self.assertIsInstance(first["brand"], str)
        self.assertGreaterEqual(first["rating"] or 0, 0)

    def test_max_pages(self):
        listing = _page(ListingPage, "search_fragment.html", f"{BASE}/search?q=milk")
        self.assertGreaterEqual(listing.max_pages(), 1)


class ProductPageTest(unittest.TestCase):
    def test_extraction_from_live_fixture(self):
        page = _page(ProductPage, "pdp_fragment.html",
                     f"{BASE}/ip/milk/46942839")
        self.assertTrue(page.is_valid())
        item = asyncio.run(page.to_item())
        self.assertEqual(item.name,
                         "Crystal Creamery, Real California Milk, Whole Vitamin D, "
                         "Milk, Plastic Jug, Gallon128 fl oz, Fresh Taste")
        self.assertEqual(item.product_id, "46942839")
        self.assertEqual(item.price, 5.26)
        self.assertEqual(item.price_string, "$5.26")
        self.assertEqual(item.currency, "USD")
        self.assertEqual(item.availability, "IN_STOCK")
        self.assertEqual(item.fulfillment_type, "STORE")
        self.assertEqual(item.brand, "Crystal Creamery")
        self.assertTrue(item.url.startswith(f"{BASE}/ip/"))

    def test_invalid_page(self):
        page = ProductPage(response=HttpResponse(
            f"{BASE}/ip/x/1", body=b"<html><body>shell</body></html>"))
        self.assertFalse(page.is_valid())


class StoresPageTest(unittest.TestCase):
    def test_store_cards_from_live_fixture(self):
        page = _page(StoresPage, "finder_cards_fragment.html",
                     f"{BASE}/store/finder?distance=10")
        stores = page.stores()
        self.assertTrue(stores)
        first = stores[0]
        self.assertEqual(first.name, "Walmart Supercenter")
        self.assertEqual(first.street, "1301 N Victory Pl")
        self.assertEqual(first.city, "Burbank")
        self.assertEqual(first.state, "CA")
        self.assertEqual(first.zip_code, "91502")
        # all stores from the steered 90210 run are LA-metro
        self.assertTrue(all(s.state == "CA" for s in stores))
        self.assertIn(TYPED_OK, type_zip_script("90210"))


class SteeringScriptTest(unittest.TestCase):
    def test_script_contains_zip_and_status(self):
        script = type_zip_script("10001")
        self.assertIn("'10001'", script)
        self.assertIn("store-zip-code", script)
        self.assertIn("wm-steer-status", script)

    def test_rejects_non_digits(self):
        with self.assertRaises(ValueError):
            type_zip_script("abc';drop")


if __name__ == "__main__":
    unittest.main()
