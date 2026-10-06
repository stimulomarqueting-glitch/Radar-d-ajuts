# Imatge de l'aplicació web i del programador de la revisió diària (vegeu docs/desplegament.md)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Europe/Madrid
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home --uid 1000 radar && mkdir -p privat sortida data/estat && chown -R radar:radar /app
USER radar

EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/salut')" || exit 1
CMD ["python", "-m", "radar", "web", "--host", "0.0.0.0", "--port", "8000"]
