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
ALERT_THRESHOLD = 1100.00  # Set to 1100 for testing
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

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
        resp = requests.post(DISCORD_WEBHOOK, json=payload, timeout=30)
        resp.raise_for_status()
        logger.info("Discord alert sent successfully.")
    except requests.RequestException as e:
        logger.error(f"Failed to send Discord alert: {e}")

def setup_driver():
    """Sets up and returns a Chrome driver with anti-detection options."""
    opts = uc.ChromeOptions()
    opts.headless = True
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-plugins")
    opts.add_argument("--disable-images")  # Faster loading
    opts.add_argument("--disable-javascript")  # Try without JS first
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Add prefs to disable images and CSS for faster loading
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2
    }
    opts.add_experimental_option("prefs", prefs)
    
    return uc.Chrome(options=opts)

def load_page_with_scroll(driver, url):
    """Loads the page and scrolls to ensure all content is loaded."""
    logger.info("Loading page...")
    driver.get(url)
    
    # Wait for initial load and check for anti-bot measures
    time.sleep(15)  # Increased wait time
    logger.info("Initial page load complete, starting scroll...")
    
    # Check if we're being blocked
    page_title = driver.title.lower()
    if "blocked" in page_title or "access denied" in page_title or "robot" in page_title:
        logger.warning(f"Possible blocking detected. Page title: {page_title}")
    
    # Save page source for debugging and log key info
    page_source = driver.page_source
    with open("page_debug.html", "w", encoding="utf-8") as f:
        f.write(page_source)
    
    # Log key page info to console
    logger.info(f"Page title: {driver.title}")
    logger.info(f"Page URL: {driver.current_url}")
    logger.info(f"Page source length: {len(page_source)} characters")
    
    # Check for common elements/text
    if "imac" in page_source.lower():
        logger.info("✓ Found 'imac' text on page")
    if "price" in page_source.lower():
        logger.info("✓ Found 'price' text on page")
    if "blocked" in page_source.lower() or "captcha" in page_source.lower():
        logger.warning("⚠️ Possible blocking/captcha detected")
    
    logger.info("Page source saved to page_debug.html for debugging")
    
    # Scroll down in chunks to load dynamic content
    last_height = driver.execute_script("return document.body.scrollHeight")
    
    for i in range(8):  # Increased scroll attempts
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(4)  # Longer wait between scrolls
        
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            logger.info(f"Page fully loaded after {i+1} scrolls")
            break
        last_height = new_height
    
    # Scroll back to top to ensure all elements are in view
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(3)

def extract_price(price_text):
    """Extracts numeric price from text."""
    if not price_text:
        return None
    
    # Look for price patterns like $1,299.99 or 1299.99
    price_match = re.search(r'\$?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', price_text)
    if price_match:
        price_str = price_match.group(1).replace(",", "")
        try:
            return float(price_str)
        except ValueError:
            return None
    return None

