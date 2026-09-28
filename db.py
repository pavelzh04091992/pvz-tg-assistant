import sqlite3
import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "assistant.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id INTEGER,
                chat_id INTEGER,
                author_name TEXT,
                message_text TEXT,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT, -- 'notified', 'sent', 'rejected', 'skipped'
                proposed_reply TEXT,
                final_reply TEXT,
                PRIMARY KEY (chat_id, message_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sent_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                message_id INTEGER,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def is_already_processed(chat_id: int, message_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM processed_messages WHERE chat_id = ? AND message_id = ?", (chat_id, message_id))
        row = cursor.fetchone()
        return row is not None

def save_candidate(chat_id: int, message_id: int, author_name: str, message_text: str, proposed_reply: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO processed_messages 
            (chat_id, message_id, author_name, message_text, status, proposed_reply)
            VALUES (?, ?, ?, ?, 'notified', ?)
        """, (chat_id, message_id, author_name, message_text, proposed_reply))
        conn.commit()

def update_status(chat_id: int, message_id: int, status: str, final_reply: str = None):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if final_reply:
            cursor.execute("""
                UPDATE processed_messages 
                SET status = ?, final_reply = ? 
                WHERE chat_id = ? AND message_id = ?
            """, (status, final_reply, chat_id, message_id))
        else:
            cursor.execute("""
                UPDATE processed_messages 
                SET status = ? 
                WHERE chat_id = ? AND message_id = ?
            """, (status, chat_id, message_id))
        
        if status == 'sent':
            cursor.execute("INSERT INTO sent_history (chat_id, message_id) VALUES (?, ?)", (chat_id, message_id))
        conn.commit()

def can_send_reply(chat_id: int, max_daily: int = 2, min_hours: int = 3) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        now = datetime.datetime.now()
        day_ago = now - datetime.timedelta(days=1)
        hours_ago = now - datetime.timedelta(hours=min_hours)

        # Count in last 24h
        cursor.execute("SELECT COUNT(*) FROM sent_history WHERE chat_id = ? AND sent_at >= ?", (chat_id, day_ago.isoformat()))
        count_24h = cursor.fetchone()[0]
        if count_24h >= max_daily:
            return False

        # Last sent time
        cursor.execute("SELECT MAX(sent_at) FROM sent_history WHERE chat_id = ?", (chat_id,))
        last_sent = cursor.fetchone()[0]
        if last_sent:
            try:
                last_dt = datetime.datetime.fromisoformat(last_sent)
                if last_dt > hours_ago:
                    return False
            except Exception:
                pass
        return True
