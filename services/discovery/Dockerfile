FROM python:3.12-slim

WORKDIR /app

COPY services/discovery/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/discovery/app ./app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

EXPOSE 3007

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3007"]
