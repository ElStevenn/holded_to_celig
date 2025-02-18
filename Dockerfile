FROM python:3.11

WORKDIR /src

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

ENV CELERY_BROKER_URL=redis://redis:6379/0
ENV CELERY_RESULT_BACKEND=redis://redis:6379/0

EXPOSE 8000

ENTRYPOINT ["sh", "entrypoint.sh"]
