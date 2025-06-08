FROM python:3.11-slim

WORKDIR /src
COPY . .

RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends nano && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000
ENTRYPOINT ["sh", "entrypoint.sh"]
