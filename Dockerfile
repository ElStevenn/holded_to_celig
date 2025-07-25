FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 1) Dependencias del sistema mínimas (quita nano si no lo quieres)
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential nano \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# 2) Copiamos todo el código
COPY . .

# 3) Puerto interno
EXPOSE 8000

# 4) Lanza la app Quart con Hypercorn
CMD ["hypercorn", "src.quart_app.app:app", "--bind", "0.0.0.0:8000", "--worker-class", "asyncio"]
