FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code only
COPY solarman_logger/ solarman_logger/

# Default config path inside container
ENV CONFIG_PATH=/config/config.yaml

# Stop grace period: Python needs SIGTERM as PID 1
# exec form ensures python is PID 1
STOPSIGNAL SIGTERM
CMD ["python", "-m", "solarman_logger"]
