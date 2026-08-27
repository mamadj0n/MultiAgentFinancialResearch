import aiosqlite
import logging

logger = logging.getLogger(__name__)
DB_NAME = "bot_database.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                symbol TEXT,
                timeframe TEXT,
                is_active BOOLEAN DEFAULT 1,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def save_user_settings(user_id: int, name: str, symbol: str, timeframe: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO users (user_id, name, symbol, timeframe, is_active) 
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET 
            name=excluded.name, 
            symbol=excluded.symbol, 
            timeframe=excluded.timeframe, 
            is_active=1
        """, (user_id, name, symbol, timeframe))
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def set_user_active(user_id: int, is_active: bool):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET is_active = ? WHERE user_id = ?", (is_active, user_id))
        await db.commit()

async def get_active_users_grouped():
    """کاربران فعال را بر اساس (symbol, timeframe) گروه بندی می‌کند"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id, symbol, timeframe FROM users WHERE is_active = 1") as cursor:
            rows = await cursor.fetchall()
            
            grouped = {}
            for row in rows:
                key = (row['symbol'], row['timeframe'])
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(row['user_id'])
            return grouped

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            return [row[0] for row in await cursor.fetchall()]