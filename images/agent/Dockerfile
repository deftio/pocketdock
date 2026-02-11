FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl jq git \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir \
    requests httpx beautifulsoup4 lxml \
    pandas numpy \
    pyyaml toml \
    pillow
RUN useradd -m -s /bin/bash sandbox
USER sandbox
WORKDIR /home/sandbox
CMD ["sleep", "infinity"]
