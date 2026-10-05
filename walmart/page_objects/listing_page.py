"""Page object for Walmart search-result pages (browserHtml + scrollBottom).

Real structure (from debug/search_milk_next_data.json, captured 2026-10-05):

    props.pageProps.initialData.searchResult.itemStacks[*].items[]

Each item carries name / canonicalUrl / usItemId / brand / rating; tile
prices are EMPTY (Walmart lazy-loads them) — price comes from the PDP.
"""

from web_poet import handle_urls

from walmart.items import WalmartProduct
from walmart.page_objects.base import NextDataPage

BASE = "https://www.walmart.com"


@handle_urls(BASE + "/search")
class ListingPage(NextDataPage):
    """Extract product entries from a search listing page."""

    def product_entries(self) -> list[dict]:
        entries: list[dict] = []
        for stack in self._dig(
            "props", "pageProps", "initialData", "searchResult", "itemStacks",
            default=[],
        ) or []:
            for item in stack.get("items") or []:
                if not isinstance(item, dict) or not item.get("name"):
                    continue
                url = item.get("canonicalUrl") or ""
                if url and not url.startswith("http"):
                    url = BASE + url
                rating = item.get("rating")
                if isinstance(rating, dict):  # search tiles: {"averageRating": ..}
                    rating = rating.get("averageRating")
                entries.append(
                    {
                        "product_id": str(
                            item.get("usItemId") or item.get("id") or ""
                        ),
                        "name": item["name"],
                        "url": url,
                        "brand": item.get("brand")
                        or item.get("productBrand")
                        or "",
                        "rating": rating,
                    }
                )
        return entries

    def max_pages(self) -> int:
        return (
            self._dig(
                "props", "pageProps", "initialData", "searchResult",
                "paginationV2", "maxPage", default=1,
            )
            or 1
        )
