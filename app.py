import os
# Fix for Python 3.14 compatibility with Google Protobuf
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import json
import queue
import threading
import asyncio
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
import requests as _http
import urllib.parse as _urllib_parse
from openai import OpenAI, AsyncOpenAI

from amazon_scraper import AMAZON_DOMAINS
from datetime import datetime, timedelta
# Playwright is only available in local environments; gracefully degrade on Streamlit Cloud
try:
    from amazon_deals import get_banner_deals, get_products_from_deal
    PLAYWRIGHT_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    PLAYWRIGHT_AVAILABLE = False

load_dotenv()

# ── Background FastAPI Server ─────────────────────────────────────────────────
# We check if a FastAPI server is already running manually on port 8000 or 8001.
# If yes, we use it directly so the developer can see live logs and reload features.
# If no, we start a cached background FastAPI instance on port 8001 exactly once.

_API_BASE = "http://127.0.0.1:8001"

def _is_api_alive(url: str) -> bool:
    try:
        resp = _http.get(f"{url}/health", timeout=0.5)
        return resp.status_code == 200 and resp.json().get("status") == "ok"
    except Exception:
        return False

@st.cache_resource
def _start_fastapi_background():
    import threading as _threading
    def _run():
        import uvicorn
        from main import app as _fastapi_app
        uvicorn.run(_fastapi_app, host="127.0.0.1", port=8001, log_level="error")
    
    t = _threading.Thread(target=_run, daemon=True)
    t.start()
    import time
    time.sleep(1.0)  # Allow FastAPI time to boot
    return t

def _initialize_backend():
    global _API_BASE
    # 1. Check if user started a manual server on port 8000 (default uvicorn port)
    if _is_api_alive("http://127.0.0.1:8000"):
        _API_BASE = "http://127.0.0.1:8000"
        return "Manual (Port 8000)"
        
    # 2. Check if a server is already active on port 8001
    if _is_api_alive("http://127.0.0.1:8001"):
        _API_BASE = "http://127.0.0.1:8001"
        return "Existing (Port 8001)"
        
    # 3. Spin up background server and cache the thread
    _start_fastapi_background()
    _API_BASE = "http://127.0.0.1:8001"
    return "Auto-Started (Port 8001)"

_backend_status = _initialize_backend()


# ── Constants ────────────────────────────────────────────────────────────────

COUNTRY_CODES = {
    "Australia": "au",
    "Belgium": "be",
    "Brazil": "br",
    "Canada": "ca",
    "China": "cn",
    "Egypt": "eg",
    "France": "fr",
    "Germany": "de",
    "India": "in",
    "Ireland": "ie",
    "Italy": "it",
    "Japan": "jp",
    "Mexico": "mx",
    "Netherlands": "nl",
    "Poland": "pl",
    "Saudi Arabia": "sa",
    "Singapore": "sg",
    "South Africa": "za",
    "Spain": "es",
    "Sweden": "se",
    "Turkey": "tr",
    "United Arab Emirates": "ae",
    "United Kingdom": "uk",
    "United States": "us",
    "Kuwait": "kw",
}

AMAZON_COUNTRIES = {
    "Australia": "australia",
    "Belgium": "belgium",
    "Brazil": "brazil",
    "Canada": "canada",
    "China": "china",
    "Egypt": "egypt",
    "France": "france",
    "Germany": "germany",
    "India": "india",
    "Ireland": "ireland",
    "Italy": "italy",
    "Japan": "japan",
    "Mexico": "mexico",
    "Netherlands": "netherlands",
    "Poland": "poland",
    "Saudi Arabia": "saudi-arabia",
    "Singapore": "singapore",
    "South Africa": "south-africa",
    "Spain": "spain",
    "Sweden": "sweden",
    "Turkey": "turkey",
    "United Arab Emirates": "united-arab-emirates",
    "United Kingdom": "united-kingdom",
    "United States": "united-states",
    "Kuwait": "kuwait",
}

PAGE_TYPES = {
    "Best Sellers": "best-sellers",
    "New Releases": "new-releases",
    "Movers & Shakers": "movers-and-shakers",
}

CATEGORIES = {
    "All Categories": None,
    "Health & Supplements": "hpc",
    "Electronics": "electronics",
    "Beauty & Personal Care": "beauty",
    "Fashion": "fashion",
    "Home & Kitchen": "home",
    "Baby Essentials": "baby",
    "Musical Instruments": "musical-instruments",
    "Grocery & Gourmet Food": "grocery",
    "Office Supplies": "office-products",
    "Sports Outdoor & Fitness": "sports",
    "Automotive": "automotive",
    "Household Supplies": "hpc",
    "Pet Supplies": "pet-supplies",
    "Arts Crafts & Sewing": "arts-crafts",
    "Toys & Games": "toys",
    "Industrial Supplies": "industrial",
    "Books": "books",
    "Gardening Supplies": "lawn-garden",
}

SITE_CATEGORIES = {
    "All Categories": None,
    "Health & Supplements": "health",
    "Electronics": "electronics",
    "Beauty & Personal Care": "beauty",
    "Fashion": "fashion",
    "Home & Kitchen": "home",
    "Baby Essentials": "baby",
    "Musical Instruments": "musical",
    "Grocery & Gourmet Food": "grocery",
    "Office Supplies": "office",
    "Sports Outdoor & Fitness": "sports",
    "Automotive": "automotive",
    "Household Supplies": "household",
    "Pet Supplies": "pet",
    "Arts Crafts & Sewing": "arts",
    "Toys & Games": "toys",
    "Industrial Supplies": "industrial",
    "Books": "books",
    "Gardening Supplies": "gardening",
}

CATEGORY_IMAGES = {
    "All Categories": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500&auto=format&fit=crop",
    "Health & Supplements": "https://images.unsplash.com/photo-1579758629938-03607ccdbaba?w=500&auto=format&fit=crop",
    "Electronics": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&auto=format&fit=crop",
    "Beauty & Personal Care": "https://images.unsplash.com/photo-1526947425960-945c6e72858f?w=500&auto=format&fit=crop",
    "Fashion": "https://images.unsplash.com/photo-1483985988355-763728e1935b?w=500&auto=format&fit=crop",
    "Home & Kitchen": "https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=500&auto=format&fit=crop",
    "Baby Essentials": "https://images.unsplash.com/photo-1515488042361-404e9250afef?w=500&auto=format&fit=crop",
    "Musical Instruments": "https://images.unsplash.com/photo-1511192336575-5a79af67a629?w=500&auto=format&fit=crop",
    "Grocery & Gourmet Food": "https://images.unsplash.com/photo-1542838132-92c53300491e?w=500&auto=format&fit=crop",
    "Office Supplies": "https://images.unsplash.com/photo-1513151233558-d860c5398176?w=500&auto=format&fit=crop",
    "Sports Outdoor & Fitness": "https://images.unsplash.com/photo-1517838277536-f5f99be501cd?w=500&auto=format&fit=crop",
    "Automotive": "https://images.unsplash.com/photo-1486006920555-c77dce18193b?w=500&auto=format&fit=crop",
    "Household Supplies": "https://images.unsplash.com/photo-1583947215259-38e31be8751f?w=500&auto=format&fit=crop",
    "Pet Supplies": "https://images.unsplash.com/photo-1516734212186-a967f81ad0d7?w=500&auto=format&fit=crop",
    "Arts Crafts & Sewing": "https://images.unsplash.com/photo-1513364776144-60967b0f800f?w=500&auto=format&fit=crop",
    "Toys & Games": "https://images.unsplash.com/photo-1539627831859-a911cf04b3cd?w=500&auto=format&fit=crop",
    "Industrial Supplies": "https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=500&auto=format&fit=crop",
    "Books": "https://images.unsplash.com/photo-1497633762265-9d179a990aa6?w=500&auto=format&fit=crop",
    "Gardening Supplies": "https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=500&auto=format&fit=crop",
}

