"""Generate the paired management DOCX locally; no raw logs or credentials."""
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as ET

path = Path(__file__).resolve().parents[2] / 'reports/2026-09-16-first-vps-deployment-management.docx'
paragraphs = [
    'Rhisseth — первый тестовый деплой на VPS',
    '16 сентября 2026 года. Проверки: UTC / Москва (UTC+3).',
    'Результат: тестовая версия работает на VPS с 1 CPU и 1 ГБ памяти. Развёрнуты PostgreSQL, Python-приложение и HTTPS через существующий nginx. Импортированы 667 гексов.',
    'Проверено: получение и обновление проекта непосредственно из GitHub на VPS; доступ к карте и API; защита паролем; сохранение изменения после перезапуска приложения и базы; резервирование и восстановление данных в отдельную тестовую базу. Временное тестовое изменение возвращено к исходному состоянию.',
    'При первой установке выявлена ошибка прав чтения конфигурации PostgreSQL. Причина установлена по журналу и исправлена; последующий запуск и все проверки прошли. На момент ошибки новый сайт ещё не был опубликован. Перезагрузки VPS не было.',
    'Доступ: тестовый HTTPS по IP 62.113.109.168. Пароль хранится защищённо на VPS и не включён в отчёт. Сертификат временный, браузер не доверяет ему автоматически. Домен rhisseth.ru не разрешался на VPS при проверке; DNS и публичный TLS-сертификат требуют настройки.',
    'Ресурсы: после проверок доступно около 535 МБ памяти и 5,8 ГБ диска. Это подтверждает возможность первой тестовой работы, но не ёмкость под реальной нагрузкой.',
    'Передача команде: в GitHub опубликована инструкция обслуживания, обновления и отката. Для участников команды необходимо выдать отдельный SSH-доступ и права обслуживания через владельца инфраструктуры; персональные доступы ещё не создавались.',
    'Следующие действия: настроить DNS и публичный сертификат, организовать автоматические резервные копии вне VPS, выполнить визуальную приёмку и нагрузочные проверки. Генерация изображений OpenAI и многопользовательские роли относятся к следующим этапам.',
    'Подробные доказательства, ограничения и ссылки на аудит приведены в парном техническом Markdown-отчёте внутри папки проекта.'
]
body = ''.join('<w:p><w:r><w:t xml:space="preserve">' + escape(text) + '</w:t></w:r></w:p>' for text in paragraphs)
document = '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + body + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr></w:body></w:document>'
path.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
    archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    archive.writestr('_rels/.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    archive.writestr('word/document.xml', document)
with ZipFile(path) as archive:
    assert archive.testzip() is None
    for name in archive.namelist():
        ET.fromstring(archive.read(name))
print('Created and validated:', path)
