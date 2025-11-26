FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies including PostGIS
RUN apt-get update && apt-get install -y \
    postgresql-client \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cache bust - change this value to force rebuild of subsequent layers
# Railway will also pass RAILWAY_GIT_COMMIT_SHA as build arg
ARG CACHEBUST=2
ARG RAILWAY_GIT_COMMIT_SHA
RUN echo "Cache bust: ${CACHEBUST} ${RAILWAY_GIT_COMMIT_SHA}"

# Copy backend code (this layer will now rebuild when CACHEBUST changes)
COPY backend/ .

# Make startup scripts executable
RUN chmod +x start.sh start-worker.sh start-beat.sh

EXPOSE 8080

CMD ["./start.sh"]