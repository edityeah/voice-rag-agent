FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ffmpeg curl git \
 && rm -rf /var/lib/apt/lists/*

# Pull the project from GitHub at build time so the Space stays in sync.
RUN git clone https://github.com/edityeah/voice-rag-agent.git . && \
    pip install --no-cache-dir -r requirements.txt

ENV PORT=7860
EXPOSE 7860

CMD ["python", "worker_runner.py", "start"]
