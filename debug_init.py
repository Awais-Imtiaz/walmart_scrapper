"""Diagnose TooManyBadSessionInits: wrap _init_session to log swallowed exceptions.

Run:  ../.venv/bin/python debug_init.py
"""

import logging
import traceback

from dotenv import load_dotenv

load_dotenv("/home/awais/Scrapping practice/walmart/.env")

import scrapy_zyte_api._session as session_mod
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from walmart.spiders.products import ProductsSpider

_orig_init = session_mod._SessionManager._init_session


async def logging_init(self, session_id, request, pool):
    try:
        return await _orig_init(self, session_id, request, pool)
    except BaseException:
        print("=" * 70)
        print(f"INIT EXCEPTION for pool={pool} request={request.url}")
        traceback.print_exc()
        print("=" * 70)
        raise


session_mod._SessionManager._init_session = logging_init

settings = get_project_settings()
settings.set("LOG_LEVEL", "INFO")
settings.set("ZYTE_API_SESSION_MAX_BAD_INITS", 2, priority="cmdline")
process = CrawlerProcess(settings)
process.crawl(ProductsSpider, zip_codes="10001")
process.start()
