import os
import httpx

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


async def notify_admin_new_listing(listing) -> None:
    """Yangi e'lon kelganda adminga tasdiqlash/rad etish tugmalari bilan xabar yuboradi."""
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        return  # sozlanmagan bo'lsa, jim o'tkazib yuboramiz (dev muhitida qulay)

    text = (
        f"🚗 Yangi e'lon: #{listing.id}\n"
        f"{listing.brand} {listing.model}, {listing.year}\n"
        f"Narxi: {listing.price:,.0f} so'm\n"
        f"Probeg: {listing.mileage:,} km\n"
        f"Hudud: {listing.region or '-'}"
    )
    if listing.description:
        text += f"\nTavsif: {listing.description.strip()}"
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Tasdiqlash", "callback_data": f"approve:{listing.id}"},
            {"text": "❌ Rad etish", "callback_data": f"reject:{listing.id}"},
        ]]
    }

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": ADMIN_CHAT_ID, "text": text, "reply_markup": keyboard},
            timeout=10,
        )
