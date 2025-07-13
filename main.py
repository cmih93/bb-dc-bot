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
    """Sends a Discord alert with the found iMac deals."""
    if not DISCORD_WEBHOOK:
        logger.error("DISCORD_WEBHOOK environment variable not set. Cannot send alert.")
        return
    content = "\n\n".join(matches)
    payload = {
        "content": f"🔥 **iMacs Under ${ALERT_THRESHOLD:.2f} Found!**\n\n{content}\n\nCheck them out: {URL}"
    }
    try:
        resp = requests.post(DISCORD_WEBHOOK, json=payload, timeout=TIMEOUT)
        resp.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        logger.info("Discord alert sent successfully.")
    except requests.RequestException as e:
        logger.error(f"Failed to send Discord alert: {e}")

def check_bestbuy():
    """
    Initializes a Chrome driver, navigates to the Best Buy iMac page,
    scrapes product titles and prices, and sends a Discord alert for
    iMacs found below the ALERT_THRESHOLD.
    """
    opts = uc.ChromeOptions()
    opts.headless = True # Run Chrome in headless mode (without a UI)
    opts.add_argument("--no-sandbox") # Required for running in some environments
    opts.add_argument("--disable-dev-shm-usage") # Overcomes limited resource problems
    opts.add_argument("--disable-gpu") # Helpful for headless in CI/some environments
    # Use a common user-agent to mimic a regular browser
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
    
    driver = None # Initialize driver to None for proper cleanup in finally block
    matches = []

    try:
        logger.info("Initializing Chrome driver...")
        driver = uc.Chrome(options=opts)
        logger.info("Chrome driver initialized. Loading page...")
        driver.get(URL)
        logger.info("Page loaded. Waiting for product items to be present...")

        # Wait for the main product list to load.
        # Use a robust wait condition for elements that contain product information.
        WebDriverWait(driver, TIMEOUT).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "sku-item"))
        )
        logger.info("Product items found on the page.")

        # Save page source for debugging purposes if needed
        # This can help verify the HTML structure that the scraper is seeing
        with open("page_source_after_load.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        logger.info("Page source saved to page_source_after_load.html for debugging.")

        # Find all product items using the common 'sku-item' class
        items = driver.find_elements(By.CLASS_NAME, "sku-item")
        if not items:
            logger.warning("No 'sku-item' elements found on the page. Check selector or page structure.")
            return # Exit if no items are found

        logger.info(f"Processing {len(items)} product items.")

        for i, item in enumerate(items, 1):
            try:
                # Extract product title
                # Look for 'sku-header' within the item, which usually contains the title link.
                title_elem = item.find_element(By.CLASS_NAME, "sku-header")
                title = title_elem.text.strip() # .strip() to remove leading/trailing whitespace
                logger.info(f"Item {i} - Title: '{title}'")

                # Extract product price
                # Best Buy prices are typically within 'priceView-customer-price'
                price_container = item.find_element(By.CLASS_NAME, "priceView-customer-price")
                
                # Try to get the price text from the direct container or a nested span
                price_text = ""
                try:
                    # Often the actual price number is in a span directly inside or a sibling
                    # Let's try to get all text content from the price_container
                    price_text = price_container.text.strip()
                    if not price_text: # If direct text is empty, try a span inside
                        price_span = price_container.find_element(By.TAG_NAME, "span")
                        price_text = price_span.text.strip()
                except Exception as nested_e:
                    logger.warning(f"Could not find direct text or span within price container for item {i}. Error: {nested_e}")
                    # Fallback to getting text from the parent price_container if nested fails
                    price_text = price_container.text.strip()

                logger.info(f"Item {i} - Raw price text: '{price_text}'")

                # Use a more flexible regex to parse the price
                # This regex handles prices with or without commas, and optional decimal places.
                # Example: $1,199.99, $999, $123.45
                price_match = re.search(r'\$?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', price_text)
                
                if price_match:
                    # Extract the matched price string (e.g., "1,199.99" or "999")
                    price_str = price_match.group(1).replace(",", "")
                    price = float(price_str)
                    logger.info(f"Item {i} - Parsed price: ${price:.2f}")

                    if price < ALERT_THRESHOLD:
                        # Construct the match string for Discord
                        matches.append(f"**{title}**\n💵 ${price:.2f}\n[View Product]({URL})") # Added URL for direct link
                        logger.info(f"Match found: {title} - ${price:.2f} (Below threshold)")
                else:
                    logger.warning(f"Item {i} - Could not parse numerical price from text: '{price_text}'")

            except Exception as e:
                logger.error(f"Error processing item {i} (Title: '{title if 'title' in locals() else 'N/A'}'): {e}")
                # Continue to the next item even if one fails
                continue
    except Exception as e:
        logger.error(f"An unexpected error occurred during scraping: {e}")
    finally:
        if driver:
            logger.info("Closing Chrome driver.")
            driver.quit()
        else:
            logger.warning("Driver was not initialized, nothing to quit.")

    if matches:
        logger.info(f"Found {len(matches)} iMac(s) under ${ALERT_THRESHOLD:.2f}. Sending Discord alert.")
        send_discord_alert(matches)
    else:
        logger.info(f"No iMacs found under ${ALERT_THRESHOLD:.2f}.")

if __name__ == "__main__":
    check_bestbuy()
