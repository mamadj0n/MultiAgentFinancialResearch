FROM python:3.12-slim

# جلوگیری از کش شدن لاگ‌های پایتون برای دیدن در لحظه لاگ‌ها
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent data volumes
VOLUME ["/app/data", "/app/logs"]

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Graceful shutdown via SIGTERM
STOPSIGNAL SIGTERM

CMD ["python", "scripts/bot.py"]
