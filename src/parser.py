from bs4 import BeautifulSoup

def parse_public_profile(html, url):
    soup = BeautifulSoup(html, "lxml")

    out = {
        "profile_url": url,
        "name": None,
        "headline": None,
        "location": None
    }

    # NAME
    name_tag = soup.select_one("h1")
    out["name"] = name_tag.get_text(strip=True) if name_tag else None

    # HEADLINE
    headline_tag = soup.select_one("div.text-body-medium")
    out["headline"] = headline_tag.get_text(strip=True) if headline_tag else None

    # LOCATION
    location_tag = soup.select_one("span.text-body-small.inline")
    out["location"] = location_tag.get_text(strip=True) if location_tag else None

    return out
