# Release review 2026-09-18 (0.0.2): Generate paired technical Markdown and management Word from sanitized facts.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Generate paired technical Markdown and management Word from sanitized facts."""
import argparse
import datetime as dt
import json
from pathlib import Path
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--facts',required=True)
    args = parser.parse_args()
    facts = json.loads(Path(args.facts).read_text(encoding='utf-8-sig'))
    root = Path(__file__).resolve().parents[2]/'reports'
    root.mkdir(parents=True,exist_ok=True)
    stem = facts.get('report_stem',dt.date.today().isoformat()+'-rhisseth-backup-recovery')
    if Path(stem).name != stem or '/' in stem or '\\' in stem:
        raise ValueError('Invalid report stem')
    technical = root/(stem+'.md')
    management = root/(stem+'.docx')
    technical.write_text(facts['technical_markdown'],encoding='utf-8')
    paragraphs = facts['management_paragraphs']
    body = ''.join('<w:p><w:r><w:t xml:space="preserve">'+escape(text)+'</w:t></w:r></w:p>' for text in paragraphs)
    document = '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+body+'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr></w:body></w:document>'
    with ZipFile(management,'w',ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr('word/document.xml',document)
    with ZipFile(management) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Word ZIP integrity failed')
        for name in archive.namelist():
            ET.fromstring(archive.read(name))
        ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        tree = ET.fromstring(archive.read('word/document.xml'))
        if [p.text for p in tree.findall('.//w:t',ns)]!=paragraphs:
            raise RuntimeError('Word text round-trip failed')
    print('Created and verified:',technical,management)
if __name__=='__main__':
    main()