def get_product_info(item):
    """Extracts title and price from a product item."""
    title = "Unknown Product"
    price = None
    
    # Try multiple title selectors
    title_selectors = [
        "h4.sku-header a",
        ".sku-title",
        "[data-testid='product-title']",
        "h3 a",
        "h4 a", 
        "a[href*='/site/']",
        ".product-title",
        "[class*='title'] a",
        "[class*='header'] a"
    ]
    
    for selector in title_selectors:
        try:
            title_elem = item.find_element(By.CSS_SELECTOR, selector)
            title = title_elem.text.strip()
            if title and len(title) > 3:  # Valid title found
                break
        except:
            continue
    
    # If still no title, try getting any link text
    if title == "Unknown Product":
        try:
            links = item.find_elements(By.CSS_SELECTOR, "a")
            for link in links:
                link_text = link.text.strip()
                if link_text and len(link_text) > 10 and "imac" in link_text.lower():
                    title = link_text
                    break
        except:
            pass
    
    # Try multiple price selectors with more aggressive searching
    price_selectors = [
        ".sr-only",
        ".visually-hidden", 
        ".priceView-customer-price",
        ".pricing-price__value",
        "[data-testid='customer-price']",
        ".price",
        "[class*='price']",
        "[aria-label*='current price']",
        "span[class*='price']"
    ]
    
    for selector in price_selectors:
        try:
            price_elements = item.find_elements(By.CSS_SELECTOR, selector)
            for elem in price_elements:
                elem_text = elem.text.strip()
                
                # Check if this element contains price info
                if any(keyword in elem_text.lower() for keyword in ['current price', 'price']

def check_bestbuy():
    """Main function to check Best Buy for iMac deals."""
    driver = None
    matches = []
    
    try:
        driver = setup_driver()
        load_page_with_scroll(driver, URL)
        
        # Wait for products to load - try multiple approaches
        selectors_to_try = [
            ".sku-item",
            "[data-testid='product-card']", 
            ".list-item",
            ".product-item",
            ".sr-product-item",
            ".product",
            "[class*='product']",
            "[class*='sku']"
        ]
        
        products_found = False
        for selector in selectors_to_try:
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                products_found = True
                logger.info(f"Products found with selector: {selector}")
                break
            except:
                logger.debug(f"No products found with selector: {selector}")
                continue
        
        if not products_found:
            logger.error("No products found with any selector")
            logger.info("Checking page content...")
            
            # Check what's actually on the page
            page_text = driver.page_source.lower()
            if "imac" in page_text:
                logger.info("iMac text found on page - selector issue")
            if "price" in page_text:
                logger.info("Price text found on page")
            if "out of stock" in page_text:
                logger.info("Out of stock text found")
            if "no results" in page_text:
                logger.info("No results text found")
            
            return
        
        # Find all product items with expanded selectors
        product_selectors = [
            ".sku-item", 
            "[data-testid='product-card']", 
            ".list-item",
            ".product-item",
            ".sr-product-item", 
            ".product",
            "[class*='product']",
            "[class*='sku']",
            "article",
            "[role='article']"
        ]
        items = []
        
        for selector in product_selectors:
            try:
                items = driver.find_elements(By.CSS_SELECTOR, selector)
                if items:
                    logger.info(f"Found {len(items)} products using selector: {selector}")
                    break
            except:
                continue
        
        if not items:
            logger.error("No product items found with any selector")
            return
        
        logger.info(f"Processing {len(items)} products...")
        
        for i, item in enumerate(items, 1):
            try:
                title, price = get_product_info(item)
                
                # Log what we found for debugging
                logger.debug(f"Item {i}: Title='{title}', Price={price}")
                
                if price and price < ALERT_THRESHOLD:
                    # Check if it's actually an iMac
                    if any(keyword in title.lower() for keyword in ['imac', 'mac']):
                        matches.append(f"**{title}**\n💵 ${price:.2f}")
                        logger.info(f"🎯 Match found: {title} - ${price:.2f}")
                    else:
                        logger.info(f"Under threshold but not iMac: {title} - ${price:.2f}")
                elif price:
                    if 'imac' in title.lower():
                        logger.info(f"iMac above threshold: {title} - ${price:.2f}")
                    else:
                        logger.debug(f"Product above threshold: {title} - ${price:.2f}")
                else:
                    if 'imac' in title.lower():
                        logger.warning(f"iMac found but no price: {title}")
                    else:
                        logger.debug(f"No price found for: {title}")
                    
            except Exception as e:
                logger.error(f"Error processing item {i}: {e}")
                continue
        
        if matches:
            logger.info(f"Found {len(matches)} iMac(s) under ${ALERT_THRESHOLD:.2f}")
            send_discord_alert(matches)
        else:
            logger.info(f"No iMacs found under ${ALERT_THRESHOLD:.2f}")
            
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    check_bestbuy()]):
                    price = extract_price(elem_text)
                    if price:
                        break
                
                # Also check aria-label for price
                aria_label = elem.get_attribute('aria-label') or ''
                if 'price' in aria_label.lower():
                    price = extract_price(aria_label)
                    if price:
                        break
            
            if price:
                break
        except:
            continue
    
    # Try to find open-box pricing if regular price not found
    if not price:
        try:
            # Look for open-box links
            open_box_selectors = [
                "a[href*='open-box']",
                "a[href*='openbox']", 
                "a:contains('Open Box')",
                "a:contains('from 

def check_bestbuy():
    """Main function to check Best Buy for iMac deals."""
    driver = None
    matches = []
    
    try:
        driver = setup_driver()
        load_page_with_scroll(driver, URL)
        
        # Wait for products to load - try multiple approaches
        selectors_to_try = [
            ".sku-item",
            "[data-testid='product-card']", 
            ".list-item",
            ".product-item",
            ".sr-product-item",
            ".product",
            "[class*='product']",
            "[class*='sku']"
        ]
        
        products_found = False
        for selector in selectors_to_try:
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                products_found = True
                logger.info(f"Products found with selector: {selector}")
                break
            except:
                logger.debug(f"No products found with selector: {selector}")
                continue
        
        if not products_found:
            logger.error("No products found with any selector")
            logger.info("Checking page content...")
            
            # Check what's actually on the page
            page_text = driver.page_source.lower()
            if "imac" in page_text:
                logger.info("iMac text found on page - selector issue")
            if "price" in page_text:
                logger.info("Price text found on page")
            if "out of stock" in page_text:
                logger.info("Out of stock text found")
            if "no results" in page_text:
                logger.info("No results text found")
            
            return
        
        # Find all product items with expanded selectors
        product_selectors = [
            ".sku-item", 
            "[data-testid='product-card']", 
            ".list-item",
            ".product-item",
            ".sr-product-item", 
            ".product",
            "[class*='product']",
            "[class*='sku']",
            "article",
            "[role='article']"
        ]
        items = []
        
        for selector in product_selectors:
            try:
                items = driver.find_elements(By.CSS_SELECTOR, selector)
                if items:
                    logger.info(f"Found {len(items)} products using selector: {selector}")
                    break
            except:
                continue
        
        if not items:
            logger.error("No product items found with any selector")
            return
        
        logger.info(f"Processing {len(items)} products...")
        
        for i, item in enumerate(items, 1):
            try:
                title, price = get_product_info(item)
                
                if price and price < ALERT_THRESHOLD:
                    # Check if it's actually an iMac
                    if any(keyword in title.lower() for keyword in ['imac', 'mac']):
                        matches.append(f"**{title}**\n💵 ${price:.2f}")
                        logger.info(f"Match found: {title} - ${price:.2f}")
                    else:
                        logger.debug(f"Product under threshold but not an iMac: {title}")
                elif price:
                    logger.debug(f"Product above threshold: {title} - ${price:.2f}")
                else:
                    logger.debug(f"No price found for: {title}")
                    
            except Exception as e:
                logger.error(f"Error processing item {i}: {e}")
                continue
        
        if matches:
            logger.info(f"Found {len(matches)} iMac(s) under ${ALERT_THRESHOLD:.2f}")
            send_discord_alert(matches)
        else:
            logger.info(f"No iMacs found under ${ALERT_THRESHOLD:.2f}")
            
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    check_bestbuy())"
            ]
            
            for selector in open_box_selectors:
                try:
                    if ":contains(" in selector:
                        # Handle contains differently
                        links = item.find_elements(By.CSS_SELECTOR, "a")
                        for link in links:
                            if "open box" in link.text.lower() or "from $" in link.text.lower():
                                price_match = re.search(r'from \$?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', link.text)
                                if price_match:
                                    price = float(price_match.group(1).replace(",", ""))
                                    break
                    else:
                        open_box_elem = item.find_element(By.CSS_SELECTOR, selector)
                        open_box_text = open_box_elem.text
                        price_match = re.search(r'from \$?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', open_box_text)
                        if price_match:
                            price = float(price_match.group(1).replace(",", ""))
                            break
                except:
                    continue
                
                if price:
                    break
        except:
            pass
    
    return title, price

