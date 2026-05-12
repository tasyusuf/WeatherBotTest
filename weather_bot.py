#!/usr/bin/env python3
"""
Telegram Hava Durumu Botu
Her sabah 09:00'da sesli hava durumu mesajı gönderir.
Şehir adı yazarak istediğin zaman hava durumu öğrenebilirsin.
"""

import os
import json
import tempfile
import logging
from datetime import time

import requests
from gtts import gTTS
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.request import HTTPXRequest
from dotenv import load_dotenv
import pytz

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv()

BOT_TOKEN       = os.getenv("BOT_TOKEN")
CHAT_ID         = os.getenv("CHAT_ID")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
DEFAULT_CITY    = os.getenv("DEFAULT_CITY", "Istanbul")
PROXY_URL       = os.getenv("PROXY_URL", "")   # örn: socks5://127.0.0.1:1080
CONFIG_FILE     = os.path.join(os.path.dirname(__file__), "config.json")

TURKEY_TZ = pytz.timezone("Europe/Istanbul")

# ── Yardımcı fonksiyonlar ─────────────────────────────────────────────────────

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"city": DEFAULT_CITY}


def save_config(config: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_weather(city: str) -> tuple[str | None, str | None]:
    """OpenWeatherMap'ten hava durumu alır. (metin, şehir_adı) döner."""
    url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": WEATHER_API_KEY,
        "units": "metric",
        "lang": "tr",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            logger.warning("Hava durumu alınamadı: %s → %s", city, resp.status_code)
            return None, None

        data = resp.json()
        city_name   = data["name"]
        temp        = round(data["main"]["temp"])
        feels_like  = round(data["main"]["feels_like"])
        humidity    = data["main"]["humidity"]
        description = data["weather"][0]["description"].capitalize()
        wind_speed  = data["wind"]["speed"]

        text = (
            f"Günaydın! {city_name} için bugünkü hava durumu. "
            f"{description}. "
            f"Sıcaklık {temp} derece, hissedilen {feels_like} derece. "
            f"Nem yüzde {humidity}. "
            f"Rüzgar hızı saniyede {wind_speed:.1f} metre."
        )
        return text, city_name

    except Exception as e:
        logger.error("Hava durumu hatası: %s", e)
        return None, None


def text_to_voice(text: str) -> str:
    """Metni Türkçe ses dosyasına çevirir, geçici dosya yolunu döner."""
    tts = gTTS(text=text, lang="tr", slow=False)
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tts.save(tmp.name)
    return tmp.name


async def send_weather_voice(bot: Bot, chat_id: str, city: str) -> bool:
    """Hava durumu sesli mesajını gönderir."""
    text, city_name = get_weather(city)
    if not text:
        return False

    voice_path = text_to_voice(text)
    try:
        with open(voice_path, "rb") as f:
            await bot.send_voice(chat_id=chat_id, voice=f)
        logger.info("Sesli mesaj gönderildi → %s", city_name)
        return True
    finally:
        os.unlink(voice_path)


# ── Komutlar ──────────────────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = load_config()
    current_city = config.get("city", DEFAULT_CITY)

    # Chat ID'yi kullanıcıya göster (ilk kurulum için)
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"👋 Merhaba! Ben hava durumu botuyum.\n\n"
        f"🆔 Senin Chat ID'n: <code>{chat_id}</code>\n\n"
        f"🌆 Kayıtlı şehir: <b>{current_city}</b>\n\n"
        f"📋 <b>Komutlar:</b>\n"
        f"/setcity &lt;şehir&gt; — Sabah mesajı için şehir ayarla\n"
        f"/weather — Kayıtlı şehrin hava durumu\n"
        f"/weather &lt;şehir&gt; — Belirli şehrin hava durumu\n\n"
        f"💬 Ya da sadece şehir adını yaz, sana sesli hava durumu göndereyim!",
        parse_mode="HTML",
    )


async def setcity_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Kullanım: /setcity İstanbul")
        return

    city = " ".join(context.args)
    # Şehrin geçerli olup olmadığını kontrol et
    text, city_name = get_weather(city)
    if not text:
        await update.message.reply_text(
            f"❌ '{city}' bulunamadı. Şehir adını kontrol et (İngilizce de deneyebilirsin)."
        )
        return

    config = load_config()
    config["city"] = city
    save_config(config)

    await update.message.reply_text(
        f"✅ Varsayılan şehir <b>{city_name}</b> olarak ayarlandı!\n"
        f"Her sabah 09:00'da buradan hava durumu gelecek. 🌅",
        parse_mode="HTML",
    )


async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        city = " ".join(context.args)
    else:
        city = load_config().get("city", DEFAULT_CITY)

    await update.message.reply_text(f"🌤️ {city} için hava durumu getiriliyor...")
    success = await send_weather_voice(context.bot, update.effective_chat.id, city)
    if not success:
        await update.message.reply_text(
            f"❌ '{city}' bulunamadı. Şehir adını kontrol et."
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kullanıcı herhangi bir şehir adı yazarsa sesli hava durumu gönder."""
    city = update.message.text.strip()
    await update.message.reply_text(f"🌤️ {city} için hava durumu getiriliyor...")
    success = await send_weather_voice(context.bot, update.effective_chat.id, city)
    if not success:
        await update.message.reply_text(
            f"❌ '{city}' bulunamadı. Şehir adını kontrol et (örn: Istanbul, Ankara, Izmir)."
        )


# ── Sabah zamanlanmış görevi ──────────────────────────────────────────────────

async def morning_weather_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Her sabah 09:00'da çalışır."""
    city = load_config().get("city", DEFAULT_CITY)
    logger.info("☀️ Sabah hava durumu gönderiliyor → %s", city)
    success = await send_weather_voice(context.bot, CHAT_ID, city)
    if not success:
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=f"❌ Sabah hava durumu alınamadı ({city}). /setcity komutuyla şehri güncelle.",
        )


# ── Ana fonksiyon ─────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN eksik! .env dosyasını kontrol et.")
    if not WEATHER_API_KEY:
        raise ValueError("WEATHER_API_KEY eksik! .env dosyasını kontrol et.")

    # Proxy desteği (Türkiye'de Telegram erişimi için)
    builder = Application.builder().token(BOT_TOKEN)
    if PROXY_URL:
        logger.info("🔌 Proxy kullanılıyor: %s", PROXY_URL)
        request = HTTPXRequest(proxy=PROXY_URL)
        builder = builder.request(request)
    app = builder.build()

    # Komut handler'ları
    app.add_handler(CommandHandler("start",   start_command))
    app.add_handler(CommandHandler("setcity", setcity_command))
    app.add_handler(CommandHandler("weather", weather_command))

    # Metin mesajları → şehir adı olarak işle
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Sabah 09:00 Türkiye saati
    app.job_queue.run_daily(
        morning_weather_job,
        time=time(hour=9, minute=0, second=0, tzinfo=TURKEY_TZ),
        name="morning_weather",
    )

    logger.info("🤖 Bot başlatıldı! Her sabah 09:00'da hava durumu gönderilecek.")
    logger.info("📍 Varsayılan şehir: %s", load_config().get("city", DEFAULT_CITY))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
