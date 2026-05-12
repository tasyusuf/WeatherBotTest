#!/usr/bin/env python3
"""
Sabah hava durumu gönderici — GitHub Actions tarafından çalıştırılır.
config.json'daki tüm şehirler için sesli mesaj gönderir.
"""

import os
import json
import tempfile
import logging
import asyncio

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


def get_cities() -> list[str]:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f).get("cities", ["Istanbul"])


def get_weather_text(city: str) -> str | None:
    resp = requests.get(
        "http://api.openweathermap.org/data/2.5/weather",
        params={"q": city, "appid": WEATHER_API_KEY, "units": "metric", "lang": "tr"},
        timeout=10,
    )
    if resp.status_code != 200:
        logger.error("Hava durumu alınamadı (%s): %s", city, resp.status_code)
        return None

    d = resp.json()
    return (
        f"{d['name']} için hava durumu. "
        f"{d['weather'][0]['description'].capitalize()}. "
        f"Sıcaklık {round(d['main']['temp'])} derece, "
        f"hissedilen {round(d['main']['feels_like'])} derece. "
        f"Nem yüzde {d['main']['humidity']}. "
        f"Rüzgar saniyede {d['wind']['speed']:.1f} metre."
    )


def make_voice(text: str) -> str:
    tts = gTTS(text=text, lang="tr", slow=False)
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tts.save(tmp.name)
    return tmp.name


async def main() -> None:
    cities = get_cities()
    bot = Bot(token=BOT_TOKEN)

    async with bot:
        # Giriş mesajı
        await bot.send_message(
            chat_id=CHAT_ID,
            text="☀️ Günaydın! İşte bugünkü hava durumları:",
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
