FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies (build-essential for compiling C modules, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download SpaCy English model to speed up container startup
RUN python -m spacy download en_core_web_sm

# Copy project source code
COPY . .

# Create directory structure for SQLite database and logs
RUN mkdir -p app/data/raw app/data/processed app/data/curriculum app/data/exports

# Expose ports for FastAPI (8000) and Dash (8050)
EXPOSE 8000 8050

# Run the project entrypoint script
CMD ["python", "run.py"]
