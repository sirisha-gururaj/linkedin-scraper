# src/main_selenium.py
import os
import time
import random
import csv
import re
import json
import traceback
from urllib.parse import urljoin, quote_plus
from bs4 import BeautifulSoup
from dotenv import load_dotenv

import chromedriver_autoinstaller
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# Securely load environment variables from .env file
load_dotenv()

# Optional AI Integration via Groq
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

chromedriver_autoinstaller.install()

# Absolute path resolution logic
current_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(current_dir) == "src":
    BASE_DIR = os.path.abspath(os.path.join(current_dir, ".."))
else:
    BASE_DIR = current_dir

# --- AI CONFIGURATION ---
USE_AI_PARSER = True  # Set to True to use Groq AI for perfect text extraction
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
# ------------------------

OUTPUT_CSV = os.path.join(BASE_DIR, "data", "output.csv")
DEBUG_DIR = os.path.join(BASE_DIR, "data")
COOKIE_FILE = os.path.join(BASE_DIR, "cookies.json")

DELAY_MIN = 0.6
DELAY_MAX = 1.2
SCROLL_PAUSES = 6
MAX_RECORDS = 200
CSV_FIELDS = ["profile_url", "name", "location", "current_role", "current_company"]

COMMON_LOCATIONS = [
    "Bengaluru", "Bangalore", "Hyderabad", "Pune", "Mumbai", "New Delhi", "Delhi", 
    "Gurugram", "Gurgaon", "Noida", "Chennai", "Kolkata", "Ahmedabad", "Karnataka", 
    "Maharashtra", "Telangana", "India", "United States", "USA", "UK", "United Kingdom", 
    "London", "New York", "San Francisco", "Seattle", "Chicago", "Boston", "Austin", "Texas", "California",
    "Kochi", "Trivandrum", "Chandigarh", "Jaipur", "Indore", "Coimbatore", "Bhubaneswar", "Nagpur", "Lucknow"
]

def polite_sleep():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

