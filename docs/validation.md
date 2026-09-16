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

Не проверены: миграции и импорт на живой PostgreSQL, сохранение после перезапуска,
реальное восстановление дампа, Caddy/TLS и внешний доступ к домену.
Это обязательные проверки при подготовке staging перед production.
VPS проверен read-only через runner/Passbolt; см. парные отчёты в `../reports/`
этого проекта. Overlay `compose.test.yml` проверен совместно с базовым
Compose, exit 0. Развёртывание ещё не выполнено.
Тестовое окружение Python перенесено в `.local/runtime/` этого проекта
и не входит в Git-репозиторий. Производные кэши при необходимости пересоздаются.

Повторить тесты: Python 3.12, зависимости `app/backend/requirements.txt` и httpx,
затем `python -m unittest discover -s tests -v` из корня нового проекта.
