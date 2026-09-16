"""Write sanitized reports for the local V5 interactive grid correction."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET
import struct

root = Path(__file__).resolve().parents[2]
asset = root / 'app/frontend/terrain-map-group3-artistic-v5-no-grid.png'
assert struct.unpack('>II', asset.read_bytes()[16:24]) == (1508, 1043)
base = root / 'reports/2026-09-16-map-v5-live-grid'
technical = '''# Исправление интерактивной сетки Rhisseth V5

## Область и время
16.09.2026, около 11:49–11:52 UTC / 14:49–14:52 Europe/Moscow.
Контроллер: Codex / N7198. Область: frontend интерактивной карты Rhisseth.

## Свидетельства и причина
Предыдущий frontend отображал PNG со встроенной художественной сеткой,
но области выбора создавал отдельной геометрией: радиус 80, viewBox 3200×2200.
CSS использовал пропорции 1514/1039 вместо фактических 1508/1043.
Две независимые сетки не совпадали. Чистая подложка пользователя визуально
проверена; её PNG-заголовок подтверждает размер 1508×1043.

## Изменение
Подключён terrain-map-group3-artistic-v5-no-grid.png. Границы рисуются stroke
тех же SVG polygons, которые получают события выбора. CSS использует 1508/1043;
preserveAspectRatio=none обеспечивает одинаковое масштабирование PNG и SVG.
Параметры геометрии, координаты и данные БД сохранены. Добавлены версии URL
JS/CSS для обновления браузерного кэша. Скрипт публикации и live audit проверяют новый PNG.

## Последовательность и проверки
Визуально проверены обе подложки и исходный frontend. git diff --check прошёл.
Создан локальный commit bf01c86. Подключение к runner отклонено из-за недоступности
ключа в sandbox; целевой VDS не изменялся. Автоматическая проверка отклонила
эскалацию git push: требуется явное разрешение передачи изменений в GitHub remote.

## Ограничения и воздействие
Локальное исправление устраняет двойную сетку. Публикация и проверка рабочей
страницы не завершены. Полная интерактивность полотна не подтверждена:
существующие 407 активных гексов и пробелы координат остаются как в прежнем
отчёте. Классификация и характеристики БД не обновлялись по изображению.

## Вывод и рекомендации
После разрешения публикации отправить commit в urgat07-star/rhisseth,
выполнить publish-map и audit-map через закреплённый STU-AUTOMATION-01
(10.210.52.128). Проверить выдачу HTML, PNG, CSS/JS и неизменность checksum БД.
Затем отдельно расширить покрытие координат и актуализировать игровые данные.
Изменений VDS/БД, перезапусков служб и reboot не было.

## Санитизированный журнал
[Неуспешный preflight runner](automation-logs/2026-09-16/20260916-114953-rhisseth-runner-native.md).
Passbolt resource ID: da44a388-e458-4379-ab4c-c204696804b2; секреты не включены.
'''
technical += '''
## Дополнение: вся подложка
По последующему указанию пользователя render() формирует все пересекающие
полотно клетки независимо от прежней категории «Вне полотна». Для отсутствующих
записей создаётся клиентская карточка Q/R с пустыми параметрами. Первый PUT
авторизованного admin/moderator выполняет INSERT; повторные сохранения используют
ON CONFLICT с объединением только переданных полей и сохранением остальных данных.
Сервер ограничивает допустимые координаты геометрией полотна. CSRF и роли сохранены.
Автоматического массового заполнения БД или назначения биомов не выполняется.
Тесты проверяют покрытие 70400 точек полотна, создание гекса в нижнем левом углу,
отказ вставки вне полотна и прежние проверки API/прав. Восемь тестов прошли.
При будущем развёртывании нужен перезапуск приложения rhisseth для нового PUT;
скрипт публикации учитывает это. Сейчас перезапуск не выполнялся.
'''
base.with_suffix('.md').write_text(technical, encoding='utf-8')
paragraphs = [
    'Rhisseth V5 — исправление интерактивной сетки',
    '16 сентября 2026 года; UTC / Europe/Moscow.',
    'Причина несовпадения: отдельные видимая и интерактивная сетки, а также различие пропорций изображения и слоя выбора.',
    'Подготовлено локальное исправление: чистая подложка и единая сетка, которая одновременно показывает границы и обрабатывает выбор гекса.',
    'Публикация не завершена. Автоматическая проверка требует явного разрешения отправки изменений в GitHub. Подключение к runner ограничено доступом к SSH-ключу.',
    'Дополнительно подготовлена сетка на всё изображение. Отсутствующие в базе гексы получают пустую карточку и создаются при первом сохранении администратором или модератором. Игровые параметры автоматически не назначаются. Восемь локальных тестов прошли.',
    'Рабочий сайт и база данных не изменены; перезапусков не было. Для публикации обновлённого сохранения потребуется перезапуск приложения. Игровые параметры по новой подложке требуют отдельной актуализации.',
    'Требуется разрешить публикацию в urgat07-star/rhisseth, затем выполнить развёртывание и проверку через обязательный runner. Расширение покрытия и обновление игровых данных требуют отдельной работы.'
]
body = ''.join('<w:p><w:r><w:t>'+escape(p)+'</w:t></w:r></w:p>' for p in paragraphs)
with ZipFile(base.with_suffix('.docx'), 'w', ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    z.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+body+'</w:body></w:document>')
with ZipFile(base.with_suffix('.docx')) as z:
    assert z.testzip() is None
    for name in z.namelist():
        ET.fromstring(z.read(name))
print('PNG dimensions and report package validated; reports:', base)
