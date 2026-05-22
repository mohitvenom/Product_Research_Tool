# Product Research Tool

A FastAPI-based backend API for product research, utilizing SERP API to fetch genuine product information from Google Shopping.

## Features

- Search for products using Google Shopping via SERP API
- Scrape Amazon product listings for supported markets
- Static frontend dashboard served from `/`
- RESTful API endpoints for search and analytics
- Easy to extend for additional data sources (e.g., GSC, price tracking)

## Setup

1. Clone the repository or navigate to the project directory.

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   - Copy `.env`
   - Update `SERP_API_KEY` with your SerpApi key (get from https://serpapi.com/)
   - For GSC (Google Search Console):
     - Create a Google Cloud project and enable Search Console API
     - Create OAuth 2.0 credentials, download `client_secret.json`, rename to `gsc_credentials.json`, place in project root
     - For each country's Gmail account, log in to GSC, go to the property settings, add the OAuth client email as a user with "Read" access to the respective property (e.g., https://www.ubuy.com.au for Australia)
     - Update the GSC_PROPERTY_* variables in `.env` with the correct URLs for each country

4. Run the server:
   ```
   uvicorn main:app --reload
   ```

   Or use the VS Code task "Run Server".

5. Open the web dashboard:
   - http://127.0.0.1:8000/

## Usage

- **GET /**: Welcome message
- **GET /search/{country}/{query}**: Search for products in a specific country using SERP API Google Shopping. This returns product-only results and excludes blogs or news.
- **GET /amazon/{country}/{page_type}**: Scrape Amazon listing pages for supported countries and sections.
- **GET /gsc/queries/{country}?days=30**: Get search queries from GSC for the specified country property (default 30 days, cached)
- **GET /gsc/pages/{country}?days=30**: Get pages from GSC for the specified country property (default 30 days, cached)

Supported countries:
- australia
- kuwait
- united-kingdom
- saudi-arabia
- india

Supported page types:
- best-sellers
- new-releases
- movers-and-shakers

Example search response:
```json
{
  "country": "india",
  "query": "laptop",
  "shopping_results": [...],
  "immersive_products": [...]
}
```

Example Amazon scraping response:
```json
{
  "country": "india",
  "page_type": "best-sellers",
  "url": "https://www.amazon.in/gp/bestsellers",
  "products": [
    {
      "title": "Example Product",
      "link": "https://...",
      "price": "₹1,999",
      "rating": "4.5 out of 5 stars",
      "reviews": "1,234",
      "seller": "Example Store",
      "rank": "#1"
    }
  ]
}
```

## API Documentation

Once running, visit http://127.0.0.1:8000/docs for interactive API docs.

## Development

- Add more endpoints in `main.py`
- For database integration, use SQLite as specified
- For Amazon scraping, implement additional endpoints using BeautifulSoup

## Requirements

- Python 3.8+
- SerpApi account for API key