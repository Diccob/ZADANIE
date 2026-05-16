import aiosqlite

DB_NAME = "/app/shared/smokes.db"


async def init_db():

    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute("""
        CREATE TABLE IF NOT EXISTS smokes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT
        )
        """)

        await db.commit()
