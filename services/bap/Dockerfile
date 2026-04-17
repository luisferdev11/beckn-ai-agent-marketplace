FROM python:3.12-slim

WORKDIR /app

# Install shared library first (cached layer)
COPY libs/beckn_models /tmp/beckn_models
RUN pip install --no-cache-dir /tmp/beckn_models && rm -rf /tmp/beckn_models

# Install service dependencies
COPY services/bap/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/bap/app ./app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

EXPOSE 3001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3001"]
