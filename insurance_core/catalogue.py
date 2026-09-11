"""The product catalogue (config/products.csv)."""
import csv
from functools import lru_cache

from insurance_core.settings import CONFIG_DIR


@lru_cache(maxsize=None)
def products() -> dict:
    """{product_code: {"product_name": ..., "category": ..., "description": ...}}"""
    with open(CONFIG_DIR / "products.csv", encoding="utf-8") as f:
        return {row["product_code"]: row for row in csv.DictReader(f)}


def product_name(code: str) -> str:
    return products().get(code, {}).get("product_name", code)