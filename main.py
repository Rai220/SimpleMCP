"""
FastMCP Server with CSV-backed product lookup.
"""

import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional
import requests
import os

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
    Расчет НДФЛ для физических лиц — налоговых резидентов РФ по основным видам
    доходов (зарплата, премии и т.п.; п. 2.1 ст. 210 НК РФ).

    Аргументы:
        amount (float): Совокупный облагаемый доход за календарный год, ₽.
        year (int): Календарный год.

    Возвращает:
        float: Сумма НДФЛ в рублях (2 знака).
    """
    # Граничные случаи
    if amount <= 0:
        return 0.0

    # До 2020 включительно — плоская ставка
    if year <= 2020:
        return round(amount * 0.13, 2)

    # 2021–2024 — прогрессия 13%/15% с порогом 5 млн ₽
    if year <= 2024:
        threshold = 5_000_000.0
        base_part = min(amount, threshold)
        over_part = max(amount - threshold, 0.0)
        tax = base_part * 0.13 + over_part * 0.15
        return round(tax, 2)

    # 2025+ — пятиступенчатая шкала
    brackets = [
        (2_400_000.0, 0.13),            # до 2,4 млн ₽
        (5_000_000.0, 0.15),            # 2,4–5 млн ₽
        (20_000_000.0, 0.18),           # 5–20 млн ₽
        (50_000_000.0, 0.20),           # 20–50 млн ₽
        (float("inf"), 0.22),           # свыше 50 млн ₽
    ]

    tax = 0.0
    prev_limit = 0.0
    for limit, rate in brackets:
        slab = min(amount, limit) - prev_limit
        if slab <= 0:
            break
        tax += slab * rate
        prev_limit = limit

    return round(tax, 2)


@mcp.tool
def search_products(query: str, limit: int = 10) -> List[dict]:
    """
Search products whose name or description contains the given substring (case-insensitive).

query : str
    The search string. Leading/trailing whitespace is ignored. If empty after stripping,
    an empty list is returned.
limit : int, optional
    Maximum number of results to return. If less than 1, at most one result is returned.
    Defaults to 10.
Returns

List[dict]
    A list of matching product dictionaries, in the order they appear in the data source.
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


@mcp.tool
def send_message_to_telegram(message: str) -> str:
    """
Send message to a Telegram chat using a bot. Message will send to current user.

Args:
    message (str): The message text to send.
    
Returns:
    str: "OK" if the message was sent successfully, otherwise an error description.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        logger.warning("Telegram bot token or chat ID not set in environment variables")
        return "No TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID found in environment variables"

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        text = message if isinstance(message, str) else str(message)
        if len(text) > 4096:
            logger.warning("Message exceeds 4096 chars, truncating")
            text = text[:4096]

        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok", False):
            desc = data.get("description") or "Unknown Telegram API error"
            logger.error("Telegram API error: %s", desc)
            return f"Telegram API error: {desc}"
    except requests.RequestException as e:
        logger.error("Telegram request failed: %s", e)
        return f"Request failed: {e}"
    
    return "OK"

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
