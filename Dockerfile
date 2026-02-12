FROM python:3.10-slim

# Install system dependencies:
# - ffmpeg with libx264/libass for video rendering and subtitle burn-in
# - git (required by openai-whisper pip install)
# - fonts-freefont-ttf as Arial Black substitute on Linux
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    fonts-freefont-ttf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cache-friendly layer ordering)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and assets (respects .dockerignore)
COPY . .

# Ensure output directories exist
RUN mkdir -p output/temp output/final output/pipeline_logs

CMD ["python", "-m", "src.batch_runner", "--limit", "1"]
