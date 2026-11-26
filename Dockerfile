# Printyz website: FastAPI + the same geometry engine as the desktop studio.
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libxrender1 libxext6 libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY customer/customer_policy.json ./customer/customer_policy.json
RUN pip install --no-cache-dir -e ".[web]"
ENV PRINTYZ_DATA_DIR=/data PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "printyz_web.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
