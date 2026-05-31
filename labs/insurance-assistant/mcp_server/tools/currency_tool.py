"""Currency conversion tool — uses the free Frankfurter API (no API key needed)."""

import httpx

FRANKFURTER_BASE = "https://api.frankfurter.app"


def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """
    Convert an amount between currencies using live exchange rates.

    Args:
        amount: The numeric amount to convert.
        from_currency: ISO 4217 source currency code (e.g. "USD").
        to_currency: ISO 4217 target currency code (e.g. "EUR").

    Returns:
        A human-readable conversion result, or an error message.
    """
    from_currency = from_currency.strip().upper()
    to_currency = to_currency.strip().upper()

    if amount <= 0:
        return "Error: amount must be a positive number."

    if from_currency == to_currency:
        return f"{amount:.2f} {from_currency} = {amount:.2f} {to_currency} (same currency)"

    try:
        url = f"{FRANKFURTER_BASE}/latest"
        params = {"amount": amount, "from": from_currency, "to": to_currency}

        with httpx.Client(timeout=10) as client:
            response = client.get(url, params=params)

        if response.status_code == 404:
            return (
                f"Error: Unknown currency code(s). Received 404 from Frankfurter API. "
                f"Check that '{from_currency}' and '{to_currency}' are valid ISO 4217 codes."
            )

        response.raise_for_status()
        data = response.json()

        if "rates" not in data or to_currency not in data["rates"]:
            return (
                f"Error: '{to_currency}' not found in API response. "
                f"It may not be supported. Available response: {data}"
            )

        converted = data["rates"][to_currency]
        rate = converted / amount
        date = data.get("date", "unknown date")

        return (
            f"{amount:.2f} {from_currency} = {converted:.4f} {to_currency} "
            f"(rate: 1 {from_currency} = {rate:.6f} {to_currency}, as of {date})"
        )

    except httpx.TimeoutException:
        return "Error: Request to Frankfurter API timed out. Try again later."
    except httpx.HTTPStatusError as exc:
        return f"Error: Frankfurter API returned HTTP {exc.response.status_code}: {exc.response.text}"
    except Exception as exc:
        return f"Error converting currency: {exc}"
