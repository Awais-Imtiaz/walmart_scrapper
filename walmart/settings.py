import os

from dotenv import load_dotenv

import walmart.page_objects  # noqa: E402,F401  registers @handle_urls rules
import walmart.session_configs  # noqa: E402,F401  registers @session_config rules

load_dotenv()

BOT_NAME = "walmart"
SPIDER_MODULES = ["walmart.spiders"]
NEWSPIDER_MODULE = "walmart.spiders"

# walmart.com's robots.txt itself is served as raw HTTP, which Walmart's
# Akamai layer blocks for Zyte API requests (503, docs/00-phase0-discovery.md
# R14) — obeying it is impossible through the API. The crawl only touches
# public SEO pages (/search, /ip/*, /store/finder); noted in EXPLANATION.md.
ROBOTSTXT_OBEY = False

ADDONS = {
    "scrapy_poet.Addon": 400,
    "scrapy_zyte_api.Addon": 500,
}

ZYTE_API_KEY = os.getenv("ZYTE_API_KEY")
ZIP_CODES = [z.strip() for z in os.getenv("ZIP_CODES", "10001,90210").split(",") if z.strip()]
USER_AGENT = ""  # "" passes RobotsTxtMiddleware's check but sends no UA header → Zyte API sets one
ZYTE_API_SESSION_POOL_SIZE = 1  # one sticky session per zip pool = one shopper per zip
# Sessions are opted in per-request by ZipCodeCrawlMixin (zyte_api_session_enabled
# meta), NOT globally — otherwise even the robots.txt fetch pulls a browser session.

DOWNLOADER_MIDDLEWARES = {
    "walmart.middlewares.WalmartShellDetectorMiddleware": 560,  # > 550: rewrite shells before RetryMiddleware
    "walmart.middlewares.ZipStatsMiddleware": 570,
}

RETRY_ENABLED = True
RETRY_TIMES = 2
RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408, 429]

DOWNLOAD_DELAY = 1.0
CONCURRENT_REQUESTS = 4
CONCURRENT_REQUESTS_PER_DOMAIN = 2

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_CONCURRENCY = 1
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0
AUTOTHROTTLE_MAX_CONCURRENCY = 4

ITEM_PIPELINES = {
    "walmart.pipelines.ProductValidationPipeline": 100,
    "walmart.pipelines.DuplicateFilterPipeline": 200,
    "walmart.pipelines.PerZipCodeExportPipeline": 300,
}

OUTPUT_DIR = "output"

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

FEED_EXPORT_ENCODING = "utf-8"
LOG_LEVEL = "INFO"
