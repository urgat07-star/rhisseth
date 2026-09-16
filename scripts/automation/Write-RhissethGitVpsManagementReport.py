"""Create a concise management DOCX locally, without logs or credentials."""
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

path = Path(__file__).resolve().parents[2] / 'reports/2026-09-16-rhisseth-git-vps-management.docx'
path.parent.mkdir(parents=True, exist_ok=True)
paragraphs = [
    'Rhisseth: готовность Git и тестового VPS',
    '16 сентября 2026 года. Время проверок: UTC / Москва (UTC+3).',
    'Результат: чтение GitHub восстановлено; SSH-подключение к тестовому серверу успешно. Развёртывание приложения ещё не выполнялось.',
    'Проблема Git связана с TLS-компонентом Windows Schannel в текущем окружении. Переход проекта на OpenSSL позволил получить существующую ветку и историю репозитория. Проверка сертификатов сохранена. Права публикации в GitHub пока не подтверждены.',
    'Сервер соответствует выбранному тестовому профилю: 1 CPU, около 1 ГБ памяти, Ubuntu 24.04 LTS. На момент проверки доступно около 619 МБ памяти и 6,1 ГБ диска. Swap отсутствует. Веб-сервер nginx уже работает.',
    'Влияние на сервис: изменения на VPS не вносились, установки и перезагрузки не выполнялись. Проверка не устанавливает состояние существующего сайта и его доступность для пользователей.',
    'Риски: малый запас памяти и диска, возможный конфликт нового веб-сервера с nginx. Производительность приложения и восстановление базы на этом сервере ещё не проверены. Ключ SSH сервера принят при первом подключении; независимая сверка с провайдером остаётся открытой.',
    'Следующие действия: проверить назначение nginx, подготовить тестовый деплой с одним процессом приложения и ограниченной памятью PostgreSQL, оценить добавление swap и организовать резервные копии вне VPS. После запуска проверить сохранение данных, перезапуск, восстановление и потребление ресурсов.',
    'Решение о тестовом VPS 1 CPU / 1 ГБ принято пользователем. Переход к более мощному серверу следует оценить по результатам нагрузочных тестов. Подробные доказательства и аудит находятся в парном техническом Markdown-отчёте.'
]
body = ''.join('<w:p><w:r><w:t xml:space="preserve">' + escape(p) + '</w:t></w:r></w:p>' for p in paragraphs)
document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + body + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr></w:body></w:document>'
with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
    archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    archive.writestr('_rels/.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    archive.writestr('word/document.xml', document)
with ZipFile(path) as archive:
    assert archive.testzip() is None
    import xml.etree.ElementTree as ET
    for name in archive.namelist():
        ET.fromstring(archive.read(name))
print('Created and validated:', path)
