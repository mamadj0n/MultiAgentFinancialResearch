FROM python:3.12-slim

# جلوگیری از کش شدن لاگ‌های پایتون برای دیدن در لحظه لاگ‌ها
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ایجاد پوشه‌های Persistent برای Render Disk
RUN mkdir -p /app/data /app/logs

# Render پورت را via ENV PORT می‌دهد
EXPOSE 8080
ENV PORT=8080

# Persistent data volumes (برای Render Disk روی /app/data مانت کن)
VOLUME ["/app/data", "/app/logs"]

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen(f'http://localhost:{__import__(\"os\").environ.get(\"PORT\", \"8080\")}/health').read()" || exit 1

# Graceful shutdown via SIGTERM
STOPSIGNAL SIGTERM

CMD ["python", "scripts/bot.py"]
