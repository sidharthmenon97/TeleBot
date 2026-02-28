FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependencies first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Ensure pipeline is executable
RUN chmod +x pipeline.sh

# Expose the web UI port
EXPOSE 36168

# Run the FastAPI server via main.py
CMD ["python", "main.py"]
