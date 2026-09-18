"""Create a management Word report from sanitized deployment findings."""
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[2]
path = root / 'reports/2026-09-18-player-onboarding-release-management.docx'
paragraphs = [
    'Rhisseth: публикация личного кабинета игрока для тестирования',
    '18 сентября 2026 года. Время: UTC / Москва (UTC+3).',
    'Статус: версия опубликована на rhisseth.ru. Страницы создания баронии и личного кабинета, API и проверенный герб доступны через публичный HTTPS. Сервер приложения работает.',
    'Изменения: после регистрации игрок создаёт баронию из смежных свободных гексов, задаёт названия, герб и цвет и переходит в личный кабинет. Морские гексы без отметки острова недоступны. Заливка выбранных гексов прозрачная, контур показывает внешний периметр.',
    'При публикации выявлены два затруднения: настройка проверочного процесса БД была неполной, затем права нового каталога гербов мешали приложению читать изображения. Обе причины устранены. Финальная проверка страниц, API и герба прошла. Второй сбой временно ограничивал показ новых гербов; длительность и число затронутых пользователей не измерялись.',
    'Сохранность: до изменения сделана резервная копия БД и заменяемых файлов; перед повтором создана дополнительная копия. Миграция проверена на изолированной восстановленной БД. Полный перезапуск сервера и PostgreSQL не выполнялся. Доказательств потери данных не получено; исчерпывающее сравнение содержимого БД не проводилось.',
    'Ограничения: браузерная проверка сценария прошла на тестовых данных локально. На опубликованном сайте проверена доступность компонентов, но новый реальный аккаунт и барония автоматически не создавались. Длительная нагрузка не проверялась.',
    'Требуемые действия: выполнить пользовательское тестирование регистрации, создания баронии и внешних границ на карте. Согласовать окончательный текст пользовательского соглашения и передать оформление подложки дизайнеру. Перед следующим выпуском оформить текущие изменения в согласованную Git-версию.',
    'Технический отчёт и журналы операций хранятся в папке проекта reports. Отправка отчётов по электронной почте не выполнялась.',
    'После первого визуального теста опубликованы исправления: оставлено только название баронии, существующие названия территорий сохраняются, добавлен случайный подбор 2–3 смежных свободных гексов и усилена проверка занятой земли. Новые миграции не требовались; до обновления сделана новая резервная копия.',
    'Повторная публикация завершилась успешно. Первичная проверка публичного адреса прервалась из-за временного DNS-сбоя на сервере; отдельная проверка без перезапуска и миграции прошла. Причина временного сбоя глубже сообщения DNS не установлена, настройки DNS не изменялись. Локально прошли 19 тестов и браузерный сценарий. Пользовательское тестирование продолжается.',
]
body = ''.join('<w:p><w:r><w:t xml:space="preserve">' + escape(text) + '</w:t></w:r></w:p>' for text in paragraphs)
document = '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + body + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr></w:body></w:document>'
with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
    archive.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    archive.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    archive.writestr('word/document.xml', document)
with ZipFile(path) as archive:
    assert archive.testzip() is None
    for name in archive.namelist(): ET.fromstring(archive.read(name))
print('Created and validated:', path)
