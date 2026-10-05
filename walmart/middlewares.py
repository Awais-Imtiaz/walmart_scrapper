"""Downloader middlewares: per-zip stats + challenge-shell detection.

walmart.com intermittently serves degraded "shell" pages even through
Zyte browserHtml: ~500KB instead of ~1.2MB, no <title>, no product data,
"challenge" markers (docs/00-phase0-discovery.md R13). They are 200s, not
API errors, so WalmartShellDetectorMiddleware rewrites them to 503 —
Scrapy's RetryMiddleware (priority 550) then retries them, subject to
RETRY_TIMES. Priority 560 > 550 so the rewrite happens before Retry
sees the response (process_response runs highest-priority first).
"""

import logging
from collections import defaultdict

from scrapy.http import Response
from scrapy.spiders import Spider
from scrapy_zyte_api import is_session_init_request

logger = logging.getLogger(__name__)

SHELL_MARKERS = ("px-captcha", "Robot or human")
MIN_HEALTHY_BYTES = 600_000  # healthy search/PDP renders are 1MB+


class ZipStatsMiddleware:
    """Count healthy responses and shells per zip (mirrors ralphlauren project)."""

    def __init__(self):
        self.stats = defaultdict(lambda: {"ok": 0, "shells": 0})

    @classmethod
    def from_crawler(cls, crawler):
        mw = cls()
        crawler.signals.connect(mw.spider_closed, signal="spider_closed")
        return mw

    def process_response(self, request, response, spider):
        zip_code = request.meta.get("zip_code", "?")
        if isinstance(response, Response) and response.status == 200:
            self.stats[zip_code]["ok" if not looks_like_shell(response) else "shells"] += 1
        elif isinstance(response, Response):
            self.stats[zip_code]["shells"] += 1
        return response

    def process_exception(self, request, exception, spider):
        # Session-init downloads fail INSIDE scrapy-zyte-api's session manager,
        # whose `except Exception: return False` swallows the cause — 8 silent
        # failures later the spider dies with TooManyBadSessionInits and no
        # hint why. This hook still sees those downloads, so log the real
        # exception (402 credits, 429 throttle, 400 params, network...).
        logger.warning(
            "download failed (zip=%s, init=%s): %s: %s — %s",
            request.meta.get("zip_code", "?"),
            is_session_init_request(request),
            type(exception).__name__,
            exception,
            request.url,
        )
        return None

    def spider_closed(self, spider: Spider):
        for zip_code, s in sorted(self.stats.items()):
            spider.logger.info(
                "[%s] zip=%s ok=%d shells=%d",
                type(self).__name__, zip_code, s["ok"], s["shells"],
            )


class WalmartShellDetectorMiddleware:
    """Rewrite degraded 200 shells to 503 so Scrapy retries them."""

    def process_response(self, request, response, spider):
        # Session-init requests are managed by scrapy-zyte-api: rewriting
        # them to 503 poisons the session pool (empty rotation deque ->
        # "could not get a session ID" RuntimeErrors for that whole zip).
        if is_session_init_request(request):
            return response
        if isinstance(response, Response) and looks_like_shell(response):
            logger.warning(
                "challenge shell (%d bytes) -> 503 for retry: %s",
                len(response.body), request.url,
            )
            return response.replace(status=503)
        return response


def looks_like_shell(response: Response) -> bool:
    if response.status != 200:
        return False
    body = response.text or ""
    if any(marker in body for marker in SHELL_MARKERS):
        return True
    if len(response.body) < MIN_HEALTHY_BYTES:
        # The real R13 shell embedded __NEXT_DATA__ too — what it lacked
        # was a <title>. Healthy finder pages (~300-450KB) always have one.
        return "<title" not in body
    return False
