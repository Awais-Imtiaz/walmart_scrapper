"""Item pipelines: validation -> dedupe -> per-zip JSONL export.

Mirrors the ralphlauren project's pipeline stack; see docs there. The
export writes one ``output/<zip>.jsonl`` per zip, each line a
(product x zip) item with the product fields plus that zip's store list.
"""

import json
import logging
import os
from itertools import islice
from pathlib import Path

from itemadapter import ItemAdapter
from scrapy import Spider
from scrapy.exceptions import DropItem

from walmart.items import WalmartProduct, WalmartZipProduct

logger = logging.getLogger(__name__)


class ProductValidationPipeline:
    """Drop items missing the fields that make them useful."""

    def process_item(self, item, spider: Spider):
        if isinstance(item, WalmartProduct):
            if not item.name or not item.url:
                raise DropItem(f"incomplete product: {item!r:.80}")
        elif isinstance(item, WalmartZipProduct):
            if not item.product.name:
                raise DropItem(f"incomplete zip product: zip={item.zip_code}")
        return item


class DuplicateFilterPipeline:
    """Keep one item per (product_id, zip_code)."""

    def __init__(self):
        self.seen: set[tuple[str, str]] = set()

    def process_item(self, item, spider: Spider):
        if isinstance(item, WalmartZipProduct):
            key = (item.product.product_id, item.zip_code)
            if key in self.seen:
                raise DropItem(f"duplicate {key}")
            self.seen.add(key)
        return item


class PerZipCodeExportPipeline:
    """Write items to output/<zip>.jsonl, one file per zip."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.files: dict[str, object] = {}

    @classmethod
    def from_crawler(cls, crawler):
        return cls(output_dir=crawler.settings.get("OUTPUT_DIR", "output"))

    def open_spider(self, spider: Spider):
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def process_item(self, item, spider: Spider):
        if not isinstance(item, WalmartZipProduct):
            return item
        zip_code = item.zip_code
        fh = self.files.get(zip_code)
        if fh is None:
            fh = open(self.output_dir / f"{zip_code}.jsonl", "w", encoding="utf-8")
            self.files[zip_code] = fh
        stores = [
            {
                "name": s.name,
                "address": s.address,
                "city": s.city,
                "state": s.state,
                "zip_code": s.zip_code,
            }
            for s in item.stores
        ]
        fh.write(json.dumps(
            {
                "product": ItemAdapter(item.product).asdict(),
                "zip_code": zip_code,
                "stores": stores,
                "stores_count": item.stores_count,
            },
            default=str,
        ) + "\n")
        return item

    def close_spider(self, spider: Spider):
        for fh in self.files.values():
            fh.close()
        if self.files:
            logger.info("wrote %d zip files to %s", len(self.files), self.output_dir)
