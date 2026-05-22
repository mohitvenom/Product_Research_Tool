import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

AMAZON_DOMAINS = {
    "australia": "https://www.amazon.com.au",
    "belgium": "https://www.amazon.com.be",
    "brazil": "https://www.amazon.com.br",
    "canada": "https://www.amazon.ca",
    "china": "https://www.amazon.cn",
    "egypt": "https://www.amazon.eg",
    "france": "https://www.amazon.fr",
    "germany": "https://www.amazon.de",
    "india": "https://www.amazon.in",
    "italy": "https://www.amazon.it",
    "japan": "https://www.amazon.co.jp",
    "mexico": "https://www.amazon.com.mx",
    "netherlands": "https://www.amazon.nl",
    "poland": "https://www.amazon.pl",
    "saudi-arabia": "https://www.amazon.sa",
    "singapore": "https://www.amazon.sg",
    "spain": "https://www.amazon.es",
    "sweden": "https://www.amazon.se",
    "turkey": "https://www.amazon.com.tr",
    "united-arab-emirates": "https://www.amazon.ae",
    "united-kingdom": "https://www.amazon.co.uk",
    "united-states": "https://www.amazon.com",
    "south-africa": "https://www.amazon.co.za",
    "ireland": "https://www.amazon.ie",
}

PAGE_PATHS = {
    "best-sellers": "/gp/bestsellers",
    "new-releases": "/gp/new-releases",
    "movers-and-shakers": "/gp/movers-and-shakers",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
}

COUNTRY_LANGUAGE = {
    "australia": "en-AU,en;q=0.9",
    "kuwait": "en-AE,en;q=0.9",
    "united-kingdom": "en-GB,en;q=0.9",
    "saudi-arabia": "en-SA,en;q=0.9",
    "india": "en-IN,en;q=0.9",
    "south-africa": "en-ZA,en;q=0.9",
    "ireland": "en-IE,en;q=0.9",
}


def _clean_text(tag):
    return tag.get_text(separator=" ", strip=True) if tag else None


def _build_url(country: str, page_type: str, category: str = None) -> str:
    domain = AMAZON_DOMAINS.get(country.lower())
    if not domain:
        raise ValueError(f"Unable to scrape as there is no amazon domain for {country.replace('-', ' ').title()} country")

    path = PAGE_PATHS.get(page_type.lower())
    if not path:
        raise ValueError(f"Unsupported page type '{page_type}'. Supported: {', '.join(PAGE_PATHS)}")

    # Amazon is sensitive to trailing slashes
    url = domain + path.rstrip("/") + "/"
    if category:
        url += category.strip("/") + "/"
    return url


def _is_blocked_html(html: str) -> bool:
    blocked_signals = [
        "Server Busy",
        "To discuss automated access",
        "Enter the characters you see below",
    ]
    return any(signal in html for signal in blocked_signals)


def _fetch_html(url: str, country: str) -> str:
    attempts = []
    country_lower = country.lower()

    base_headers = HEADERS.copy()
    if country_lower in COUNTRY_LANGUAGE:
        base_headers["Accept-Language"] = COUNTRY_LANGUAGE[country_lower]

    attempts.append(base_headers)

    fallback_headers = HEADERS.copy()
    fallback_headers["Accept-Language"] = "en-US,en;q=0.9"
    fallback_headers["Referer"] = url
    attempts.append(fallback_headers)

    alt_headers = HEADERS.copy()
    alt_headers["Accept-Language"] = COUNTRY_LANGUAGE.get(country_lower, "en-US,en;q=0.9")
    alt_headers["Referer"] = "https://www.google.com/"
    attempts.append(alt_headers)

    last_html = None
    for headers in attempts:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        last_html = response.text
        if not _is_blocked_html(last_html):
            return last_html

    return last_html


