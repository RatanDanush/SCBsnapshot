# SCB FX Snapshot Generator

Weekly FX market snapshot generator for Standard Chartered India FM Sales desk.

Produces an email-ready HTML briefing (and optional JPEG) covering USD/INR, G3 vs INR, bond yields, policy rates, Brent crude, and gold — with AI-written commentary and macro story cards.

---

## Architecture

| Data source | What it covers |
|---|---|
| **Bloomberg terminal** | All FX pairs: USD/INR, EUR/INR, GBP/INR, JPY/INR, CNH/INR — you enter week open + close |
| **Gemini AI + Google Search** | DXY, US 10Y, India 10Y (CCIL), Brent, Gold, Fed Funds, RBI Repo |
| **yfinance** | Brent 5-day chart series + 52-week ranges (supplementary only) |

### Gemini model routing

| Task | Model | RPD budget |
|---|---|---|
| Market data fetch (search) | `gemini-3.1-flash-lite` | 500 RPD |
| Commentary + per-pair narrative | `gemini-2.5-flash` | 20 RPD |
| Story search (Step A) | `gemini-2.5-flash` + search | 20 RPD |
| Story structure (Step B) | `gemini-2.5-flash-lite` | 20 RPD |
| Week ahead | `gemini-3.1-flash-lite` | 500 RPD |

One full weekly snapshot ≈ 6–8 Gemini calls (2–3 on the 20 RPD models).

---

## Setup

### Local

```bash
# 1. Clone and install
git clone <your-repo-url>
cd scb-fx-snapshot
pip install -r requirements.txt

# WeasyPrint system deps (macOS)
brew install pango cairo gdk-pixbuf libffi

# WeasyPrint system deps (Ubuntu/Debian)
sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf2.0-0

# 2. Add your Gemini API key
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit secrets.toml and set GEMINI_API_KEY = "AIza..."

# 3. Run
streamlit run app.py
```

### Streamlit Cloud

1. Push this repo to GitHub (keep `.streamlit/secrets.toml` out — it's in `.gitignore`).
2. Connect the repo in [share.streamlit.io](https://share.streamlit.io).
3. In **App Settings → Secrets**, add:
   ```
   GEMINI_API_KEY = "AIza..."
   ```
4. Streamlit Cloud will automatically install system packages from `packages.txt` on deploy.

---

## Usage — 3-step flow

**Step 1 — Configure**
- Select which sections to include (FX pairs, yields, commodities, macro).
- Enter Bloomberg terminal week open + close for each selected FX pair.
- Click **Fetch AI Data** — Gemini searches for DXY, yields, Brent, Gold, policy rates.

**Step 2 — Review**
- All AI-fetched values are pre-filled in editable fields.
- Correct any values before generating (especially India 10Y — verify against CCIL/FIMMDA).
- Click **Generate Snapshot**.

**Step 3 — Preview & Download**
- HTML preview in-page.
- **Download HTML** — open in browser, paste into Outlook or Gmail.
- **Render JPEG** → **Download JPEG** — for attachments or chat distribution.

---

## Important notes

- **India 10Y G-Sec**: Gemini gives an estimate — always verify against [CCIL](https://www.ccilindia.com) or FIMMDA before client distribution. The HTML footer carries this warning.
- **Gold**: International XAU/USD spot price only (not MCX proxy).
- **52-week ranges for FX pairs**: Not shown (Bloomberg data only covers open/close). Ranges for yields and commodities come from yfinance.
- **JPEG rendering**: Requires WeasyPrint system libraries (`packages.txt`). On Streamlit Cloud, these are installed automatically. Locally, install the brew/apt packages above.

---

## File structure

```
scb-fx-snapshot/
├── app.py               # Streamlit entry point
├── snapshot_page.py     # 3-step UI (config → review → preview)
├── data_fetcher.py      # Bloomberg FX processing + yfinance supplements
├── macro_generator.py   # Gemini tiered model routing + all AI calls
├── html_generator.py    # HTML + SVG chart builder + WeasyPrint JPEG
├── requirements.txt
├── packages.txt         # System deps for WeasyPrint on Streamlit Cloud
└── .streamlit/
    └── secrets.toml.example
```
