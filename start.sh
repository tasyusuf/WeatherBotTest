#!/bin/bash
# Telegram Hava Durumu Botunu başlatır

cd "$(dirname "$0")"

echo "📦 Bağımlılıklar kuruluyor..."
pip3 install -r requirements.txt -q

echo "🤖 Bot başlatılıyor..."
python3 weather_bot.py
