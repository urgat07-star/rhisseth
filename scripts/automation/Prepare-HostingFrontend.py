"""Keep the provided appearance; replace PHP/MySQL logic with Python templates."""
from pathlib import Path
import re
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'app/backend'))
from import_users import decode, load_archive

def main():
    tables = load_archive(ROOT / 'temp/sql-bkp.zip')
    print('Account counts:', len(tables['roles']), 'roles,',len(tables['users']),'users')
    print('Role aliases:', [r['role_alias'] for r in tables['roles']])
    with ZipFile(ROOT / 'temp/hosting-bkp.zip') as archive:
        names = archive.namelist()
        prefix = next(n[:-len('index.php')] for n in names if n.count('/') == 1 and n.endswith('index.php'))
        static = ROOT / 'app/site/static'
        templates = ROOT / 'app/site/templates'
        for folder in ('img', 'css'):
            for name in names:
                if name.startswith(prefix + folder + '/') and not name.endswith('/'):
                    relative = Path(name[len(prefix):])
                    if '..' in relative.parts or relative.is_absolute():
                        raise ValueError('Invalid archive path')
                    target = static / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    data = archive.read(name)
                    target.write_bytes(('\n'.join(line.rstrip() for line in decode(data).splitlines()).rstrip()+'\n').encode('utf-8') if folder == 'css' else data)
        for source, target_name in [('index.php','login.html'),('register.php','register.html')]:
            source_text = decode(archive.read(prefix + source)).replace('\r\r\n','\n').replace('\r\n','\n')
            html = source_text[source_text.lower().index('<!doctype'):]
            html = re.sub(r'<\?php if \(!empty\(\$error_message\)\): \?>', '{% if error_message %}', html)
            html = re.sub(r'<\?php if \(!empty\(\$success_message\)\): \?>', '{% if success_message %}', html)
            html = html.replace('<?php else: ?>','{% else %}').replace('<?php endif; ?>','{% endif %}')
            html = re.sub(r'<\?=\s*htmlspecialchars\(\$error_message,.*?\)\s*\?>', '{{ error_message }}', html)
            html = re.sub(r'<\?=\s*htmlspecialchars\(\$success_message,.*?\)\s*\?>', '{{ success_message }}', html)
            html = re.sub(r'<\?=\s*htmlspecialchars\(\$login\s*\?\?\s*\'\'\).*?\?>', '{{ login }}', html)
            html = re.sub(r'(<form\b[^>]*>)', r'\1\n<input type="hidden" name="csrf" value="{{ csrf }}">', html)
            html = html.replace('src="img/', 'src="/site/img/').replace('href="css/', 'href="/site/css/')
            html = html.replace("'index.php'", "'/index.php'").replace('href="index.php"','href="/index.php"').replace('href="register.php"','href="/register.php"')
            html = re.sub(r'\n{3,}', '\n\n', html)
            if '<?' in html:
                raise ValueError('Unconverted PHP template expression')
            templates.mkdir(parents=True, exist_ok=True)
            (templates / target_name).write_text('\n'.join(line.rstrip() for line in html.splitlines()).rstrip()+'\n',encoding='utf-8')
        print('Appearance assets and two UTF-8 templates prepared; conn.php and old map excluded')

if __name__ == '__main__':
    main()
