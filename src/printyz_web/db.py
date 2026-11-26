"""SQLite storage: orders, products (gallery), posts (updates), key/value site settings."""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token TEXT UNIQUE NOT NULL,
  created REAL NOT NULL,
  updated REAL NOT NULL,
  status TEXT NOT NULL,
  name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL, notes TEXT DEFAULT '',
  marketing INTEGER NOT NULL DEFAULT 0,
  summary TEXT NOT NULL,
  project TEXT NOT NULL,
  price REAL NOT NULL,
  price_breakdown TEXT NOT NULL,
  final_price REAL,
  payment_link TEXT DEFAULT '',
  ready_days INTEGER,
  admin_note TEXT DEFAULT '',
  history TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL, description TEXT DEFAULT '', price TEXT DEFAULT '',
  images TEXT NOT NULL DEFAULT '[]', visible INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0,
  created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL, body TEXT DEFAULT '', visible INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

STATUSES = {
    "pending": "ממתינה לאישור",
    "approved": "אושרה — ממתינה לתשלום",
    "paid": "שולמה",
    "in_production": "בייצור",
    "ready": "מוכנה",
    "delivered": "נמסרה",
    "rejected": "נדחתה",
    "cancelled": "בוטלה",
}


class DB:
    def __init__(self, path: Path):
        self.path = path
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # ---- key / value ----------------------------------------------------------------------
    def get(self, key: str, default=None):
        with self.conn() as c:
            r = c.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default

    def put(self, key: str, value) -> None:
        with self.conn() as c:
            c.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (key, json.dumps(value, ensure_ascii=False)))

    # ---- orders ---------------------------------------------------------------------------
    def create_order(self, *, name, email, phone, notes, marketing, summary, project, price, breakdown) -> dict:
        now = time.time()
        token = secrets.token_urlsafe(16)
        hist = [{"t": now, "status": "pending", "note": "הזמנה התקבלה"}]
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO orders(token,created,updated,status,name,email,phone,notes,marketing,summary,project,"
                "price,price_breakdown,history) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (token, now, now, "pending", name, email, phone, notes, int(marketing),
                 json.dumps(summary, ensure_ascii=False), json.dumps(project, ensure_ascii=False), price,
                 json.dumps(breakdown, ensure_ascii=False), json.dumps(hist, ensure_ascii=False)))
            oid = cur.lastrowid
        return self.order(oid)

    def order(self, oid: int) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        return _order_row(r)

    def order_by_token(self, token: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM orders WHERE token=?", (token,)).fetchone()
        return _order_row(r)

    def orders(self, status: str | None = None) -> list[dict]:
        q = "SELECT * FROM orders" + (" WHERE status=?" if status else "") + " ORDER BY created DESC"
        with self.conn() as c:
            rows = c.execute(q, (status,) if status else ()).fetchall()
        return [_order_row(r) for r in rows]

    def update_order(self, oid: int, *, status: str | None = None, note: str = "", **fields) -> dict:
        o = self.order(oid)
        hist = o["history"]
        if status:
            hist.append({"t": time.time(), "status": status, "note": note})
            fields["status"] = status
        fields["history"] = json.dumps(hist, ensure_ascii=False)
        fields["updated"] = time.time()
        cols = ",".join(f"{k}=?" for k in fields)
        with self.conn() as c:
            c.execute(f"UPDATE orders SET {cols} WHERE id=?", (*fields.values(), oid))
        return self.order(oid)

    def subscribers(self) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT name,email,phone,MAX(created) AS last FROM orders WHERE marketing=1 "
                             "GROUP BY email ORDER BY last DESC").fetchall()
        return [dict(r) for r in rows]

    # ---- gallery / posts ----------------------------------------------------------------------
    def products(self, visible_only: bool = True) -> list[dict]:
        q = "SELECT * FROM products" + (" WHERE visible=1" if visible_only else "") + " ORDER BY sort, created DESC"
        with self.conn() as c:
            rows = c.execute(q).fetchall()
        return [dict(r) | {"images": json.loads(r["images"])} for r in rows]

    def product(self, pid: int) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        return dict(r) | {"images": json.loads(r["images"])} if r else None

    def save_product(self, pid: int | None, **f) -> int:
        f["images"] = json.dumps(f.get("images", []))
        with self.conn() as c:
            if pid:
                c.execute(f"UPDATE products SET {','.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), pid))
                return pid
            f["created"] = time.time()
            cur = c.execute(f"INSERT INTO products({','.join(f)}) VALUES({','.join('?' * len(f))})", tuple(f.values()))
            return cur.lastrowid

    def delete_product(self, pid: int) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM products WHERE id=?", (pid,))

    def posts(self, visible_only: bool = True) -> list[dict]:
        q = "SELECT * FROM posts" + (" WHERE visible=1" if visible_only else "") + " ORDER BY created DESC"
        with self.conn() as c:
            return [dict(r) for r in c.execute(q).fetchall()]

    def save_post(self, pid: int | None, title: str, body: str, visible: bool) -> None:
        with self.conn() as c:
            if pid:
                c.execute("UPDATE posts SET title=?,body=?,visible=? WHERE id=?", (title, body, int(visible), pid))
            else:
                c.execute("INSERT INTO posts(title,body,visible,created) VALUES(?,?,?,?)",
                          (title, body, int(visible), time.time()))

    def delete_post(self, pid: int) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM posts WHERE id=?", (pid,))


def _order_row(r) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    for k in ("summary", "project", "price_breakdown", "history"):
        d[k] = json.loads(d[k])
    d["status_label"] = STATUSES.get(d["status"], d["status"])
    return d
