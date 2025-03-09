FROM python:3.11

WORKDIR /src

COPY . . 

RUN apt-get update && apt-get install -y nano && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

# Expose only if you have a web service
EXPOSE 8000

ENTRYPOINT ["sh", "entrypoint.sh"]
