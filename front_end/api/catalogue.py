from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKEND_ROOT = PROJECT_ROOT.parent / "back_end" / "product_importer"
DEFAULT_DATABASE = DEFAULT_BACKEND_ROOT / "products.db"
DEFAULT_MEDIA_ROOT = DEFAULT_BACKEND_ROOT / "media"

PUBLIC_FIELDS = (
    "id", "brand", "name", "category", "model", "sku", "barcode",
    "description", "color", "size", "gender", "material", "quantity",
    "wholesale_price", "retail_price", "currency", "status", "image_path",
    "offer_type", "origin", "hs_code", "grade", "model_year", "collection",
    "frame_color", "lens_color", "color_code", "material_code",
    "frame_material", "bridge_size", "branch_size", "uva_filter", "fitting",
    "release_code", "phase", "exceeding_quantity", "total_retail_value",
)

LIST_FIELDS = (
    "id", "brand", "name", "category", "model", "sku", "barcode", "color",
    "size", "gender", "quantity", "wholesale_price", "retail_price", "currency",
    "status", "image_path", "offer_type", "origin", "grade", "collection",
)

SORTS = {
    "name": "COALESCE(name, model, sku) COLLATE NOCASE ASC, id ASC",
    "brand": "COALESCE(brand, '') COLLATE NOCASE ASC, COALESCE(name, model, sku) COLLATE NOCASE ASC",
    "quantity_desc": "quantity IS NULL ASC, quantity DESC, id ASC",
    "price_asc": "wholesale_price IS NULL ASC, wholesale_price ASC, id ASC",
    "price_desc": "wholesale_price IS NULL ASC, wholesale_price DESC, id ASC",
    "newest": "id DESC",
}

STATUS_LABELS = {
    "AVAILABLE": "Available",
    "LAST_PIECES": "Last pieces",
    "PREORDER": "Pre-order",
    "BACKORDER": "Back order",
    "NOT_AVAILABLE": "Not available",
}

MOQ_PATTERN = re.compile(r"MOQ\s*(\d+)\s*pcs", re.IGNORECASE)


@dataclass(frozen=True)
class ProductQuery:
    page: int = 1
    page_size: int = 24
    query: str = ""
    brand: str = ""
    category: str = ""
    status: str = ""
    gender: str = ""
    currency: str = ""
    in_stock: bool = False
    sort: str = "name"


def connect(database: Path = DEFAULT_DATABASE) -> sqlite3.Connection:
    database = database.resolve()
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def display_brand(value: str) -> str:
    value = " ".join(value.split())
    if value.isupper() and len(value) > 4:
        return value.title()
    return value


def display_category(value: str) -> str:
    value = " ".join(value.split())
    aliases = {
        "optical frames": "Optical frames",
        "sunglasses": "Sunglasses",
        "shoes": "Shoes",
        "handbag": "Handbags",
        "watches": "Watches",
        "watch": "Watches",
    }
    return aliases.get(value.casefold(), value)


def image_url(path: Any) -> str | None:
    value = clean_text(path)
    if not value:
        return None
    normalized = value.replace("\\", "/").lstrip("/")
    if not normalized.startswith("media/") or ".." in Path(normalized).parts:
        return None
    return "/" + normalized


def status_label(value: Any) -> str | None:
    status = clean_text(value)
    if not status:
        return None
    return STATUS_LABELS.get(status.upper(), status.replace("_", " ").title())


def serialize_product(row: sqlite3.Row) -> dict[str, Any]:
    product = {key: row[key] for key in row.keys() if key in PUBLIC_FIELDS}
    product["brand"] = display_brand(product["brand"]) if product.get("brand") else None
    product["category"] = display_category(product["category"]) if product.get("category") else None
    product["status_label"] = status_label(product.get("status"))
    product["image_url"] = image_url(product.pop("image_path", None))
    product["has_quantity"] = product.get("quantity") is not None
    return product


def _where(query: ProductQuery) -> tuple[str, list[Any]]:
    clauses = ["COALESCE(name, model, sku) IS NOT NULL"]
    params: list[Any] = []
    if query.query:
        clauses.append("LOWER(COALESCE(brand,'') || ' ' || COALESCE(name,'') || ' ' || COALESCE(model,'') || ' ' || COALESCE(sku,'') || ' ' || COALESCE(barcode,'')) LIKE ?")
        params.append(f"%{query.query.strip().casefold()}%")
    for column, value in (
        ("brand", query.brand), ("category", query.category), ("status", query.status),
        ("gender", query.gender), ("currency", query.currency),
    ):
        if value:
            clauses.append(f"LOWER(TRIM({column})) = ?")
            params.append(value.strip().casefold())
    if query.in_stock:
        clauses.append("quantity > 0")
    return " AND ".join(clauses), params