def _parse_product(item, base_url):
    title_tag = item.select_one(
        "div.p13n-sc-truncate, div.p13n-sc-truncate-desktop-type2, span.a-size-medium, span.a-size-base-plus, span.a-size-base, span.zg-text-center-align, div[class*='p13n-sc-css-line-clamp'], div._cDEzb_p13n-sc-css-line-clamp-3_77_fX, [class*='TitleLink'], [class*='title' i], [class*='Title'], span.a-truncate"
    )
    title = _clean_text(title_tag)

    if item.name == "a":
        link_tag = item
    else:
        link_tag = item.select_one(
            "a[data-testid='product-card-link'], a.a-link-normal.aok-block[href], a.a-link-normal.s-no-outline[href], a.a-link-normal[href], a[href]"
        )
        
    link = None
    if link_tag and link_tag.get("href"):
        link = urljoin(base_url, link_tag["href"])
        
    if not title and link_tag:
        t = _clean_text(link_tag)
        # Avoid grabbing the "Limited time deal" promo text if the anchor only contains the badge
        if t and "limited time deal" not in t.lower() and not t.lower().endswith("off"):
            title = t
            
    # Rescue garbage titles (if title tag grabbed a promo block by accident)
    if title and ("limited time deal" in title.lower() or title.startswith("$") or "deal of the day" in title.lower()):
        title = ""

    # Parse product name from URL slug if still empty
    if not title and link:
        import urllib.parse
        parsed = urllib.parse.urlparse(link)
        parts = parsed.path.split('/')
        if len(parts) > 1 and parts[1] and parts[1].lower() not in ["dp", "gp", "product", "s", "b", "events"]:
            # e.g., /Cambridge-2026-2027-July-June-Cherrywood-CL17-90... -> Cambridge 2026 2027 July...
            slug = parts[1].replace("-", " ").replace("_", " ").title()
            title = slug

    price_tag = item.select_one(
        "._cDEzb_p13n-sc-price-animation-wrapper_3PzN2, .p13n-sc-price, .a-price .a-offscreen, span.a-price-whole, span.a-price, span.a-color-price, span[class*='p13n-sc-price']"
    )
    price = _clean_text(price_tag)

    rating_tag = item.select_one("span.a-icon-alt, .a-icon-alt")
    rating = _clean_text(rating_tag)

    reviews_tag = item.select_one("a[href*='product-reviews'], span.a-size-small, .a-size-small.a-link-normal")
    reviews = _clean_text(reviews_tag)

    seller_tag = item.select_one(
        ".a-size-small.a-color-secondary, .a-row.a-size-small, .aok-inline-block.a-static-right"
    )
    seller = _clean_text(seller_tag)

    rank_tag = item.select_one(".zg-bdg-text, span.zg-bdg-text, div.zg-bdg-text")
    rank = _clean_text(rank_tag)

    img_tag = item.select_one("img.a-dynamic-image, img.s-image, img.a-dynamic-image[src], img[src], img.p13n-product-image")
    thumbnail = img_tag.get("src") if img_tag else None

    return {
        "title": title,
        "link": link,
        "price": price,
        "rating": rating,
        "reviews": reviews,
        "seller": seller,
        "rank": rank,
        "thumbnail": thumbnail,
    }


def scrape_amazon_page(country: str, page_type: str, category: str = None) -> dict:
    url = _build_url(country, page_type, category)
    html = _fetch_html(url, country)
    soup = BeautifulSoup(html, "html.parser")

    selectors = [
        "div[data-testid='deal-card']",
        "div[class*='DealGridItem']",
        "div[class*='DealItem']",
        "a[data-testid='product-card-link']",
        "div#gridItemRoot",
        "div[data-asin]",
        "div.zg-grid-general-faceout",
        "div.zg-item-immersion",
        "div.s-result-item",
        "li.a-carousel-card",
    ]

    candidates = []
    for selector in selectors:
        candidates = soup.select(selector)
        if candidates:
            break

    products = []
    for item in candidates:
        product = _parse_product(item, url)
        if product["title"]:
            products.append(product)
        if len(products) >= 30:
            break

    return {
        "country": country,
        "page_type": page_type,
        "url": url,
        "products": products,
    }
