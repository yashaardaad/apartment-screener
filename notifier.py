"""SMS notifications via Textbelt free API."""

import requests

import config


def send_sms(message: str, phone: str = "") -> dict:
    """Send an SMS via Textbelt free API.

    Free tier: 1 text/day with key='textbelt'.
    Returns API response dict with 'success' and 'quotaRemaining'.
    """
    phone = phone or config.SMS_RECIPIENT
    if not phone:
        print("[SMS] No recipient number configured. Set SMS_RECIPIENT env var.")
        return {"success": False, "error": "No recipient configured"}

    payload = {
        "phone": phone,
        "message": message,
        "key": config.TEXTBELT_KEY,
    }

    try:
        resp = requests.post(config.TEXTBELT_URL, data=payload, timeout=15)
        result = resp.json()
        if result.get("success"):
            print(f"[SMS] Sent successfully. Quota remaining: {result.get('quotaRemaining')}")
        else:
            print(f"[SMS] Failed: {result.get('error', 'Unknown error')}")
        return result
    except Exception as e:
        print(f"[SMS] Error: {e}")
        return {"success": False, "error": str(e)}


def format_notification(ranked_listings: list[dict]) -> str:
    """Format top listings into an SMS-friendly message."""
    count = len(ranked_listings)
    if count == 0:
        return "Apartment Screener: No new listings found this week."

    lines = [f"Apartment Screener: {count} listings found!\n"]
    lines.append("Top 3:")

    for item in ranked_listings[:3]:
        price = f"${item['price']:.0f}"
        dist = f"{item['distance_miles']:.1f}mi" if item.get("distance_miles") else "N/A"
        title = item["title"][:30]
        lines.append(f"- {title} | {price} | {dist}")

    lines.append(f"\nView all: check your Streamlit dashboard")
    return "\n".join(lines)


def notify(ranked_listings: list[dict], phone: str = "") -> dict:
    """Send SMS notification with top listings summary."""
    message = format_notification(ranked_listings)
    return send_sms(message, phone)


if __name__ == "__main__":
    # Test with a sample message
    print("Testing SMS notification...")
    result = send_sms("Test from Apartment Screener!")
    print(f"Result: {result}")