def list_products(connection: sqlite3.Connection, query: ProductQuery) -> dict[str, Any]:
    page = max(1, query.page)
    page_size = min(100, max(1, query.page_size))
    where, params = _where(query)
    total = connection.execute(
        f"SELECT COUNT(*) FROM website_products WHERE {where}", params
    ).fetchone()[0]
    fields = ", ".join(LIST_FIELDS)
    order = SORTS.get(query.sort, SORTS["name"])
    rows = connection.execute(
        f"SELECT {fields} FROM website_products WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    return {
        "items": [serialize_product(row) for row in rows],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
        },
    }


def _normalized_facets(connection: sqlite3.Connection, column: str, formatter) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"SELECT {column}, COUNT(*) count FROM website_products "
        f"WHERE {column} IS NOT NULL AND TRIM({column}) <> '' "
        f"GROUP BY LOWER(TRIM({column})) ORDER BY count DESC, {column} COLLATE NOCASE"
    ).fetchall()
    return [
        {"value": clean_text(row[column]), "label": formatter(row[column]), "count": row["count"]}
        for row in rows
    ]


def facets(connection: sqlite3.Connection) -> dict[str, Any]:
    plain = lambda value: " ".join(value.replace("_", " ").split()).title()
    return {
        "brands": _normalized_facets(connection, "brand", display_brand),
        "categories": _normalized_facets(connection, "category", display_category),
        "statuses": _normalized_facets(connection, "status", lambda value: status_label(value) or value),
        "genders": _normalized_facets(connection, "gender", plain),
        "currencies": _normalized_facets(connection, "currency", lambda value: value.upper()),
    }


def summary(connection: sqlite3.Connection) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT COUNT(*) products,
               COUNT(DISTINCT UPPER(TRIM(brand))) brands,
               ROUND(SUM(CASE WHEN quantity > 0 THEN quantity ELSE 0 END), 2) explicit_units,
               SUM(CASE WHEN quantity > 0 THEN 1 ELSE 0 END) in_stock_products,
               MAX(id) latest_product_id
        FROM website_products
        WHERE COALESCE(name, model, sku) IS NOT NULL
        """
    ).fetchone()
    featured = connection.execute(
        f"SELECT {', '.join(LIST_FIELDS)} FROM website_products "
        "WHERE quantity > 0 AND wholesale_price IS NOT NULL AND image_path IS NOT NULL "
        "ORDER BY id DESC LIMIT 6"
    ).fetchall()
    return {**dict(row), "featured": [serialize_product(item) for item in featured]}


def _moq_tiers(attributes: dict[str, Any]) -> list[dict[str, Any]]:
    tiers = []
    for key, value in attributes.items():
        match = MOQ_PATTERN.search(key)
        if match and value not in (None, ""):
            try:
                price = float(str(value).replace(",", "."))
            except ValueError:
                continue
            tiers.append({"minimum_quantity": int(match.group(1)), "price": price})
    return sorted(tiers, key=lambda tier: tier["minimum_quantity"])


def get_product(connection: sqlite3.Connection, product_id: int) -> dict[str, Any] | None:
    fields = ", ".join(PUBLIC_FIELDS)
    row = connection.execute(
        f"SELECT {fields}, attributes_json FROM website_products WHERE id = ?", (product_id,)
    ).fetchone()
    if row is None:
        return None
    product = serialize_product(row)
    try:
        attributes = json.loads(row["attributes_json"] or "{}")
    except json.JSONDecodeError:
        attributes = {}
    product["moq_tiers"] = _moq_tiers(attributes)
    product["variants"] = [
        dict(item) for item in connection.execute(
            "SELECT id, size, quantity, barcode, sku FROM product_variants WHERE product_id = ? ORDER BY id",
            (product_id,),
        )
    ]
    product["images"] = [
        {
            "id": item["id"],
            "url": image_url(item["image_path"]),
            "mime_type": item["mime_type"],
            "is_primary": bool(item["is_primary"]),
            "sort_order": item["sort_order"],
        }
        for item in connection.execute(
            "SELECT id, image_path, mime_type, is_primary, sort_order FROM product_images "
            "WHERE product_id = ? ORDER BY is_primary DESC, sort_order, id",
            (product_id,),
        )
    ]
    return product


def related_products(connection: sqlite3.Connection, product_id: int, limit: int = 4) -> list[dict[str, Any]]:
    active = connection.execute(
        "SELECT brand, category FROM website_products WHERE id = ?", (product_id,)
    ).fetchone()
    if not active:
        return []
    rows = connection.execute(
        f"SELECT {', '.join(LIST_FIELDS)} FROM website_products "
        "WHERE id <> ? AND image_path IS NOT NULL AND (LOWER(TRIM(brand)) = LOWER(TRIM(?)) "
        "OR (category IS NOT NULL AND LOWER(TRIM(category)) = LOWER(TRIM(?)))) "
        "ORDER BY CASE WHEN LOWER(TRIM(brand)) = LOWER(TRIM(?)) THEN 0 ELSE 1 END, id DESC LIMIT ?",
        (product_id, active["brand"] or "", active["category"] or "", active["brand"] or "", limit),
    ).fetchall()
    return [serialize_product(row) for row in rows]
