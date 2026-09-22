# Основная карта V6

16.09.2026 одобренный программный вариант островов установлен на
https://rhisseth.ru/interactive-map/ как Artistic V6.

Подложка app/frontend/terrain-map-group3-artistic-v6-no-grid.png полностью
совпадает по SHA256 с одобренным PNG страницы https://rhisseth.ru/map/.
Нарисованных границ гексов в подложке нет. Сетка отображается отдельным
интерактивным SVG слоем; её радиус 80 и полотно 3200×2200 сохранены.
Перемещения 21 небольшого острова описаны в docs/islands-comparison.md.

В frontend изменены только ссылка и описание PNG, метка версии и параметры
кэширования JS/CSS. Данные гексов и логика просмотра/редактирования сохранены.
Проверены авторизация, загрузка HTML/JS/CSS/PNG по HTTPS с точными SHA256,
GET /api/hexes, совпадение нового PNG с одобренным вариантом, неизменность
остальных файлов frontend, контрольной суммы PostgreSQL hexes и nginx.
Проверочный аккаунт и сессии удалены; перезапусков приложения/nginx нет.

Сценарии: scripts/automation/Promote-V6FromDocker.py и Promote-V6Vps.py.
Манифест: reports/previews/islands-v2/v6-promotion-manifest.json.
Копия прежних index.html и app.js:
/opt/rhisseth/backups/20260916-201914-frontend-before-v6/.
Для отката вернуть только эти два файла. Подложка V5 сохранена.

Локальный журнал:
reports/automation-logs/2026-09-16/20260916-201850-v6-local-docker.md.
Журнал VDS:
/opt/rhisseth/reports/automation-logs/2026-09-16/20260916-201914-v6-promotion.md.
