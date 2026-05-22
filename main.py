from datetime import date, timedelta
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import serpapi
from dotenv import load_dotenv

from amazon_scraper import scrape_amazon_page
from gsc_client import get_search_queries, get_pages, get_cached_response, cache_response, get_gsc_service, list_verified_properties

COUNTRY_CODES = {
    "australia": "au",
    "kuwait": "kw",
    "united-kingdom": "uk",
    "saudi-arabia": "sa",
    "india": "in",
}

load_dotenv()

GSC_PROPERTY_URLS = {
    "australia": "https://u-buy.com.au",
    "kuwait": "https://a.ubuy.com.kw",
    "united-kingdom": "https://u-buy.co.uk",
    "saudi-arabia": "https://ubuy.com.sa",
    "india": "https://ubuy.co.in",
}

app = FastAPI(title="Product Research Tool", description="API for product research using SERP API and GSC data")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/search/{country}/{query}")
def search_products(country: str, query: str):
    api_key = os.getenv("SERP_API_KEY")
    if not api_key:
        return {"error": "SERP API key not configured"}

    gl = COUNTRY_CODES.get(country.lower())
    if not gl:
        return {"error": f"Unsupported country '{country}'. Supported: {', '.join(COUNTRY_CODES.keys())}"}
    
    params = {
        "engine": "google_shopping",
        "q": query,
        "api_key": api_key,
        "gl": gl,
    }
    
    try:
        search = serpapi.search(params)
        results = search.as_dict()
        shopping_results = results.get("shopping_results", [])
        immersive_products = results.get("immersive_products", [])
        return {
            "country": country,
            "query": query,
            "shopping_results": shopping_results,
            "immersive_products": immersive_products,
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/amazon/{country}/{page_type}")
def amazon_scrape(country: str, page_type: str):
    try:
        return scrape_amazon_page(country, page_type)
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


@app.get("/gsc/queries/{country}")
def gsc_queries(country: str, days: int = 30):
    property_url = GSC_PROPERTY_URLS.get(country.lower())
    if not property_url:
        return {"error": f"GSC property URL not configured for country '{country}'. Supported: {', '.join(GSC_PROPERTY_URLS.keys())}"}

    cache_key = f"queries_{country}_{days}"
    cached = get_cached_response(cache_key)
    if cached:
        return {"cached": True, "data": cached}

    try:
        rows = get_search_queries(country, property_url, days)
        cache_response(cache_key, rows)
        return {"cached": False, "data": rows}
    except Exception as e:
        return {"error": str(e)}


@app.get("/gsc/properties/{country}")
def gsc_properties(country: str):
    try:
        props = list_verified_properties(country)
        return {"country": country, "properties": props}
    except Exception as e:
        return {"error": str(e)}


@app.get("/gsc/pages/{country}")
def gsc_pages(country: str, days: int = 30):
    property_url = GSC_PROPERTY_URLS.get(country.lower())
    if not property_url:
        return {"error": f"GSC property URL not configured for country '{country}'. Supported: {', '.join(GSC_PROPERTY_URLS.keys())}"}

    cache_key = f"pages_{country}_{days}"
    cached = get_cached_response(cache_key)
    if cached:
        return {"cached": True, "data": cached}

    try:
        rows = get_pages(country, property_url, days)
        cache_response(cache_key, rows)
        return {"cached": False, "data": rows}
    except Exception as e:
        return {"error": str(e)}