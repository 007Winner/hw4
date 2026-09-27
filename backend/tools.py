from __future__ import annotations

import sqlite3
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

try:
    from .models import ProductCard, ProductStockLookup, SizeStock
except ImportError:  # Supports direct module execution from backend/.
    from models import ProductCard, ProductStockLookup, SizeStock

DATABASE = Path(__file__).resolve().parents[1] / "data" / "campus_customs.db"
AUDIT_TRAIL = Path(__file__).resolve().parents[1] / "output" / "audit_trail.json"
_AUDIT_LOCK = threading.Lock()


def audit_event(tool_name: str, arguments: dict[str, object], stop_reason: str) -> None:
    """Append one safe, compact agent-loop event to the persistent JSON log.

    Audit logging is deliberately best-effort: a logging problem must never
    break catalogue lookup or chat. Arguments are supplied by callers in
    already-redacted, short form; credentials and customer messages are never
    written here.
    """
    event = {
        "time": datetime.now(timezone.utc).isoformat(),
        "tool_name": tool_name,
        "arguments": arguments,
        "stop_reason": stop_reason,
    }
    try:
        AUDIT_TRAIL.parent.mkdir(parents=True, exist_ok=True)
        with _AUDIT_LOCK:
            if AUDIT_TRAIL.exists():
                try:
                    existing = json.loads(AUDIT_TRAIL.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    return
            else:
                existing = []
            if not isinstance(existing, list):
                return
            existing.append(event)
            AUDIT_TRAIL.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return


def _db() -> sqlite3.Connection:
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


def _card(db: sqlite3.Connection, row: sqlite3.Row) -> ProductCard:
    stock = db.execute("SELECT size, quantity FROM inventory WHERE product_id = ? ORDER BY id", (row["product_id"],)).fetchall()
    inventory = [SizeStock(size=item["size"], quantity=item["quantity"], in_stock=item["quantity"] > 0) for item in stock]
    return ProductCard(
        product_id=row["product_id"], name=row["name"], price=row["price"], garment_type=row["garment_type"],
        description=row["description"], colors=json.loads(row["colors"]), image_url=f"/images/{Path(row['image_file_path']).name}",
        inventory=inventory, total_stock=sum(item.quantity for item in inventory),
    )


def search_catalog(query: str, limit: int = 5) -> list[ProductCard]:
    """Look up catalogue descriptions, prices, images, and every size's stock quantity from SQLite."""
    db = _db()
    try:
        # Keep both model tool calls and API responses bounded for predictable
        # latency and a compact chat panel.
        limit = min(max(limit, 1), 8)
        stopwords = {"what", "which", "where", "when", "have", "with", "does", "show", "want", "your", "you", "the", "are", "for"}
        raw_words = [word.strip(".,?!") for word in query.lower().replace("'", " ").split()]
        words = []
        for word in raw_words:
            if len(word) <= 2 or word in stopwords:
                continue
            # The catalogue uses singular garment names, while shoppers
            # naturally ask for plurals such as "hoodies" or "tees".
            singular = word[:-3] + "ie" if word.endswith("ies") else word[:-1] if word.endswith("s") else word
            words.append(singular)
        if not words:
            rows = db.execute("SELECT * FROM catalogue ORDER BY name LIMIT ?", (limit,)).fetchall()
        else:
            clauses = []
            params: list[object] = []
            for word in words:
                term = f"%{word}%"
                clauses.append("(lower(name) LIKE ? OR lower(garment_type) LIKE ? OR lower(description) LIKE ? OR lower(colors) LIKE ? OR lower(search_tags) LIKE ?)")
                params.extend([term] * 5)
            rows = db.execute(f"SELECT * FROM catalogue WHERE {' OR '.join(clauses)} ORDER BY name", params).fetchall()
        ranked = []
        for row in rows:
            haystack = " ".join(str(row[field]).lower() for field in ("name", "garment_type", "description", "colors", "search_tags"))
            score = sum(word in haystack for word in words)
            ranked.append((score, row))
        ranked.sort(key=lambda item: (-item[0], item[1]["name"]))
        result = [_card(db, row) for _, row in ranked[:limit]]
        audit_event("search_catalog", {"query_preview": query[:80], "limit": limit}, f"returned_{len(result)}_matches")
        return result
    finally:
        db.close()


def get_product_stock(product_id: str) -> ProductStockLookup:
    """Look up a product's exact description, price, and quantity for every size from SQLite."""
    db = _db()
    try:
        product = db.execute("SELECT product_id, name, description, price FROM catalogue WHERE product_id = ?", (product_id,)).fetchone()
        if product is None:
            raise ValueError(f"No catalogue product exists for product_id={product_id}")
        rows = db.execute("SELECT size, quantity FROM inventory WHERE product_id = ? ORDER BY id", (product_id,)).fetchall()
        result = ProductStockLookup(
            product_id=product["product_id"], name=product["name"], description=product["description"], price=product["price"],
            inventory=[SizeStock(size=row["size"], quantity=row["quantity"], in_stock=row["quantity"] > 0) for row in rows],
        )
        audit_event("get_product_stock", {"product_id": product_id}, "returned_verified_inventory")
        return result
    finally:
        db.close()


def get_product_details(product_id: str) -> ProductCard:
    """Load the canonical catalogue and inventory record for the product on the current page."""
    db = _db()
    try:
        row = db.execute("SELECT * FROM catalogue WHERE product_id = ?", (product_id,)).fetchone()
        if row is None:
            raise ValueError(f"No catalogue product exists for product_id={product_id}")
        result = _card(db, row)
        audit_event("get_product_details", {"product_id": product_id}, "returned_verified_product")
        return result
    finally:
        db.close()
