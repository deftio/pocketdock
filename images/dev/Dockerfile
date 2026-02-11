FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git jq vim-tiny tree htop less \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir ipython requests httpx
RUN useradd -m -s /bin/bash sandbox
USER sandbox
WORKDIR /home/sandbox
CMD ["sleep", "infinity"]
