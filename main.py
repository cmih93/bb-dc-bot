import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import time
import requests
import os

URL = "https://www.bestbuy.com/site/apple-imacs-minis-mac-pros/imac/pcmcat378600050012.c?id=pcmcat378600050012&sp=Price-Low-To-High"
ALERT_THRESHOLD = 1100.00
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

def send_discord_alert(matches):
    content = "\n\n".join(matches)
    payload = {
        "content": f"🔥 **Open‑Box iMacs Under $500 Found!**\n\n{content}"
    }
    resp = requests.post(DISCORD_WEBHOOK, json=payload)
    resp.raise_for_status()
    print("✅ Discord alert sent.")

def check_bestbuy():
    opts = uc.ChromeOptions()
    opts.headless = True
    opts.add_argument("--no‑sandbox")
    opts.add_argument("--disable‑dev‑shm‑usage")
    driver = uc.Chrome(options=opts)

    matches = []
    try:
        driver.get(URL)
        time.sleep(5)
        items = driver.find_elements(By.CLASS_NAME, "sku-item")
        for item in items:
            try:
                title = item.find_element(By.CLASS_NAME, "sku-header").text
                open_box_marker = item.find_element(By.XPATH, ".//*[contains(text(),'Open-Box')]")
                price_text = item.find_element(By.CLASS_NAME, "priceView-customer-price").text
                price = float(price_text.replace("$","").replace(",",""))
                if price < ALERT_THRESHOLD:
                    matches.append(f"**{title}**\n💵 ${price}\n🛒 {open_box_marker.text.strip()}")
            except Exception:
                continue
    finally:
        driver.quit()

    if matches:
        send_discord_alert(matches)
    else:
        print("❌ No deals under $500 found.")

if __name__ == "__main__":
    check_bestbuy()