def get_product_image(title: str, category: str) -> str:
    """Choose a highly specific product stock image based on keywords in title with category fallback."""
    t_lower = title.lower()
    
    # Specific product keyword matches
    if any(w in t_lower for w in ["shoe", "sneaker", "boot", "adidas", "nike", "puma", "footwear", "sandal", "heel"]):
        return "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=500&auto=format&fit=crop"
    if any(w in t_lower for w in ["watch", "smartwatch", "garmin", "fitbit", "apple watch", "rolex", "clock"]):
        return "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500&auto=format&fit=crop"
    if any(w in t_lower for w in ["bike", "bicycle", "cycling", "giant", "trek", "scooter"]):
        return "https://images.unsplash.com/photo-1485965120184-e220f721d03e?w=500&auto=format&fit=crop"
    if any(w in t_lower for w in ["headphone", "earphone", "bud", "audio", "speaker", "soundbar"]):
        return "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&auto=format&fit=crop"
    if any(w in t_lower for w in ["phone", "smartphone", "iphone", "samsung galaxy", "pixel"]):
        return "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=500&auto=format&fit=crop"
    if any(w in t_lower for w in ["laptop", "computer", "macbook", "pc", "monitor"]):
        return "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=500&auto=format&fit=crop"
    if any(w in t_lower for w in ["protein", "whey", "creatine", "supplement", "vitamin", "powder", "collagen"]):
        return "https://images.unsplash.com/photo-1579758629938-03607ccdbaba?w=500&auto=format&fit=crop"
    if any(w in t_lower for w in ["face", "cream", "skin", "serum", "lotion", "makeup", "shampoo", "perfume"]):
        return "https://images.unsplash.com/photo-1526947425960-945c6e72858f?w=500&auto=format&fit=crop"
    if any(w in t_lower for w in ["coffee", "tea", "chocolate", "food", "snack", "cookie"]):
        return "https://images.unsplash.com/photo-1542838132-92c53300491e?w=500&auto=format&fit=crop"
    if any(w in t_lower for w in ["guitar", "piano", "keyboard", "drum", "violin", "music"]):
        return "https://images.unsplash.com/photo-1511192336575-5a79af67a629?w=500&auto=format&fit=crop"
    if any(w in t_lower for w in ["sofa", "chair", "table", "lamp", "desk", "furniture"]):
        return "https://images.unsplash.com/photo-1524758631624-e2822e304c36?w=500&auto=format&fit=crop"
    
    # Category fallback matches
    return CATEGORY_IMAGES.get(category, CATEGORY_IMAGES["All Categories"])



# ── Page Config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Product Research Dashboard",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Theme Configuration ─────────────────────────────────────────────────────────
if "theme_mode" not in st.session_state:
    st.session_state["theme_mode"] = "Light"

col_spacer, col_toggle = st.columns([0.85, 0.15])
with col_toggle:
    is_dark = st.toggle("🌙 Dark Mode", value=(st.session_state["theme_mode"] == "Dark"))
    st.session_state["theme_mode"] = "Dark" if is_dark else "Light"

