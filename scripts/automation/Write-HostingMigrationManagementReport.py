"""Create the paired management DOCX without raw logs or account values."""
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile,ZIP_DEFLATED
import xml.etree.ElementTree as ET

path = Path(__file__).resolve().parents[2]/'reports/2026-09-16-hosting-accounts-migration-management.docx'
paragraphs = [
    'Rhisseth — перенос хостинга, пользователей и прав',
    '16 сентября 2026 года. Проверки: UTC / Москва (UTC+3).',
    'Результат: на VPS восстановлено оформление страниц входа и регистрации из предоставленного архива. Два пользователя и три роли перенесены в PostgreSQL с сохранением исходных идентификаторов, хешей паролей и назначений. Все 667 гексов текущей карты сохранены.',
    'Пользовательский сценарий: вход на сайт открывает карту. Обычный пользователь просматривает её; администратор и модератор могут изменять параметры. Регистрация выдаёт только обычную роль. Прежний общий пароль тестового сайта больше не требуется.',
    'Проверки: вход, регистрация, выход, ограничения прав и сохранение сессии и данных после перезапуска прошли на временных аккаунтах. Они удалены после проверки. Все поля исходных аккаунтов сверены без раскрытия данных. Страница входа доступна извне.',
    'Выявленные затруднения: публикация GitHub задерживалась в HTTPS-процессе, повтор через HTTP/1.1 прошёл. Проверочный скрипт первоначально использовал неверное Python-окружение; запуск исправлен, повторные проверки успешны. Приложение работает, полного перезапуска VPS не было.',
    'Сохранность: сделаны резервные копии базы до и после переноса и копия конфигурации nginx. Контрольная сумма гексов совпала с предыдущей версией. Автоматическое внешнее резервирование пока не настроено.',
    'Ограничения: временный сертификат HTTPS не доверен обычным браузером автоматически; DNS домена и публичный сертификат ещё требуют настройки. Реальные пароли пользователей не сбрасывались и контроллеру не раскрывались; вход ими должен проверить владелец сайта. Визуальная приёмка и длительная нагрузка ещё не выполнены.',
    'Решения: подтвердить прямой переход после входа и права модератора, выполнить пользовательскую приёмку, настроить домен и публичный TLS, передать обслуживающей команде отдельный SSH-доступ и опубликованные инструкции. Все отчёты и журналы хранятся внутри папки проекта.'
]
body=''.join('<w:p><w:r><w:t xml:space="preserve">'+escape(text)+'</w:t></w:r></w:p>' for text in paragraphs)
document='<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+body+'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr></w:body></w:document>'
path.parent.mkdir(parents=True,exist_ok=True)
with ZipFile(path,'w',ZIP_DEFLATED) as archive:
    archive.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    archive.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    archive.writestr('word/document.xml',document)
with ZipFile(path) as archive:
    assert archive.testzip() is None
    for name in archive.namelist():
        ET.fromstring(archive.read(name))
print('Created and validated:',path)
