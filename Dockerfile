FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and its browser dependencies
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy the rest of the application code
COPY . .

# Expose the port Streamlit uses
EXPOSE 8501

# Command to run the app
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
