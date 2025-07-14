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
TIMEOUT = 30 # Increased timeout for more robust page loading

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
        
        # Add a small sleep to allow initial page rendering before explicit waits
        logger.info("Waiting for 3 seconds for initial page render...")
        time.sleep(3) 

        logger.info("Page loaded. Waiting for product items to be present in DOM...")
        # Step 1: Wait for the presence of at least one 'sku-item' element
        # This confirms that the basic structure for product listings has loaded.
        WebDriverWait(driver, TIMEOUT).until(
            EC.presence_of_element_located((By.CLASS_NAME, "sku-item"))
        )
        logger.info("At least one 'sku-item' element is present in the DOM.")

        logger.info("Now waiting for product prices to be visible...")
        # Step 2: Wait for the visibility of at least one 'priceView-customer-price' element
        # This indicates that the product details, including prices, are actually rendered.
        WebDriverWait(driver, TIMEOUT).until(
            EC.visibility_of_element_located((By.CLASS_NAME, "priceView-customer-price"))
        )
        logger.info("At least one price element is visible. Proceeding to find all items.")

        # Save page source for debugging purposes if needed
        with open("page_source_after_load.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        logger.info("Page source saved to page_source_after_load.html for debugging.")

        # Find all product items using the common 'sku-item' class
        items = driver.find_elements(By.CLASS_NAME, "sku-item")
        if not items:
            logger.warning("No 'sku-item' elements found on the page after waiting. Check selector or page structure.")
            return # Exit if no items are found

        logger.info(f"Processing {len(items)} product items.")

        for i, item in enumerate(items, 1):
            title = "N/A" # Initialize title for logging in case of early error
            price = None # Initialize price to None

            try:
                # Extract product title
                title_elem = item.find_element(By.CLASS_NAME, "sku-header")
                title = title_elem.text.strip()
                logger.info(f"Item {i} - Title: '{title}'")

                # --- Attempt to extract regular price ---
                try:
                    price_container = item.find_element(By.CLASS_NAME, "priceView-customer-price")
                    price_text = ""
                    try:
                        price_text = price_container.text.strip()
                        if not price_text:
                            price_span = price_container.find_element(By.TAG_NAME, "span")
                            price_text = price_span.text.strip()
                    except Exception as nested_e:
                        logger.debug(f"Could not find direct text or span within price container for regular price. Error: {nested_e}")
                        price_text = price_container.text.strip() # Fallback to parent text

                    logger.info(f"Item {i} - Raw regular price text: '{price_text}'")
                    price_match = re.search(r'\$?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', price_text)
                    if price_match:
                        price_str = price_match.group(1).replace(",", "")
                        price = float(price_str)
                        logger.info(f"Item {i} - Parsed regular price: ${price:.2f}")
                    else:
                        logger.debug(f"Could not parse numerical regular price from text: '{price_text}'")

                except Exception as e:
                    logger.debug(f"Regular price element (priceView-customer-price) not found for item {i}. Trying open-box price. Error: {e}")

                # --- If regular price not found or parsed, attempt to extract open-box price ---
                if price is None:
                    try:
                        # Look for the 'Open Box' link which contains the price
                        open_box_link = item.find_element(By.XPATH, ".//a[contains(@class, 'buying-option-link') and contains(text(), 'from $')]")
                        open_box_text = open_box_link.text.strip()
                        logger.info(f"Item {i} - Raw open-box price text: '{open_box_text}'")
                        
                        # Regex to extract price from "from $XXX.XX"
                        open_box_price_match = re.search(r'from \$?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', open_box_text)
                        if open_box_price_match:
                            price_str = open_box_price_match.group(1).replace(",", "")
                            price = float(price_str)
                            logger.info(f"Item {i} - Parsed open-box price: ${price:.2f}")
                        else:
                            logger.warning(f"Item {i} - Could not parse numerical open-box price from text: '{open_box_text}'")

                    except Exception as e:
                        logger.debug(f"Open-box price link not found for item {i}. Error: {e}")
                        logger.warning(f"Item {i} - No price (regular or open-box) could be found or parsed.")
                        continue # Skip this item if no price is found

                # --- Check if a valid price was found and if it's below the threshold ---
                if price is not None:
                    if price < ALERT_THRESHOLD:
                        matches.append(f"**{title}**\n💵 ${price:.2f}\n[View Product]({URL})")
                        logger.info(f"Match found: {title} - ${price:.2f} (Below threshold)")
                else:
                    logger.warning(f"Item {i} - Final price for '{title}' is None after all attempts. Skipping.")

            except Exception as e:
                logger.error(f"Error processing item {i} (Title: '{title}'): {e}")
                continue # Continue to the next item even if one fails
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
