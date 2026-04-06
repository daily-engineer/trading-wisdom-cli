FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install --no-cache-dir poetry==1.8.3 && \
    poetry config virtualenvs.create false

# Copy dependency files first for layer caching
COPY pyproject.toml ./
RUN poetry install --no-interaction --no-ansi --only main 2>/dev/null || \
    pip install click rich pydantic pyyaml pandas numpy requests

# Copy source
COPY trading_cli/ trading_cli/
COPY README.md ./

# Install package
RUN pip install --no-cache-dir -e .

# Default config directory
RUN mkdir -p /root/.trading-cli

ENTRYPOINT ["trading-cli"]
CMD ["--help"]