if st.session_state["theme_mode"] == "Dark":
    theme_css = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    .stMarkdown p, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4, .stMarkdown h5, .stMarkdown h6 {
        color: #f0f9ff !important;
    }
    label, .st-emotion-cache-1629p8f p {
        color: #9bb3c8 !important;
        font-weight: 500 !important;
    }
    ::placeholder {
        color: #475569 !important;
    }

    .stApp {
        background: radial-gradient(circle at top left, rgba(45,212,191,0.12), transparent 30%),
                    radial-gradient(circle at 80% 10%, rgba(56,189,248,0.10), transparent 30%),
                    linear-gradient(180deg, #071219 0%, #081a22 100%);
    }
    header[data-testid="stHeader"] { background: transparent; }
    .hero {
        background: rgba(9,19,33,0.90);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 24px;
        padding: 32px 36px;
        margin-bottom: 28px;
        backdrop-filter: blur(18px);
    }
    .hero h1 {
        margin: 0 0 8px;
        font-size: 2.1rem;
        font-weight: 800;
        background: linear-gradient(135deg, #2dd4bf, #38bdf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .hero p { margin: 0; color: #9bb3c8; font-size: 1rem; line-height: 1.7; }
    .product-card {
        background: rgba(10,20,35,0.92);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 20px;
        padding: 20px;
        margin-bottom: 0px;
        display: flex;
        flex-direction: column;
        height: 100%;
    }
    .product-card:hover {
        border-color: rgba(45,212,191,0.30);
        box-shadow: 0 16px 40px rgba(0,0,0,0.25);
    }
    .product-img {
        width: 100%;
        height: 200px;
        object-fit: cover;
        border-radius: 12px;
        margin-bottom: 16px;
        background-color: rgba(255,255,255,0.02);
        border: 1px solid rgba(255,255,255,0.05);
    }
    .product-title {
        font-size: 0.97rem;
        font-weight: 700;
        color: #f0f9ff;
        line-height: 1.45;
        margin-bottom: 6px;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        height: 2.9rem;
    }
    .crisp-title {
        font-size: 0.97rem;
        font-weight: 700;
        color: #2dd4bf;
        line-height: 1.45;
        margin-bottom: 6px;
        font-style: italic;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        height: 2.9rem;
    }
    .product-price {
        color: #2dd4bf;
        font-weight: 700;
        font-size: 1.05rem;
        margin-bottom: 12px;
    }
    .meta-row {
        display: flex;
        justify-content: space-between;
        font-size: 0.875rem;
        color: #9bb3c8;
        padding: 5px 0;
        border-bottom: 1px solid rgba(255,255,255,0.05);
    }
    .meta-row span:first-child { color: rgba(255,255,255,0.70); font-weight: 500; }
    .view-btn {
        display: inline-block;
        margin-top: 14px;
        padding: 8px 16px;
        background: rgba(45,212,191,0.12);
        border: 1px solid rgba(45,212,191,0.30);
        border-radius: 10px;
        color: #2dd4bf !important;
        font-size: 0.875rem;
        font-weight: 600;
        text-decoration: none !important;
        text-align: center;
    }
    .view-btn:hover { background: rgba(45,212,191,0.22); }
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background: rgba(9,19,33,0.85);
        border-radius: 16px;
        padding: 8px;
        border: 1px solid rgba(255,255,255,0.06);
        margin-bottom: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 12px;
        color: #9bb3c8;
        font-weight: 600;
        padding: 10px 22px;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, rgba(45,212,191,0.18), rgba(56,189,248,0.16)) !important;
        color: #f0f9ff !important;
        border-color: rgba(45,212,191,0.45) !important;
    }
    .stSelectbox > div > div,
    .stTextInput > div > div > input {
        background: rgba(18,35,56,0.95) !important;
        border: 1px solid rgba(148,163,184,0.14) !important;
        border-radius: 14px !important;
        color: #f0f9ff !important;
    }
    .stSelectbox > div > div:focus-within,
    .stTextInput > div > div > input:focus {
        border-color: #2dd4bf !important;
        box-shadow: 0 0 0 1px #2dd4bf !important;
    }
    .stButton > button {
        background: linear-gradient(135deg, #22d3ee, #0d9488) !important;
        color: #071219 !important;
        font-weight: 700 !important;
        border: none !important;
        border-radius: 14px !important;
        padding: 12px 28px !important;
        font-size: 0.95rem !important;
        width: 100%;
    }
    .stButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 14px 30px rgba(45,212,191,0.20) !important;
    }
    .stDownloadButton > button {
        background: rgba(15,30,50,0.80) !important;
        color: #f0f9ff !important;
        border: 1px solid rgba(45,212,191,0.30) !important;
    }
    .stDownloadButton > button:hover {
        border-color: rgba(45,212,191,0.60) !important;
    }
    .status-box {
        background: rgba(45,212,191,0.08);
        border: 1px solid rgba(45,212,191,0.20);
        border-radius: 12px;
        padding: 12px 18px;
        color: #2dd4bf;
        font-size: 0.9rem;
        margin-bottom: 20px;
    }
    .error-box {
        background: rgba(248,113,113,0.08);
        border: 1px solid rgba(248,113,113,0.20);
        border-radius: 12px;
        padding: 12px 18px;
        color: #f87171;
        font-size: 0.9rem;
        margin-bottom: 20px;
    }
    hr { border-color: rgba(255,255,255,0.07); }
    .enriched-value {
        color: #fbbf24;
        font-weight: 600;
    }
    .ai-badge {
        display: inline-block;
        font-size: 0.72rem;
        background: rgba(251,191,36,0.12);
        border: 1px solid rgba(251,191,36,0.30);
        border-radius: 6px;
        color: #fbbf24;
        padding: 1px 7px;
        margin-left: 6px;
        vertical-align: middle;
    }
    .summary-box {
        background: linear-gradient(135deg, rgba(15,30,50,0.80), rgba(9,19,33,0.90));
        border: 1px solid rgba(45,212,191,0.25);
        border-radius: 20px;
        padding: 28px;
        margin: 24px 0;
        box-shadow: 0 12px 40px rgba(0,0,0,0.3);
    }
    .summary-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 20px;
        padding-bottom: 15px;
        border-bottom: 1px solid rgba(255,255,255,0.08);
    }
    .summary-title {
        color: #2dd4bf;
        font-size: 1.25rem;
        font-weight: 800;
        margin: 0;
    }
    .summary-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 20px;
    }
    .summary-item {
        background: rgba(255,255,255,0.03);
        padding: 16px;
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.05);
    }
    .summary-label {
        color: #94a3b8;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 6px;
    }
    .summary-value {
        color: #f0f9ff;
        font-size: 0.95rem;
        font-weight: 500;
        line-height: 1.5;
    }
    </style>
    """
else:
    theme_css = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    .stMarkdown p, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4, .stMarkdown h5, .stMarkdown h6 {
        color: #1e293b !important;
    }
    label, .st-emotion-cache-1629p8f p {
        color: #475569 !important;
        font-weight: 500 !important;
    }
    ::placeholder {
        color: #94a3b8 !important;
    }

    .stApp {
        background: radial-gradient(circle at top left, rgba(20, 184, 166, 0.05), transparent 30%),
                    radial-gradient(circle at 80% 10%, rgba(14, 165, 233, 0.05), transparent 30%),
                    linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
    }
    header[data-testid="stHeader"] { background: transparent; }
    .hero {
        background: rgba(255, 255, 255, 0.90);
        border: 1px solid rgba(226, 232, 240, 0.8);
        border-radius: 24px;
        padding: 32px 36px;
        margin-bottom: 28px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
    }
    .hero h1 {
        margin: 0 0 8px;
        font-size: 2.1rem;
        font-weight: 800;
        background: linear-gradient(135deg, #0d9488, #0284c7);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .hero p { margin: 0; color: #475569; font-size: 1rem; line-height: 1.7; }
    .product-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 20px;
        padding: 20px;
        margin-bottom: 0px;
        display: flex;
        flex-direction: column;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
        transition: all 0.2s ease-in-out;
        height: 550px;
    }
    .product-card:hover {
        border-color: #cbd5e1;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
        transform: translateY(-2px);
    }
    .product-img {
        width: 100%;
        height: 200px;
        object-fit: cover;
        border-radius: 12px;
        margin-bottom: 16px;
        background-color: #f8fafc;
        border: 1px solid #f1f5f9;
    }
    .product-title {
        font-size: 0.97rem;
        font-weight: 700;
        color: #1e293b;
        line-height: 1.45;
        margin-bottom: 6px;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        height: 2.9rem;
    }
    .crisp-title {
        font-size: 0.97rem;
        font-weight: 700;
        color: #0d9488;
        line-height: 1.45;
        margin-bottom: 6px;
        font-style: italic;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        height: 2.9rem;
    }
    .product-price {
        color: #0f766e;
        font-weight: 800;
        font-size: 1.1rem;
        margin-bottom: 12px;
    }
    .meta-row {
        display: flex;
        justify-content: space-between;
        font-size: 0.875rem;
        color: #64748b;
        padding: 6px 0;
        border-bottom: 1px solid #f1f5f9;
    }
    .meta-row span:first-child { color: #64748b; font-weight: 500; }
    .meta-row span:last-child { color: #334155; font-weight: 600; }
    .view-btn {
        display: inline-block;
        margin-top: 14px;
        padding: 8px 16px;
        background: #f0fdfa;
        border: 1px solid #ccfbf1;
        border-radius: 10px;
        color: #0d9488 !important;
        font-size: 0.875rem;
        font-weight: 600;
        text-decoration: none !important;
        text-align: center;
        transition: all 0.2s;
    }
    .view-btn:hover { background: #ccfbf1; border-color: #99f6e4; }
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background: #ffffff;
        border-radius: 16px;
        padding: 8px;
        border: 1px solid #e2e8f0;
        margin-bottom: 24px;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 12px;
        color: #64748b;
        font-weight: 600;
        padding: 10px 22px;
    }
    .stTabs [aria-selected="true"] {
        background: #f0fdfa !important;
        color: #0d9488 !important;
        border: 1px solid #ccfbf1 !important;
    }
    .stSelectbox > div > div,
    .stTextInput > div > div > input {
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 14px !important;
        color: #0f172a !important;
    }
    .stSelectbox > div > div:focus-within,
    .stTextInput > div > div > input:focus {
        border-color: #0d9488 !important;
        box-shadow: 0 0 0 1px #0d9488 !important;
    }
    .stButton > button {
        background: linear-gradient(135deg, #14b8a6, #0891b2) !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        border: none !important;
        border-radius: 14px !important;
        padding: 12px 28px !important;
        font-size: 0.95rem !important;
        width: 100%;
        box-shadow: 0 4px 6px -1px rgba(20, 184, 166, 0.2) !important;
    }
    .stButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 10px -1px rgba(20, 184, 166, 0.3) !important;
    }
    .stDownloadButton > button {
        background: #ffffff !important;
        color: #0f766e !important;
        border: 1px solid #cbd5e1 !important;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05) !important;
    }
    .stDownloadButton > button:hover {
        border-color: #94a3b8 !important;
        background: #f8fafc !important;
    }
    .status-box {
        background: #f0fdfa;
        border: 1px solid #ccfbf1;
        border-radius: 12px;
        padding: 12px 18px;
        color: #0f766e;
        font-size: 0.95rem;
        margin-bottom: 20px;
        font-weight: 500;
    }
    .error-box {
        background: #fef2f2;
        border: 1px solid #fee2e2;
        border-radius: 12px;
        padding: 12px 18px;
        color: #b91c1c;
        font-size: 0.95rem;
        margin-bottom: 20px;
        font-weight: 500;
    }
    hr { border-color: #e2e8f0; }
    
    .enriched-value {
        color: #d97706;
        font-weight: 700;
    }
    .ai-badge {
        display: inline-block;
        font-size: 0.72rem;
        background: #fef3c7;
        border: 1px solid #fde68a;
        border-radius: 6px;
        color: #d97706;
        padding: 1px 7px;
        margin-left: 6px;
        vertical-align: middle;
        font-weight: 600;
    }
    .summary-box {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        color: #334155;
    }
    .summary-box h4 {
        color: #0f172a;
        margin-top: 0;
        margin-bottom: 16px;
    }
    </style>
    """

st.markdown(theme_css, unsafe_allow_html=True)

# ── Hero ───────────────────────────────────────────────────────────────────────

