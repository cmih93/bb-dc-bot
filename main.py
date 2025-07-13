import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import requests
import os
import re

URL = "https://www.bestbuy.com/site/apple-imacs-minis-mac-pros/imac/pcmcat378600050012.c?id=pcmcat378600050012&sp=Price-Low-To-High"
ALERT_THRESHOLD = 1200.00
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
TIMEOUT = 20  # Timeout for webhook requests

def send_discord_alert(matches):
    if not DISCORD_WEBHOOK:
        print("❌ DISCORD_WEBHOOK environment variable not set.")
        return
    content = "\n\n".join(matches)
    payload = {
        "content": f"🔥 **iMacs Under ${ALERT_THRESHOLD} Found!**\n\n{content}"
    }
    try:
        resp = requests.post(DISCORD_WEBHOOK, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        print("✅ Discord alert sent.")
    except requests.RequestException as e:
        print(f"❌ Failed to send Discord alert: {e}")

def test_discord_webhook():
    if not DISCORD_WEBHOOK:
        print("❌ DISCORD_WEBHOOK environment variable not set.")
        return
    payload = {
        "content": "🔔 **Test Alert**: This is a test message to verify the Discord webhook is working."
    }
    try:
        resp = requests.post(DISCORD_WEBHOOK, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        print("✅ Test Discord webhook sent successfully.")
    except requests.RequestException as e:
        print(f"❌ Failed to send test Discord webhook: {e}")

def check_bestbuy():
    opts = uc.ChromeOptions()
    opts.headless = True
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
    driver = uc.Chrome(options=opts)

    matches = []
    try:
        driver.get(URL)
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "sku-item"))
        )
        items = driver.find_elements(By.CLASS_NAME, "sku-item")
        print(f"Found {len(items)} items.")

        for item in items:
            try:
                title = item.find_element(By.CLASS_NAME, "sku-header").text
                price_elem = item.find_element(By.CLASS_NAME, "priceView-customer-price")
                price_text = price_elem.find_element(By.TAG_NAME, "span").text
                price_match = re.search(r"\d{1,3}(,\d{3})*\.\d{2}", price_text)
                if price_match:
                    price = float(price_match.group().replace(",", ""))
                    if price < ALERT_THRESHOLD:
                        matches.append(f"**{title}**\n💵 ${price:.2f}")
                        print(f"Match found: {title} - ${price:.2f}")
                else:
                    print(f"Could not parse price for {title}: {price_text}")
            except Exception as e:
                print(f"Error processing item: {e}")
                continue
    except Exception as e:
        print(f"Error loading page or finding items: {e}")
    finally:
        driver.quit()

    if matches:
        send_discord_alert(matches)
    else:
        print(f"❌ No iMacs under ${ALERT_THRESHOLD} found.")

if __name__ == "__main__":
    # Run the test webhook
    test_discord_webhook()
    # Optionally run the BestBuy check
    # check_bestbuy()
