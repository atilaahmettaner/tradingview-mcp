FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock README.md ./

# Install dependencies only, skip building the local package (src/ not copied yet)
RUN uv sync --frozen --no-dev --no-install-project

# Copy source
COPY src/ ./src/

# Install the package itself
RUN uv pip install --no-deps -e . --python /app/.venv/bin/python

ENV PYTHONPATH=src
ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

CMD ["/app/.venv/bin/tradingview-mcp", "streamable-http"]
