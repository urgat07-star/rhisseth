# Проверка подготовки — 16.09.2026

Локальные проверки проекта, без операций на внутренней инфраструктуре и VPS:

- `python -m unittest discover -s rhisseth.ru/tests -v`: 2 теста, OK.
  Проверены CSV, канонические уникальные координаты, статическая карта,
  отсутствие доступа к CSV через HTTP, неверные поля/рейтинги/JSON и лимит тела.
- `docker compose ... config --quiet`: exit 0. Проверялась только конфигурация,
  контейнеры не запускались. Docker сообщил о недоступности локального config.json;
  проверка Compose завершилась успешно.
- Git создан в `rhisseth.ru`, ветка main, origin установлен на указанный GitHub.
- `git ls-remote origin`: exit 1, локальный Schannel не получил credentials.
  Повторная диагностика: локальный backend изменён на OpenSSL с TLS verification,
  ls-remote/fetch прошли. Получен Initial commit и README; локальная main
  привязана к origin/main без удаления рабочих файлов. Права push не проверены.

Первый деплой выполнен на VPS через runner: PostgreSQL 16.15, systemd и nginx.
Миграция, импорт 667 строк с полным сравнением полей, сохранение после рестартов
приложения/БД, backup и реальное восстановление с совпадением checksum прошли.
HTTPS/Basic Auth, HTML/JS/CSS/PNG, 400/404 API проверены. Внешние запросы runner
подтвердили HTTP 301 и HTTPS 401 без credentials.
TLS временный self-signed; DNS rhisseth.ru на VPS не разрешался.
Не проверены нагрузка, визуальная приёмка браузером, полный reboot и публичный
TLS по домену. Caddy/Compose не запускались: используется native deployment.
VPS проверен read-only через runner/Passbolt; см. парные отчёты в `../reports/`
этого проекта. Overlay `compose.test.yml` проверен совместно с базовым
Compose, exit 0. Рабочий первый деплой описан в `deploy/native/README.md`.
Тестовое окружение Python перенесено в `.local/runtime/` этого проекта
и не входит в Git-репозиторий. Производные кэши при необходимости пересоздаются.

Повторить тесты: Python 3.12, зависимости `app/backend/requirements.txt` и httpx,
затем `python -m unittest discover -s tests -v` из корня нового проекта.
