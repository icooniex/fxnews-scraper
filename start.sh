#!/bin/bash

echo "🔧 Installing Playwright Chromium with dependencies..."
playwright install --with-deps chromium

echo "🚀 Starting Gunicorn..."
exec gunicorn app:app --timeout 300 --workers 1 --bind 0.0.0.0:${PORT:-8000}
