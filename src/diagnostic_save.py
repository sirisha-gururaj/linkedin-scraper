# diagnostic_save.py (new file)
from fetcher import fetch
from pathlib import Path

def save_html(url, out="debug_search.html"):
    html = fetch(url)
    Path(out).write_text(html, encoding="utf-8")
    print(f"[INFO] Saved HTML to {out} (size: {len(html)} bytes)")

if __name__ == "__main__":
    url = "https://www.linkedin.com/search/results/people/?keywords=Sales%20Manager%20India"
    save_html(url)
