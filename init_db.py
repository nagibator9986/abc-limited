"""
Идемпотентная инициализация базы данных для деплоя (Railway и т.п.).

Создаёт таблицы и наполняет их контентом ТОЛЬКО если база пуста.
Безопасно запускать при каждом старте — существующие данные не трогаются.
"""
from app import app, db
from models import AdminUser
from seed import populate


def init():
    with app.app_context():
        db.create_all()
        if AdminUser.query.count() == 0:
            populate()
            print("✓ База данных создана и наполнена контентом.")
        else:
            print("✓ База данных уже инициализирована — наполнение пропущено.")


if __name__ == "__main__":
    init()
