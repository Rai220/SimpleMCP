"""
FastMCP Server with CSV-backed product lookup.
"""

import csv
import logging
import os
from pathlib import Path
from typing import Dict, List

import requests
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create server
mcp = FastMCP("Product & Tax Server")


def load_cars_data(csv_path: str = "prices.csv") -> Dict[str, Dict[str, object]]:
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
            brand = row.get("brand", "")
            model = row.get("model", "")
            price_rub = float(row.get("price_rub", 0) or 0)
            engine_power_hp = int(float(row.get("engine_power_hp", 0) or 0))

            key = f"{brand} {model}".strip()
            data[key] = {
                "brand": brand,
                "model": model,
                "price_rub": price_rub,
                "engine_power_hp": engine_power_hp,
            }

    logger.info("Loaded %d products from %s", len(data), path.resolve())
    return data


@mcp.tool
def transport_tax(tax_year: int, power: int) -> int:
    """
    Calculate the Moscow transport tax for a passenger car.

    Supports tax years 2015–2025.

    Args:
        tax_year (int): Tax year (inclusive range 2015–2025).
        power (int): Engine power in horsepower.

    Returns:
        int: Tax amount in rubles.

    Raises:
        ValueError: If tax_year is outside 2015–2025.
    """

    # Проверим диапазон
    if not (2015 <= tax_year <= 2025):
        raise ValueError("Поддерживаются годы с 2015 по 2025")

    # ---- Ставки 2015–2024 ----
    if tax_year <= 2024:
        if power <= 100:
            rate = 12
        elif power <= 125:
            rate = 25
        elif power <= 150:
            rate = 35
        elif power <= 175:
            rate = 45
        elif power <= 200:
            rate = 50
        elif power <= 225:
            rate = 65
        elif power <= 250:
            rate = 75
        else:
            rate = 150

    # ---- Ставки 2025 ----
    else:  # tax_year == 2025
        if power <= 100:
            rate = 13
        elif power <= 125:
            rate = 28
        elif power <= 150:
            rate = 35
        elif power <= 200:
            rate = 50
        elif power <= 225:
            rate = 72
        elif power <= 250:
            rate = 75
        else:
            rate = 150

    return power * rate


@mcp.tool
def search_cars_db(query: str, limit: int = 10) -> List[dict]:
    """
    Search cars by brand and model in a database (case-insensitive).

    Looks for the query substring in "brand model" or "model brand". Returns matching
    entries including price (price_rub) and horsepower (engine_power_hp).

    Args:
        query (str): Brand/model search string. Leading/trailing whitespace is ignored.
                     If empty after stripping, an empty list is returned.
        limit (int, optional): Maximum number of results to return. If less than 1,
                               at most one result is returned. Defaults to 10.

    Returns:
        List[dict]: List of car dicts with keys: brand, model, price_rub, engine_power_hp.
    """
    CARS = load_cars_data("prices.csv")

    q = query.strip().lower()
    if not q:
        return []
    results: List[dict] = []
    for p in CARS.values():
        brand = str(p.get("brand", "")).strip()
        model = str(p.get("model", "")).strip()
        combo1 = f"{brand} {model}".strip().lower()
        combo2 = f"{model} {brand}".strip().lower()
        if q in combo1 or q in combo2:
            results.append(p)
            if len(results) >= max(1, limit):
                break
    return results


@mcp.tool
def send_message_to_telegram(message: str, chat_id: str = None) -> str:
    """
    Send message to a Telegram chat using a bot.

    Args:
        message (str): The message text to send.
        chat_id (str, optional): The Telegram chat ID or group ID to send the message to.
                                 If not provided, uses TELEGRAM_CHAT_ID from environment variables.

    Returns:
        str: "OK" if the message was sent successfully, otherwise an error description.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if chat_id is None:
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        logger.warning("Telegram bot token or chat ID not set in environment variables")
        return (
            "No TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID found in environment variables"
        )

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
