"""
ТОО «АВС-Лимитед» — корпоративный сайт с полноценной CMS.

Запуск:
    python app.py            # http://127.0.0.1:5000  (сайт)
                             # http://127.0.0.1:5000/admin  (админ-панель)

Первичная инициализация БД и наполнение контентом:
    python seed.py
"""
import os
import re
import secrets
import threading
import time
import uuid
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Flask, abort, flash, g, redirect, render_template, request,
    send_from_directory, session, url_for,
)
from markupsafe import Markup, escape
from werkzeug.middleware.proxy_fix import ProxyFix

from models import (
    AdminUser, Advantage, Asset, db, Equipment, Lead,
    License, Page, Partner, Project, Service, Setting, Stat, Task, Testimonial,
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# Каталог для данных (SQLite, загрузки). На Railway укажите DATA_DIR = точку монтирования тома.
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

# Признак запуска на хостинге за HTTPS-прокси (Railway/Render и т.п.)
BEHIND_PROXY = bool(
    os.environ.get("ABS_HTTPS") == "1"
    or os.environ.get("RAILWAY_ENVIRONMENT")
    or os.environ.get("RAILWAY_PROJECT_ID")
)


def _database_uri():
    """Postgres/иной DATABASE_URL, иначе SQLite в DATA_DIR."""
    url = os.environ.get("DATABASE_URL")
    if url:
        # SQLAlchemy требует схему postgresql:// (а Railway иногда даёт postgres://)
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    return "sqlite:///" + os.path.join(DATA_DIR, "abc.db")


app = Flask(__name__)
# Доверяем заголовкам X-Forwarded-* от прокси хостинга (нужно для https и url_for).
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.config.update(
    # В проде задайте ABS_SECRET_KEY; иначе генерируется случайный ключ на сессию процесса.
    SECRET_KEY=os.environ.get("ABS_SECRET_KEY") or secrets.token_hex(32),
    SQLALCHEMY_DATABASE_URI=_database_uri(),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
    UPLOAD_FOLDER=UPLOAD_DIR,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 МБ на загрузку
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Secure-cookie автоматически на хостинге за HTTPS (или при ABS_HTTPS=1).
    SESSION_COOKIE_SECURE=BEHIND_PROXY,
)
# Для SQLite — увеличенный таймаут блокировки (несколько потоков gunicorn).
if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"]["connect_args"] = {"timeout": 30}

# SVG исключён намеренно: может содержать исполняемый скрипт (хранимый XSS).
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

db.init_app(app)


# --------------------------------------------------------------------------- #
#  Защита от CSRF (без внешних зависимостей): токен в сессии + проверка POST
# --------------------------------------------------------------------------- #
def csrf_token():
    tok = session.get("_csrf")
    if not tok:
        tok = secrets.token_hex(16)
        session["_csrf"] = tok
    return tok


@app.before_request
def csrf_protect():
    if request.method == "POST":
        sent = request.form.get("_csrf", "")
        if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
            abort(400)


# ===========================================================================
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ===========================================================================
def get_settings():
    """Все настройки → dict {key: value}, кэш на время запроса."""
    if "settings" not in g:
        g.settings = {s.key: s.value for s in Setting.query.all()}
    return g.settings


def nav_pages():
    if "nav_pages" not in g:
        g.nav_pages = (
            Page.query.filter_by(in_menu=True, is_published=True)
            .order_by(Page.sort_order)
            .all()
        )
    return g.nav_pages


def get_page(slug):
    return Page.query.filter_by(slug=slug).first()


def get_published_page(slug):
    """Страница для публичного рендера: 404, если снята с публикации."""
    page = Page.query.filter_by(slug=slug).first()
    if not page or not page.is_published:
        abort(404)
    return page


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def save_upload(file_storage):
    """Сохраняет загруженный файл в каталог данных, возвращает путь 'uploads/<имя>'."""
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_file(file_storage.filename):
        return None
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    name = f"{uuid.uuid4().hex}.{ext}"
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    file_storage.save(os.path.join(app.config["UPLOAD_FOLDER"], name))
    return f"uploads/{name}"


@app.route("/media/uploads/<path:filename>")
def uploaded_file(filename):
    """Отдаёт загруженные через админку файлы из каталога данных (вне /static)."""
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# --------------------------------------------------------------------------- #
#  Валидация и санитизация ввода
# --------------------------------------------------------------------------- #
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")
_DANGEROUS_TAGS = re.compile(
    r"<\s*/?\s*(script|style|iframe|object|embed|link|meta|form|svg|base)\b[^>]*>",
    re.IGNORECASE,
)
_EVENT_ATTRS = re.compile(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE)
_JS_URLS = re.compile(r"(href|src)\s*=\s*([\"']?)\s*javascript:[^\"'>\s]*\2", re.IGNORECASE)


def sanitize_html(value):
    """Лёгкая защита от хранимого XSS в HTML-полях CMS (script/обработчики событий)."""
    if not value:
        return value
    value = _DANGEROUS_TAGS.sub("", value)
    value = _EVENT_ATTRS.sub("", value)
    value = _JS_URLS.sub(r'\1=\2#\2', value)
    return value


# ===========================================================================
#  JINJA-ФИЛЬТРЫ / ГЛОБАЛЫ
# ===========================================================================
@app.template_filter("nl2br")
def nl2br(text):
    if not text:
        return ""
    text = str(escape(text))
    return Markup(text.replace("\n", "<br>\n"))


@app.template_filter("paragraphs")
def paragraphs(text):
    """Текст с пустыми строками → набор <p>; одиночные переносы → <br>."""
    if not text:
        return ""
    blocks = re.split(r"\n\s*\n", str(text).strip())
    html = ""
    for b in blocks:
        safe = str(escape(b)).replace("\n", "<br>\n")
        html += f"<p>{safe}</p>\n"
    return Markup(html)


def media_url(value, fallback=""):
    """Путь к изображению из БД → URL. Загрузки (uploads/) отдаются спец-маршрутом,
    остальное (img/ из репозитория) — штатным /static."""
    def _url(v):
        if v.startswith("uploads/"):
            return url_for("uploaded_file", filename=v[len("uploads/"):])
        return url_for("static", filename=v)
    if value:
        return _url(value)
    if fallback:
        return _url(fallback)
    return ""


@app.template_filter("tel_clean")
def tel_clean(value):
    """Телефон → формат для tel:-ссылки (только + и цифры)."""
    return re.sub(r"[^+\d]", "", str(value or ""))


@app.context_processor
def inject_globals():
    s = get_settings()
    return {
        "S": s,
        "setting": lambda k, d="": s.get(k, d),
        "nav_pages": nav_pages(),
        "media": media_url,
        "page_url": lambda slug: _page_url(slug),
        "csrf_token": csrf_token,
    }


# Соответствие slug страницы → endpoint маршрута
PAGE_ENDPOINTS = {
    "home": "home",
    "about": "about",
    "services": "services",
    "production": "production",
    "equipment": "equipment",
    "projects": "projects",
    "tasks": "tasks",
    "partners": "partners",
    "testimonials": "testimonials",
    "contacts": "contacts",
}


def _page_url(slug):
    endpoint = PAGE_ENDPOINTS.get(slug)
    if endpoint:
        try:
            return url_for(endpoint)
        except Exception:
            pass
    return url_for("home") + slug


# ===========================================================================
#  ПУБЛИЧНЫЕ МАРШРУТЫ
# ===========================================================================
@app.route("/")
def home():
    page = get_page("home")
    stats = Stat.query.filter_by(is_active=True).order_by(Stat.sort_order).all()
    advantages = (
        Advantage.query.filter_by(is_active=True).order_by(Advantage.sort_order).all()
    )
    services = (
        Service.query.filter_by(is_active=True).order_by(Service.sort_order).all()
    )
    featured = (
        Project.query.filter_by(is_active=True, is_featured=True)
        .order_by(Project.sort_order)
        .limit(6)
        .all()
    )
    if not featured:
        featured = (
            Project.query.filter_by(is_active=True).order_by(Project.sort_order).limit(6).all()
        )
    licenses = (
        License.query.filter_by(is_active=True).order_by(License.sort_order).all()
    )
    return render_template(
        "index.html",
        page=page,
        stats=stats,
        advantages=advantages,
        services=services,
        featured=featured,
        licenses=licenses,
    )


@app.route("/o-kompanii", endpoint="about")
def about():
    page = get_published_page("about")
    advantages = (
        Advantage.query.filter_by(is_active=True).order_by(Advantage.sort_order).all()
    )
    licenses = (
        License.query.filter_by(is_active=True).order_by(License.sort_order).all()
    )
    stats = Stat.query.filter_by(is_active=True).order_by(Stat.sort_order).all()
    return render_template(
        "about.html", page=page, advantages=advantages, licenses=licenses, stats=stats
    )


@app.route("/deyatelnost", endpoint="services")
def services():
    page = get_published_page("services")
    services = (
        Service.query.filter_by(is_active=True).order_by(Service.sort_order).all()
    )
    return render_template("services.html", page=page, services=services)


@app.route("/proizvodstvo", endpoint="production")
def production():
    page = get_published_page("production")
    assets = Asset.query.filter_by(is_active=True).order_by(Asset.sort_order).all()
    return render_template("production.html", page=page, assets=assets)


@app.route("/tehnika", endpoint="equipment")
def equipment():
    page = get_published_page("equipment")
    items = (
        Equipment.query.filter_by(is_active=True)
        .order_by(Equipment.sort_order, Equipment.num)
        .all()
    )
    total_units = sum(i.qty or 0 for i in items)
    return render_template(
        "equipment.html", page=page, items=items, total_units=total_units
    )


@app.route("/proekty", endpoint="projects")
def projects():
    page = get_published_page("projects")
    items = (
        Project.query.filter_by(is_active=True).order_by(Project.sort_order).all()
    )
    categories = []
    for p in items:
        if p.category and p.category not in categories:
            categories.append(p.category)
    return render_template(
        "projects.html", page=page, projects=items, categories=categories
    )


@app.route("/zadachi", endpoint="tasks")
def tasks():
    page = get_published_page("tasks")
    items = Task.query.filter_by(is_active=True).order_by(Task.sort_order).all()
    equipment = (
        Equipment.query.filter_by(is_active=True)
        .order_by(Equipment.sort_order, Equipment.num)
        .all()
    )
    total_units = sum(e.qty or 0 for e in equipment)
    return render_template(
        "tasks.html", page=page, tasks=items, equipment=equipment, total_units=total_units
    )


@app.route("/partnery", endpoint="partners")
def partners():
    page = get_published_page("partners")
    items = (
        Partner.query.filter_by(is_active=True)
        .order_by(Partner.sort_order)
        .all()
    )
    featured = [p for p in items if p.is_featured]
    return render_template("partners.html", page=page, items=items, featured=featured)


@app.route("/blagodarnosti", endpoint="testimonials")
def testimonials():
    page = get_published_page("testimonials")
    items = (
        Testimonial.query.filter_by(is_active=True)
        .order_by(Testimonial.sort_order)
        .all()
    )
    return render_template("testimonials.html", page=page, testimonials=items)


@app.route("/kontakty", methods=["GET", "POST"], endpoint="contacts")
def contacts():
    page = get_published_page("contacts")
    if request.method == "POST":
        lead = Lead(
            name=request.form.get("name", "").strip(),
            phone=request.form.get("phone", "").strip(),
            email=request.form.get("email", "").strip(),
            message=request.form.get("message", "").strip(),
        )
        if not lead.name or not (lead.phone or lead.email):
            flash("Укажите имя и телефон или e-mail для связи.", "error")
        elif lead.email and not EMAIL_RE.match(lead.email):
            flash("Укажите корректный e-mail.", "error")
        else:
            db.session.add(lead)
            db.session.commit()
            flash("Спасибо! Ваша заявка отправлена. Мы свяжемся с вами в ближайшее время.", "success")
            return redirect(url_for("contacts") + "#contact-form")
    return render_template("contacts.html", page=page)


@app.route("/robots.txt")
def robots():
    return app.response_class(
        "User-agent: *\nAllow: /\nDisallow: /admin\n", mimetype="text/plain"
    )


def _safe_error_page(template, status, heading):
    """Рендер страницы ошибки, устойчивый к «грязной» сессии БД."""
    try:
        db.session.rollback()
    except Exception:
        pass
    try:
        return render_template(template), status
    except Exception:
        return (
            f'<!doctype html><meta charset="utf-8"><title>{status}</title>'
            f'<h1>{status} — {heading}</h1>'
            f'<p>Приносим извинения за временные неудобства.</p>',
            status,
        )


@app.errorhandler(404)
def not_found(e):
    return _safe_error_page("404.html", 404, "Страница не найдена")


@app.errorhandler(500)
def server_error(e):
    return _safe_error_page("500.html", 500, "Внутренняя ошибка сервера")


@app.errorhandler(413)
def too_large(e):
    return _safe_error_page("413.html", 413, "Файл слишком большой")


# ===========================================================================
#  АДМИН-ПАНЕЛЬ
# ===========================================================================
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        uid = session.get("admin_id")
        if not uid:
            return redirect(url_for("admin_login", next=request.path))
        user = db.session.get(AdminUser, uid)
        if user is None:  # запись администратора исчезла — сессия устарела
            session.clear()
            return redirect(url_for("admin_login", next=request.path))
        g.admin_user = user
        return view(*args, **kwargs)

    return wrapped


# Простой анти-брутфорс по IP (на процесс; для прода — Redis/flask-limiter)
_LOGIN_ATTEMPTS = {}
_LOGIN_LOCK = threading.Lock()
_LOGIN_MAX = 5
_LOGIN_BLOCK = 300  # секунд


def _login_blocked(ip):
    with _LOGIN_LOCK:
        rec = _LOGIN_ATTEMPTS.get(ip)
        return bool(rec and rec[1] > time.time())


def _login_fail(ip):
    with _LOGIN_LOCK:
        cnt, _ = _LOGIN_ATTEMPTS.get(ip, (0, 0))
        cnt += 1
        until = time.time() + _LOGIN_BLOCK if cnt >= _LOGIN_MAX else 0
        _LOGIN_ATTEMPTS[ip] = (cnt, until)


def _login_ok(ip):
    with _LOGIN_LOCK:
        _LOGIN_ATTEMPTS.pop(ip, None)


@app.context_processor
def inject_admin_globals():
    unread = 0
    if session.get("admin_id"):
        unread = Lead.query.filter_by(is_read=False).count()
    return {"admin_registry": ADMIN_REGISTRY, "admin_unread": unread}


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_id"):
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        if _login_blocked(ip):
            flash("Слишком много попыток входа. Повторите через несколько минут.", "error")
            return render_template("admin/login.html")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = AdminUser.query.filter_by(username=username).first()
        if user and user.check_password(password):
            _login_ok(ip)
            session["admin_id"] = user.id
            session["admin_name"] = user.full_name or user.username
            flash("Добро пожаловать в панель управления!", "success")
            # защита от open redirect: только локальный относительный путь
            nxt = request.args.get("next") or ""
            parsed = urlparse(nxt)
            if parsed.scheme or parsed.netloc or not nxt.startswith("/") or nxt.startswith("//"):
                nxt = url_for("admin_dashboard")
            return redirect(nxt)
        _login_fail(ip)
        flash("Неверный логин или пароль.", "error")
    return render_template("admin/login.html")


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    flash("Вы вышли из панели управления.", "success")
    return redirect(url_for("admin_login"))


@app.route("/admin/")
@login_required
def admin_dashboard():
    counts = {
        "pages": Page.query.count(),
        "services": Service.query.count(),
        "projects": Project.query.count(),
        "assets": Asset.query.count(),
        "equipment": Equipment.query.count(),
        "advantages": Advantage.query.count(),
        "licenses": License.query.count(),
        "tasks": Task.query.count(),
        "partners": Partner.query.count(),
        "testimonials": Testimonial.query.count(),
        "stats": Stat.query.count(),
        "leads": Lead.query.count(),
    }
    unread = Lead.query.filter_by(is_read=False).count()
    recent_leads = Lead.query.order_by(Lead.created_at.desc()).limit(5).all()
    return render_template(
        "admin/dashboard.html", counts=counts, unread=unread, recent_leads=recent_leads
    )


# --------------------------------------------------------------------------- #
#  Настройки сайта (сгруппированные)
# --------------------------------------------------------------------------- #
@app.route("/admin/settings", methods=["GET", "POST"])
@login_required
def admin_settings():
    settings = Setting.query.order_by(Setting.group, Setting.sort_order).all()
    if request.method == "POST":
        for s in settings:
            if s.input_type == "image":
                up = save_upload(request.files.get(f"file_{s.key}"))
                if up:
                    s.value = up
                elif request.form.get(f"clear_{s.key}"):
                    s.value = ""
                elif f"setting_{s.key}" in request.form:
                    s.value = request.form.get(f"setting_{s.key}", "").strip()
            else:
                if f"setting_{s.key}" in request.form:
                    val = request.form.get(f"setting_{s.key}", "")
                    # цвета — только корректный hex, иначе игнорируем (защита от CSS-инъекции)
                    if s.input_type == "color" and val and not HEX_COLOR_RE.match(val.strip()):
                        continue
                    s.value = val
        db.session.commit()
        flash("Настройки сохранены.", "success")
        return redirect(url_for("admin_settings"))

    groups = {}
    for s in settings:
        groups.setdefault(s.group, []).append(s)
    return render_template("admin/settings.html", groups=groups)


# --------------------------------------------------------------------------- #
#  Заявки
# --------------------------------------------------------------------------- #
@app.route("/admin/leads")
@login_required
def admin_leads():
    leads = Lead.query.order_by(Lead.created_at.desc()).all()
    return render_template("admin/leads.html", leads=leads)


@app.route("/admin/leads/<int:lead_id>/toggle", methods=["POST"])
@login_required
def admin_lead_toggle(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    lead.is_read = not lead.is_read
    db.session.commit()
    return redirect(url_for("admin_leads"))


@app.route("/admin/leads/<int:lead_id>/delete", methods=["POST"])
@login_required
def admin_lead_delete(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    db.session.delete(lead)
    db.session.commit()
    flash("Заявка удалена.", "success")
    return redirect(url_for("admin_leads"))


# --------------------------------------------------------------------------- #
#  Смена пароля администратора
# --------------------------------------------------------------------------- #
@app.route("/admin/account", methods=["GET", "POST"])
@login_required
def admin_account():
    user = g.admin_user  # гарантированно существует (проверено в login_required)
    if request.method == "POST":
        current = request.form.get("current", "")
        new = request.form.get("new", "")
        confirm = request.form.get("confirm", "")
        if not user.check_password(current):
            flash("Текущий пароль указан неверно.", "error")
        elif len(new) < 5:
            flash("Новый пароль слишком короткий (минимум 5 символов).", "error")
        elif new != confirm:
            flash("Пароли не совпадают.", "error")
        else:
            user.set_password(new)
            db.session.commit()
            flash("Пароль успешно изменён.", "success")
        return redirect(url_for("admin_account"))
    return render_template("admin/account.html", user=user)


# ===========================================================================
#  ОБОБЩЁННЫЙ CRUD ДЛЯ ВСЕХ КОЛЛЕКЦИЙ КОНТЕНТА
# ===========================================================================
def F(name, label, ftype="text", **kw):
    d = {"name": name, "label": label, "type": ftype}
    d.update(kw)
    return d


ADMIN_REGISTRY = {
    "pages": {
        "model": Page, "title": "Страницы", "singular": "страницу", "icon": "file",
        "order_by": Page.sort_order,
        "list_display": ["menu_label", "title", "slug", "in_menu", "is_published"],
        "can_create": False, "can_delete": False,
        "fields": [
            F("slug", "Системный slug", "text", readonly=True),
            F("menu_label", "Пункт меню", "text"),
            F("title", "Заголовок (H1)", "text"),
            F("eyebrow", "Надзаголовок", "text"),
            F("subtitle", "Подзаголовок героя", "textarea"),
            F("hero_image", "Фон героя", "image"),
            F("intro", "Вступительный текст", "html"),
            F("body", "Дополнительный текст", "html"),
            F("meta_description", "SEO-описание", "textarea"),
            F("sort_order", "Порядок в меню", "number"),
            F("in_menu", "Показывать в меню", "bool"),
            F("is_published", "Опубликовано", "bool"),
        ],
    },
    "stats": {
        "model": Stat, "title": "Показатели", "singular": "показатель", "icon": "trending-up",
        "order_by": Stat.sort_order,
        "list_display": ["value", "suffix", "label", "sort_order", "is_active"],
        "fields": [
            F("prefix", "Префикс", "text"),
            F("value", "Число / значение", "text"),
            F("suffix", "Суффикс (млн $, +, …)", "text"),
            F("label", "Подпись", "text"),
            F("icon", "Иконка", "icon"),
            F("sort_order", "Порядок", "number"),
            F("is_active", "Активно", "bool"),
        ],
    },
    "advantages": {
        "model": Advantage, "title": "Преимущества", "singular": "преимущество", "icon": "award",
        "order_by": Advantage.sort_order,
        "list_display": ["title", "sort_order", "is_active"],
        "fields": [
            F("title", "Заголовок", "text"),
            F("text", "Описание", "textarea"),
            F("icon", "Иконка", "icon"),
            F("sort_order", "Порядок", "number"),
            F("is_active", "Активно", "bool"),
        ],
    },
    "services": {
        "model": Service, "title": "Виды деятельности", "singular": "направление", "icon": "layers",
        "order_by": Service.sort_order,
        "list_display": ["title", "sort_order", "is_active"],
        "fields": [
            F("title", "Название направления", "text"),
            F("description", "Краткое описание", "textarea"),
            F("items", "Подпункты (по одному в строке)", "textarea"),
            F("icon", "Иконка", "icon"),
            F("image", "Изображение", "image"),
            F("sort_order", "Порядок", "number"),
            F("is_active", "Активно", "bool"),
        ],
    },
    "licenses": {
        "model": License, "title": "Лицензии и стандарты", "singular": "лицензию", "icon": "shield",
        "order_by": License.sort_order,
        "list_display": ["title", "sort_order", "is_active"],
        "fields": [
            F("title", "Заголовок", "text"),
            F("body", "Описание", "textarea"),
            F("icon", "Иконка", "icon"),
            F("image", "Изображение / скан", "image"),
            F("sort_order", "Порядок", "number"),
            F("is_active", "Активно", "bool"),
        ],
    },
    "assets": {
        "model": Asset, "title": "Производственные активы", "singular": "актив", "icon": "factory",
        "order_by": Asset.sort_order,
        "list_display": ["title", "category", "year", "sort_order", "is_active"],
        "fields": [
            F("title", "Название", "text"),
            F("category", "Категория", "text"),
            F("description", "Описание", "textarea"),
            F("location", "Местоположение", "text"),
            F("capacity", "Мощность / характеристика", "text"),
            F("year", "Год", "text"),
            F("image", "Изображение 1", "image"),
            F("image2", "Изображение 2", "image"),
            F("sort_order", "Порядок", "number"),
            F("is_active", "Активно", "bool"),
        ],
    },
    "equipment": {
        "model": Equipment, "title": "Парк техники", "singular": "технику", "icon": "truck",
        "order_by": (Equipment.sort_order, Equipment.num),
        "list_display": ["num", "name", "year", "spec", "qty", "is_active"],
        "fields": [
            F("num", "№", "number"),
            F("name", "Наименование", "text"),
            F("year", "Год выпуска", "text"),
            F("spec", "Категория / масса", "text"),
            F("qty", "Кол-во, ед.", "number"),
            F("category", "Группа", "text"),
            F("sort_order", "Порядок", "number"),
            F("is_active", "Активно", "bool"),
        ],
    },
    "projects": {
        "model": Project, "title": "Проекты", "singular": "проект", "icon": "briefcase",
        "order_by": Project.sort_order,
        "list_display": ["title", "category", "period", "is_featured", "is_active"],
        "fields": [
            F("title", "Название проекта", "text"),
            F("description", "Описание", "textarea"),
            F("client", "Заказчик", "text"),
            F("period", "Годы реализации", "text"),
            F("category", "Категория", "text"),
            F("location", "Локация", "text"),
            F("image", "Изображение", "image"),
            F("is_featured", "Избранный (на главной)", "bool"),
            F("sort_order", "Порядок", "number"),
            F("is_active", "Активно", "bool"),
        ],
    },
    "tasks": {
        "model": Task, "title": "Актуальные задачи", "singular": "задачу", "icon": "target",
        "order_by": Task.sort_order,
        "list_display": ["title", "customer", "sort_order", "is_active"],
        "fields": [
            F("title", "Заголовок", "text"),
            F("object_name", "Объект", "textarea"),
            F("customer", "Заказчик", "textarea"),
            F("description", "Описание", "textarea"),
            F("quote", "Цитата", "textarea"),
            F("quote_author", "Автор цитаты", "text"),
            F("image", "Изображение", "image"),
            F("sort_order", "Порядок", "number"),
            F("is_active", "Активно", "bool"),
        ],
    },
    "partners": {
        "model": Partner, "title": "Наши партнёры", "singular": "партнёра", "icon": "users",
        "order_by": Partner.sort_order,
        "list_display": ["title", "category", "is_featured", "sort_order", "is_active"],
        "fields": [
            F("title", "Название организации", "text"),
            F("category", "Тип (Заказчик / Партнёр)", "text"),
            F("description", "Описание сотрудничества", "textarea"),
            F("image", "Логотип / фото", "image"),
            F("url", "Сайт (необязательно)", "text"),
            F("is_featured", "Ключевой партнёр", "bool"),
            F("sort_order", "Порядок", "number"),
            F("is_active", "Активно", "bool"),
        ],
    },
    "testimonials": {
        "model": Testimonial, "title": "Благодарности", "singular": "благодарность", "icon": "heart",
        "order_by": Testimonial.sort_order,
        "list_display": ["title", "author", "sort_order", "is_active"],
        "fields": [
            F("title", "Заголовок", "text"),
            F("author", "От кого", "text"),
            F("image", "Скан / изображение", "image"),
            F("sort_order", "Порядок", "number"),
            F("is_active", "Активно", "bool"),
        ],
    },
}


@app.template_global()
def col_label(cfg, col):
    for f in cfg["fields"]:
        if f["name"] == col:
            return f["label"]
    fallback = {
        "is_active": "Активно", "in_menu": "В меню", "is_published": "Опубликовано",
        "is_featured": "Избранное", "sort_order": "Порядок", "category": "Категория",
        "num": "№", "name": "Наименование", "year": "Год", "spec": "Параметры",
        "qty": "Кол-во", "slug": "Slug", "menu_label": "Меню", "title": "Заголовок",
        "client": "Заказчик", "period": "Период", "customer": "Заказчик",
        "value": "Значение", "suffix": "Суффикс", "label": "Подпись", "author": "Автор",
    }
    return fallback.get(col, col)


def _apply_fields(obj, cfg):
    """Заполняет поля объекта из формы согласно конфигурации."""
    for field in cfg["fields"]:
        name, ftype = field["name"], field["type"]
        if field.get("readonly"):
            continue
        if ftype == "bool":
            setattr(obj, name, bool(request.form.get(name)))
        elif ftype == "number":
            raw = request.form.get(name, "").strip()
            if raw == "":
                continue  # пустой ввод — сохраняем default модели / прежнее значение
            try:
                setattr(obj, name, int(raw))
            except ValueError:
                pass  # некорректное число игнорируем, не обнуляем
        elif ftype == "image":
            up = save_upload(request.files.get(f"file_{name}"))
            if up:
                setattr(obj, name, up)
            elif request.form.get(f"clear_{name}"):
                setattr(obj, name, "")
            elif f"{name}" in request.form:
                setattr(obj, name, request.form.get(name, "").strip())
        elif ftype == "html":
            setattr(obj, name, sanitize_html(request.form.get(name, "")))
        else:
            setattr(obj, name, request.form.get(name, ""))


@app.route("/admin/<key>/")
@login_required
def admin_list(key):
    cfg = ADMIN_REGISTRY.get(key)
    if not cfg:
        abort(404)
    ob = cfg["order_by"]
    ob = ob if isinstance(ob, (tuple, list)) else (ob,)
    items = cfg["model"].query.order_by(*ob).all()
    return render_template("admin/list.html", cfg=cfg, key=key, items=items)


@app.route("/admin/<key>/new", methods=["GET", "POST"])
@login_required
def admin_create(key):
    cfg = ADMIN_REGISTRY.get(key)
    if not cfg or cfg.get("can_create") is False:
        abort(404)
    obj = cfg["model"]()
    if request.method == "POST":
        _apply_fields(obj, cfg)
        db.session.add(obj)
        db.session.commit()
        flash(f"Запись добавлена.", "success")
        return redirect(url_for("admin_list", key=key))
    return render_template("admin/form.html", cfg=cfg, key=key, obj=obj, is_new=True)


@app.route("/admin/<key>/<int:obj_id>/edit", methods=["GET", "POST"])
@login_required
def admin_edit(key, obj_id):
    cfg = ADMIN_REGISTRY.get(key)
    if not cfg:
        abort(404)
    obj = cfg["model"].query.get_or_404(obj_id)
    if request.method == "POST":
        _apply_fields(obj, cfg)
        db.session.commit()
        flash("Изменения сохранены.", "success")
        return redirect(url_for("admin_list", key=key))
    return render_template("admin/form.html", cfg=cfg, key=key, obj=obj, is_new=False)


@app.route("/admin/<key>/<int:obj_id>/delete", methods=["POST"])
@login_required
def admin_delete(key, obj_id):
    cfg = ADMIN_REGISTRY.get(key)
    if not cfg or cfg.get("can_delete") is False:
        abort(404)
    obj = cfg["model"].query.get_or_404(obj_id)
    db.session.delete(obj)
    db.session.commit()
    flash("Запись удалена.", "success")
    return redirect(url_for("admin_list", key=key))


@app.route("/admin/<key>/<int:obj_id>/toggle", methods=["POST"])
@login_required
def admin_toggle(key, obj_id):
    cfg = ADMIN_REGISTRY.get(key)
    if not cfg:
        abort(404)
    obj = cfg["model"].query.get_or_404(obj_id)
    if hasattr(obj, "is_active"):
        obj.is_active = not obj.is_active
        db.session.commit()
    return redirect(url_for("admin_list", key=key))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="127.0.0.1", port=5000)
