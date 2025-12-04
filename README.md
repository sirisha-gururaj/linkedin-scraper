# LinkedIn Public Search Scraper (Selenium)

This project scrapes **only public LinkedIn search-result cards** (not full profiles) and extracts:

- `profile_url`
- `name`
- `location`
- `current_role`
- `current_company`

It **does NOT open profiles**, so **no “profile viewed” notifications** are generated.

---

## Setup (Windows)

### 1. Environment Setup

```bash
# 1. Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# 2. Install dependencies
pip install selenium chromedriver-autoinstaller beautifulsoup4 lxml
```
### 2. Create a separate Chrome profile (Required)

Run the following in PowerShell:

```bash
taskkill /F /IM chrome.exe        # close Chrome
$P="C:\Users\<YOU>\ChromeSeleniumProfile"
Remove-Item $P -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $P
```
### Why? 
LinkedIn requires login to show search results. Using a separate profile keeps your main Chrome untouched and allows Selenium to reuse a logged-in session.

### IMPORTANT

After creating the folder you must update your script (main_selenium.py) and replace:
```bash
USER_DATA_DIR = r"C:\Users\Sirisha G\ChromeSeleniumProfile"
PROFILE_DIR   = "Default"
```
with your own:
```bash
USER_DATA_DIR = r"C:\Users\<YOU>\ChromeSeleniumProfile"
PROFILE_DIR   = "Default"
```
Both variable names must match exactly:
USER_DATA_DIR → your folder path
PROFILE_DIR → usually "Default"

### 3. Usage

First Run
```bash
python src\main_selenium.py
```
1. A Chrome window opens using the Selenium profile.
2. Login to LinkedIn once, then return to the terminal and press Enter.
3. Future runs will not require login unless cookies expire.

### 4. Output

Results are saved to: data/output.csv
* The file is cleared automatically on each run.
* Missing fields appear as n/a.

### 5. Limitations

* Only public information visible on the search-results page is scraped.
* Private or restricted profiles cannot be accessed.
* LinkedIn blocks non-public data for logged-out or programmatic views.

### 6. Files

src/main_selenium.py           # main script
data/output.csv                # results
data/debug_after_nav.html      # debug snapshots

### 7. Notes

Safe: The script never opens profile pages → no notifications sent.
Debug: HTML is sanitized so VS Code shows no errors.
Troubleshooting: If results look empty, delete the profile folder & re-login once.

