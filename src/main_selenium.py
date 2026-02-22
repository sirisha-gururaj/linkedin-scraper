# src/main_selenium.py
"""
LinkedIn public search scraper (Selenium)
- DOES NOT visit individual profile pages (no view notifications)
- Clears data/output.csv at start of each run
- Parses search-results page and extracts: profile_url, name, location, current_role, current_company
- Writes 'n/a' for missing fields
- Uses ', ' (comma + space) as separator and safely quotes fields containing commas/newlines/quotes
- Improved heuristics to extract location reliably from search-result cards
"""
import os
import time
import random
import csv
import re
import traceback
from urllib.parse import urljoin, quote_plus
from bs4 import BeautifulSoup, Doctype

# Selenium imports
import chromedriver_autoinstaller
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

chromedriver_autoinstaller.install()

# CONFIG
OUTPUT_CSV = os.path.join("data", "output.csv")
DEBUG_DIR = "data"
DELAY_MIN = 0.6
DELAY_MAX = 1.2
SCROLL_PAUSES = 6
USER_DATA_DIR = os.path.expanduser("~/.config/Selenium/ChromeProfile") # change if needed
PROFILE_DIR = "Default"
MAX_RECORDS = 200
CSV_FIELDS = ["profile_url", "name", "location", "current_role", "current_company"]

COUNTRY_PREFER = ["India", "United States", "USA", "United Kingdom", "UK", "Bengaluru", "Bangalore", "Karnataka"]

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
            print(f"[INFO] Removed existing {OUTPUT_CSV}")
        except Exception:
            pass

# CSV pretty writer using ", " and safe quoting
def append_pretty_csv_row(csv_path, row_dict, fieldnames=CSV_FIELDS):
    """
    Write a single row to CSV using csv.DictWriter with a fixed header order.
    This ensures the output file always has the same columns and proper quoting.
    """
    ensure_data_dir(csv_path)
    write_header = not os.path.exists(csv_path)
    with open(csv_path, "a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction='ignore', quoting=csv.QUOTE_MINIMAL)
        if write_header:
            writer.writeheader()
        out = {fn: (row_dict.get(fn) or "") for fn in fieldnames}
        writer.writerow(out)
    print("[SAVED]", out.get("profile_url") or out.get("name"))

def build_search_url(keyword):
    q = quote_plus(keyword)
    return f"https://www.linkedin.com/search/results/people/?keywords={q}&origin=GLOBAL_SEARCH_HEADER"

def start_driver(headless=False, use_persistent_profile=True, user_data_dir=None, profile_dir="Default"):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--window-size=1920,1080")

    possible_binary = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if os.path.exists(possible_binary):
        options.binary_location = possible_binary

    if use_persistent_profile and user_data_dir:
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument(f"--profile-directory={profile_dir}")
        print(f"[INFO] Using persistent Chrome profile: user-data-dir={user_data_dir}, profile={profile_dir}")
    else:
        print("[INFO] Using temporary Selenium profile (no persistence).")

    service = Service()
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def looks_like_login_page(driver):
    title = driver.title.lower() if driver.title else ""
    src = driver.page_source.lower()[:3000]
    if "sign in" in title or "sign in" in src:
        return True
    try:
        if driver.find_elements(By.NAME, "session_key"):
            return True
    except Exception:
        pass
    return False

def prompt_manual_login(driver):
    if not looks_like_login_page(driver):
        return True
    print("\n[ACTION REQUIRED] LinkedIn is asking you to sign in in the opened browser window.")
    print("Please sign in manually, then come back to this terminal and press Enter.")
    ensure_data_dir(DEBUG_DIR + "/debug_before_manual_login.html")
    with open(os.path.join(DEBUG_DIR, "debug_before_manual_login.html"), "w", encoding="utf-8") as fh:
        fh.write(driver.page_source)
    try:
        input("Press Enter after you have logged in (or Ctrl+C to abort)...")
    except KeyboardInterrupt:
        return False
    time.sleep(1.5)
    try:
        driver.refresh()
        time.sleep(2.0)
    except Exception:
        pass
    with open(os.path.join(DEBUG_DIR, "debug_after_manual_login.html"), "w", encoding="utf-8") as fh:
        fh.write(driver.page_source)
    return True

def scroll_page(driver, times=SCROLL_PAUSES):
    for i in range(times):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.8 + i * 0.2)

