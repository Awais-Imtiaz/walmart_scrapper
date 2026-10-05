"""Page object for the steered store-finder page (zip -> stores).

The finder page (https://www.walmart.com/store/finder?distance=10) renders
store cards whose buttons carry everything we need:

    <button aria-label="Make this my store, Walmart Supercenter,
                       1301 N Victory Pl, Burbank, CA 91502" ...>

The zip arrives via an ``evaluate`` action that types it into the page's
combobox (see walmart/spiders/products.py) — the page's OWN authenticated
search then re-renders the cards for that zip. Verified live: typing
"90210" yielded 50 LA-area stores from a Sacramento-IP session
(docs/00-phase0-discovery.md, experiment R17).
"""

import re

from web_poet import handle_urls

from walmart.items import Store
from walmart.page_objects.base import NextDataPage

BASE = "https://www.walmart.com"

# "Name, Street, City, ST ZIP" — parse from the end; names may contain commas.
STORE_RE = re.compile(
    r"Make this my store,\s*(?P<name>.+?),\s*(?P<street>.+?),\s*"
    r"(?P<city>.+?),\s*(?P<state>[A-Z]{2})\s*(?P<zip>\d{5}(?:-\d{4})?)"
)


@handle_urls(BASE + "/store/finder")
class StoresPage(NextDataPage):
    """Parse store cards from a steered finder page."""

    def store_labels(self) -> list[str]:
        labels = self.response.css(
            'button[aria-label^="Make this my store"]::attr(aria-label)'
        ).getall()
        return [label.strip() for label in labels]

    def stores(self) -> list[Store]:
        out: list[Store] = []
        for label in self.store_labels():
            m = STORE_RE.search(label)
            if not m:
                continue
            d = m.groupdict()
            out.append(
                Store(
                    name=d["name"].strip(),
                    street=d["street"].strip(),
                    city=d["city"].strip(),
                    state=d["state"],
                    zip_code=d["zip"],
                )
            )
        return out
