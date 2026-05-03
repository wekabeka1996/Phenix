FROM python:3.12-slim

# Install system tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    git \
    ripgrep \
    curl \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash agent

# Install package
WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e ".[dev]"

# Workspace directory (volume-mounted at runtime)
RUN mkdir -p /workspace/project && chown agent:agent /workspace/project

USER agent
WORKDIR /workspace/project

ENTRYPOINT ["deepseek-agent"]
CMD ["chat"]