# helpers for cleaning
def _clean_text(s):
    if not s:
        return ""
    s = re.sub(r'[\u2022•]', ' ', s)  # bullets
    s = re.sub(r'\b(is a mutual connection|is a mutual|mutual connection)\b', ' ', s, flags=re.I)
    s = re.sub(r'(?i)\b\d+(st|nd|rd|th)\+?\b', ' ', s)  # 2nd, 3rd
    s = re.sub(r'\b(followers|follower)\b', ' ', s, flags=re.I)
    s = re.sub(r'\b(Connect|Message|Follow|Following)\b', ' ', s, flags=re.I)
    s = re.sub(r'\s+', ' ', s).strip(' ,;:-')
    return s.strip()

def extract_name_from_text(s):
    if not s:
        return ""
    s = _clean_text(s)
    if "\n" in s:
        s = s.split("\n", 1)[0].strip()
    s = re.split(r'\||\(|\-|\,\s*(Current|Past|at\s|Connect|Message)', s, flags=re.I)[0].strip()
    m = re.search(r'\b[A-Z][\w\.\-]*(?:\s+[A-Z][\w\.\-]*){0,3}\b', s)
    if m:
        name = m.group(0).strip()
        if len(name.split()) <= 4:
            return name
    parts = s.split()
    return " ".join(parts[:2]) if parts else ""

def extract_current_from_text(text):
    if not text:
        return "", ""
    text = _clean_text(text)
    m = re.search(r'Current[:\s\-]*\s*(.+?)\s+at\s+(.+)', text, flags=re.I)
    if m:
        role = m.group(1).strip()
        company = m.group(2).strip()
        company = re.split(r'\s{2,}|,|and\b|\band\b|•|followers', company, flags=re.I)[0].strip()
        return _clean_text(role), _clean_text(company)
    m2 = re.search(r'(.{1,80}?)\s+at\s+([A-Z0-9][\w &\.-]{1,150})', text)
    if m2:
        role = m2.group(1).strip()
        company = m2.group(2).strip()
        company = re.split(r'\s{2,}|,|and\b|\band\b|•|followers', company, flags=re.I)[0].strip()
        return _clean_text(role), _clean_text(company)
    if '|' in text:
        first = text.split('|',1)[0].strip()
        return _clean_text(first), ""
    return "", ""


