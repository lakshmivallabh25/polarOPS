# Dockerfile for PolarOPS backend (Render deployment)
# Use official Python slim image for a small footprint
FROM python:3.12-slim

# Install system dependencies required by some Python packages (git, gcc, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends git gcc && rm -rf /var/lib/apt/lists/*

# Set working directory inside the container
WORKDIR /app

# Install Python dependencies first (leverages Docker layer caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code
COPY . ./

# Expose the port that Render will provide via $PORT
EXPOSE $PORT

# Default command (Render overrides this via render.yaml)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "$PORT"]
