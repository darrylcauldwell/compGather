# Stage 1: Build Tailwind CSS
FROM node:22-slim AS css-builder
WORKDIR /build
COPY package.json postcss.config.js tailwind.config.js ./
RUN npm install
COPY app/static/css/input.css app/static/css/input.css
COPY app/templates/ app/templates/
RUN npm run build:css

# Stage 2: Python app + Playwright
FROM python:3.13-slim

WORKDIR /app

# Install system deps for Playwright Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libx11-xcb1 \
    fonts-liberation \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create appuser before installing Playwright so browsers go in the right cache
RUN useradd -m -u 1000 appuser

# Install Playwright browsers as appuser so the cache path matches at runtime
USER appuser
RUN playwright install chromium
USER root

COPY app/ ./app/
COPY tests/ ./tests/
COPY scripts/ ./scripts/
COPY ruff.toml ./
COPY --from=css-builder /build/app/static/css/output.css ./app/static/css/output.css

# SQLite data directory
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
