import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import requests
import os
import re
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bestbuy_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

URL = "https://www.bestbuy.com/site/apple-imacs-minis-mac-pros/imac/pcmcat378600050012.c?id=pcmcat378600050012&sp=Price-Low-To-High"
ALERT_THRESHOLD = 1200.00
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
TIMEOUT = 20

def send_discord_alert(matches):
    if not DISCORD_WEBHOOK:
        logger.error("DISCORD_WEBHOOK environment variable not set.")
        return
    content = "\n\n".join(matches)
    payload = {
        "content": f"🔥 **iMacs Under ${ALERT_THRESHOLD} Found!**\n\n{content}"
    }
    try:
        resp = requests.post(DISCORD_WEBHOOK, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        logger.info("Discord alert sent successfully.")
    except requests.RequestException as e:
        logger.error(f"Failed to send Discord alert: {e}")

def check_bestbuy():
    opts = uc.ChromeOptions()
    opts.headless = True
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")  # Helpful for headless in CI
    opts.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
    try:
        driver = uc.Chrome(options=opts)
    except Exception as e:
        logger.error(f"Failed to initialize Chrome driver: {e}")
        return

    matches = []
    try:
        logger.info("Loading page...")
        driver.get(URL)
        logger.info("Page loaded. Waiting for items...")

        # Save page source for debugging
        with open("page_source.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        logger.info("Page source saved to page_source.html")

        # Try CSS selector first, fall back to XPath
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "sku-item"))
            )
            items = driver.find_elements(By.CLASS_NAME, "sku-item")
            logger.info(f"Found {len(items)} items using CSS selector.")
        except Exception as e:
            logger.warning(f"CSS selector failed: {e}. Trying XPath...")
            items = driver.find_elements(By.XPATH, "//div[contains(@class, 'sku-item')]")
            logger.info(f"Found {len(items)} items using XPath.")

        for i, item in enumerate(items, 1):
            try:
                title_elem = item.find_element(By.CLASS_NAME, "sku-header")
                title = title_elem.text
                logger.info(f"Item {i}: {title}")

                price_elem = item.find_element(By.CLASS_NAME, "priceView-customer-price")
                price_text = price_elem.find_element(By.TAG_NAME, "span").text
                logger.info(f"Raw price text: {price_text}")

                price_match = re.search(r"\d{1,3}(,\d{3})*\.\d{2}", price_text)
                if price_match:
                    price = float(price_match.group().replace(",", ""))
                    logger.info(f"Parsed price: ${price:.2f}")
                    if price < ALERT_THRESHOLD:
                        matches.append(f"**{title}**\n💵 ${price:.2f}")
                        logger.info(f"Match found: {title} - ${price:.2f}")
                else:
                    logger.warning(f"Could not parse price for {title}: {price_text}")
            except Exception as e:
                logger.error(f"Error processing item {i}: {e}")
                continue
    except Exception as e:
        logger.error(f"Error loading page or finding items: {e}")
    finally:
        driver.quit()

    if matches:
        send_discord_alert(matches)
    else:
        logger.info(f"No iMacs under ${ALERT_THRESHOLD} found.")

if __name__ == "__main__":
    check_bestbuy()
