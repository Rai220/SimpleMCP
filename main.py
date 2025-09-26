"""
FastMCP Server with CSV-backed product lookup.
"""

import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional

from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create server
mcp = FastMCP("Product & Tax Server")


def load_prices(csv_path: str = "prices.csv") -> Dict[str, Dict[str, object]]:
    module_dir = Path(__file__).resolve().parent
    path = Path(csv_path)
    if not path.is_absolute():
        path = module_dir / path

    if not path.is_file():
        abs_path = path.resolve()
        logger.error("CSV file not found: %s", abs_path)
        raise FileNotFoundError(f"CSV file not found: {abs_path}")

    data: Dict[str, Dict[str, object]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("sku"):
                continue
            try:
                price = float(row.get("unit_price", 0) or 0)
            except (TypeError, ValueError):
                price = 0.0
            sku = str(row["sku"]).strip()
            data[sku] = {
                "sku": sku,
                "name": (row.get("name") or "").strip(),
                "unit": (row.get("unit") or "").strip(),
                "unit_price": price,
                "description": (row.get("description") or "").strip(),
            }

    logger.info("Loaded %d products from %s", len(data), path.resolve())
    return data


@mcp.tool
def calc_tax(amount: float, year: int) -> float:
    """
    Налоговый калькулятор НДФЛ для РФ (физлица).
    """
    # Граничные случаи
    if amount <= 0:
        return 0.0

    # До 2020 включительно — плоская ставка
    if year <= 2020:
        return round(amount * 0.13, 2)

    # С 2021 — прогрессия 13%/15% с порогом 5 млн ₽
    threshold = 5_000_000.0
    base_part = min(amount, threshold)
    over_part = max(amount - threshold, 0.0)
    tax = base_part * 0.13 + over_part * 0.15
    return round(tax, 2)


@mcp.tool
def search_products(query: str, limit: int = 10) -> List[dict]:
    """
    Поиск товаров по подстроке в названии (регистронезависимо).
    """
    PRODUCTS = load_prices("prices.csv")
    
    q = query.strip().lower()
    if not q:
        return []
    results: List[dict] = []
    for p in PRODUCTS.values():
        if q in str(p.get("name", "")).lower() or q in str(p.get("description", "")).lower():
            results.append(p)
            if len(results) >= max(1, limit):
                break
    return results


def main():
    logger.info("Starting MCP server on 0.0.0.0:8000")
    logger.info("Server will be accessible via SSE transport")

    try:
        # Use FastMCP's built-in run method with SSE transport
        mcp.run(transport="sse", host="0.0.0.0", port=8000)
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error("Server error: %s", e)
        raise


if __name__ == "__main__":
    main()