def check_bestbuy():
    """Main function to check Best Buy for iMac deals."""
    driver = None
    matches = []
    
    try:
        driver = setup_driver()
        load_page_with_scroll(driver, URL)
        
        # Wait for products to load - try multiple approaches
        selectors_to_try = [
            ".sku-item",
            "[data-testid='product-card']", 
            ".list-item",
            ".product-item",
            ".sr-product-item",
            ".product",
            "[class*='product']",
            "[class*='sku']"
        ]
        
        products_found = False
        for selector in selectors_to_try:
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                products_found = True
                logger.info(f"Products found with selector: {selector}")
                break
            except:
                logger.debug(f"No products found with selector: {selector}")
                continue
        
        if not products_found:
            logger.error("No products found with any selector")
            logger.info("Checking page content...")
            
            # Check what's actually on the page
            page_text = driver.page_source.lower()
            if "imac" in page_text:
                logger.info("iMac text found on page - selector issue")
            if "price" in page_text:
                logger.info("Price text found on page")
            if "out of stock" in page_text:
                logger.info("Out of stock text found")
            if "no results" in page_text:
                logger.info("No results text found")
            
            return
        
        # Find all product items with expanded selectors
        product_selectors = [
            ".sku-item", 
            "[data-testid='product-card']", 
            ".list-item",
            ".product-item",
            ".sr-product-item", 
            ".product",
            "[class*='product']",
            "[class*='sku']",
            "article",
            "[role='article']"
        ]
        items = []
        
        for selector in product_selectors:
            try:
                items = driver.find_elements(By.CSS_SELECTOR, selector)
                if items:
                    logger.info(f"Found {len(items)} products using selector: {selector}")
                    break
            except:
                continue
        
        if not items:
            logger.error("No product items found with any selector")
            return
        
        logger.info(f"Processing {len(items)} products...")
        
        for i, item in enumerate(items, 1):
            try:
                title, price = get_product_info(item)
                
                if price and price < ALERT_THRESHOLD:
                    # Check if it's actually an iMac
                    if any(keyword in title.lower() for keyword in ['imac', 'mac']):
                        matches.append(f"**{title}**\n💵 ${price:.2f}")
                        logger.info(f"Match found: {title} - ${price:.2f}")
                    else:
                        logger.debug(f"Product under threshold but not an iMac: {title}")
                elif price:
                    logger.debug(f"Product above threshold: {title} - ${price:.2f}")
                else:
                    logger.debug(f"No price found for: {title}")
                    
            except Exception as e:
                logger.error(f"Error processing item {i}: {e}")
                continue
        
        if matches:
            logger.info(f"Found {len(matches)} iMac(s) under ${ALERT_THRESHOLD:.2f}")
            send_discord_alert(matches)
        else:
            logger.info(f"No iMacs found under ${ALERT_THRESHOLD:.2f}")
            
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    check_bestbuy()
