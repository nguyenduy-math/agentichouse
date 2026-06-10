FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for pymupdf and python-docx
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create runtime directories
RUN mkdir -p graphrag_workspace/input graphrag_workspace/output graphrag_workspace/logs data/documents

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