st.markdown(
    """
    <div class="hero">
        <h1>🔍 Product Research Dashboard</h1>
        <p>Search Google Shopping, scrape Amazon listings, and use AI to discover & analyse trending products across multiple markets.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── OpenAI client (lazy) ──────────────────────────────────────────────────────

@st.cache_resource
def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


@st.cache_resource
def get_async_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return AsyncOpenAI(api_key=api_key)


async def async_crisp_name(title: str, client: AsyncOpenAI) -> str:
    """Use OpenAI asynchronously to shorten a product name."""
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a product naming expert. Your job is to shorten messy, "
                        "long product titles from e-commerce sites into a clean, concise name "
                        "that keeps ALL important information (brand, key specs, size, model). "
                        "Remove only filler words, repetition, and marketing fluff. "
                        "Return ONLY the shortened name, nothing else."
                    ),
                },
                {"role": "user", "content": f"Shorten this product name:\n{title}"},
            ],
            max_tokens=80,
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return title


async def async_enrich_product(title: str, link: str, client: AsyncOpenAI) -> dict:
    """Ask OpenAI asynchronously to fill in missing product details."""
    prompt = (
        f"A product is listed on an e-commerce site with the following details:\n"
        f"Title: {title}\n"
        f"Product URL: {link}\n\n"
        f"Based on your knowledge of this product and similar products, provide:\n"
        f"1. An estimated customer rating (out of 5, e.g. 4.3)\n"
        f"2. An approximate number of customer reviews (e.g. 1,240)\n"
        f"3. A brief 1-sentence product description (max 20 words)\n\n"
        f"Return ONLY a valid JSON object with exactly these keys: rating, reviews, description.\n"
        f"No extra text or markdown fences."
    )
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.3,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception:
        return {}


def crisp_name(title: str) -> str:
    """Use OpenAI to shorten a product name without losing key info."""
    client = get_openai_client()
    if not client:
        return title
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a product naming expert. Your job is to shorten messy, "
                        "long product titles from e-commerce sites into a clean, concise name "
                        "that keeps ALL important information (brand, key specs, size, model). "
                        "Remove only filler words, repetition, and marketing fluff. "
                        "Return ONLY the shortened name, nothing else."
                    ),
                },
                {"role": "user", "content": f"Shorten this product name:\n{title}"},
            ],
            max_tokens=80,
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return title


def enrich_product(title: str, link: str) -> dict:
    """Ask OpenAI to fill in missing product details (rating, reviews, description)."""
    client = get_openai_client()
    if not client:
        return {}
    prompt = (
        f"A product is listed on an e-commerce site with the following details:\n"
        f"Title: {title}\n"
        f"Product URL: {link}\n\n"
        f"Based on your knowledge of this product and similar products, provide:\n"
        f"1. An estimated customer rating (out of 5, e.g. 4.3)\n"
        f"2. An approximate number of customer reviews (e.g. 1,240)\n"
        f"3. A brief 1-sentence product description (max 20 words)\n\n"
        f"Return ONLY a valid JSON object with exactly these keys: rating, reviews, description.\n"
        f"No extra text or markdown fences."
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.3,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception:
        return {}


def ai_verify_amazon_domain(country_name: str) -> bool:
    """Use OpenAI to determine if a country has a dedicated personal Amazon domain."""
    client = get_openai_client()
    if not client:
        return True # Default to True if AI check fails to not block users
    
    prompt = (
        f"Does the country '{country_name}' have its own dedicated, native Amazon domain? "
        f"Examples of YES: 'Saudi Arabia' (amazon.sa), 'United Kingdom' (amazon.co.uk), 'India' (amazon.in), 'Australia' (amazon.com.au), 'United States' (amazon.com). "
        f"Examples of NO: 'Kuwait' (uses amazon.ae), 'Qatar' (uses amazon.ae), 'Bahrain' (uses amazon.ae). "
        f"Answer ONLY 'YES' if it has its own dedicated local Amazon site, or 'NO' if it primarily uses a neighboring country's Amazon site."
    )
    
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0.0,
        )
        answer = resp.choices[0].message.content.strip().upper()
        return "YES" in answer
    except Exception:
        return True


def generate_market_summary(products: list) -> str:
    """Ask OpenAI to generate a market summary based on a list of products."""
    client = get_openai_client()
    if not client or not products:
        return "Unable to generate summary."
    
    prompt = (
        f"You are an expert e-commerce market analyst. Analyze the following products "
        f"and provide a professional, structured market summary.\n\n"
        f"Return ONLY a valid JSON object with these keys:\n"
        f"1. average_price: (string, e.g., '$20 - $50')\n"
        f"2. top_brands: (string, comma-separated)\n"
        f"3. common_features: (string, key shared specs)\n"
        f"4. market_sentiment: (string, 1-2 sentences on trend/opportunity)\n\n"
        f"Products:\n{json.dumps(products, indent=2)}"
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        return {"error": str(e)}


def openai_product_search(query: str, country: str, num_results: int = 10) -> list[dict]:
    """Ask OpenAI to generate a list of real/representative products for a query."""
    client = get_openai_client()
    if not client:
        return []
    prompt = (
        f"You are a product research assistant. A user is researching '{query}' products "
        f"for the {country} market. Generate a list of {num_results} realistic and currently "
        f"popular products for this query. For each product include: title, brand, estimated price "
        f"(in local currency), key features (2-3 bullet points), estimated rating (out of 5), "
        f"and approximate number of reviews. Return ONLY a valid JSON array with objects having "
        f"these exact keys: title, brand, price, features (array of strings), rating, reviews. "
        f"No extra text or markdown."
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.7,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        st.error(f"OpenAI error: {e}")
        return []


# ── Helpers for batch actions and export ────────────────────────────────────────

def prepare_dataframe(products: list, source_key: str) -> pd.DataFrame:
    """Prepare a DataFrame combining original and enriched/crisped data for export."""
    rows = []
    for i, p in enumerate(products):
        row = p.copy()
        card_key = f"{source_key}_{i}"
        
        crisp_state_key = f"crisp_result_{card_key}"
        if crisp_state_key in st.session_state:
            row['title_crisped'] = st.session_state[crisp_state_key]
        else:
            row['title_crisped'] = ""
            
        enrich_state_key = f"enrich_result_{card_key}"
        if enrich_state_key in st.session_state:
            enriched = st.session_state[enrich_state_key]
            if enriched.get("rating"): row['rating_ai'] = enriched['rating']
            if enriched.get("reviews"): row['reviews_ai'] = enriched['reviews']
            if enriched.get("description"): row['description_ai'] = enriched['description']
            
        rows.append(row)
    
    df = pd.DataFrame(rows)
    # Reorder columns to put 'title_crisped' right after 'title' if 'title' is present
    if not df.empty and 'title' in df.columns and 'title_crisped' in df.columns:
        cols = list(df.columns)
        cols.remove('title_crisped')
        try:
            title_idx = cols.index('title')
            cols.insert(title_idx + 1, 'title_crisped')
            df = df[cols]
        except ValueError:
            pass
    return df


def render_action_bar(products: list, source_key: str):
    """Render action buttons: Enrich All, Crisp All, AI Summary, Export to CSV."""
    if not products:
        return

    st.markdown("<br>", unsafe_allow_html=True)
    
    # Check if this is the AI tab, which does not need Crisp All or Enrich All
    is_ai_tab = (source_key == "ai")
    
    if is_ai_tab:
        col1, col3, _ = st.columns([1.2, 1.4, 3.4])
    else:
        col1, col1b, col2, col3, _ = st.columns([1.2, 1.2, 1.4, 1.4, 0.8])
    
    crisp_clicked = False
    enrich_clicked = False
    
    # Export CSV
    with col1:
        df = prepare_dataframe(products, source_key)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"product_research_{source_key}.csv",
            mime="text/csv",
            key=f"csv_{source_key}"
        )
        
    if not is_ai_tab:
        # Crisp All
        with col1b:
            crisp_clicked = st.button("✨ Crisp All", key=f"crisp_all_{source_key}", help="Shorten all product names on this page using AI.")

        # Enrich All
        with col2:
            enrich_clicked = st.button("⚡ Enrich All Missing", key=f"enrich_all_{source_key}", help="Use AI to fill in missing ratings/reviews for all products on this page.")
            
    # AI Market Summary
    summary_key = f"summary_{source_key}"
    with col3:
        summary_clicked = st.button("📊 Generate AI Summary", key=f"btn_{summary_key}", help="Generate a market insights summary using AI.")

    # Process actions outside columns to prevent layout bugs during spinner execution
    if crisp_clicked:
        with st.spinner("Shortening all product names concurrently…"):
            async_client = get_async_openai_client()
            if async_client:
                async def run_crisp_all():
                    tasks = []
                    keys = []
                    for i, p in enumerate(products):
                        title = p.get('title') or p.get('position_text') or ''
                        if title:
                            crisp_state_key = f"crisp_result_{source_key}_{i}"
                            if crisp_state_key not in st.session_state:
                                tasks.append(async_crisp_name(title, async_client))
                                keys.append(crisp_state_key)
                    if tasks:
                        results = await asyncio.gather(*tasks)
                        for k, res in zip(keys, results):
                            st.session_state[k] = res
                asyncio.run(run_crisp_all())
        st.rerun()

    if enrich_clicked:
        with st.spinner("Enriching products concurrently..."):
            async_client = get_async_openai_client()
            if async_client:
                async def run_enrich_all():
                    tasks = []
                    keys = []
                    for i, p in enumerate(products):
                        rating = p.get('rating') or p.get('star_rating') or "N/A"
                        reviews = p.get('reviews') or p.get('review_count') or "N/A"
                        link = p.get('product_link') or p.get('link') or p.get('source') or "#"
                        
                        if (not rating or rating == "N/A" or not reviews or reviews == "N/A") and link and link != "#":
                            enrich_state_key = f"enrich_result_{source_key}_{i}"
                            if enrich_state_key not in st.session_state:
                                tasks.append(async_enrich_product(p.get('title', ''), link, async_client))
                                keys.append(enrich_state_key)
                    if tasks:
                        results = await asyncio.gather(*tasks)
                        for k, res in zip(keys, results):
                            if res:
                                st.session_state[k] = res
                asyncio.run(run_enrich_all())
        st.rerun()

    if summary_clicked:
        with st.spinner("Analyzing market data..."):
            df_clean = prepare_dataframe(products, source_key)
            # Keep it concise for tokens, select only available columns
            cols_to_use = [c for c in ['title', 'price', 'rating', 'star_rating'] if c in df_clean.columns]
            clean_list = df_clean[cols_to_use].head(20).to_dict('records')
            summary = generate_market_summary(clean_list)
            st.session_state[summary_key] = summary
                
    if summary_key in st.session_state:
        s = st.session_state[summary_key]
        if isinstance(s, dict) and "error" not in s:
            html = f"""
            <div class="summary-box">
                <div class="summary-header">
                    <span style="font-size:1.5rem;">📊</span>
                    <h4 class="summary-title">Market Insights Summary</h4>
                </div>
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-label">Average Price</div>
                        <div class="summary-value">{s.get('average_price', 'N/A')}</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-label">Top Brands</div>
                        <div class="summary-value">{s.get('top_brands', 'N/A')}</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-label">Common Features</div>
                        <div class="summary-value">{s.get('common_features', 'N/A')}</div>
                    </div>
                    <div class="summary-item" style="grid-column: span 2;">
                        <div class="summary-label">Market Sentiment & Opportunity</div>
                        <div class="summary-value">{s.get('market_sentiment', 'N/A')}</div>
                    </div>
                </div>
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)
        else:
            st.error(f"Could not generate summary: {s.get('error', 'Unknown error')}")

    st.markdown("<hr style='margin-bottom: 24px;'>", unsafe_allow_html=True)


