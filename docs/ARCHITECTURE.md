# ARCHITECTURE.md — Furuzon

## 1. Слои кода
- `routers/` — принимают запрос, проверяют вход через `schemas/`, вызывают сервис, возвращают ответ. Логики и SQL нет.
- `services/` — вся логика и работа с БД. Каждая функция, которая трогает данные преподавателя, принимает `owner_id`.
- `models/` — таблицы SQLAlchemy, без логики.
- `schemas/` — Pydantic-модели запросов и ответов.
- `storage/` — хранение файлов за общим интерфейсом.
- Транзакция: одна на запрос. Зависимость выдаёт сессию и делает commit при успехе, rollback при ошибке. Сервисы используют `flush`.
- Все id — целые числа. Время — UTC (timestamptz).

## 2. Настройки (`.env`, читает `core/config.py`)
`DATABASE_URL`, `SECRET_KEY`, `COOKIE_SECURE`, `SESSION_MAX_AGE_DAYS`, `PUBLIC_BASE_URL`, `STORAGE_BACKEND` (`local` | `supabase`), `UPLOADS_DIR`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_BUCKET`, `MAIL_BACKEND` (`console` | `smtp`), `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`.
Рабочие базы `furuzon` и `furuzon_test` и файл `.env` создаёт пользователь.

## 3. База данных

| Таблица | Поля | Заметки |
|---|---|---|
| `users` | id, email (уникальный, в нижнем регистре), password_hash, first_name (текст до 50 символов, по умолчанию пустая строка), last_name (текст до 50 символов, по умолчанию пустая строка), language (`ru`/`tg`, по умолчанию `ru`), theme (`light`/`dark`, по умолчанию `light`), created_at | |
| `password_reset_tokens` | id, user_id → users (cascade), token_hash, expires_at, used_at | токен живёт 1 час, одноразовый, в БД только хеш |
| `groups` | id, owner_id → users (cascade), number (текст), course (1–6), columns (JSONB), created_at, updated_at | `columns` — упорядоченный список `[{key, title}]`, например `{"key":"c1","title":"ФИО"}`. Ключи стабильные, при перестановке не меняются |
| `students` | id, group_id → groups (cascade), position, data (JSONB), created_at | `data` — `{ "c1": "Иванов И.", "c2": "..." }` по ключам колонок |
| `files` | id, owner_id → users (cascade), original_name, storage_key, size_bytes, content_type, public_token (уникальный), created_at | `storage_key` — случайное имя, не оригинальное |
| `file_groups` | file_id, group_id (оба cascade), PK (file_id, group_id) | один файл в нескольких группах хранится один раз |
| `activity` | id, owner_id → users (cascade), type, object_type, object_id (может быть пустым), object_title, created_at | см. раздел 8 |

Правила данных:
- Удаление колонки группы: убрать ключ из `groups.columns` и из `data` всех студентов этой группы.
- Удаление студента или группы каскадом чистит связанные строки (см. раздел 8 SPEC). Файлы-сироты (у которых не осталось групп) удаляет сервис вместе с объектом в хранилище.
- Уникальности номера группы нет (SPEC молчит).

## 4. Страницы (HTML, `routers/pages.py`)
Требуют входа, кроме помеченных.

| Адрес | Что |
|---|---|
| `/login`, `/register`, `/forgot-password`, `/reset-password?token=` | без входа |
| `/` | главная |
| `/groups`, `/groups/new`, `/groups/{id}` | группы, загрузка, список группы |
| `/materials` | материалы |
| `/settings` | смена пароля |
| `/f/{token}` | публичная ссылка файла, без входа |

Раздел `/materials` без групп перенаправляет на `/groups` (GEN-6). Группа открыта: `group_viewed` (пишет роутер страницы).

## 5. API (JSON, префикс `/api`, требуют входа)

**Авторизация и профиль**
`POST /auth/register` (тело содержит first_name и last_name), `POST /auth/login`, `POST /auth/logout`, `POST /auth/forgot-password`, `POST /auth/reset-password`, `POST /auth/change-password`, `GET /auth/me` (возвращает ещё и имя с фамилией), `PATCH /me/profile` (first_name, last_name), `PATCH /me/preferences` (language, theme). Первые пять (кроме logout) — без входа.

**Группы**
- `POST /groups/parse` — multipart: файл и необязательный `header_row`. Возвращает предпросмотр (первые 30 строк), найденную строку заголовка и список колонок. Ничего не сохраняет.
- `POST /groups` — multipart: файл, `header_row`, настройка колонок (порядок, какие оставить), `number`, `course`. Создаёт группу и студентов. (Файл присылается заново: сервер ничего не хранит между шагами.)
- `GET /groups` (`?course=`), `GET /groups/{id}`, `PATCH /groups/{id}` (number, course, порядок колонок), `DELETE /groups/{id}`
- `DELETE /groups/{id}/columns/{key}`
- `GET /groups/{id}/students` (`?q=` — поиск), `POST /groups/{id}/students`, `PATCH /groups/{id}/students/{sid}` (изменить ячейку: `key`, `value`), `DELETE /groups/{id}/students/{sid}`
- `GET /groups/{id}/export` — Excel

**Материалы**
- `GET /materials/tree` — дерево Курс → Группа → файлы
- `POST /materials` — multipart: файл, `course`, `group_ids[]` (все группы должны принадлежать преподавателю и выбранному курсу)
- `DELETE /materials/{id}` — удалить файл целиком
- `DELETE /materials/{id}/groups/{group_id}` — убрать из одной группы; если групп не осталось, файл удаляется целиком
- `PUT /materials/{id}/file` — заменить файл. Запись остаётся, но `public_token` и `storage_key` новые, старый файл удаляется из хранилища. Старая ссылка и QR перестают работать (MAT-7)
- `GET /materials/{id}/qr.svg` — QR на `PUBLIC_BASE_URL/f/{token}`

**Главная**
`GET /activity?limit=4`

**Публичное, без входа**
`GET /f/{token}` — отдаёт файл со скачиванием (`Content-Disposition: attachment`, оригинальное имя, `X-Content-Type-Options: nosniff`). Неизвестный токен → HTML-страница «файл не найден» на русском и таджикском, статус 404.

## 6. Ошибки API
Формат: `{"error": {"code": "group_not_found", "details": {...}}}`. Текста на языке пользователя сервер не отдаёт: фронтенд переводит по ключу `errors.<code>` из локалей.
Статусы: 401 нет входа, 404 не найдено или чужое, 409 конфликт, 413 файл слишком большой, 415 неподходящий тип, 422 неверные данные.

## 7. Безопасность
- Доступ к данным: любые выборки и изменения идут через функции вида `get_owned_or_404(model, id, owner_id)`. Чужой объект неотличим от несуществующего (404).
- Сессия: подписанная cookie (HttpOnly, SameSite=Lax, Secure на проде).
- Пароль: argon2, минимум 8 символов. Сброс: `forgot-password` всегда отвечает одинаково (не раскрывает, есть ли такой email); токен случайный, хранится хеш.
- Файлы: расширение, размер (до 10 МБ) и сигнатура (PDF — `%PDF-`; DOCX — ZIP со структурой Word; DOC — OLE). Excel: .xlsx — ZIP, .xls — OLE. Имя в хранилище — случайное.
- Лимиты разбора Excel: до 2000 строк и 50 колонок, больше — понятная ошибка.

## 8. Журнал действий (`activity`)
Типы: `group_viewed`, `file_uploaded`, `file_deleted`.
- Повтор типа над тем же объектом не создаёт новую запись, а обновляет `created_at` у прежней (DEF-2).
- `object_title` — название на момент действия.
- Записи про удалённую группу удаляются вместе с ней. У `file_deleted` объекта нет, клик ведёт в «Материалы».
- Главная показывает 4 самых свежих записи.

## 9. Excel
- Чтение: `.xlsx` через openpyxl (read-only), `.xls` через xlrd. Пустые строки пропускаются.
- Поиск заголовка (`services/excel/header_detect.py`): первая строка, где заполнено столько же ячеек, сколько в большинстве строк ниже, и это в основном текст. Это эвристика, она проверяется набором тестовых файлов в `tests/fixtures/` (чистый, с шапкой из 1–5 строк, пустые строки сверху, объединённые ячейки, `.xls`).
- Выгрузка: openpyxl, колонки в текущем порядке, убранные колонки не попадают.
- Поиск студентов: приведение к нижнему регистру, удаление всех пробелов, rapidfuzz по значениям всех ячеек студента.

## 10. Файловое хранилище
Интерфейс `Storage`: `save(key, data, content_type)`, `read(key)`, `delete(key)`, `exists(key)`. Реализации: `local` (папка `uploads/`) и `supabase`. Выбор по `STORAGE_BACKEND`. Остальной код про реализацию не знает.

## 11. Язык и тема
- Язык: пользователь → cookie → `ru`. Словари `ru.json` и `tg.json` с плоскими ключами (`groups.title`, `errors.group_not_found`). Набор ключей в обоих файлах всегда одинаковый. Словарь передаётся в JS из шаблона.
- Тема: `data-theme` на `<html>`, ставится сервером из профиля до отрисовки, чтобы не мигало. На страницах без входа — по cookie или системной теме.

## 12. Фронтенд
Сервер отдаёт каркас страницы (Jinja), JS ES-модулями грузит данные через `/api` и рисует. `static/js/core/api.js` — единая обёртка запросов: на 401 ведёт на `/login`, коды ошибок переводит через i18n. Одна страница — один файл в `static/js/pages/` и один в `static/css/pages/`.

## 13. Тесты
- `tests/unit/` — парсер Excel и поиск заголовка, поиск студентов.
- `tests/api/` — API через httpx + ASGITransport на базе `furuzon_test`, данные чистятся между тестами.
- Обязательно для каждого ресурса (группа, студент, файл): тест, что преподаватель Б не видит и не меняет данные преподавателя А.
- `tests/e2e/` — Playwright: регистрация, загрузка группы, загрузка файла и скачивание по `/f/{token}`.