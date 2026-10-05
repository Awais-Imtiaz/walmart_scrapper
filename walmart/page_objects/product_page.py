"""Page object for Walmart product pages (browserHtml).

Real structure (from debug/pdp_10001_next_data.json, captured 2026-10-05):

    props.pageProps.initialData.data.product

NOTE: price/fulfillment reflect the session's location context. Zyte
sessions exit from datacenter IPs, so Walmart pins them to a default store
(see EXPLANATION.md § "The zip pinning investigation") — prices are real
USD online prices, but not regionally varied per requested zip.
"""

from web_poet import handle_urls

from walmart.items import WalmartProduct
from walmart.page_objects.base import NextDataPage

BASE = "https://www.walmart.com"


@handle_urls(BASE + "/ip")
class ProductPage(NextDataPage):
    """Extract product fields from a PDP's __NEXT_DATA__."""

    def is_valid(self) -> bool:
        """Degraded/challenge shells carry no product node."""
        return bool(self._product())

    def _product(self) -> dict:
        return self._dig(
            "props", "pageProps", "initialData", "data", "product", default={}
        ) or {}

    async def to_item(self) -> WalmartProduct:
        p = self._product()
        price_info = (p.get("priceInfo") or {}).get("currentPrice") or {}
        image_info = p.get("imageInfo") or {}
        url = p.get("canonicalUrl") or str(self.response.url)
        if url and not url.startswith("http"):
            url = BASE + url
        return WalmartProduct(
            name=p.get("name") or "",
            url=url,
            product_id=str(p.get("usItemId") or p.get("id") or ""),
            brand=p.get("brand") or "",
            price=price_info.get("price"),
            currency=price_info.get("currencyUnit") or "USD",
            price_string=price_info.get("priceString") or "",
            availability=p.get("availabilityStatus") or "",
            fulfillment_type=p.get("fulfillmentType") or "",
            rating=p.get("averageRating"),
            reviews=p.get("numberOfReviews"),
            image_url=image_info.get("thumbnailUrl") or "",
            short_description=p.get("shortDescription") or "",
        )