# ── Helper: render a product card ─────────────────────────────────────────────

def render_product_card(title, price, rank, rating, reviews, link, thumbnail=None, card_key=None):
    """Render a styled product card with Crisp Name + Enrich with AI buttons."""
    crisp_state_key = f"crisp_result_{card_key}" if card_key else None
    enrich_state_key = f"enrich_result_{card_key}" if card_key else None

    # Resolve crisped title
    display_title = title or "Untitled product"
    title_class = "product-title"
    if crisp_state_key and crisp_state_key in st.session_state:
        display_title = st.session_state[crisp_state_key]
        title_class = "crisp-title"

    # Resolve enriched data
    enriched = st.session_state.get(enrich_state_key, {}) if enrich_state_key else {}
    ai_badge = '<span class="ai-badge">AI</span>'
    display_rating = f'<span class="enriched-value">{enriched["rating"]}</span>{ai_badge}' if enriched.get("rating") else (rating or "N/A")
    display_reviews = f'<span class="enriched-value">{enriched["reviews"]}</span>{ai_badge}' if enriched.get("reviews") else (reviews or "N/A")
    desc = enriched.get("description", "")
    desc_row = f'<div style="color:#94a3b8;font-size:0.83rem;margin:8px 0 4px;font-style:italic;">💡 {desc}</div>' if desc else ""
    link_html = f'<a class="view-btn" href="{link}" target="_blank" rel="noopener noreferrer">Check Site →</a>' if link and link != "#" else ""
    
    display_price = price or "Price unavailable"
    price_html = f'<div class="product-price">{display_price}</div>' if display_price.lower() != "check site" else ""
    
    img_html = f'<img src="{thumbnail}" class="product-img">' if thumbnail else ""

    # Build card HTML as a single string (no blank lines — they break Streamlit markdown)
    html = (
        f'<div class="product-card">'
        f'{img_html}'
        f'<div class="{title_class}">{display_title}</div>'
        f'{price_html}'
        f'{desc_row}'
        f'<div style="flex-grow: 1;"></div>' # Push following items to bottom
        f'<div class="meta-row"><span>Rank</span><span>{rank or "N/A"}</span></div>'
        f'<div class="meta-row"><span>Rating</span><span>{display_rating}</span></div>'
        f'<div class="meta-row"><span>Reviews</span><span>{display_reviews}</span></div>'
        f'{link_html}'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

    # Show buttons conditionally
    if card_key:
        already_crisped = bool(crisp_state_key in st.session_state and st.session_state[crisp_state_key])
        already_enriched = bool(enriched)
        
        if already_crisped and already_enriched:
            # Both done! No buttons needed.
            pass
        elif already_crisped:
            # Only enrich button needed
            btn_label = "✅ Enriched" if already_enriched else "🔍 Enrich with AI"
            if st.button(btn_label, key=f"enrich_{card_key}", disabled=already_enriched):
                with st.spinner("Enriching…"):
                    data = enrich_product(title or "", link or "")
                    if data:
                        st.session_state[enrich_state_key] = data
                st.rerun()
        elif already_enriched:
            # Only crisp button needed
            if st.button("✨ Crisp Name", key=f"crisp_{card_key}"):
                with st.spinner("Crisping…"):
                    st.session_state[crisp_state_key] = crisp_name(title or "")
                st.rerun()
        else:
            # Show both side-by-side
            col_left, col_right = st.columns(2)
            with col_left:
                if st.button("✨ Crisp Name", key=f"crisp_{card_key}"):
                    with st.spinner("Crisping…"):
                        st.session_state[crisp_state_key] = crisp_name(title or "")
                    st.rerun()
            with col_right:
                btn_label = "✅ Enriched" if already_enriched else "🔍 Enrich with AI"
                if st.button(btn_label, key=f"enrich_{card_key}", disabled=already_enriched):
                    with st.spinner("Enriching…"):
                        data = enrich_product(title or "", link or "")
                        if data:
                            st.session_state[enrich_state_key] = data
                    st.rerun()


def render_openai_card(p: dict, idx: int):
    """Render a product card for OpenAI-generated results with category image and localized shop link."""
    import urllib.parse  # used for quote_plus below
    
    title = p.get("title", "Untitled")
    features = p.get("features", [])
    features_html = "".join(f'<li style="color:#9bb3c8;font-size:0.84rem;">{f}</li>' for f in features)

    # Get localized Amazon domain based on selected AI country
    country_name = st.session_state.get("ai_country", "United States")
    amazon_country_key = AMAZON_COUNTRIES.get(country_name, "united-states")
    domain = AMAZON_DOMAINS.get(amazon_country_key, "https://www.amazon.com")
    
    # Generate direct localized Amazon search link
    escaped_title = urllib.parse.quote_plus(title)
    buy_link = f"{domain}/s?k={escaped_title}"
    
    # Resolve category-based premium image with specific keyword intelligence (Removed for AI Search)
    img_html = ""
    
    # Styled buy link button matching the card design
    links_html = f'<a class="view-btn" href="{buy_link}" target="_blank" rel="noopener noreferrer" style="margin-top:14px;background:rgba(251,191,36,0.12);border:1px solid rgba(251,191,36,0.30);color:#fbbf24 !important;text-align:center;display:block;">Check on Amazon →</a>'

    html = (
        f'<div class="product-card" style="height: auto; min-height: 250px;">'
        f'<div class="product-title">{title}</div>'
        f'<div style="color:#7dd3fc;font-size:0.85rem;margin-bottom:8px;">{p.get("brand","")}</div>'
        f'<div class="product-price">{p.get("price","N/A")}</div>'
        f'<ul style="margin:8px 0 12px 16px;padding:0;">{features_html}</ul>'
        f'<div style="flex-grow: 1;"></div>'
        f'<div class="meta-row"><span>Rating</span><span>⭐ {p.get("rating","N/A")}</span></div>'
        f'<div class="meta-row"><span>Reviews</span><span>{p.get("reviews","N/A")}</span></div>'
        f'{links_html}'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_search, tab_amazon, tab_ai, tab_deals = st.tabs(
    ["🛒 Google Shopping", "📦 Amazon Scraper", "🤖 AI Product Search", "🏷️ Amazon Deal Scraper"]
)

# ════════════════════════════════════════════════════════════════════
# TAB 1 — Google Shopping Search
# ════════════════════════════════════════════════════════════════════
with tab_search:
    st.markdown("#### Search Google Shopping")

    col1, col2, col3, col4 = st.columns([1.5, 3, 1.5, 1])
    with col1:
        search_country = st.selectbox("Country", list(COUNTRY_CODES.keys()), key="s_country")
    with col2:
        search_query = st.text_input("Search Query", placeholder="e.g. wireless earbuds", key="s_query")
    with col3:
        search_category = st.selectbox("Category", list(SITE_CATEGORIES.keys()), key="s_cat")
    with col4:
        st.markdown("<br>", unsafe_allow_html=True)
        search_clicked = st.button("Search", key="s_btn")



    if search_clicked:
        if not search_query.strip():
            st.markdown('<div class="error-box">⚠️ Please enter a search query to continue.</div>', unsafe_allow_html=True)
        else:
            api_key = os.getenv("SERP_API_KEY")
            if not api_key:
                st.markdown('<div class="error-box">❌ SERP API key not configured.</div>', unsafe_allow_html=True)
            else:
                with st.spinner("Fetching Google Shopping results…"):
                    try:
                        gl = COUNTRY_CODES[search_country]
                        query = search_query.strip()
                        
                        # Prepend category if specified
                        if SITE_CATEGORIES[search_category]:
                            query = f"{search_category} {query}"

                        # Route through FastAPI backend
                        encoded_query = _urllib_parse.quote(query, safe="")
                        resp = _http.get(
                            f"{_API_BASE}/search/{gl}/{encoded_query}",
                            timeout=30,
                        )
                        resp.raise_for_status()
                        data = resp.json()

                        if "error" in data:
                            st.markdown(f'<div class="error-box">❌ {data["error"]}</div>', unsafe_allow_html=True)
                            products = []
                        else:
                            if data.get("fallback_used"):
                                st.info(f"ℹ️ Google Shopping is limited in {search_country}. Falling back to standard search...")
                            products = data.get("products", [])

                        if not products:
                            st.markdown('<div class="status-box">No products found for this query.</div>', unsafe_allow_html=True)
                        else:
                            st.markdown(f'<div class="status-box">✅ {len(products)} product(s) found.</div>', unsafe_allow_html=True)
                            st.session_state["serp_products"] = products
                            
                            # Clear old summaries/enrichments
                            keys_to_clear = [k for k in st.session_state.keys() if "serp" in k and k != "serp_products"]
                            for k in keys_to_clear:
                                del st.session_state[k]
                    except Exception as e:
                        st.markdown(f'<div class="error-box">❌ Error: {e}</div>', unsafe_allow_html=True)

    if "serp_products" in st.session_state:
        products = st.session_state["serp_products"]
        
        render_action_bar(products, "serp")
        
        for i in range(0, len(products[:30]), 3):
            cols = st.columns(3)
            for j, p in enumerate(products[i:i+3]):
                with cols[j]:
                    render_product_card(
                        title=p.get("title") or p.get("position_text") or "No title",
                        price=p.get("price") or p.get("inline_price") or "Price unavailable",
                        rank=p.get("rank") or p.get("position", "N/A"),
                        rating=p.get("rating") or p.get("star_rating") or "N/A",
                        reviews=p.get("reviews") or p.get("review_count") or "N/A",
                        link=p.get("product_link") or p.get("link") or p.get("source") or "#",
                        thumbnail=p.get("thumbnail"),
                        card_key=f"serp_{i+j}",
                    )
            st.markdown("<div style='margin-bottom: 24px;'></div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# TAB 2 — Amazon Scraper
# ════════════════════════════════════════════════════════════════════
with tab_amazon:
    st.markdown("#### Scrape Amazon Listings")
    st.markdown("<p style='color:#9bb3c8;margin-bottom:20px;'>Pull the latest Amazon bestseller and trend pages for supported regional stores.</p>", unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns([1.5, 1.5, 2, 1])
    with col1:
        amazon_country_label = st.selectbox("Country", list(AMAZON_COUNTRIES.keys()), key="a_country")
    with col2:
        amazon_page_label = st.selectbox("Page Type", list(PAGE_TYPES.keys()), key="a_page")
    with col3:
        amazon_category_label = st.selectbox("Category", list(CATEGORIES.keys()), key="a_cat")
    with col4:
        st.markdown("<br>", unsafe_allow_html=True)
        amazon_clicked = st.button("Scrape Amazon", key="a_btn")

    if amazon_clicked:
        # 1. AI Verification Check
        with st.spinner("Checking Amazon domain availability…"):
            has_personal_domain = ai_verify_amazon_domain(amazon_country_label)
        
        if not has_personal_domain:
            st.error(f"Unable to scrape as there is no personal amazon domain for {amazon_country_label} country")
        else:
            country_key = AMAZON_COUNTRIES[amazon_country_label]
            page_key = PAGE_TYPES[amazon_page_label]
            category_key = CATEGORIES[amazon_category_label]
        
        status_msg = f"Scraping Amazon {amazon_country_label} — {amazon_page_label}"
        if amazon_category_label != "All Categories":
            status_msg += f" ({amazon_category_label})"
        
        with st.spinner(f"{status_msg}…"):
            try:
                # Route through FastAPI backend
                api_params = {"category": category_key} if category_key else {}
                resp = _http.get(
                    f"{_API_BASE}/amazon/{country_key}/{page_key}",
                    params=api_params,
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()

                if "error" in data:
                    error_msg = data["error"]
                    if "no amazon domain" in error_msg.lower():
                        st.error(f"Unable to scrape as there is no amazon domain for {amazon_country_label} country")
                    else:
                        st.markdown(f'<div class="error-box">❌ {error_msg}</div>', unsafe_allow_html=True)
                else:
                    products = data.get("products", [])
                    if not products:
                        st.markdown('<div class="status-box">No products were returned from Amazon.</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="status-box">✅ {len(products)} product(s) scraped.</div>', unsafe_allow_html=True)
                        st.session_state["amazon_products"] = products
                        # Clear old summaries/enrichments
                        keys_to_clear = [k for k in st.session_state.keys() if "amz" in k and k != "amazon_products"]
                        for k in keys_to_clear:
                            del st.session_state[k]
            except Exception as e:
                st.markdown(f'<div class="error-box">❌ Unable to retrieve Amazon products: {e}</div>', unsafe_allow_html=True)

    if "amazon_products" in st.session_state:
        products = st.session_state["amazon_products"]
        
        render_action_bar(products, "amz")
        
        for i in range(0, len(products), 3):
            cols = st.columns(3)
            for j, p in enumerate(products[i:i+3]):
                with cols[j]:
                    render_product_card(
                        title=p.get("title"),
                        price=p.get("price"),
                        rank=p.get("rank"),
                        rating=p.get("rating"),
                        reviews=p.get("reviews"),
                        link=p.get("link") or "#",
                        thumbnail=p.get("thumbnail"),
                        card_key=f"amz_{i+j}",
                    )
            st.markdown("<div style='margin-bottom: 24px;'></div>", unsafe_allow_html=True)





# ════════════════════════════════════════════════════════════════════
# TAB 4 — AI Product Search (OpenAI)
# ════════════════════════════════════════════════════════════════════
with tab_ai:
    st.markdown("#### 🤖 AI-Powered Product Search")
    st.markdown(
        "<p style='color:#9bb3c8;margin-bottom:20px;'>Ask OpenAI to research and surface trending products "
        "for any query and market — no scraping required. Each result includes key specs, price estimates, "
        "and ratings.</p>",
        unsafe_allow_html=True,
    )

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        st.markdown(
            '<div class="error-box">⚠️ <strong>OPENAI_API_KEY</strong> is not set in your <code>.env</code> file. '
            "Add it to enable AI search.</div>",
            unsafe_allow_html=True,
        )
    else:
        col1, col2, col3, col4, col5 = st.columns([1.5, 3, 1.5, 1, 1])
        with col1:
            ai_country = st.selectbox("Country / Market", list(COUNTRY_CODES.keys()), key="ai_country")
        with col2:
            ai_query = st.text_input("Product Query (Optional)", placeholder="e.g. portable blenders", key="ai_query")
        with col3:
            ai_category = st.selectbox("Category", list(SITE_CATEGORIES.keys()), key="ai_category")
        with col4:
            ai_num = st.number_input("Results", min_value=3, max_value=20, value=9, key="ai_num")
        with col5:
            st.markdown("<br>", unsafe_allow_html=True)
            ai_clicked = st.button("Ask AI", key="ai_btn")

        if ai_clicked:
            # Country is always required, Category must be selected if no query
            if not ai_country:
                st.markdown('<div class="error-box">⚠️ Please select a **Country**.</div>', unsafe_allow_html=True)
            elif not ai_query.strip() and (ai_category == "All Categories" or not ai_category):
                st.markdown('<div class="error-box">⚠️ Please provide either a **Search Query** or select a **Category**.</div>', unsafe_allow_html=True)
            else:
                with st.spinner("AI is researching..."):
                    # Combine query and category for the AI
                    final_query = ai_query.strip()
                    if ai_category and ai_category != "All Categories":
                        if final_query:
                            final_query = f"{ai_category} {final_query}"
                        else:
                            final_query = f"trending products in {ai_category}"
                    
                    results = openai_product_search(final_query, ai_country, int(ai_num))
                    if results:
                        st.session_state["ai_products"] = results
                        st.markdown(f'<div class="status-box">✅ {len(results)} product(s) generated by AI.</div>', unsafe_allow_html=True)
                        
                        # Clear old summaries/enrichments
                        keys_to_clear = [k for k in st.session_state.keys() if "ai" in k and k != "ai_products"]
                        for k in keys_to_clear:
                            del st.session_state[k]

        if "ai_products" in st.session_state:
            products = st.session_state["ai_products"]

            render_action_bar(products, "ai")

            for i in range(0, len(products), 3):
                cols = st.columns(3)
                for j, p in enumerate(products[i:i+3]):
                    with cols[j]:
                        render_openai_card(p, i+j)
                st.markdown("<div style='margin-bottom: 24px;'></div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# TAB 4 — Amazon Deal Scraper (helpers + UI)
# ════════════════════════════════════════════════════════════════════

def _run_banner_scrape(zip_code: str, log_q: queue.Queue, result_q: queue.Queue):
    """Scrape Amazon homepage deal banners in a background thread (own asyncio loop)."""
    import asyncio
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

    async def _inner():
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = await browser.new_page(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            log_q.put("🌐 Opening Amazon homepage...")
            await page.goto("https://www.amazon.com", wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            if zip_code:
                log_q.put(f"📍 Setting zip code to {zip_code}...")
                is_modal_visible = await page.locator("#GLUXZipUpdateInput").is_visible()
                if not is_modal_visible:
                    await page.locator("#nav-global-location-slot").click()
                    await page.wait_for_timeout(2000)
                    is_modal_visible = await page.locator("#GLUXZipUpdateInput").is_visible()

                if is_modal_visible:
                    await page.locator("#GLUXZipUpdateInput").fill(zip_code)
                    await page.wait_for_timeout(1000)
                    await page.locator("#GLUXZipUpdate input").click()
                    await page.wait_for_timeout(3000)
                    done_btn = page.locator("input[name='glowDoneButton']")
                    confirm_close = page.locator("#GLUXConfirmClose").first
                    if await done_btn.is_visible():
                        await done_btn.click()
                    elif await confirm_close.is_visible():
                        await confirm_close.click()
                    else:
                        await page.reload()
                    await page.wait_for_timeout(4000)
                    try:
                        loc_text = await page.locator("#glow-ingress-line2").text_content()
                        log_q.put(f"✅ Location set: {loc_text.strip() if loc_text else 'Unknown'}")
                    except Exception:
                        pass
                else:
                    log_q.put("⚠️ Zip input not visible — skipping location set.")

            soup = BeautifulSoup(await page.content(), "html.parser")
            deals = {}
            hero_sections = soup.select(".a-carousel-card")
            log_q.put(f"🔎 Found {len(hero_sections)} carousel card(s) — extracting banners...")

            for section in hero_sections:
                title = ""
                img = section.find("img")
                if img and img.get("alt"):
                    title = img.get("alt").strip()
                if not title:
                    texts = section.get_text("\n", strip=True).split("\n")
                    cleaned = [t.strip() for t in texts if len(t.strip()) > 8]
                    if cleaned:
                        title = " ".join(cleaned[:3])
                if title:
                    garbage = ["video player", "dialog window", "transparency", "prime video", "watch ", "stream"]
                    if any(g in title.lower() for g in garbage):
                        continue
                    if "amazon" not in title.lower() or "off" in title.lower() or "shop" in title.lower():
                        link = ""
                        a_tag = section.find("a")
                        if a_tag and a_tag.get("href"):
                            link = a_tag.get("href").strip()
                            if link.startswith("/"):
                                link = "https://www.amazon.com" + link
                        deals[title] = link

            await browser.close()
            log_q.put(f"🏷️ Extracted {len(deals)} valid deal banner(s).")
            result_q.put(deals)

    if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_inner())
    except Exception as e:
        log_q.put(f"❌ Banner scrape error: {e}")
        result_q.put({})
    finally:
        loop.close()


def _run_products_scrape(
    deal_title: str,
    deal_link: str,
    custom_selector,
    scroll_wait_time: int,
    zip_code: str,
    log_q: queue.Queue,
    result_q: queue.Queue,
):
    """Scrape products from a deal page in a background thread. Sets zip code first to avoid India redirect."""
    import asyncio
    import builtins
    from playwright.async_api import async_playwright

    original_print = builtins.print

    def patched_print(*args, **kwargs):
        msg = " ".join(str(a) for a in args)
        log_q.put(msg)

    builtins.print = patched_print

    async def _inner():
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = await browser.new_page(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            # ── Step 1: Set US zip code on homepage first so Amazon uses correct locale ──
            if zip_code:
                log_q.put(f"📍 Setting location to zip {zip_code} before navigating to deal...")
                await page.goto("https://www.amazon.com", wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)

                is_modal_visible = await page.locator("#GLUXZipUpdateInput").is_visible()
                if not is_modal_visible:
                    try:
                        await page.locator("#nav-global-location-slot").click()
                        await page.wait_for_timeout(2000)
                        is_modal_visible = await page.locator("#GLUXZipUpdateInput").is_visible()
                    except Exception:
                        pass

                if is_modal_visible:
                    await page.locator("#GLUXZipUpdateInput").fill(zip_code)
                    await page.wait_for_timeout(800)
                    await page.locator("#GLUXZipUpdate input").click()
                    await page.wait_for_timeout(3000)
                    done_btn = page.locator("input[name='glowDoneButton']")
                    confirm_close = page.locator("#GLUXConfirmClose").first
                    if await done_btn.is_visible():
                        await done_btn.click()
                    elif await confirm_close.is_visible():
                        await confirm_close.click()
                    else:
                        await page.reload()
                    await page.wait_for_timeout(3000)
                    try:
                        loc_text = await page.locator("#glow-ingress-line2").text_content()
                        log_q.put(f"✅ Location set: {loc_text.strip() if loc_text else 'Unknown'}")
                    except Exception:
                        pass
                else:
                    log_q.put("⚠️ Zip input not visible — proceeding without location set.")

            # ── Step 2: Now navigate to the deal and scrape products ──
            log_q.put(f"🔍 Navigating to deal: {deal_title}")
            products = await get_products_from_deal(
                page, deal_link, custom_selector, scroll_wait_time
            )
            await browser.close()
            result_q.put(products)

    if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_inner())
    except Exception as e:
        log_q.put(f"❌ Product scrape error: {e}")
        result_q.put([])
    finally:
        loop.close()
        builtins.print = original_print


with tab_deals:
    st.markdown("#### 🏷️ Amazon Deal Scraper")

    if not PLAYWRIGHT_AVAILABLE:
        st.warning(
            "⚠️ **Amazon Deal Scraper is not available in this environment.**\n\n"
            "This feature uses **Playwright** (a browser automation library) to scrape live deal banners "
            "from Amazon. Playwright requires browser binaries that cannot run on Streamlit Community Cloud.\n\n"
            "✅ **Run the app locally** to use this feature:\n"
            "```\nstreamlit run app.py\n```",
            icon="🖥️",
        )
        st.stop()

    st.markdown(
        "<p style='color:#9bb3c8;margin-bottom:20px;'>Scrape live deal banners from the Amazon homepage "
        "and pull all product listings from any featured deal page in real time.</p>",
        unsafe_allow_html=True,
    )

    # ── Controls row ──────────────────────────────────────────────────
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([1.2, 1.2, 1])
    with ctrl_col1:
        deals_zip = st.text_input(
            "Zip Code (US)",
            value="41018",
            placeholder="e.g. 10001",
            key="deals_zip",
            help="Sets your Amazon delivery location for localised deal banners.",
        )
    with ctrl_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        scrape_banners_btn = st.button("🚀 Scrape Deal Banners", key="deals_scrape_btn")
    with ctrl_col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ Clear Results", key="deals_clear_btn"):
            for k in ["deals_logs", "deals_dict", "deals_products", "deals_product_logs", "deals_selected_deal"]:
                st.session_state.pop(k, None)
            st.rerun()

    # ── Trigger banner scrape ─────────────────────────────────────────
    if scrape_banners_btn:
        _log_q: queue.Queue = queue.Queue()
        _result_q: queue.Queue = queue.Queue()

        st.session_state["deals_logs"] = []
        for k in ["deals_dict", "deals_products", "deals_product_logs", "deals_selected_deal"]:
            st.session_state.pop(k, None)

        _t = threading.Thread(
            target=_run_banner_scrape,
            args=(deals_zip.strip(), _log_q, _result_q),
            daemon=True,
        )
        _t.start()

        _log_ph = st.empty()
        _live_logs: list = []

        with st.spinner("🔄 Scraping Amazon deal banners… (~20 seconds)"):
            while _t.is_alive() or not _log_q.empty():
                try:
                    while True:
                        _live_logs.append(_log_q.get_nowait())
                except queue.Empty:
                    pass
                _log_ph.code("\n".join(_live_logs), language="")
                threading.Event().wait(0.4)

        while not _log_q.empty():
            _live_logs.append(_log_q.get_nowait())
        _log_ph.code("\n".join(_live_logs), language="")

        st.session_state["deals_logs"] = _live_logs
        st.session_state["deals_dict"] = _result_q.get() if not _result_q.empty() else {}
        st.rerun()

    # ── Persisted banner-scrape log ───────────────────────────────────
    if st.session_state.get("deals_logs"):
        with st.expander("📋 Banner Scrape Log", expanded=False):
            st.code("\n".join(st.session_state["deals_logs"]), language="")

    # ── Deal selection ────────────────────────────────────────────────
    _deals_dict: dict = st.session_state.get("deals_dict", {})
    if _deals_dict:
        _deal_titles = list(_deals_dict.keys())

        st.markdown("---")
        st.markdown(f"##### 🏷️ {len(_deal_titles)} Deal Banner(s) Found — Select One to Scrape")

        _deal_options = [f"{i+1}. {t}" for i, t in enumerate(_deal_titles)]
        _selected_option = st.selectbox(
            "Choose a deal to scrape products from:",
            _deal_options,
            key="deals_select_box",
        )
        _sel_idx = _deal_options.index(_selected_option)
        _sel_title = _deal_titles[_sel_idx]
        _sel_link = _deals_dict[_sel_title]

        # ── Per-deal options ──────────────────────────────────────────
        opt_col1, opt_col2, opt_col3 = st.columns([2, 1.2, 1])
        with opt_col1:
            _custom_sel = st.text_input(
                "Custom CSS Selector (optional)",
                placeholder="e.g. .a-cardui  or  productCard  or leave blank for auto-detect",
                key="deals_custom_sel",
                help="Leave blank to auto-detect. Provide a CSS class/selector to target specific cards.",
            )
        with opt_col2:
            _wait_time = st.number_input(
                "Scroll wait (seconds)",
                min_value=2,
                max_value=30,
                value=5,
                key="deals_wait",
                help="How long to wait after scrolling for lazy-loaded content.",
            )
        with opt_col3:
            st.markdown("<br>", unsafe_allow_html=True)
            _scrape_prod_btn = st.button("🔍 Scrape Products", key="deals_prod_btn")

        if not _sel_link:
            st.markdown(
                '<div class="error-box">⚠️ This deal banner has no navigable link. Try a different deal.</div>',
                unsafe_allow_html=True,
            )
        elif _scrape_prod_btn:
            _log_q2: queue.Queue = queue.Queue()
            _result_q2: queue.Queue = queue.Queue()

            st.session_state["deals_product_logs"] = []
            st.session_state.pop("deals_products", None)
            st.session_state["deals_selected_deal"] = _sel_title

            _t2 = threading.Thread(
                target=_run_products_scrape,
                args=(
                    _sel_title,
                    _sel_link,
                    _custom_sel.strip() if _custom_sel.strip() else None,
                    int(_wait_time),
                    deals_zip.strip(),
                    _log_q2,
                    _result_q2,
                ),
                daemon=True,
            )
            _t2.start()

            _log_ph2 = st.empty()
            _live_logs2: list = []

            with st.spinner(f"🔄 Scraping products from '{_sel_title}'…"):
                while _t2.is_alive() or not _log_q2.empty():
                    try:
                        while True:
                            _live_logs2.append(_log_q2.get_nowait())
                    except queue.Empty:
                        pass
                    _log_ph2.code("\n".join(_live_logs2), language="")
                    threading.Event().wait(0.4)

            while not _log_q2.empty():
                _live_logs2.append(_log_q2.get_nowait())
            _log_ph2.code("\n".join(_live_logs2), language="")

            st.session_state["deals_product_logs"] = _live_logs2
            st.session_state["deals_products"] = _result_q2.get() if not _result_q2.empty() else []
            st.rerun()

    # ── Persisted product-scrape log ──────────────────────────────────
    if st.session_state.get("deals_product_logs"):
        with st.expander("📋 Product Scrape Log", expanded=False):
            st.code("\n".join(st.session_state["deals_product_logs"]), language="")

    # ── Render scraped products ───────────────────────────────────────
    if "deals_products" in st.session_state:
        _deal_products = st.session_state["deals_products"]
        _deal_name = st.session_state.get("deals_selected_deal", "Deal")

        st.markdown("---")
        if not _deal_products:
            st.markdown(
                '<div class="status-box">⚠️ No products found for this deal. Try a different CSS selector or increase the scroll wait time.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="status-box">✅ {len(_deal_products)} product(s) scraped from <strong>{_deal_name}</strong></div>',
                unsafe_allow_html=True,
            )

            render_action_bar(_deal_products, "deals")

            for i in range(0, len(_deal_products), 3):
                cols = st.columns(3)
                for j, p in enumerate(_deal_products[i : i + 3]):
                    with cols[j]:
                        _title = p.get("title") or "No title"
                        render_product_card(
                            title=_title,
                            price=p.get("price") or "N/A",
                            rank=i + j + 1,
                            rating="N/A",
                            reviews="N/A",
                            link=p.get("link") or "#",
                            thumbnail=p.get("image"),
                            card_key=f"deals_{i+j}",
                        )
                st.markdown("<div style='margin-bottom: 24px;'></div>", unsafe_allow_html=True)
