FROM python:3.12-slim

WORKDIR /app

# System deps: curl for healthcheck, build-essential transitively pulled by
# torch+sentence-transformers. Slim base means no extras.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/mock-network/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-fetch the embedding model into the image so container startup is
# instant. ~120MB layer; acceptable trade-off vs runtime download on every
# fresh container.
RUN python3 -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

# The AgentFacts JSON Schema is the source of truth for catalog validation.
# Mounted at /app/schemas so the validator can load it deterministically
# without depending on git checkouts at runtime.
COPY schemas/agentfacts-v1.json /app/schemas/agentfacts-v1.json

COPY services/mock-network/app ./app

EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
