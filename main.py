import os
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import serpapi
from amazon_scraper import scrape_amazon_page

load_dotenv()

# All 24 supported Google Shopping country codes
COUNTRY_CODES = {
    "au": "au",  # Australia
    "be": "be",  # Belgium
    "br": "br",  # Brazil
    "ca": "ca",  # Canada
    "cn": "cn",  # China
    "eg": "eg",  # Egypt
    "fr": "fr",  # France
    "de": "de",  # Germany
    "in": "in",  # India
    "ie": "ie",  # Ireland
    "it": "it",  # Italy
    "jp": "jp",  # Japan
    "mx": "mx",  # Mexico
    "nl": "nl",  # Netherlands
    "pl": "pl",  # Poland
    "sa": "sa",  # Saudi Arabia
    "sg": "sg",  # Singapore
    "za": "za",  # South Africa
    "es": "es",  # Spain
    "se": "se",  # Sweden
    "tr": "tr",  # Turkey
    "ae": "ae",  # United Arab Emirates
    "uk": "uk",  # United Kingdom
    "us": "us",  # United States
    "kw": "kw",  # Kuwait
}

app = FastAPI(
    title="Product Research Tool API",
    description=(
        "REST API powering the Product Research Tool Streamlit dashboard. "
        "Provides Google Shopping search and Amazon product scraping across 24+ countries."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    """Returns API status. Used by the Streamlit frontend to verify the backend is live."""
    return {"status": "ok"}


# ── Google Shopping Search ─────────────────────────────────────────────────────

@app.get("/search/{gl}/{query:path}", tags=["Search"])
def search_products(
    gl: str,
    query: str,
    category: str = Query(None, description="Optional category prefix to prepend to the query"),
):
    """
    Search Google Shopping for products.

    - **gl**: 2-letter country/locale code (e.g. `in`, `us`, `uk`)
    - **query**: Search term (URL-encoded, e.g. `wireless+earbuds`)
    - **category**: Optional category string to prepend to query (e.g. `Electronics`)

    Falls back to a standard Google organic search for locales where Shopping is unsupported.
    """
    api_key = os.getenv("SERP_API_KEY")
    if not api_key:
        return {"error": "SERP_API_KEY is not configured on the server."}

    if gl.lower() not in COUNTRY_CODES:
        return {"error": f"Unsupported locale code '{gl}'. Supported: {', '.join(COUNTRY_CODES)}"}

    full_query = f"{category} {query}".strip() if category else query
    params = {
        "engine": "google_shopping",
        "q": full_query,
        "api_key": api_key,
        "gl": gl.lower(),
    }

    fallback_used = False
    try:
        result = serpapi.search(params).as_dict()
        products = result.get("shopping_results", []) + result.get("immersive_products", [])

        # If Shopping returned nothing, attempt organic fallback silently
        if not products:
            raise Exception("No shopping results — attempt organic fallback")

    except Exception as e:
        # Fallback: organic search (works for all locales)
        fallback_used = True
        try:
            params["engine"] = "google"
            result = serpapi.search(params).as_dict()
            products = (
                result.get("shopping_results")
                or result.get("inline_products")
                or [
                    {
                        "title": org.get("title"),
                        "link": org.get("link"),
                        "price": "Check site",
                        "rank": org.get("position"),
                        "thumbnail": org.get("thumbnail"),
                        "snippet": org.get("snippet"),
                    }
                    for org in result.get("organic_results", [])[:5]
                ]
            ) or []
        except Exception as e2:
            return {"error": str(e2)}

    return {
        "gl": gl,
        "query": query,
        "fallback_used": fallback_used,
        "products": products,
    }


# ── Amazon Scraper ─────────────────────────────────────────────────────────────

@app.get("/amazon/{country}/{page_type}", tags=["Amazon"])
def amazon_scrape(
    country: str,
    page_type: str,
    category: str = Query(None, description="Amazon category slug (e.g. electronics, beauty)"),
):
    """
    Scrape an Amazon listing page (Best Sellers / New Releases / Movers & Shakers).

    - **country**: Country slug (e.g. `india`, `united-states`, `united-kingdom`)
    - **page_type**: One of `best-sellers`, `new-releases`, `movers-and-shakers`
    - **category**: Optional category slug to filter results (e.g. `electronics`)
    """
    try:
        return scrape_amazon_page(country, page_type, category)
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}