# LinkedIn Scraper

Scrapes public LinkedIn people search results and saves the extracted data to CSV. The project includes a command-line scraper and a Flask web UI.

## What It Does

- Takes a company name or search keyword
- Opens LinkedIn people search results
- Extracts `profile_url`, `name`, `location`, `current_role`, and `current_company`
- Saves results to `data/output.csv`
- Uses optional Groq parsing when `GROQ_API_KEY` is set

## Requirements

- Python 3.10+
- Google Chrome
- A LinkedIn account with access to search results
- Optional: `GROQ_API_KEY` for AI-assisted parsing

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

- Set `GROQ_API_KEY` in your environment or `.env` file if you want AI parsing
- Update `USER_DATA_DIR` and `PROFILE_DIR` in `src/main_selenium.py` if you want to use a custom Chrome profile
- Keep the same profile folder between runs so LinkedIn login cookies can be reused

## Run

CLI scraper:

```bash
python src\main_selenium.py
```

Web UI:

```bash
python src\ui.py
```

## Output

- Main results: `data/output.csv`
- Debug snapshots: `data/`

## Project Structure

- `src/main_selenium.py` - Selenium scraper
- `src/main.py` - non-Selenium scraper variant
- `src/ui.py` - Flask web interface
- `src/fetcher.py` - HTTP fetch helper
- `src/parser.py` - profile parsing logic
- `src/util.py` - CSV saving helper
- `templates/` - HTML templates
- `static/` - CSS and JavaScript assets
- `data/` - output and debug files

## Notes

- The scraper only targets public search-result data
- It does not open profile pages directly
- Empty or invalid results usually mean the session cookies or Chrome profile need to be refreshed

