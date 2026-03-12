FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev deps, no editable install yet)
RUN uv sync --frozen --no-dev

# Copy source
COPY src/ ./src/

# Install the package itself
RUN uv pip install --no-deps -e .

ENV PYTHONPATH=src
ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

CMD ["uv", "run", "tradingview-mcp", "streamable-http"]
