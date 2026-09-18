# Release review 2026-09-18 (0.0.2): Local browser checks using intercepted requests and synthetic data only.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Local browser checks using intercepted requests and synthetic data only."""
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app/backend'))
from player_cabinet import statistics
from hex_rules import FIELDS
errors, submissions = [], []
rows = [{'Q':str(q),'R':'2','Категория':'Суша' if q != 4 else 'Море',
         'Название':'Тестовый гекс','Тип владельца':'Ничейная территория',
         'Имя владельца':'Нет владельца','Проходимость':'5'} for q in range(5)]
barony = None
random_requests = 0
rows[3].update({'Тип владельца':'Игрок','Владелец':'9','Название территории':'Чужие земли'})
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless=True)
    page = browser.new_page(viewport={'width':1440,'height':1100})
    page.on('pageerror',lambda error:errors.append(str(error)))
    def handle(route):
        global barony, random_requests
        path = urlsplit(route.request.url).path
        if path == '/api/me':
            route.fulfill(json={'id':'2','login':'Тестовый игрок','role':'user','csrf':'synthetic','can_edit':False})
        elif path == '/api/hexes': route.fulfill(json=rows)
        elif path == '/api/cabinet':
            owned=[row for row in rows if row.get('Владелец')=='2']
            route.fulfill(json={'account':{'login':'Тестовый игрок','email':'test@example.invalid'},'crests':[f'gerb_{i}.png' for i in range(1,6)],'hex_fields':FIELDS,'barony':{**barony,'id':1,'hexes':owned,'statistics':statistics(owned)}})
        elif path == '/api/start/options':
            random_cells=[]
            if 'random=true' in route.request.url:
                random_requests += 1
                random_cells=[[q,2] for q in range(2 if random_requests == 1 else 3)]
            route.fulfill(json=barony or {'started':False,'available_cells':[[q,2] for q in range(3)],'random_cells':random_cells,'crests':[f'gerb_{i}.png' for i in range(1,6)],'options':[]})
        elif path == '/api/start':
            data = json.loads(route.request.post_data)
            submissions.append(data)
            assert route.request.headers['x-csrf-token'] == 'synthetic'
            assert 'territory_name' not in data
            barony = {**data,'started':True,'title':'Барон','territory_name':''}
            for row in rows:
                if [int(row['Q']),int(row['R'])] in data['cells']:
                    row.update({'Тип владельца':'Игрок','Владелец':'2','ID территории':'1','Название баронии':data['name'],'Цвет баронии':data['color']})
            route.fulfill(json=barony)
        else:
            route.fulfill(path=str(ROOT/'app/frontend'/path.removeprefix('/interactive-map/')))
    page.route('https://rhisseth.test/**',handle)
    page.goto('https://rhisseth.test/interactive-map/create-barony.html')
    page.wait_for_selector('#crest-list img')
    assert page.locator('#territory-name').count()==0
    # Keyboard selection also works on clipped boundary cells.
    def select(q):
        polygon = page.locator(f'polygon[aria-label^="Гекс Q {q}, R 2:"]')
        polygon.focus(); polygon.press('Enter')
    select(0); select(2)
    assert page.locator('.barony-chosen').count() == 1
    assert 'смежную' in page.locator('#start-status').inner_text()
    select(4)
    assert 'свободный' in page.locator('#start-status').inner_text()
    select(3)
    assert page.locator('.barony-chosen').count()==1
    assert 'свободный' in page.locator('#start-status').inner_text()
    select(1); select(2)
    assert page.locator('.barony-chosen').count() == 3
    select(1)
    assert page.locator('.barony-chosen').count() == 3
    polygon=page.locator('polygon[aria-label^="Гекс Q 1, R 2:"]')
    polygon.press('Shift+Enter')
    assert page.locator('#hex-details dt').all_text_contents() == ['Владелец','Владение','Территория','Категория','Ландшафт','Объект']
    page.locator('#close-card').click()
    page.locator('#random-barony').click()
    page.wait_for_function("document.querySelectorAll('.barony-chosen').length===2")
    assert not submissions
    page.locator('#random-barony').click()
    page.wait_for_function("document.querySelectorAll('.barony-chosen').length===3")
    page.locator('#barony-name').fill('Тестовая барония')
    page.locator('input[name=crest][value="gerb_2.png"]').check()
    page.locator('#barony-color').evaluate("el => { el.value='#2355aa'; el.dispatchEvent(new Event('input')); }")
    assert page.locator('.barony-boundary-preview').count() == 14
    assert page.locator('.barony-chosen').first.evaluate("el=>getComputedStyle(el).stroke") == 'none'
    assert page.locator('.barony-chosen').first.evaluate("el=>getComputedStyle(el).fillOpacity") == '0.14'
    page.locator('#claim-choice').click()
    assert not submissions  # Browser blocks submission until agreement is checked.
    page.locator('#barony-agreement').check()
    page.screenshot(path=str(ROOT/'reports/player-onboarding-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(ROOT/'reports/player-onboarding-mobile.png'),full_page=True)
    page.locator('#claim-choice').click()
    page.wait_for_url('**/cabinet.html')
    page.wait_for_function("document.querySelector('#cabinet-name').textContent==='Тестовая барония'")
    assert page.locator('#map-viewport').count()==0
    assert page.locator('#barony-hexes details').count()==3
    assert submissions[0]['crest'] == 'gerb_2.png'
    assert submissions[0]['color'] == '#2355aa'
    assert not errors, errors
    browser.close()
print('PASS: connected selection, sea rejection, limited details, crest, color, agreement, save, cabinet, mobile, no JavaScript errors')
