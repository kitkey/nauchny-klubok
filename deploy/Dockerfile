FROM python:3.12-slim
WORKDIR /app

# Системные либы для PyMuPDF (рендер/OCR-фолбэк)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY p2kg ./p2kg
RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "p2kg.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