def ensure_data_dir(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def clear_output_csv():
    if os.path.exists(OUTPUT_CSV):
        try:
            os.remove(OUTPUT_CSV)
            print(f"[INFO] Cleared previous output at {OUTPUT_CSV}", flush=True)
        except Exception:
            pass

def append_pretty_csv_row(csv_path, row_dict, fieldnames=CSV_FIELDS):
    ensure_data_dir(csv_path)
    write_header = not os.path.exists(csv_path)
    with open(csv_path, "a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction='ignore', quoting=csv.QUOTE_MINIMAL)
        if write_header:
            writer.writeheader()
        out = {fn: (row_dict.get(fn) or "") for fn in fieldnames}
        writer.writerow(out)
    print(f"[SAVED] {out.get('name') or 'n/a'} | {out.get('profile_url')}", flush=True)

def build_search_url(keyword):
    q = quote_plus(keyword)
    return f"https://www.linkedin.com/search/results/people/?keywords={q}&origin=GLOBAL_SEARCH_HEADER"

def start_driver(headless=False):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    
    # AGGRESSIVE MEMORY OPTIMIZATIONS FOR RENDER FREE TIER
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--blink-settings=imagesEnabled=false") # CRITICAL: Don't load heavy images
    
    # ULTIMATE ANTI-BOT & HEADLESS DETECTION BYPASS
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--accept-lang=en-US,en;q=0.9") 
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    
    service = Service()
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """
        })
    except Exception:
        pass
        
    return driver

def load_cookies(driver, default_cookie_path):
    cookie_path = default_cookie_path
    if os.environ.get("RENDER") and os.path.exists("/etc/secrets/cookies.json"):
        cookie_path = "/etc/secrets/cookies.json"

    print(f"[INFO] Loading cookies from: {cookie_path}", flush=True)
    try:
        driver.get("https://www.linkedin.com")
        time.sleep(2)
        if os.path.exists(cookie_path):
            with open(cookie_path, "r") as f:
                cookies = json.load(f)
            count = 0
            for cookie in cookies:
                try:
                    # FIX: Forcefully remove bad formatting from browser extensions so Selenium accepts them
                    if 'domain' in cookie and 'linkedin.com' not in cookie['domain']:
                        continue
                    
                    cookie.pop('sameSite', None)
                    cookie.pop('storeId', None)
                    cookie.pop('hostOnly', None)
                    cookie.pop('session', None)
                    
                    driver.add_cookie(cookie)
                    count += 1
                except Exception as e:
                    pass
            driver.refresh()
            time.sleep(3)
            print(f"[INFO] Successfully injected {count} cookies!", flush=True)
        else:
            print(f"[WARN] No cookie file found at {cookie_path}! Proceeding without login.", flush=True)
    except Exception as e:
        print(f"[ERROR] Failed to load cookies: {e}", flush=True)

def looks_like_login_page(driver):
    title = driver.title.lower() if driver.title else ""
    if "sign in" in title or "login" in title:
        return True
    try:
        if driver.find_elements(By.NAME, "session_key") or driver.find_elements(By.ID, "username"):
            return True
    except Exception:
        pass
    return False

def scroll_page(driver, times=SCROLL_PAUSES):
    for i in range(times):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.8 + i * 0.2)

# --- AI PARSING ENGINE (USING GROQ) ---
def parse_with_ai(raw_text):
    if not GROQ_AVAILABLE or not GROQ_API_KEY:
        return None
    
    try:
        client = Groq(api_key=GROQ_API_KEY)
        prompt = f"""
        Analyze the messy LinkedIn profile text below and extract the person's details.
        Return ONLY a valid JSON object with EXACTLY these four keys: "name", "current_role", "current_company", "location".
        If a field cannot be safely determined, output "n/a" for that field.

        CRITICAL Formatting Rules:
        1. "name": Clean full name ONLY. No prefixes, titles, or suffixes.
        2. "current_role": ONLY the core job title. NEVER include the company name, department, or locations here. Remove anything after a hyphen (-), pipe (|), or "at".
        3. "current_company": ONLY the primary company name. Strip out "Inc", "LLC", "Pvt", "Ltd", or any city names attached to it.
        4. "location": ONLY the primary city name (e.g., "Bengaluru", "San Francisco"). Strip out all states, countries, or regions.
        
        Raw Text:
        {raw_text}
        """
        
        response = client.chat.completions.create(
            model="llama3-8b-8192", 
            messages=[
                {"role": "system", "content": "You are a strict data extraction assistant. You output ONLY valid JSON format."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content.strip()
        data = json.loads(content)
        return data
    except Exception as e:
        print(f"[WARN] Groq AI Parsing failed: {e}", flush=True)
        return None
# --------------------------------------

def _clean_text(s):
    if not s: return ""
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'\b(is a mutual connection|mutual connection|followers|follower|Connect|Message|Follow)\b', ' ', s, flags=re.I)
    return re.sub(r'\s+', ' ', s).strip(' ,;:-•·|')

def extract_name_from_text(s):
    if not s: return ""
    s = _clean_text(s)
    s = re.sub(r'[\u2022•·]', '', s) 
    if "\n" in s:
        s = s.split("\n", 1)[0].strip()
    s = re.split(r'\||\(|\-|\,\s*(Current|Past|at\s)', s, flags=re.I)[0].strip()
    m = re.search(r'\b[A-Za-z][\w\.\-]*(?:\s+[A-Za-z][\w\.\-]*){0,3}\b', s)
    if m:
        return m.group(0).strip()
    return " ".join(s.split()[:2])

def extract_current_from_text(text):
    if not text: return "", ""
    text = re.sub(r'\s+', ' ', text) 
    
    role, company = "", ""
    m = re.search(r'Current[:\s\-]*\s*(.+?)\s+at\s+(.+)', text, flags=re.I)
    if m:
        role, company = m.group(1), m.group(2)
    else:
        m2 = re.search(r'(.{1,80}?)\s+at\s+([A-Z0-9][\w &\.-]{1,150})', text)
        if m2:
            role, company = m2.group(1), m2.group(2)
        elif '|' in text:
            role = text.split('|')[0]
        elif ' - ' in text:
            role = text.split(' - ')[0]
            
    if company:
        company = re.split(r'\s{2,}|,|and\b|\band\b|•|·|\|', company, flags=re.I)[0]
        
    return _clean_text(role), _clean_text(company)

def clean_role_name(role):
    if not role: return ""
    role = re.sub(r'\s+', ' ', role).strip()
    role = re.split(r'\s*[|•·,]\s*|\s+at\s+|\s+[-–—]\s+', role, flags=re.I)[0]
    return role.strip(' ,;-')

def separate_company_location(company_str, loc_str):
    if not company_str:
        return "", loc_str
    
    company_str = re.sub(r'\s+', ' ', company_str).strip()
    loc_str = re.sub(r'\s+', ' ', loc_str).strip() if loc_str else ""
    
    if loc_str and loc_str.lower() != "n/a":
        city = loc_str.split(',')[0].strip()
        pattern = r'\s+' + re.escape(city) + r'\s*$'
        company_str = re.sub(pattern, '', company_str, flags=re.I)

    sorted_locs = sorted(COMMON_LOCATIONS, key=len, reverse=True)
    for loc in sorted_locs:
        pattern = r'\s+(' + re.escape(loc) + r')\s*$'
        m = re.search(pattern, company_str, flags=re.I)
        if m:
            extracted_loc = m.group(1)
            company_str = company_str[:m.start()].strip(' ,;-|•·')
            if not loc_str or loc_str == "n/a":
                loc_str = extracted_loc
            break
            
    return company_str, loc_str

def clean_company_name(company):
    if not company: return ""
    company = re.sub(r'\s+', ' ', company).strip()
    
    sorted_locs = sorted(COMMON_LOCATIONS, key=len, reverse=True)
    pattern = r'\s+(' + '|'.join(re.escape(c) for c in sorted_locs) + r')\s*$'
    
    while True:
        new_company = re.sub(pattern, '', company, flags=re.I).strip(' ,;-|•·')
        if new_company == company or len(new_company) < 3 or new_company.lower().endswith(' of'):
            break
        company = new_company
        
    return company

def parse_search_results(html):
    soup = BeautifulSoup(html, "lxml")
    
    for hidden in soup.select(".visually-hidden, .visually-hidden-text, .a11y-text"):
        hidden.decompose()

    records = []
    selectors = [
        "li.reusable-search__result-container", 
        "div.entity-result__item", 
        "div.search-result__wrapper",
        "div.search-result",
        "li.search-result__occluded-item",
        "div.result-card",
        "div[data-chameleon-result-urn]",
        "ul.search-results__list > li"
    ]

    containers = []
    for sel in selectors:
        found = soup.select(sel)
        if found:
            containers.extend(found)

    if not containers:
        seen_ids = set()
        for a in soup.find_all("a", href=True):
            if "/in/" in a["href"].split("?")[0]:
                parent = a
                for _ in range(6):
                    if parent.parent and parent.parent.name not in ["ul", "body", "html", "main"]:
                        parent = parent.parent
                    else:
                        break
                if parent and id(parent) not in seen_ids:
                    containers.append(parent)
                    seen_ids.add(id(parent))

    for raw_c in containers:
        try:
            c = BeautifulSoup(str(raw_c), "html.parser")
            text_block = c.get_text(" | ", strip=True) or ""
            text_block = re.sub(r'\s+', ' ', text_block)
            lines = [ln.strip() for ln in re.split(r'\||\n|\r', text_block) if ln.strip()]

            # 1. STRICT PROFILE URL NORMALIZATION
            link_tag = c.select_one("span.entity-result__title-text a.app-aware-link") or c.select_one("a[href*='/in/']")
            profile_url = ""
            if link_tag:
                raw_href = link_tag.get("href", "").split("?")[0]
                if raw_href.startswith("/"):
                    raw_href = urljoin("https://www.linkedin.com", raw_href)
                
                match = re.search(r'(https://(?:www\.)?linkedin\.com/in/[^/]+)', raw_href)
                if match:
                    profile_url = match.group(1)
                else:
                    profile_url = raw_href

            # --- AI PARSING ENGINE ---
            if USE_AI_PARSER and GROQ_AVAILABLE and GROQ_API_KEY:
                ai_extracted = parse_with_ai(text_block)
                if ai_extracted:
                    loc = ai_extracted.get("location", "n/a")
                    if loc and loc.lower() != "n/a":
                        loc = loc.split(",")[0].strip()
                        
                    role = ai_extracted.get("current_role", "n/a")
                    comp = ai_extracted.get("current_company", "n/a")
                    
                    role = str(role).strip() if role else "n/a"
                    comp = str(comp).strip() if comp else "n/a"

                    records.append({
                        "profile_url": profile_url or "n/a",
                        "name": str(ai_extracted.get("name", "n/a")).strip(),
                        "location": loc or "n/a",
                        "current_role": role,
                        "current_company": comp
                    })
                    continue 
            # -------------------------

            # --- MANUAL REGEX FALLBACK ---
            name = ""
            name_span = c.select_one(".entity-result__title-text span[aria-hidden='true']")
            if name_span:
                name = name_span.get_text(" ", strip=True)
            elif link_tag:
                name = link_tag.get_text(" ", strip=True)
            elif lines:
                name = lines[0]
            
            name = extract_name_from_text(name)
            
            if not name and profile_url:
                parts = profile_url.split("/in/")
                if len(parts) > 1:
                    raw_parts = parts[1].strip("/").split("?")[0].split("-")
                    clean_parts = [p for p in raw_parts if not re.match(r'^[0-9a-fA-F]{5,}$', p)]
                    name = " ".join(clean_parts[:2]).title()

            location = ""
            loc_el = c.select_one(".entity-result__secondary-subtitle") or c.select_one(".search-result__info .subline-level-2") or c.select_one(".location")
            if loc_el:
                loc_text = loc_el.get_text(" | ", strip=True) 
                loc_text = re.sub(r'\s+', ' ', loc_text)
                if any(sep in loc_text for sep in ["•", "·", "|"]):
                    parts = re.split(r'•|·|\|', loc_text)
                    location = parts[-1].strip()
                else:
                    location = loc_text
                    
            location = _clean_text(location)

            if not location and lines:
                for ln in lines[:6]:
                    if "," in ln and len(ln) < 80 and not any(kw in ln.lower() for kw in ["current", "past", "follower", "mutual"]):
                        location = _clean_text(ln)
                        break
                
                if not location:
                    for i, ln in enumerate(lines[:5]):
                        if " at " in ln or "Current:" in ln:
                            if i + 1 < len(lines):
                                loc_candidate = lines[i+1]
                                if len(loc_candidate) < 40 and not any(kw in loc_candidate.lower() for kw in ["current", "past", "follower", "mutual"]):
                                    location = _clean_text(loc_candidate)
                                    break

            current_role, current_company = "", ""
            for ln in lines[:6]:
                r, comp = extract_current_from_text(ln)
                if r or comp:
                    current_role, current_company = r, comp
                    break
            
            if not current_role and not current_company:
                prim = c.select_one("div.entity-result__primary-subtitle") or c.select_one("p.subline-level-1")
                prim_text = prim.get_text(" | ", strip=True) if prim else ""
                r, comp = extract_current_from_text(prim_text.split(" | ")[0] if prim_text else "")
                if r or comp:
                    current_role, current_company = r, comp

            current_company, location = separate_company_location(current_company, location)
            
            current_role = clean_role_name(current_role)
            current_company = clean_company_name(current_company)
            
            if location and location.lower() != "n/a":
                location = location.split(",")[0].strip()
            location = re.sub(r'[\u2022•·]', '', location).strip(' ,;-|')

            rec = {
                "profile_url": profile_url or "n/a",
                "name": name or "n/a",
                "location": location or "n/a",
                "current_role": current_role or "n/a",
                "current_company": current_company or "n/a"
            }

            if rec["name"] == "n/a" and rec["profile_url"] == "n/a":
                continue

            records.append(rec)
        except Exception as e:
            continue

    return records

def scrape_keyword(keyword, headless=False, limit_records=MAX_RECORDS):
    driver = None
    try:
        clear_output_csv()
        print("[INFO] Starting Chrome Driver...", flush=True)
        driver = start_driver(headless=headless)

        load_cookies(driver, COOKIE_FILE)

        search_url_base = build_search_url(keyword)
        
        seen = set()
        cleaned = []
        page = 1
        
        while len(cleaned) < limit_records and page <= 20:
            search_url = search_url_base
            if page > 1:
                search_url += f"&page={page}"
                
            print(f"\n[DEBUG] Navigating to: {search_url} (Page {page})", flush=True)
            driver.get("data:,")
            time.sleep(1.0)
            driver.get(search_url)
            time.sleep(4.0)

            if looks_like_login_page(driver):
                print("[ERROR] 🛑 LinkedIn blocked access! Your cookies are expired or invalid.", flush=True)
                err_path = os.path.join(DEBUG_DIR, "debug_login_error.html")
                with open(err_path, "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                print(f"[INFO] Saved error page to: {err_path}", flush=True)
                break

            print(f"[INFO] Waiting for results to load on page {page}...", flush=True)
            try:
                # Increased timeout to 20 seconds for slower Render cloud environments
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/in/'], .reusable-search__result-container, .entity-result__item"))
                )
            except TimeoutException:
                print(f"[WARN] Search results timed out on page {page}. Proceeding to parse whatever is on the screen.", flush=True)

            print(f"[INFO] Scrolling page {page} to load dynamic content...", flush=True)
            scroll_page(driver, times=SCROLL_PAUSES)

            html = driver.page_source
            records = parse_search_results(html)
            print(f"[INFO] Successfully parsed {len(records)} raw records from HTML on page {page}.", flush=True)

            if len(records) == 0:
                if page == 1:
                    err_path = os.path.join(DEBUG_DIR, "debug_no_results.html")
                    with open(err_path, "w", encoding="utf-8") as f:
                        f.write(driver.page_source)
                    print(f"[WARN] ⚠️ Found 0 results. LinkedIn may have altered the layout for your account. Saved HTML snapshot to: {err_path}", flush=True)
                else:
                    print(f"[INFO] No more results found at page {page}. Reached the end.", flush=True)
                break

            new_adds_this_page = 0
            for r in records:
                key = r.get("profile_url")
                if not key or key in seen or key == "n/a":
                    continue
                seen.add(key)
                cleaned.append(r)
                new_adds_this_page += 1
                
                if len(cleaned) >= limit_records:
                    break

            if new_adds_this_page == 0:
                print(f"[WARN] ⚠️ No NEW unique profiles found on page {page}. Stopping pagination to prevent loops.", flush=True)
                break
            
            page += 1
            polite_sleep() 

        print(f"\n[INFO] Saving {len(cleaned)} unique records to CSV...", flush=True)
        for rec in cleaned:
            append_pretty_csv_row(OUTPUT_CSV, rec, fieldnames=CSV_FIELDS)

        return cleaned

    finally:
        if driver:
            try:
                driver.quit()
                print("[INFO] Chrome Driver successfully closed.", flush=True)
            except Exception:
                pass