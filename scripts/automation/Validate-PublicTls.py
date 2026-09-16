"""Validate deployed public TLS and read-only Rhisseth endpoints."""
import datetime as dt
import json
from pathlib import Path
import socket
import ssl
import urllib.request
import urllib.error

context = ssl.create_default_context()
with socket.create_connection(('rhisseth.ru', 443), timeout=20) as connection:
    with context.wrap_socket(connection, server_hostname='rhisseth.ru') as tls:
        cert = tls.getpeercert()
        result = {'domain': 'rhisseth.ru', 'tls': tls.version(),
                  'issuer': cert['issuer'], 'san': cert['subjectAltName'],
                  'not_before': cert['notBefore'], 'not_after': cert['notAfter'],
                  'verified': True, 'endpoints': []}
for url, expected in (('http://rhisseth.ru/', 200), ('https://rhisseth.ru/index.php', 200),
                      ('https://rhisseth.ru/health', 401), ('https://rhisseth.ru/site/css/style.css', 200),
                      ('https://rhisseth.ru/interactive-map/', 200)):
    try:
        response = urllib.request.urlopen(url, context=context, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        assert response.status == expected, (url, response.status, expected)
        assert response.url.startswith('https://rhisseth.ru/'), response.url
        if '/interactive-map/' in url:
            assert response.url == 'https://rhisseth.ru/index.php', response.url
        result['endpoints'].append({'requested': url, 'final': response.url,
                                    'status': response.status})
now = dt.datetime.now(dt.timezone.utc)
result['utc'] = now.isoformat()
directory = Path(__file__).resolve().parents[2] / 'reports/automation-logs' / now.strftime('%Y-%m-%d')
directory.mkdir(parents=True, exist_ok=True)
output = json.dumps(result, ensure_ascii=False, indent=2)
path = directory / (now.strftime('%Y%m%d-%H%M%S') + '-public-tls.json')
path.write_text(output + '\n', encoding='utf-8')
print(output)
print(f'Audit log: {path}')
