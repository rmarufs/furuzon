# STACK.md — технологии Furuzon

Точные версии зафиксированы в `requirements.txt`. Менять стек и ставить пакеты — только с разрешения пользователя.

## Backend
- Python 3.12
- FastAPI 0.162 (Starlette 1.10), uvicorn 0.54
- Pydantic 2.14 + pydantic-settings 2.16 (настройки из `.env`)
- SQLAlchemy 2.1 (только async) + asyncpg 0.32
- Alembic 1.20 — миграции
- PostgreSQL: локальный в разработке, Supabase на деплое

## Авторизация
- Cookie-сессия: SessionMiddleware (itsdangerous 2.2), подписанная cookie
- Пароли: argon2-cffi 25.1
- Сброс пароля: одноразовая ссылка с токеном, письмо через aiosmtplib 5.1 (SMTP-настройки из `.env`; в разработке ссылка печатается в консоль)

## Файлы и данные
- Excel: openpyxl 3.1 (.xlsx, выгрузка) и xlrd 2.0 (.xls)
- Поиск с опечатками: rapidfuzz 3.14
- QR-коды: segno 1.6 (SVG)
- Хранилище файлов: локальная папка `uploads/` в разработке (aiofiles), Supabase Storage на деплое (запросы через httpx 0.28). Выбор через `.env`, код работает с общим интерфейсом `Storage`.

## Frontend
- Jinja2 3.1 — шаблоны страниц
- Чистые HTML, CSS, JavaScript (ES-модули). Без фреймворков, CDN, npm и сборщиков
- CSS-переменные для светлой и тёмной тем

## Тесты и качество
- pytest 9.2 + pytest-asyncio 1.4 — backend
- Playwright 1.64 (pytest-playwright) — e2e в браузере
- ruff 0.17 — линтер и форматирование

## Деплой (позже)
GitHub → Render, база и файлы в Supabase.

## Не используем
React, Vue и другие фронтенд-фреймворки, Celery, Redis, GraphQL, синхронный SQLAlchemy, любые ORM кроме SQLAlchemy.