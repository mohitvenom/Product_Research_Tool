# 🛍️ Product Research Tool

<div align="center">

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://prtool-mohitsharma.streamlit.app/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-412991?style=for-the-badge&logo=openai&logoColor=white)](https://openai.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

**An AI-powered product research platform for e-commerce teams.**  
Search Google Shopping, scrape Amazon listings, and monitor live deal banners — across **24 countries**.

</div>

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔍 **Google Shopping Search** | Search any product across 24 countries using SerpAPI. Filter, sort, and export results. |
| 🛒 **Amazon Scraper** | Scrape Best Sellers, New Releases, and Movers & Shakers from Amazon storefronts worldwide. |
| 🤖 **AI Analysis** | Use OpenAI GPT-4 to summarize trends, compare products, and extract insights from data. |
| 🏷️ **Amazon Deal Scraper** | Scrape live homepage deal banners and product listings from Amazon using Playwright *(local only)*. |
| 📊 **Data Export** | Export all results to CSV/JSON directly from the UI. |
| 🐳 **Docker Support** | Fully containerized with Playwright browser support for self-hosting. |

---

## 🌍 Supported Countries

Australia · Belgium · Brazil · Canada · China · Egypt · France · Germany · India · Ireland · Italy · Japan · Mexico · Netherlands · Poland · Saudi Arabia · Singapore · South Africa · Spain · Sweden · Turkey · UAE · United Kingdom · United States · Kuwait

---

## 🚀 Live Demo

👉 **[prtool-mohitsharma.streamlit.app](https://prtool-mohitsharma.streamlit.app/)**

> ⚠️ The **Amazon Deal Scraper** tab requires Playwright and is only available when running locally or via Docker.

---

## 🏗️ Tech Stack

- **Frontend/UI** — [Streamlit](https://streamlit.io/)
- **Backend API** — [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/)
- **Product Search** — [SerpAPI](https://serpapi.com/) (Google Shopping)
- **Amazon Scraping** — [Requests](https://requests.readthedocs.io/) + [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/)
- **Deal Scraping** — [Playwright](https://playwright.dev/python/) (browser automation)
- **AI Analysis** — [OpenAI API](https://openai.com/api/) (GPT-4)
- **Containerization** — [Docker](https://www.docker.com/)

---

## ⚙️ Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/mohitvenom/Product_Research_Tool.git
cd Product_Research_Tool
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

Create a `.env` file in the root directory:

```env
SERP_API_KEY=your_serpapi_key_here
OPENAI_API_KEY=your_openai_key_here
```

> 🔑 Get your SerpAPI key from [serpapi.com](https://serpapi.com/)  
> 🔑 Get your OpenAI key from [platform.openai.com](https://platform.openai.com/)

### 5. Run the Streamlit app

```bash
streamlit run app.py
```

### 6. (Optional) Run the FastAPI backend

```bash
uvicorn main:app --reload
# API docs → http://127.0.0.1:8000/docs
```

---

## 🐳 Docker (with Playwright support)

Build and run the container — this enables the **Amazon Deal Scraper** tab:

```bash
docker build -t product-research-tool .
docker run -p 8501:8501 --env-file .env product-research-tool
```

Open → **http://localhost:8501**

---

## 📡 API Endpoints (FastAPI)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/search/{country}/{query}` | Google Shopping search |
| `GET` | `/amazon/{country}/{page_type}` | Scrape Amazon listings |
| `GET` | `/gsc/queries/{country}?days=30` | Google Search Console queries |
| `GET` | `/gsc/pages/{country}?days=30` | Google Search Console pages |

**Supported `page_type` values:** `best-sellers` · `new-releases` · `movers-and-shakers`

**Example:**
```bash
GET /search/india/laptop
GET /amazon/united-states/best-sellers
```

Interactive API docs: `http://localhost:8000/docs`

---

## 📁 Project Structure

```
product_research_tool/
├── app.py                  # Streamlit UI (main app)
├── main.py                 # FastAPI backend
├── amazon_scraper.py       # Amazon listings scraper (requests + BS4)
├── amazon_deals.py         # Amazon deal banner scraper (Playwright)
├── requirements.txt        # Python dependencies
├── Dockerfile              # Docker config with Playwright
├── .env                    # Environment variables (not committed)
└── .github/
    └── copilot-instructions.md
```

---

## 🤝 Contributing

Contributions are welcome! Feel free to open an issue or submit a pull request.

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "Add your feature"`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<div align="center">
Made with ❤️ by <a href="https://github.com/mohitvenom">mohitvenom</a>
</div>