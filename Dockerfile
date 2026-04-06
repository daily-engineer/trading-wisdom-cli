# Stage 1: builder — install dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY trading_cli/ trading_cli/

# Install the package and its runtime dependencies (base only, no [ib] extra)
RUN pip install --no-cache-dir .

# Stage 2: runtime — minimal image
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy installed site-packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/trading-cli /usr/local/bin/trading-cli

# Copy source code
COPY trading_cli/ trading_cli/

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

USER appuser

# Config and trade log are provided via volume mount at runtime:
#   -v ~/.trading-cli:/home/appuser/.trading-cli
# The CLI auto-creates ~/.trading-cli/config.yaml on first run.

ENTRYPOINT ["trading-cli"]
CMD ["--help"]
