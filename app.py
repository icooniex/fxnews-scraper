from flask import Flask, jsonify, send_file
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from playwright.sync_api import sync_playwright
from datetime import datetime
import pytz
import re
import json
import os
import logging

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

URL = "https://www.forexfactory.com/calendar"
TARGET_CURRENCIES = {"USD","EUR","GBP","AUD","NZD"}
FF_TIMEZONE = pytz.timezone("Asia/Bangkok")
TIME_PATTERN = re.compile(r"\b(\d{1,2}:\d{2}\s*(?:am|pm))\b", re.I)
JSON_FILE = 'weekly_ecocar.json'

def scrape_forexfactory():
    """Scrape forex factory calendar for high impact events"""
    events = {}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, slow_mo=20)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                locale="en-US"
            )

            logger.info("🌐 Opening Forex Factory page...")
            page.goto(URL, timeout=60000)
            page.wait_for_timeout(3000)

            current_year = datetime.utcnow().year
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(1000)

            total_height = page.evaluate("document.body.scrollHeight")
            scroll_y = 0

            logger.info("🖱️ Scrolling and collecting data...")

            while scroll_y < total_height:
                page.evaluate(f"window.scrollTo(0, {scroll_y})")
                page.wait_for_timeout(120)

                rows = page.query_selector_all("tr.calendar__row")

                for row in rows:
                    event_id = row.get_attribute("data-event-id")
                    if not event_id or event_id in events:
                        continue

                    # DATE
                    date_text = row.evaluate("""
                        (row) => {
                            let el = row;
                            while (el) {
                                const d = el.querySelector('.calendar__date .date');
                                if (d) return d.innerText;
                                el = el.previousElementSibling;
                            }
                            return null;
                        }
                    """)
                    if not date_text:
                        continue

                    date_text_clean = date_text.replace("\n", " ")

                    try:
                        date = datetime.strptime(
                            f"{date_text_clean} {current_year}",
                            "%a %b %d %Y"
                        )
                    except:
                        continue

                    # TIME
                    time_text = row.evaluate("""
                        (row) => {
                            let el = row;
                            while (el) {
                                const t = el.querySelector('.calendar__cell.calendar__time span');
                                if (t) return t.innerText;
                                el = el.previousElementSibling;
                            }
                            return null;
                        }
                    """)
                    if not time_text:
                        continue

                    m = TIME_PATTERN.search(time_text.lower())
                    if not m:
                        continue

                    time_str = m.group(1)

                    # CURRENCY
                    currency_cell = row.query_selector(".calendar__currency span")
                    if not currency_cell:
                        continue

                    currency = currency_cell.inner_text().strip()
                    if currency not in TARGET_CURRENCIES:
                        continue

                    # IMPACT (HIGH ONLY)
                    impact_span = row.query_selector(
                        '.calendar__impact span[title="High Impact Expected"]'
                    )
                    if not impact_span:
                        continue

                    # EVENT
                    event_cell = row.query_selector(".calendar__event-title")
                    event = event_cell.inner_text().strip() if event_cell else ""

                    # DATETIME → UTC
                    try:
                        dt_local = datetime.strptime(
                            f"{date.strftime('%Y-%m-%d')} {time_str}",
                            "%Y-%m-%d %I:%M%p"
                        )
                    except:
                        continue

                    dt_local = FF_TIMEZONE.localize(dt_local)
                    dt_utc = dt_local.astimezone(pytz.UTC)

                    events[event_id] = {
                        "event_time_utc": dt_utc.isoformat(),
                        "currency": currency,
                        "impact": "HIGH",
                        "event": event
                    }

                scroll_y += 100
                total_height = page.evaluate("document.body.scrollHeight")

            browser.close()

        return list(events.values())
    
    except Exception as e:
        logger.error(f"Error during scraping: {e}")
        return []

def update_json_file():
    """Scrape data and save to JSON file"""
    logger.info("⏰ Starting scheduled scrape...")
    data = scrape_forexfactory()
    
    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"✅ Saved {len(data)} events to {JSON_FILE}")

@app.route('/')
def home():
    """Homepage with API info"""
    return jsonify({
        "message": "Forex Factory News Scraper Service",
        "endpoints": {
            "/": "This info page",
            "/api/news": "Get weekly forex news data (JSON)",
            "/weekly_ecocar.json": "Direct file download",
            "/health": "Health check"
        },
        "schedule": "Updates every Sunday at 00:00 Bangkok time"
    })

@app.route('/api/news')
def get_news():
    """Return JSON data"""
    try:
        if not os.path.exists(JSON_FILE):
            # If file doesn't exist yet, scrape now
            update_json_file()
        
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return jsonify({
            "success": True,
            "count": len(data),
            "data": data,
            "last_updated": datetime.fromtimestamp(
                os.path.getmtime(JSON_FILE)
            ).isoformat() if os.path.exists(JSON_FILE) else None
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/weekly_ecocar.json')
def download_json():
    """Serve the JSON file directly"""
    try:
        if not os.path.exists(JSON_FILE):
            update_json_file()
        
        return send_file(
            JSON_FILE,
            mimetype='application/json',
            as_attachment=False
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "file_exists": os.path.exists(JSON_FILE),
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/scrape-now')
def scrape_now():
    """Manual trigger for scraping (for testing)"""
    try:
        update_json_file()
        return jsonify({
            "success": True,
            "message": "Scraping completed successfully"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# Initialize scheduler
scheduler = BackgroundScheduler()

# Schedule to run every Sunday at 00:00 Bangkok time
scheduler.add_job(
    func=update_json_file,
    trigger=CronTrigger(day_of_week='sun', hour=0, minute=0, timezone=FF_TIMEZONE),
    id='weekly_scrape',
    name='Weekly Forex Factory Scrape',
    replace_existing=True
)

if __name__ == '__main__':
    # Start the scheduler
    scheduler.start()
    logger.info("📅 Scheduler started - will run every Sunday at 00:00 Bangkok time")
    
    # Run once on startup if file doesn't exist
    if not os.path.exists(JSON_FILE):
        logger.info("📦 No existing data file, running initial scrape...")
        update_json_file()
    
    # Get port from environment variable (Railway uses this)
    port = int(os.environ.get('PORT', 5000))
    
    # Start Flask app
    app.run(host='0.0.0.0', port=port, debug=False)
