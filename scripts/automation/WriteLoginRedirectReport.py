# Release review 2026-09-18 (0.0.2): Generate the management report from the matching sanitized technical report.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Generate the management report from the matching sanitized technical report."""
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[2]
source=root/'reports/2026-09-18-login-redirect-technical.md'
output=root/'reports/2026-09-18-login-redirect-management.docx'
assert source.is_file()
paragraphs=[
    'Rhisseth: исправление перехода после входа, 18 сентября 2026 года (UTC / Москва).',
    'Проблема: пользователь сообщил, что после входа открывается карта вместо личного кабинета. Проверка опубликованного сайта подтвердила такой переход для администратора.',
    'Причина: обработчик входа направлял обычных игроков в кабинет, а администраторов и модераторов на карту. Роль аккаунта пользователя не проверялась, поэтому привязка его конкретного теста к этой причине не установлена.',
    'Изменение: единый переход в личный кабинет для всех ролей. Доступ к карте и административные права сохранены. Данные аккаунтов и бароний исправлением не меняются.',
    'Проверки: локально прошли 30 тестов, включая вход всех трёх ролей. Результат публикации, резервная копия и проверка публичного перенаправления указаны в техническом отчёте.',
    'Влияние: затронут порядок открытия страниц; недоступность сайта и потеря данных не установлены. Перезапускается только приложение, без перезагрузки VPS или PostgreSQL.',
    'Действия: повторить пользовательский вход. Если отклонение сохраняется, потребуется адрес страницы и цепочка переходов конкретного сценария. Отчёты и журналы доступны в папке reports; отправка по электронной почте не выполнялась.',
]
body=''.join('<w:p><w:r><w:t>'+escape(p)+'</w:t></w:r></w:p>' for p in paragraphs)
with ZipFile(output,'w',ZIP_DEFLATED) as archive:
    archive.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    archive.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+body+'</w:body></w:document>')
with ZipFile(output) as archive:
    assert archive.testzip() is None
    for name in archive.namelist():ET.fromstring(archive.read(name))
print('Created and validated management report')
