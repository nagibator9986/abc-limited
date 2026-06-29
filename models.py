"""
Модели данных для корпоративного сайта ТОО «АВС-Лимитед».

Архитектура CMS: всё содержимое сайта хранится в БД и редактируется
через админ-панель. Ни один текст/изображение не «зашит» в шаблоны —
шаблоны только отображают данные из этих моделей.
"""
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


# --------------------------------------------------------------------------- #
#  Администраторы CMS
# --------------------------------------------------------------------------- #
class AdminUser(db.Model):
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), default="Администратор")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


# --------------------------------------------------------------------------- #
#  Глобальные настройки (бренд, контакты, футер, соцсети, CTA, карта…)
#  Хранятся как «ключ → значение», что позволяет добавлять новые поля без
#  миграций. Тип ввода управляет виджетом в админке.
# --------------------------------------------------------------------------- #
class Setting(db.Model):
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False)
    value = db.Column(db.Text, default="")
    label = db.Column(db.String(160), default="")       # подпись в админке
    group = db.Column(db.String(60), default="Общие")    # вкладка в админке
    input_type = db.Column(db.String(20), default="text")  # text|textarea|image|color
    hint = db.Column(db.String(255), default="")
    sort_order = db.Column(db.Integer, default=0)


# --------------------------------------------------------------------------- #
#  Страницы сайта — герой-блок, вступление, мета и пункт меню.
#  Каждая основная страница привязана к маршруту по slug.
# --------------------------------------------------------------------------- #
class Page(db.Model):
    __tablename__ = "pages"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    menu_label = db.Column(db.String(120), default="")
    title = db.Column(db.String(200), default="")        # H1 / заголовок героя
    eyebrow = db.Column(db.String(160), default="")      # надзаголовок
    subtitle = db.Column(db.Text, default="")            # подзаголовок героя
    hero_image = db.Column(db.String(200), default="")
    intro = db.Column(db.Text, default="")               # вступительный текст (HTML)
    body = db.Column(db.Text, default="")                # доп. содержимое (HTML)
    meta_description = db.Column(db.String(300), default="")
    sort_order = db.Column(db.Integer, default=0)
    in_menu = db.Column(db.Boolean, default=True)
    is_published = db.Column(db.Boolean, default=True)


# --------------------------------------------------------------------------- #
#  Ключевые показатели (счётчики на главной)
# --------------------------------------------------------------------------- #
class Stat(db.Model):
    __tablename__ = "stats"

    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.String(40), default="")     # число, напр. "20"
    prefix = db.Column(db.String(20), default="")
    suffix = db.Column(db.String(40), default="")    # напр. "млн $", "+"
    label = db.Column(db.String(160), default="")
    icon = db.Column(db.String(60), default="")      # имя иконки
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)


# --------------------------------------------------------------------------- #
#  Конкурентные преимущества
# --------------------------------------------------------------------------- #
class Advantage(db.Model):
    __tablename__ = "advantages"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), default="")
    text = db.Column(db.Text, default="")
    icon = db.Column(db.String(60), default="check")
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)


# --------------------------------------------------------------------------- #
#  Виды деятельности / услуги
# --------------------------------------------------------------------------- #
class Service(db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), default="")
    description = db.Column(db.Text, default="")
    items = db.Column(db.Text, default="")           # подпункты, по строке на пункт
    icon = db.Column(db.String(60), default="layers")
    image = db.Column(db.String(200), default="")
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)

    @property
    def item_list(self):
        return [i.strip() for i in (self.items or "").splitlines() if i.strip()]


# --------------------------------------------------------------------------- #
#  Лицензии и стандарты
# --------------------------------------------------------------------------- #
class License(db.Model):
    __tablename__ = "licenses"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), default="")
    body = db.Column(db.Text, default="")
    icon = db.Column(db.String(60), default="shield")
    image = db.Column(db.String(200), default="")
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)


# --------------------------------------------------------------------------- #
#  Производственные активы (базы, заводы, БСУ, карьер…)
# --------------------------------------------------------------------------- #
class Asset(db.Model):
    __tablename__ = "assets"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), default="")
    category = db.Column(db.String(120), default="")   # «Производственная база», «Завод», …
    description = db.Column(db.Text, default="")
    location = db.Column(db.String(200), default="")
    capacity = db.Column(db.String(160), default="")   # мощность / характеристика
    year = db.Column(db.String(40), default="")
    image = db.Column(db.String(200), default="")
    image2 = db.Column(db.String(200), default="")
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)


# --------------------------------------------------------------------------- #
#  Парк техники (таблицы из презентации)
# --------------------------------------------------------------------------- #
class Equipment(db.Model):
    __tablename__ = "equipment"

    id = db.Column(db.Integer, primary_key=True)
    num = db.Column(db.Integer, default=0)
    name = db.Column(db.String(255), default="")
    year = db.Column(db.String(20), default="")
    spec = db.Column(db.String(80), default="")        # категория / масса
    qty = db.Column(db.Integer, default=1)
    category = db.Column(db.String(80), default="Техника")
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)


# --------------------------------------------------------------------------- #
#  Проекты / портфолио
# --------------------------------------------------------------------------- #
class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), default="")
    description = db.Column(db.Text, default="")
    client = db.Column(db.String(200), default="")     # заказчик
    period = db.Column(db.String(80), default="")      # годы реализации
    category = db.Column(db.String(80), default="Дороги")
    location = db.Column(db.String(160), default="")
    image = db.Column(db.String(200), default="")
    is_featured = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)


# --------------------------------------------------------------------------- #
#  Актуальные задачи (текущие объекты)
# --------------------------------------------------------------------------- #
class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), default="")
    object_name = db.Column(db.Text, default="")       # описание объекта
    customer = db.Column(db.String(255), default="")   # заказчик
    description = db.Column(db.Text, default="")
    quote = db.Column(db.Text, default="")             # цитата/комментарий
    quote_author = db.Column(db.String(200), default="")
    image = db.Column(db.String(200), default="")
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)


# --------------------------------------------------------------------------- #
#  «Расширяем границы» — привлечённые мегапроекты / партнёрства
# --------------------------------------------------------------------------- #
class ExpansionItem(db.Model):
    __tablename__ = "expansion_items"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), default="")
    description = db.Column(db.Text, default="")
    image = db.Column(db.String(200), default="")
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)


# --------------------------------------------------------------------------- #
#  Благодарности (галерея)
# --------------------------------------------------------------------------- #
class Testimonial(db.Model):
    __tablename__ = "testimonials"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), default="")
    author = db.Column(db.String(200), default="")
    image = db.Column(db.String(200), default="")
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)


# --------------------------------------------------------------------------- #
#  Заявки с формы обратной связи
# --------------------------------------------------------------------------- #
class Lead(db.Model):
    __tablename__ = "leads"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), default="")
    phone = db.Column(db.String(80), default="")
    email = db.Column(db.String(160), default="")
    message = db.Column(db.Text, default="")
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
