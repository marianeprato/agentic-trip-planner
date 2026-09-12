"""Currency conversion tool backed by the Frankfurter API (free, keyless)."""

from __future__ import annotations

import httpx
from agents import function_tool

from app.models import CurrencyConversionResult

FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"


@function_tool
async def convert_currency(amount: float, from_currency: str, to_currency: str) -> CurrencyConversionResult:
    """Convert an amount from one currency to another using current exchange rates.

    Args:
        amount: The amount to convert.
        from_currency: Source currency code, e.g. "USD".
        to_currency: Target currency code, e.g. "EUR".
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if from_currency == to_currency:
        return CurrencyConversionResult(
            amount=amount,
            from_currency=from_currency,
            to_currency=to_currency,
            converted_amount=amount,
            rate=1.0,
        )

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            FRANKFURTER_URL,
            params={"base": from_currency, "symbols": to_currency},
        )
        response.raise_for_status()
        data = response.json()
        rate = data["rates"][to_currency]

    return CurrencyConversionResult(
        amount=amount,
        from_currency=from_currency,
        to_currency=to_currency,
        converted_amount=round(amount * rate, 2),
        rate=rate,
    )
