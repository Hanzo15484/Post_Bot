import sqlite3

def setup_db():
    conn = sqlite3.connect("Post.db")
    c = conn.cursor()

    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            is_admin INTEGER DEFAULT 0
        )
    """)

    # Settings table
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Channels table
    c.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER UNIQUE,
            channel_title TEXT,
            owner_id INTEGER
        )
    """)

    # Posts (for logs)
    c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Default Owner
    c.execute("""
        INSERT OR IGNORE INTO users (user_id, first_name, is_admin)
        VALUES (5373577888, 'Owner', 1)
    """)

    conn.commit()
    conn.close()
