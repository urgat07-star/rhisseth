"""Build the sanitized 2026-09-18 release inventory from the fixed Git baseline."""
from pathlib import Path
import ast
import re
import subprocess
from datetime import datetime, timezone, timedelta
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
BASE = 'c023b82'
RELEASE = 'bb5204e'
paths = subprocess.check_output(
    ['git', 'diff', '--name-only', BASE, RELEASE], cwd=ROOT, text=True
).splitlines()
summaries = {
    'app/backend/main.py': 'Hex administration, owner-scoped territory naming, and cabinet access with CSRF checks.',
    'app/backend/admin_users.py': 'Administrator-only account edits, password assignment, deletion, audit, and session revocation.',
    'app/backend/game_start.py': 'Allocate 2-3 connected free land cells atomically; random preview does not reserve land.',
    'app/backend/hex_rules.py': 'Terrain categories, visible grid coordinates, revisions, and hex connectivity validation.',
    'app/backend/player_cabinet.py': 'Owner-scoped profile, barony statistics, crest, rename, and confirmed abandonment.',
    'app/backend/site_auth.py': 'Login and registration send every role to the cabinet; login redirects disable caching.',
    'app/frontend/admin.js': 'Edit hex metadata and connected territories with server-side revision checks.',
    'app/frontend/app.js': 'Render V6 ownership boundaries and preview connected free land for barony creation.',
    'app/frontend/cabinet.js': 'Cabinet tabs, account settings, crest/color, rename, and confirmed land release.',
    'app/frontend/users.js': 'Administrator account search, role/password changes, and confirmed deletion.',
    'app/frontend/styles.css': 'Styles for hex administration, barony selection, and player cabinet layouts.',
    'app/frontend/admin.html': 'Hex administration controls and navigation to account management.',
    'app/frontend/cabinet.html': 'Player cabinet with barony, economy, diplomacy, and account settings tabs.',
    'app/frontend/create-barony.html': 'Barony name, crest/color, agreement, and connected free-land selection.',
    'app/frontend/index.html': 'V6 interactive map and navigation for cabinet, barony creation, and administration.',
    'app/frontend/users.html': 'Account editor with roles, password confirmation, and deletion control.',
    'scripts/automation/Invoke-GameAccess.ps1': 'Transfer reviewed game-access scripts through pinned runner SSH and write sanitized audit logs.',
    'scripts/automation/Invoke-HexMetadata.ps1': 'Run hex metadata inspection and deployment through pinned runner SSH with audit logs.',
    'scripts/automation/Invoke-RhissethRecovery.ps1': 'Control reviewed recovery operations through pinned runner SSH with audit logs.',
    'scripts/automation/Invoke-UserAdmin.ps1': 'Control account administration deployment through pinned runner SSH with audit logs.',
    'scripts/automation/Inspect-RhissethMemory.sh': 'Read target memory and service usage for deployment diagnostics.',
    'scripts/automation/rhisseth-backup.service': 'Run the project backup worker under systemd.',
    'scripts/automation/rhisseth-backup.timer': 'Schedule the project backup service with systemd.',
}

def description(name):
    if name in summaries:
        return summaries[name]
    path = ROOT / name
    if path.suffix == '.py':
        doc = ast.get_docstring(ast.parse(path.read_text(encoding='utf-8-sig')))
        if doc:
            return doc.splitlines()[0]
    if name.startswith('tests/'):
        return 'Regression checks for ' + Path(name).stem.removeprefix('test_').replace('_', ' ') + '.'
    return 'Release component: ' + Path(name).stem.replace('_', ' ').replace('-', ' ') + '.'

# SQL migrations are immutable: even a comment would change their applied hashes.
# JSON and binary assets use the Markdown inventory because they cannot carry comments.
annotated = []
for name in paths:
    path = ROOT / name
    if path.suffix not in ('.py', '.js', '.css', '.html', '.ps1', '.sh', '.service', '.timer'):
        continue
    content = path.read_text(encoding='utf-8-sig')
    if 'Release review 2026-09-18' in content:
        if path.suffix in ('.ps1', '.sh', '.service', '.timer'):
            content = re.sub(r'(?m)^# Release review 2026-09-18.*$',
                             '# Release review 2026-09-18 (0.0.2): ' + description(name), content)
            path.write_text(content, encoding='utf-8')
        annotated.append(name)
        continue
    note = 'Release review 2026-09-18 (0.0.2): ' + description(name)
    ref = 'Details: docs/releases/0.0.2-changes-2026-09-18.md.'
    if path.suffix in ('.js', '.css'):
        comment = f'/* {note}\n * {ref} */\n'
    elif path.suffix == '.html':
        comment = f'<!-- {note}\n     {ref} -->\n'
    else:
        comment = f'# {note}\n# {ref}\n'
    if content.startswith('#!') or (path.suffix == '.html' and content.lower().startswith('<!doctype')):
        first, sep, rest = content.partition('\n')
        content = first + sep + comment + rest
    else:
        content = comment + content
    path.write_text(content, encoding='utf-8')
    annotated.append(name)

