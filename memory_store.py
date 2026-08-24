# memory_store.py
import sqlite3
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class MemoryStore:
    def __init__(self, db_path: str = "trading_memory.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS past_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                direction TEXT,
                macro_signal TEXT,
                tech_signal TEXT,
                fund_signal TEXT,
                supervisor_reason TEXT,
                pnl REAL,
                r_multiple REAL,
                win INTEGER
            )
        ''')
        self.conn.commit()

    def record_trade(self, trade_data: Dict[str, Any]):
        self.conn.execute('''
            INSERT INTO past_trades 
            (timestamp, direction, macro_signal, tech_signal, fund_signal, supervisor_reason, pnl, r_multiple, win)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade_data.get("timestamp"),
            trade_data.get("direction"),
            trade_data.get("macro_signal", "N/A"),
            trade_data.get("tech_signal", "N/A"),
            trade_data.get("fund_signal", "N/A"),
            trade_data.get("supervisor_reason", "N/A"),
            trade_data.get("pnl", 0.0),
            trade_data.get("r_multiple", 0.0),
            1 if trade_data.get("pnl", 0.0) > 0 else 0
        ))
        self.conn.commit()
        logger.info(f"[Memory] Recorded trade to DB: {trade_data.get('direction')} | PnL: {trade_data.get('pnl')}")

    def retrieve_similar_trades(self, macro_signal: str, tech_signal: str, limit: int = 3) -> List[Dict]:
        """جستجوی تریدهای مشابه بر اساس سیگنال‌های ماکرو و تکنیکال"""
        query = '''
            SELECT * FROM past_trades 
            WHERE macro_signal = ? AND tech_signal = ?
            ORDER BY timestamp DESC LIMIT ?
        '''
        cursor = self.conn.execute(query, (macro_signal, tech_signal, limit))
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]