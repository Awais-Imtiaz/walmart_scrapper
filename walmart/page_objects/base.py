"""Shared base for Walmart page objects.

Every Walmart page embeds its server-rendered data in a Next.js
``__NEXT_DATA__`` JSON blob, so parsing is JSON-walking, not CSS selectors
(selectors proved fragile — see docs/00-phase0-discovery.md).

Must subclass web_poet.ItemPage: scrapy-poet's dependency injection only
constructs ItemPage descendants for callback parameters (same lesson as
the ralphlauren project — plain classes are silently never injected).
"""

import json

from web_poet import HttpResponse, ItemPage


class NextDataPage(ItemPage):
    """Base page object that unwraps the ``__NEXT_DATA__`` script tag."""

    def __init__(self, response: HttpResponse):
        # web-poet DI is constructor-based; no super().__init__ call —
        # ItemPage's attrs machinery rejects constructor arguments
        # (same idiom as the ralphlauren project's page objects).
        self.response = response

    @property
    def next_data(self) -> dict:
        # attribute order on the tag varies (nonce=...), so match by id only
        raw = self.response.css("script#__NEXT_DATA__::text").get()
        return json.loads(raw) if raw else {}

    def _dig(self, *path, default=None):
        node = self.next_data
        for part in path:
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node
