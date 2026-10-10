FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends g++ build-essential libspatialindex-dev osmium-tool && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV VRP_RUNTIME_DIR=/data
EXPOSE 8080
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080"]
