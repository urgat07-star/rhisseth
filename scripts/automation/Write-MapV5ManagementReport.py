"""Generate the management report for V5 publication and grid coverage findings."""
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as ET

path=Path(__file__).resolve().parents[2]/'reports/2026-09-16-map-v5-publication-grid-management.docx'
paragraphs=[
    'Rhisseth — публикация карты V5 и актуализация данных',
    '16 сентября 2026 года, 10:53–10:55 UTC / 13:53–13:55 Москва.',
    'Карта V5 опубликована на VDS. Проверены вход, выдача изображения и API. Службы работают. До публикации сохранена резервная копия базы; все 667 гексов и существующие аккаунты сохранены. Перезапусков служб и сервера не было.',
    'Выявлен функциональный пробел: текущий активный слой покрывает около 89,5% полотна. Для 49 видимых координат, преимущественно внизу слева, нет записей. Поэтому полная интерактивность и актуальная база V5 ещё не подтверждены.',
    'Причина пробела — прежняя координатная выборка базы не включает всю область новой карты. Пиксельное совпадение художественной сетки и активного слоя ещё требует проверки. Старые параметры нельзя считать обновлёнными по одному изображению.',
    'Бизнес-воздействие: подложка доступна авторизованным пользователям, но часть карты пока не открывает данные гекса. Публичный HTTPS использует временный самоподписанный сертификат и вызывает предупреждения браузера.',
    'Требуется решение: параметры, не определяемые по PNG, оставить пустыми для проверки либо назначать по явно утверждённым игровым шаблонам. После этого провести регистрацию сетки, пополнить координаты, проверить классификацию местности и выполнить резервируемый импорт.',
    'Отдельный web-редактор базы создаётся после актуализации данных, как указал владелец. Требуются права ролей, история изменений и защита от конфликтующих правок. Публичный TLS и внешнее резервирование остаются отдельными задачами.',
    'Технический отчёт и санитизированные журналы хранятся в reports внутри проекта; секреты, персональные данные и сырые журналы в этот документ не включены.'
]
body=''.join('<w:p><w:r><w:t xml:space="preserve">'+escape(p)+'</w:t></w:r></w:p>' for p in paragraphs)
document='<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+body+'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>'
path.parent.mkdir(parents=True,exist_ok=True)
with ZipFile(path,'w',ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    z.writestr('word/document.xml',document)
with ZipFile(path) as z:
    assert z.testzip() is None
    for name in z.namelist():
        ET.fromstring(z.read(name))
print('Created and validated:',path)
