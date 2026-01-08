from playwright.sync_api import sync_playwright
from datetime import datetime
import pytz
import re
import json

URL = "https://www.forexfactory.com/calendar"

TARGET_CURRENCIES = {"USD","EUR","GBP","AUD","NZD"}
# FF_TIMEZONE = pytz.timezone("US/Eastern")
FF_TIMEZONE = pytz.timezone("Asia/Bangkok")
TIME_PATTERN = re.compile(r"\b(\d{1,2}:\d{2}\s*(?:am|pm))\b", re.I)


def scrape_forexfactory():
    events = {}  # key = data-event-id

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            slow_mo=20
        )
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            locale="en-US"
        )

        print("🌐 Opening page...")
        page.goto(URL, timeout=60000)
        page.wait_for_timeout(3000)

        current_year = datetime.utcnow().year

        # เริ่มบนสุด
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(1000)

        total_height = page.evaluate("document.body.scrollHeight")
        scroll_y = 0

        print("🖱️ Slow scrolling + collecting...")

        while scroll_y < total_height:
            page.evaluate(f"window.scrollTo(0, {scroll_y})")
            page.wait_for_timeout(120)

            rows = page.query_selector_all("tr.calendar__row")

            for row in rows:
                event_id = row.get_attribute("data-event-id")
                if not event_id or event_id in events:
                    continue

                # ------------------
                # DATE (look upward)
                # ------------------
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

                # ------------------
                # TIME (look upward)
                # ------------------
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

                # ------------------
                # CURRENCY
                # ------------------
                currency_cell = row.query_selector(".calendar__currency span")
                if not currency_cell:
                    continue

                currency = currency_cell.inner_text().strip()
                if currency not in TARGET_CURRENCIES:
                    continue

                # ------------------
                # IMPACT (HIGH ONLY)
                # ------------------
                impact_span = row.query_selector(
                    '.calendar__impact span[title="High Impact Expected"]'
                )
                if not impact_span:
                    continue

                # ------------------
                # EVENT
                # ------------------
                event_cell = row.query_selector(".calendar__event-title")
                event = event_cell.inner_text().strip() if event_cell else ""

                # ------------------
                # DATETIME → UTC
                # ------------------
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


if __name__ == "__main__":
    data = scrape_forexfactory()

    print("\n📦 FINAL RESULT:")
    for d in data:
        print(d)
    with open('weekly_ecocar.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Saved {len(data)} events to weekly_ecocar.json")
