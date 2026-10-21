FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install uv separately from the application dependencies.
RUN pip install --no-cache-dir uv

# Copy dependency metadata first so Docker can reuse this layer when only
# application source files change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Copy the ADK application after dependencies.
COPY app ./app

EXPOSE 8080

# Cloud Run requires the server to listen on all interfaces. Cloud Run
# provides PORT, with 8080 as the local/default value. --with_ui serves the
# ADK web interface at the root URL instead of returning Not Found at `/`.
# ADK checks Origin even for JavaScript module GET requests. Cloud Run's proxy
# changes the upstream host, so explicitly trust the local browser origins.
# This does not disable Cloud Run IAM authentication or make the service public.
CMD ["uv", "run", "adk", "api_server", "app/src", "--with_ui", "--host", "0.0.0.0", "--port", "8080", "--no-reload", "--allow_origins", "http://127.0.0.1:8081", "--allow_origins", "http://localhost:8081", "--allow_origins", "http://127.0.0.1:8080", "--allow_origins", "http://localhost:8080"]