stamp = datetime.now(timezone.utc)
utc = stamp.isoformat(timespec='seconds')
moscow = stamp.astimezone(timezone(timedelta(hours=3))).isoformat(timespec='seconds')
intro = '''# Rhisseth 0.0.2 — полный перечень изменений, 18.09.2026

Сравнение Git: `c023b82` (0.0.1) → `bb5204e` (0.0.2), 96 файлов.
Это состав выпуска, зафиксированного сегодня; часть работ по резервированию
выполнена 17.09 и включена в сегодняшний коммит. Дата коммита не означает,
что все включённые работы выполнены 18.09.

## Игровые функции и интерфейсы

- Artistic V6; расширенная таблица гексов, категории суши/побережья/моря,
  состав ландшафта, владельцы, именование территорий и проверка связности.
- Стартовая барония: 2–3 соседних свободных гекса, ручной выбор либо случайный
  предварительный подбор, пять гербов, цвет и согласие. Подбор не резервирует
  землю; сохранение повторно проверяет доступность под блокировкой.
- Личный кабинет v0.1: сведения о владении и ресурсах, настройки аккаунта,
  герб/цвет, переименование с сохранением географических названий, подтверждённый
  отказ от владения. Без баронии доступны настройки и переход к её созданию.
- Вход всех ролей и регистрация ведут в кабинет; переходы входа не кэшируются.
- Административная панель: поиск аккаунтов, логин/e-mail, роли, назначение
  пароля и удаление. Защищены собственный и последний администратор; изменения
  проверяют исходную версию, права и CSRF. Смена пароля завершает все сеансы.
- Удаление аккаунта освобождает гексы и сохраняет обезличиваемый аудит.
  Модераторы редактируют карту, но не управляют аккаунтами.

## Эксплуатация и материалы

- Автоматизация резервирования, хранения, проверки архивов и восстановления;
  systemd timer/service, native deployment и контейнер аварийного восстановления.
- Проверка SSH/SFTP-доступа игровых администраторов по роли, runner-контроллеры
  и серверные проверки. Наличие кода не подтверждает применение каждого сценария.
- Инструкции администратора, восстановление вручную, передача дизайнеру,
  регрессионные и браузерные проверки. Предложение в `docs/proposals/` остаётся
  предложением, а не включённой в приложение функцией.

## Миграции и ограничения

Схема: `003`–`008`; пояснения — [data/migrations/README.md](../../data/migrations/README.md).
Перед обновлением нужна резервная копия, миграции идут по порядку. Уже применённые
SQL-файлы нельзя менять даже ради комментариев: проверяется SHA-256.
Сегодняшнее документирование не меняет бизнес-логику и не требует новых миграций.
Экономика и дипломатия в кабинете не означают готовых игровых расчётов;
население, армии, торговля и налоги пока не реализованы. Самостоятельное
восстановление пароля по e-mail и интерфейс аудита отсутствуют.

## Полный состав исходного релизного коммита

Перечень включает все 96 изменённых файлов, включая бинарные ресурсы,
конфигурации и материалы, которым нельзя добавить комментарии внутри файла.

'''
inventory = '\n'.join(f'- [`{name}`](../../{name})' for name in paths)
(ROOT / 'docs/releases/0.0.2-changes-2026-09-18.md').write_text(intro + inventory + '\n', encoding='utf-8')

