FROM python:3.12-slim

WORKDIR /app

COPY libs/beckn_models /tmp/beckn_models
RUN pip install --no-cache-dir /tmp/beckn_models && rm -rf /tmp/beckn_models

COPY services/agents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/agents/app ./app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

EXPOSE 3004

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3004"]
