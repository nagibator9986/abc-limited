"""
Идемпотентная инициализация базы данных для деплоя (Railway и т.п.).

Создаёт таблицы и наполняет их контентом ТОЛЬКО если база пуста.
Безопасно запускать при каждом старте — существующие данные не трогаются.
"""
from sqlalchemy import inspect, text

from app import app, db
from models import AdminUser
from seed import ensure_school13, populate


# Колонки, добавленные после первичного релиза. Прогоняются на каждом старте
# (идемпотентно): create_all() создаёт только отсутствующие таблицы, но НЕ
# добавляет новые колонки в уже существующие — поэтому мигрируем вручную.
_ADDED_COLUMNS = {
    "projects": [
        ("gallery", "TEXT DEFAULT ''"),
        ("video", "VARCHAR(200) DEFAULT ''"),
        ("video_poster", "VARCHAR(200) DEFAULT ''"),
    ],
}


def ensure_columns():
    """Добавляет недостающие колонки в существующие таблицы (SQLite/Postgres)."""
    insp = inspect(db.engine)
    existing_tables = set(insp.get_table_names())
    added = 0
    for table, cols in _ADDED_COLUMNS.items():
        if table not in existing_tables:
            continue  # таблицы ещё нет — её создаст create_all() со всеми колонками
        have = {c["name"] for c in insp.get_columns(table)}
        for name, ddl in cols:
            if name not in have:
                db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                added += 1
    if added:
        db.session.commit()
        print(f"✓ Схема обновлена: добавлено колонок — {added}.")


def init():
    with app.app_context():
        db.create_all()
        ensure_columns()
        if AdminUser.query.count() == 0:
            populate()
            print("✓ База данных создана и наполнена контентом.")
        else:
            print("✓ База данных уже инициализирована — наполнение пропущено.")
        # Идемпотентно гарантируем наличие проекта «Школа №13» (фото + видео)
        # и на уже наполненных базах (напр. постоянный том Railway).
        if ensure_school13():
            print("✓ Добавлен проект «Школа №13» с фотогалереей и видео.")


if __name__ == "__main__":
    init()
