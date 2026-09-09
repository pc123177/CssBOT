import sqlite3
from datetime import datetime, timezone


class UserStore:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                paused INTEGER NOT NULL DEFAULT 0,
                include_words TEXT NOT NULL DEFAULT '',
                exclude_words TEXT NOT NULL DEFAULT '',
                max_price TEXT NOT NULL DEFAULT '',
                platforms TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                chat_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                price TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                sent_at TEXT NOT NULL,
                PRIMARY KEY (chat_id, product_id),
                FOREIGN KEY (chat_id) REFERENCES users(chat_id)
            );
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(deliveries)")}
        if "title" not in columns:
            self.db.execute("ALTER TABLE deliveries ADD COLUMN title TEXT NOT NULL DEFAULT ''")
        if "url" not in columns:
            self.db.execute("ALTER TABLE deliveries ADD COLUMN url TEXT NOT NULL DEFAULT ''")
        self.db.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _user(row) -> dict | None:
        if row is None:
            return None
        user = dict(row)
        user["paused"] = bool(user["paused"])
        user["active"] = bool(user["active"])
        user["include"] = user.pop("include_words")
        user["exclude"] = user.pop("exclude_words")
        return user

    def register(self, chat_id: str, name: str = "") -> None:
        now = self._now()
        self.db.execute("""
            INSERT INTO users (chat_id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                name=excluded.name, active=1, paused=0, updated_at=excluded.updated_at
        """, (str(chat_id), name, now, now))
        self.db.commit()

    def get(self, chat_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM users WHERE chat_id=?", (str(chat_id),)).fetchone()
        return self._user(row)

    def active_users(self) -> list[dict]:
        rows = self.db.execute("SELECT * FROM users WHERE active=1 AND paused=0 ORDER BY created_at").fetchall()
        return [self._user(row) for row in rows]

    def update(self, chat_id: str, **filters: str) -> None:
        columns = {"include": "include_words", "exclude": "exclude_words",
                   "max_price": "max_price", "platforms": "platforms"}
        values = {columns[key]: value for key, value in filters.items() if key in columns}
        if not values:
            return
        values["updated_at"] = self._now()
        assignments = ", ".join(f"{column}=?" for column in values)
        self.db.execute(f"UPDATE users SET {assignments} WHERE chat_id=?",
                        (*values.values(), str(chat_id)))
        self.db.commit()

    def set_paused(self, chat_id: str, paused: bool) -> None:
        self.db.execute("UPDATE users SET paused=?, updated_at=? WHERE chat_id=?",
                        (int(paused), self._now(), str(chat_id)))
        self.db.commit()

    def unsubscribe(self, chat_id: str) -> None:
        self.db.execute("UPDATE users SET active=0, updated_at=? WHERE chat_id=?",
                        (self._now(), str(chat_id)))
        self.db.commit()

    def mark_sent(self, chat_id: str, product_id: str, price: str,
                  title: str = "", url: str = "") -> None:
        self.db.execute("""
            INSERT INTO deliveries (chat_id, product_id, price, title, url, sent_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, product_id) DO UPDATE SET
                price=excluded.price, title=excluded.title, url=excluded.url,
                sent_at=excluded.sent_at
        """, (str(chat_id), str(product_id), str(price), title, url, self._now()))
        self.db.commit()

    def recent_deliveries(self, chat_id: str, limit: int = 5) -> list[dict]:
        rows = self.db.execute("""
            SELECT product_id, title, price, url, sent_at
            FROM deliveries WHERE chat_id=? ORDER BY sent_at DESC LIMIT ?
        """, (str(chat_id), limit)).fetchall()
        return [dict(row) for row in rows]

    def was_sent(self, chat_id: str, product_id: str) -> bool:
        row = self.db.execute("SELECT 1 FROM deliveries WHERE chat_id=? AND product_id=?",
                              (str(chat_id), str(product_id))).fetchone()
        return row is not None

    def last_price(self, chat_id: str, product_id: str) -> str | None:
        row = self.db.execute("SELECT price FROM deliveries WHERE chat_id=? AND product_id=?",
                              (str(chat_id), str(product_id))).fetchone()
        return row["price"] if row else None

    def close(self) -> None:
        self.db.close()
