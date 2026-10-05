"""Item models for the Walmart scraper.

Two item kinds flow through the pipelines:

- ``WalmartProduct`` — scraped once per product (PDP data; not zip-scoped,
  see EXPLANATION.md § "Why prices are not zip-scoped").
- ``WalmartZipProduct`` — the per-(product x zip) item that pairs a product
  with the Walmart stores found near a zip code.
"""

import attrs


@attrs.define
class Store:
    """A Walmart store rendered on the steered /store/finder page."""

    name: str
    street: str
    city: str
    state: str
    zip_code: str

    @property
    def address(self) -> str:
        return f"{self.street}, {self.city}, {self.state} {self.zip_code}"


@attrs.define
class WalmartProduct:
    """Product data from a product page (__NEXT_DATA__)."""

    name: str = ""
    url: str = ""
    product_id: str = ""
    brand: str = ""
    price: float | None = None
    currency: str = "USD"
    price_string: str = ""
    availability: str = ""
    fulfillment_type: str = ""
    rating: float | None = None
    reviews: int | None = None
    image_url: str = ""
    short_description: str = ""


@attrs.define
class WalmartZipProduct:
    """Product paired with the stores near one zip code."""

    product: WalmartProduct
    zip_code: str
    stores: list[Store] = attrs.field(factory=list)

    @property
    def stores_count(self) -> int:
        return len(self.stores)
