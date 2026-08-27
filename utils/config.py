import os

COIN = os.getenv("COIN", "ETH-USD")
TIME_FRAME = os.getenv("TIME_FRAME", "1m")
LIVE_DATA = os.getenv("LIVE_DATA", "True").lower() == "true"
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "qwen2.5:3b")
PROVIDER = os.getenv("PROVIDER", "online")
FASTAPI_HOST = os.getenv("FASTAPI_HOST", "127.0.0.1")
FASTAPI_PORT = int(os.getenv("FASTAPI_PORT", "8000"))
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
FRED_API_KEY = os.getenv("FRED_TOKEN")
online_api_key = os.getenv("API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# --- Agent Thresholds ---
TECH_BUY_THRESHOLD = int(os.getenv("TECH_BUY_THRESHOLD", "45"))
TECH_SELL_THRESHOLD = int(os.getenv("TECH_SELL_THRESHOLD", "-45"))
MACRO_BUY_THRESHOLD = int(os.getenv("MACRO_BUY_THRESHOLD", "35"))
MACRO_SELL_THRESHOLD = int(os.getenv("MACRO_SELL_THRESHOLD", "-35"))
SENTIMENT_BUY_THRESHOLD = int(os.getenv("SENTIMENT_BUY_THRESHOLD", "20"))
SENTIMENT_SELL_THRESHOLD = int(os.getenv("SENTIMENT_SELL_THRESHOLD", "-20"))
FUNDAMENTAL_BUY_THRESHOLD = int(os.getenv("FUNDAMENTAL_BUY_THRESHOLD", "20"))
FUNDAMENTAL_SELL_THRESHOLD = int(os.getenv("FUNDAMENTAL_SELL_THRESHOLD", "-20"))

# --- Risk Parameters ---
RISK_PCT_LOW = float(os.getenv("RISK_PCT_LOW", "0.025"))
RISK_PCT_MED = float(os.getenv("RISK_PCT_MED", "0.02"))
RISK_PCT_HIGH = float(os.getenv("RISK_PCT_HIGH", "0.01"))
SL_MULT_LOW = float(os.getenv("SL_MULT_LOW", "1.0"))
SL_MULT_MED = float(os.getenv("SL_MULT_MED", "1.5"))
SL_MULT_HIGH = float(os.getenv("SL_MULT_HIGH", "2.5"))
TP_MULTIPLIER = float(os.getenv("TP_MULTIPLIER", "3.0"))
INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", "1000.0"))