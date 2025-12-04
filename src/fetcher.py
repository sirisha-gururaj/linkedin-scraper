import requests
import time
import random

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; public-linkedin-scraper/1.0)"
}

def polite_delay():
    time.sleep(random.uniform(1.5, 3.0))

def fetch(url):
    print(f"[INFO] Fetching: {url}")
    resp = requests.get(url, headers=HEADERS)
    polite_delay()
    resp.raise_for_status()
    return resp.text
