"""Utils package for MultiAgentFinancialResearch.
Provides convenient imports for configuration and core utility classes.
"""

from .config import (
    COIN,
    TIME_FRAME,
    LIVE_DATA,
    LLM_MODEL_NAME,
    FASTAPI_HOST,
    FASTAPI_PORT,
    PROVIDER
)
from .DataCollect import DataCollector
from .FeatureEngineer import FeatureEngineering
# Optional utility imports – comment out or adjust if modules do not provide these symbols.
from .database import init_db, save_user_settings, get_user, set_user_active, get_active_users_grouped, get_all_users  # Not defined; remove or replace with appropriate API.
from .keyboards import main_menu_kb, symbol_kb, timeframe_kb, confirm_kb # Not defined; use functions from keyboards module directly.
from .signal_engine import get_signal  # Not defined; use get_signal function from signal_engine module.
from utils.tep import translate_en_to_fa

__all__ = [
    "COIN",
    "TIME_FRAME",
    "LIVE_DATA",
    "LLM_MODEL_NAME",
    "FASTAPI_HOST",
    "FASTAPI_PORT",
    "PROVIDER",
    "DataCollector",
    "FeatureEngineering",
    "init_db", "save_user_settings", "get_user", "set_user_active", "get_active_users_grouped", "get_all_users",
    "main_menu_kb", "symbol_kb", "timeframe_kb", "confirm_kb",
    "get_signal",
    "translate_en_to_fa"
]
