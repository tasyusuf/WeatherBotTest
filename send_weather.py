#!/usr/bin/env python3
"""
Sabah hava durumu gönderici — GitHub Actions tarafından çalıştırılır.
Şu anki hava + önümüzdeki 6 saatin tahmini dahil sesli mesaj gönderir.
"""

import os
import json
import tempfile
import logging
import asyncio
from datetime import datetime, timezone

import pytz
import requests
from gtts import gTTS
from telegram import Bot

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN       = os.environ["BOT_TOKEN"]
CHAT_ID         = os.environ["CHAT_ID"]
WEATHER_API_KEY = os.environ["WEATHER_API_KEY"]
CONFIG_FILE     = os.path.join(os.path.dirname(__file__), "config.json")
TURKEY_TZ       = pytz.timezone("Europe/Istanbul")


def get_cities() -> list[str]:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f).get("cities", ["Istanbul"])


def utc_to_turkey(dt_txt: str) -> str:
    """UTC tarih stringini Türkiye saatine çevirir → '14:00' gibi."""
    dt_utc = datetime.strptime(dt_txt, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(TURKEY_TZ).strftime("%H:%M")


def get_weather_text(city: str) -> str | None:
    params_base = {
        "q": city,
        "appid": WEATHER_API_KEY,
        "units": "metric",
        "lang": "tr",
    }

    # ── Şu anki hava durumu ──────────────────────────────────────────────────
    cur = requests.get(
        "http://api.openweathermap.org/data/2.5/weather",
        params=params_base,
        timeout=10,
    )
    if cur.status_code != 200:
        logger.error("Güncel hava alınamadı (%s): %s", city, cur.status_code)
        return None
    c = cur.json()

    city_name = c["name"]
    temp      = round(c["main"]["temp"])
    feels     = round(c["main"]["feels_like"])
    humidity  = c["main"]["humidity"]
    wind      = c["wind"]["speed"]
    desc      = c["weather"][0]["description"].capitalize()

    # ── 6 saatlik tahmin (3'er saatlik 2 dilim) ─────────────────────────────
    fct = requests.get(
        "http://api.openweathermap.org/data/2.5/forecast",
        params={**params_base, "cnt": 3},
        timeout=10,
    )
    forecast_part = ""
    if fct.status_code == 200:
        slots = fct.json()["list"][1:3]   # 3. ve 6. saat dilimleri
        parts = []
        for slot in slots:
            saat      = utc_to_turkey(slot["dt_txt"])
            slot_temp = round(slot["main"]["temp"])
            slot_desc = slot["weather"][0]["description"]
            rain_mm   = slot.get("rain", {}).get("3h", 0)
            rain_note = f", yağış {rain_mm:.1f} mm" if rain_mm > 0 else ""
            parts.append(f"saat {saat}'de {slot_temp} derece, {slot_desc}{rain_note}")
        forecast_part = " Önümüzdeki 6 saat: " + "; ".join(parts) + "."

    return (
        f"{city_name}. "
        f"Şu an {desc}, {temp} derece, hissedilen {feels} derece. "
        f"Nem yüzde {humidity}, rüzgar saniyede {wind:.1f} metre."
        f"{forecast_part}"
    )


def make_voice(text: str) -> str:
    tts = gTTS(text=text, lang="tr", slow=False)
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tts.save(tmp.name)
    return tmp.name


async def main() -> None:
    cities = get_cities()
    now_tr = datetime.now(TURKEY_TZ).strftime("%H:%M")

    bot = Bot(token=BOT_TOKEN)
    async with bot:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=f"🌤 Saat {now_tr} hava durumu raporu:",
        )
        for city in cities:
            logger.info("📍 %s işleniyor...", city)
            text = get_weather_text(city)
            if not text:
                await bot.send_message(chat_id=CHAT_ID, text=f"❌ {city} alınamadı.")
                continue
            voice_path = make_voice(text)
            try:
                with open(voice_path, "rb") as f:
                    await bot.send_voice(chat_id=CHAT_ID, voice=f)
                logger.info("✅ %s gönderildi.", city)
            finally:
                os.unlink(voice_path)

    logger.info("🎉 Tüm şehirler gönderildi.")


if __name__ == "__main__":
    asyncio.run(main())
