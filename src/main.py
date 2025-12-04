from fetcher import fetch
from parser import parse_public_profile
from util import save_csv
from bs4 import BeautifulSoup
import urllib.parse

CSV_PATH = "data/output.csv"

def build_people_url(company_name):
    # LinkedIn PUBLIC people search for a company
    q = urllib.parse.quote(company_name)
    return f"https://www.linkedin.com/search/results/people/?keywords={q}&origin=GLOBAL_SEARCH_HEADER"

def extract_public_profile_links(html):
    soup = BeautifulSoup(html, "lxml")
    links = []

    for a in soup.select("a.app-aware-link"):
        href = a.get("href")
        if href and "/in/" in href:
            full_url = href.split("?")[0]
            links.append(full_url)

    return list(set(links))  # unique profiles

def main():
    company = input("Enter company name: ")

    print("\n[STEP 1] Searching public people for:", company)
    search_url = build_people_url(company)
    search_html = fetch(search_url)

    print("[STEP 2] Extracting public profile URLs...")
    profile_urls = extract_public_profile_links(search_html)
    print(f"[FOUND] {len(profile_urls)} public profiles")

    print("\n[STEP 3] Scraping each public profile...\n")
    for url in profile_urls:
        try:
            html = fetch(url)
            rec = parse_public_profile(html, url)
            print(rec)
            save_csv(CSV_PATH, rec)
        except Exception as e:
            print("[ERROR] Could not scrape:", url, e)

if __name__ == "__main__":
    main()