report = f'''# Rhisseth — проверка проекта и документирование релиза 18.09.2026

UTC: {utc}; Europe/Moscow: {moscow}. Контроллер: Codex.
Область: локальный проект, вся текущая тестовая коллекция и состав выпуска
`c023b82` → `bb5204e`. Исходная ветка: `release/0.0.2`, рабочее дерево было чистым.
Git remote origin указывает на GitHub. Адрес GitLab требуется от пользователя.

## Результат и свидетельства

В исходном релизном коммите 96 файлов. Краткое описание уже существовало
в `docs/releases/0.0.2.md`; отчёты хранились локально и исключались через
`.gitignore`. Добавлен полный перечень релиза со всеми путями, комментарии
в {len(annotated)} исходных файлах и отдельное описание неизменяемых миграций.
Проверены backend, клиентские страницы, миграции, эксплуатационные материалы
и регрессионные проверки; это проверка состава и тестируемого поведения,
а не исчерпывающий аудит безопасности каждой ветви кода.

Проверки: `.local/hex-venv/Scripts/python.exe -m unittest discover -s tests -v`:
40 тестов, 39 успешно, 1 пропущен; exit 0. Пропущена Linux-проверка хранения
с `flock`, недоступным на Windows. Starlette сообщает об устаревшем использовании
httpx; предупреждение не помешало выполнению тестов.

Три браузерных скрипта завершились с exit 0: `check-player-cabinet-ui.py`,
`check-player-onboarding-ui.py`, `check-users-ui.py`. Проверены кабинет,
настройки и ротация сеанса, переименование/герб/отказ, создание баронии,
запрет моря, согласие, административная таблица, роли, сохранение и удаление,
мобильные окна; ошибок JavaScript не обнаружено.

После добавления комментариев повторно выполнены все 40 Python-тестов:
39 успешны, один пропущен. Проверена синтаксическая корректность изменённых
PowerShell-файлов и Python-исходников; исходный код 62 файлов отличается только
добавленными комментариями. Проверены неизменность SQL, целостность Word XML/ZIP,
отсутствие сигнатур ключей и распространённых токенов в составе коммита,
`git diff --cached --check`. Сигнатурная проверка не заменяет полный аудит секретов.

## Покрытие и ограничения

Тесты проверяют доступ и CSRF, категории и связность, выделение свободных земель,
кабинет и чужие владения, переименование и отказ, переход после входа всех ролей,
архивы и неизменность применённых миграций. Полноценные PostgreSQL-транзакции,
нагрузка, резервирование и восстановление на Linux этим прогоном не проверялись.
Браузерные сценарии используют перехват запросов и вымышленные данные.
Текущий прогон не проверяет опубликованный сайт и не изменяет реальные аккаунты.

Предыдущие технические отчёты о публикациях хранятся в `reports/`:
`rhisseth-hex-metadata-2026-09-18.md`, `user-admin-release-2026-09-18.md`,
`user-password-release-2026-09-18.md`,
`2026-09-18-player-onboarding-release-technical.md`,
`2026-09-18-login-redirect-technical.md`.
Они содержат ссылки на санитизированные журналы runner и прежние результаты;
эти результаты не выдаются за сегодняшнюю повторную серверную проверку.

## Изменения, выводы и рекомендации

SQL-файлы 003–008 сохранены побайтно. Бинарные изображения и JSON описаны
в перечне выпуска; в них комментарии не добавлялись. Изменены пояснения
и документация, бизнес-логика не менялась. Серверных операций, развёртывания,
изменений БД и перезагрузок в рамках этой проверки нет; runner не использовался.
Поэтому новых runner-журналов нет. Секреты и полные операционные архивы
не включаются в публикуемый отчёт. Новые сводные Markdown/Word-отчёты разрешены
в Git точечными исключениями, остальные локальные материалы остаются исключены.

Описание релиза: [полный состав](../docs/releases/0.0.2-changes-2026-09-18.md).
Рекомендуется выполнить Linux-проверку хранения в штатном runner-процессе
перед следующим эксплуатационным изменением, а также пользовательскую приёмку
регистрации, кабинета и выделения земли. Для публикации в GitLab нужен точный URL;
существующий GitHub origin не следует подменять догадкой.
'''
(ROOT / 'reports/project-review-2026-09-18.md').write_text(report, encoding='utf-8')

paragraphs = [
    'Rhisseth 0.0.2: проверка проекта и описание изменений, 18.09.2026',
    'Проверен состав релиза из 96 файлов. Полное описание включает карту V6, стартовую баронию, кабинет игрока, администрирование аккаунтов и средства резервирования/восстановления.',
    'Дополнены комментарии исходных файлов, подготовлены полный перечень выпуска и технический отчёт. Применённые миграции сохранены; новая схема и развёртывание не требуются.',
    'Локальная коллекция: 39 тестов успешны, один Linux-тест пропущен на Windows. Три браузерные проверки кабинета, создания баронии и администрирования успешны на синтетических данных. Проверка рабочего сервера, реальных аккаунтов и нагрузки в эту работу не входит.',
    'Сервисный эффект: документация выпуска и результаты проверки становятся доступными в Git. Бизнес-логика не менялась; серверы и база не изменялись и не перезагружались.',
    'Риски и ограничения: Linux-проверку хранения требуется выполнить в штатном runner-процессе; экономика и дипломатия ещё не являются полноценными игровыми системами. Требуется пользовательская приёмка игровых сценариев.',
    'Публикация: коммит готовится в release/0.0.2. Настроен GitHub; для отправки в запрошенный GitLab требуется URL репозитория. Фактический результат публикации фиксируется в техническом отчёте.',
]
document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
document += ''.join('<w:p><w:r><w:t>' + escape(p) + '</w:t></w:r></w:p>' for p in paragraphs)
document += '<w:sectPr/></w:body></w:document>'
with ZipFile(ROOT / 'reports/project-review-2026-09-18.docx', 'w', ZIP_DEFLATED) as archive:
    archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    archive.writestr('_rels/.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    archive.writestr('word/document.xml', document)
print(f'Inventory: {len(paths)} files; comments added: {len(annotated)}; Markdown/Word reports written.')