def strip_name_and_titles_from_company(comp, name):
    """Remove obvious person-name fragments and titles from a company string.
    Returns cleaned company or empty string if it looks like a person name.
    """
    if not comp:
        return comp
    s = comp
    # remove surrounding quotes
    s = re.sub(r'^[\"\']|[\"\']$', '', s).strip()
    # remove common titles followed by a name (Dr. John Doe)
    s = re.sub(r'\b(dr|mr|ms|mrs|miss|prof)\.?\s+[A-Z][\w\.\- ]{1,80}', '', s, flags=re.I)
    # remove explicit name tokens that match the extracted name
    if name:
        for token in name.split():
            if len(token) > 2:
                s = re.sub(re.escape(token), '', s, flags=re.I)
    # collapse separators
    s = re.sub(r'[\|\·\•\-\–\—]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip(' ,;:-"\'')

    # company keywords to prefer when extracting company name
    COMPANY_KEYWORDS = [
        'amazon','infosys','tcs','wipro','tcs','tata','capgemini','accenture','google','microsoft','ibm','hcl','tech','infosys','bpm','springboard'
    ]

    low = s.lower()
    for kw in COMPANY_KEYWORDS:
        m = re.search(r'\b' + re.escape(kw) + r'\b', low)
        if m:
            # try to keep the token containing the keyword and its nearby words (up to two following words)
            words = s.split()
            # find index of matched keyword in words (case-insensitive)
            idx = next((i for i,w in enumerate(words) if re.search(r'\b' + re.escape(kw) + r'\b', w, flags=re.I)), None)
            if idx is not None:
                # include keyword and up to 2 following tokens unless they look like person names (single capitalized tokens)
                end = idx + 1
                allowed_suffix = set(['web','services','technologies','solutions','systems','springboard','bpm','labs','group'])
                for j in range(idx+1, min(len(words), idx+4)):
                    w = re.sub(r'[.,]$','', words[j])
                    loww = w.lower()
                    if loww in allowed_suffix or re.search(r'^[A-Z][a-z]+$', w):
                        end = j+1
                        continue
                    break
                candidate = ' '.join(words[:end]) if idx==0 else ' '.join(words[idx:end])
                candidate = candidate.strip(' ,;:-"\'')
                return candidate

    # fallback: remove trailing person-like fragments at end (e.g., 'Amazon Faustin Kabeya' -> 'Amazon')
    parts = s.split()
    def is_person_token(tok):
        return bool(re.match(r'^[A-Z][a-z\-\.]+$', tok)) and len(tok) > 1

    # if last two tokens look like person name tokens, drop them
    if len(parts) >= 2 and is_person_token(parts[-1]) and is_person_token(parts[-2]):
        return ' '.join(parts[:-2]).strip(' ,;:-"\'')

    # if last one token looks like person and the remaining contains company keyword, drop last
    if len(parts) >= 2 and is_person_token(parts[-1]):
        lowrest = ' '.join(parts[:-1]).lower()
        if any(kw in lowrest for kw in COMPANY_KEYWORDS):
            return ' '.join(parts[:-1]).strip(' ,;:-"\'')

    # if still looks like a person's name (2-4 capitalized words) with no company keywords, return empty
    def looks_like_person(s2):
        parts2 = [p for p in s2.split() if p]
        if not parts2:
            return False
        capcount = sum(1 for p in parts2 if re.match(r'^[A-Z]', p))
        if capcount >= 2 and len(parts2) <= 4 and not re.search(r'\b(inc|ltd|llp|pvt|llc|technologies|systems|solutions|services|bpm|springboard|infosys|wipro|tcs|google|microsoft|amazon|accenture|capgemini)\b', s2, flags=re.I):
            return True
        return False

    if looks_like_person(s):
        return ""
    return s

def _save_debug_html(path, page_source):
    """
    Robust debug HTML saver:
    - parse and clean with BeautifulSoup
    - replace empty nonce attributes with nonce="anon"
    - remove duplicate CSP <meta http-equiv="Content-Security-Policy"> tags (keep first)
    - move head-like tags into <head> and other content into <body>
    - ensure <!doctype html> and <html><head><body>
    """
    ensure_data_dir(path)
    raw = page_source or ""

    # quick replace of empty nonce occurrences before parsing
    raw = re.sub(r'\snonce\s*=\s*(?:["\']\s*["\']|\s*)', ' nonce="anon"', raw, flags=re.I)

    soup = BeautifulSoup(raw, "html.parser")

    # remove duplicate CSP meta tags
    csp_metas = soup.find_all("meta", attrs={"http-equiv": lambda v: v and v.lower() == "content-security-policy"})
    if len(csp_metas) > 1:
        for extra in csp_metas[1:]:
            extra.decompose()

    # remove translate attr from html tag (avoid some linter warnings)
    html_tag = soup.find("html")
    if html_tag and html_tag.has_attr("translate"):
        try:
            del html_tag["translate"]
        except Exception:
            pass

    # ensure head/body exist and move top-level head-like tags into head
    if not soup.head:
        head = soup.new_tag("head")
        top_level = list(soup.contents)
        for el in top_level:
            if isinstance(el, Doctype) or getattr(el, "name", None) is None:
                continue
            tagname = el.name.lower() if getattr(el, "name", None) else ""
            if tagname in ("meta", "link", "script", "style", "title"):
                head.append(el.extract())
        if soup.html:
            soup.html.insert(0, head)
        else:
            new_html = soup.new_tag("html", lang="en")
            new_html.append(head)
            body = soup.new_tag("body")
            for content in list(soup.contents):
                if content is new_html:
                    continue
                body.append(content.extract())
            new_html.append(body)
            soup = BeautifulSoup(str(new_html), "html.parser")
    if not soup.body:
        body = soup.new_tag("body")
        for el in list(soup.html.contents):
            if el is soup.head:
                continue
            body.append(el.extract())
        soup.html.append(body)

    # ensure scripts have a non-empty nonce
    for s in soup.find_all("script"):
        if not s.has_attr("nonce") or not str(s.get("nonce")).strip():
            s["nonce"] = "anon"

    # remove empty attributes
    for tag in soup.find_all(True):
        to_del = [k for k, v in tag.attrs.items() if v == "" or v is None]
        for k in to_del:
            try:
                del tag.attrs[k]
            except Exception:
                pass

    final_html = str(soup)
    if "<!doctype" not in final_html.lower():
        final_html = "<!doctype html>\n" + final_html

    # ensure charset meta exists
    if soup.head and not soup.head.find("meta", attrs={"charset": True}):
        charset_tag = soup.new_tag("meta", charset="utf-8")
        soup.head.insert(0, charset_tag)
        final_html = "<!doctype html>\n" + str(soup)

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(final_html)

def parse_search_results(html):
    soup = BeautifulSoup(html, "lxml")
    records = []

    selectors = [
        "div.reusable-search__result-container",
        "li.reusable-search__result-container",
        "div.search-result__wrapper",
        "div.entity-result__item",
        "div.search-result",
        "div.result-lockup",
        "ul.search-results__list li",
        "div.result-card__contents",
        "div.search-result__info"
    ]

    containers = []
    for sel in selectors:
        found = soup.select(sel)
        if found:
            containers.extend(found)

    if not containers:
        anchors = soup.find_all("a", href=True)
        seen = set()
        for a in anchors:
            href = a["href"].split("?")[0]
            if "/in/" not in href:
                continue
            parent = a.find_parent()
            if parent and id(parent) not in seen:
                containers.append(parent)
                seen.add(id(parent))

    for c in containers:
        try:
            text_block = c.get_text("\n", strip=True) or ""
            # split into logical lines (preserve order)
            lines = [ln.strip() for ln in re.split(r'\n|\r|\s{2,}', text_block) if ln.strip()]

            # profile_url
            a = c.select_one("a[href*='/in/']")
            profile_url = ""
            if a:
                href = a.get("href").split("?")[0]
                if href.startswith("/"):
                    href = urljoin("https://www.linkedin.com", href)
                profile_url = href

            # name extraction - prefer anchor text or dedicated selectors
            name = ""
            if a:
                name = a.get_text(" ", strip=True)
            if not name:
                name_el = (c.select_one("span.entity-result__title-text a span") or
                           c.select_one("h3") or
                           c.select_one("span.actor-name") or
                           c.select_one(".result-card__title") or
                           c.select_one(".name"))
                if name_el:
                    name = name_el.get_text(" ", strip=True)
            if not name:
                strong = c.select_one("strong")
                if strong:
                    name = strong.get_text(" ", strip=True)
            if not name and lines:
                name = lines[0]
            name = extract_name_from_text(name)

            # location extraction: multiple strategies
            location = ""
            # 1) Try common selector(s)
            loc_el = (c.select_one(".entity-result__secondary-subtitle") or
                      c.select_one(".search-result__info .subline-level-2") or
                      c.select_one(".result__meta") or
                      c.select_one(".location") or
                      c.select_one(".search-result__location") or
                      c.select_one(".result-lockup__meta"))
            if loc_el:
                location = _clean_text(loc_el.get_text(" ", strip=True) or "")

            # 2) If above failed or was empty, use lines heuristics:
            if not location:
                # find index of name in lines (best effort)
                name_index = -1
                for idx, ln in enumerate(lines):
                    if name and name.lower() in ln.lower():
                        name_index = idx
                        break
                if name_index == -1:
                    name_index = 0
                # examine next few lines for candidate location
                candidate = ""
                for j in range(name_index + 1, min(len(lines), name_index + 5)):
                    ln = lines[j]
                    low = ln.lower()
                    if any(skip in low for skip in ("current:", "current", "connect", "mutual", "followers", "follow", "message")):
                        continue
                    # prefer lines containing country tokens or a comma (City, State)
                    if any(token.lower() in low for token in [t.lower() for t in COUNTRY_PREFER]) or ("," in ln and len(ln) < 80):
                        candidate = ln
                        break
                    # else take short lines likely to be location (<6 words)
                    if len(ln.split()) <= 6 and re.search(r'[A-Za-z]', ln):
                        candidate = ln
                        break
                if candidate:
                    location = _clean_text(candidate)

            # 3) final fallback: try to find any short line that includes a comma and a capitalized word
            if not location and lines:
                for ln in lines[:6]:
                    if "," in ln and len(ln) < 80 and not re.search(r'\b(Current|Past|Connect|mutual|followers)\b', ln, flags=re.I):
                        location = _clean_text(ln)
                        break

            # current role/company extraction (same as before)
            current_role = ""
            current_company = ""
            possible_nodes = []
            for tag in c.find_all(["p", "span", "div", "li"], recursive=True):
                txt = (tag.get_text(" ", strip=True) or "").strip()
                if not txt:
                    continue
                if re.search(r'\bCurrent[:\s]', txt, flags=re.I) or re.search(r'\bat\b', txt):
                    possible_nodes.append(txt)
            if possible_nodes:
                chosen = None
                for t in possible_nodes:
                    if 'current' in t.lower():
                        chosen = t
                        break
                if not chosen:
                    chosen = possible_nodes[0]
                role, comp = extract_current_from_text(chosen)
                current_role = role
                current_company = comp
            else:
                prim = c.select_one("div.entity-result__primary-subtitle") or c.select_one("p.subline-level-1") or c.select_one(".entity-result__summary") or c.select_one(".search-result__info .subline-level-1")
                prim_text = prim.get_text(" ", strip=True) if prim else ""
                role, comp = extract_current_from_text(prim_text)
                if role or comp:
                    current_role = role
                    current_company = comp
                else:
                    # Try multiple heuristics on the raw text lines to extract role/company
                    role, comp = extract_current_from_text(text_block)
                    current_role = role
                    current_company = comp

                    if not current_role and not current_company and lines:
                        # scan several nearby lines for 'role at company' patterns
                        for ln in lines[1:6]:
                            r2, c2 = extract_current_from_text(ln)
                            if r2 or c2:
                                if not current_role:
                                    current_role = r2
                                if not current_company:
                                    current_company = c2
                                break

                    # pattern: 'Role · Company' or 'Company · Role'
                    if (not current_role or not current_company) and lines:
                        for ln in lines[:6]:
                            m = re.split(r'\s+·\s+|\s+•\s+|\s+\|\s+', ln)
                            if len(m) == 2:
                                a, b = m[0].strip(), m[1].strip()
                                # heuristics: shorter phrase with capitals likely a name/role, all-caps or multiword company-like is company
                                def looks_like_company(s):
                                    if not s: return False
                                    keywords = ['inc','ltd','llp','pvt','llc','technologies','systems','solutions','services','infosys','wipro','tcs','google','microsoft','amazon','accenture','capgemini','bpm']
                                    low = s.lower()
                                    if any(k in low for k in keywords):
                                        return True
                                    # company tends to be multiple words and contain capitalized words
                                    if len(s.split()) >= 2 and re.search(r'[A-Z]', s):
                                        return True
                                    return False

                                if looks_like_company(a) and not current_company:
                                    current_company = _clean_text(a)
                                if looks_like_company(b) and not current_company:
                                    current_company = _clean_text(b)
                                # if a contains role-like words
                                if not current_role and re.search(r'\b(manager|engineer|specialist|consultant|director|analyst|lead|officer|developer|architect)\b', a, flags=re.I):
                                    current_role = _clean_text(a)
                                if not current_role and re.search(r'\b(manager|engineer|specialist|consultant|director|analyst|lead|officer|developer|architect)\b', b, flags=re.I):
                                    current_role = _clean_text(b)
                                if current_role or current_company:
                                    break

                    # fallback: if company still empty, find possible company-like short lines
                    if not current_company and lines:
                        for ln in lines[1:6]:
                            low = ln.lower()
                            if any(k in low for k in ['inc','ltd','llp','pvt','llc','solutions','technologies','systems']) or re.search(r'\b( infosys | wipro | tcs | accenture | capgemini | google | microsoft | amazon )\b', ' '+low+' '):
                                current_company = _clean_text(ln)
                                break

            # clean fields
            name = name or ""
            location = location or ""
            current_role = current_role or ""
            current_company = current_company or ""
            name = _clean_text(name)
            location = _clean_text(location)
            current_role = _clean_text(current_role)
            current_company = _clean_text(current_company)

            # final company cleanup: cut trailing mutual names
            if current_company:
                parts = re.split(r'\s+and\s+|,|\s{2,}', current_company, flags=re.I)
                current_company = _clean_text(parts[0].strip())
                # remove any embedded person-name fragments such as 'Dr. Name' or the extracted name
                current_company = strip_name_and_titles_from_company(current_company, name)

            rec = {
                "profile_url": profile_url or "",
                "name": name or "",
                "location": location or "",
                "current_role": current_role or "",
                "current_company": current_company or ""
            }

            # require at least name or profile_url
            if not rec["name"] and not rec["profile_url"]:
                continue

            records.append(rec)
        except Exception:
            continue

    return records

def wait_for_search_results(driver, timeout=12):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/in/'], .reusable-search__result-container, .entity-result__item"))
        )
        return True
    except TimeoutException:
        return False

