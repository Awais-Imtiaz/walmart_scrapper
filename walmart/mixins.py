from collections.abc import Callable, Iterable

from scrapy import Request


class ZipCodeCrawlMixin:
    """Tags every request with a per-zip Zyte API session.

    Requests built here join the session pool "www.walmart.com@US,<zip>".
    NOTE: unlike ralphlauren.com, Walmart IGNORES Zyte's setLocation
    geolocation override — location resolves from the session IP and is
    bound server-side to the ACID cookie (docs/00-phase0-discovery.md R2).
    The per-zip pools still matter: they keep each zip's finder-steering
    inside one warm, consistent cookie jar (fewer challenge shells).
    """

    zip_codes: list[str] = []
    country: str = "US"

    def zip_meta(self, zip_code: str) -> dict:
        return {
            "zip_code": zip_code,
            "zyte_api_session_enabled": True,
            "zyte_api_session_location": {
                "addressCountry": self.country,
                "postalCode": zip_code,
            },
        }

    def zip_requests(self, urls: Iterable[str], callback: Callable) -> Iterable[Request]:
        for url in urls:
            for zip_code in self.zip_codes:
                yield Request(url, callback=callback, meta=self.zip_meta(zip_code))

    def zip_follow(self, url: str, zip_code: str, callback: Callable, **kwargs) -> Request:
        return Request(url, callback=callback, meta=self.zip_meta(zip_code), **kwargs)