def scrape_keyword(keyword, headless=False, limit_records=MAX_RECORDS):
    driver = None
    try:
        clear_output_csv()

        try:
            driver = start_driver(headless=headless, use_persistent_profile=True,
                                  user_data_dir=USER_DATA_DIR, profile_dir=PROFILE_DIR)
        except Exception as e:
            print("[WARN] Persistent profile failed; falling back to temporary profile. Exception:", e)
            traceback.print_exc()
            try:
                import subprocess
                subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
            driver = start_driver(headless=headless, use_persistent_profile=False, user_data_dir=None, profile_dir=None)
            print("[INFO] Started Chrome with temporary profile (no persistence).")

        search_url = build_search_url(keyword)
        print("[DEBUG] Navigating to search URL:", search_url)
        try:
            driver.get("about:blank")
            time.sleep(0.5)
            driver.get(search_url)
            time.sleep(1.0)
            try:
                driver.execute_script("window.location.href = arguments[0];", search_url)
            except Exception:
                pass
            time.sleep(1.0)
            try:
                driver.refresh()
            except Exception:
                pass
        except Exception:
            pass

        debug_path = os.path.join(DEBUG_DIR, "debug_after_nav.html")
        _save_debug_html(debug_path, driver.page_source)

        print("[DEBUG] current_url:", driver.current_url)
        print("[DEBUG] title:", driver.title)
        print("[DEBUG] Saved snapshot ->", debug_path)

        if looks_like_login_page(driver):
            ok = prompt_manual_login(driver)
            if not ok:
                print("[ERROR] Manual login aborted.")
                return []

        ok = wait_for_search_results(driver, timeout=12)
        if not ok:
            print("[WARN] No visible search results detected. Saved page for inspection.")
            _save_debug_html(os.path.join(DEBUG_DIR, "debug_search.html"), driver.page_source)
            return []

        scroll_page(driver, times=SCROLL_PAUSES)

        html = driver.page_source
        records = parse_search_results(html)
        print(f"[INFO] Parsed {len(records)} records from search results.")

        # dedupe and normalize (fill n/a)
        seen = set()
        cleaned = []
        for r in records:
            key = r.get("profile_url") or r.get("name","")
            key = key.strip()
            if not key:
                continue
            if key in seen:
                continue
            seen.add(key)
            # only include this person if at least one of location/role/company is present
            if not (r.get("location") or r.get("current_role") or r.get("current_company")):
                continue
            cleaned_rec = {
                "profile_url": r.get("profile_url","") or "n/a",
                "name": r.get("name","") or "n/a",
                "location": r.get("location","") or "n/a",
                "current_role": r.get("current_role","") or "n/a",
                "current_company": r.get("current_company","") or "n/a"
            }
            cleaned.append(cleaned_rec)

        print(f"[INFO] {len(records)} raw -> {len(cleaned)} unique records after dedupe. Saving up to {limit_records} rows.")

        for rec in cleaned[:limit_records]:
            append_pretty_csv_row(OUTPUT_CSV, rec, fieldnames=CSV_FIELDS)
            polite_sleep()

        return cleaned[:limit_records]

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

def main():
    print("== LinkedIn public search scraper (Selenium) ==")
    keyword = input("Enter search keywords (e.g. 'Sales Manager India'): ").strip()
    if not keyword:
        print("No keyword provided. Exiting.")
        return
    scrape_keyword(keyword, headless=False, limit_records=MAX_RECORDS)
    print("Done. Check data/output.csv or data/debug_after_nav.html for debug output.")

if __name__ == "__main__":
    main()
