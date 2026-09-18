"""Local browser checks; all requests intercepted, no real account or barony modified."""
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app/backend'))
from player_cabinet import statistics
from hex_rules import FIELDS
rows=[{'Q':str(q),'R':'2','Название':'Лесная долина','Название территории':'Северные земли',
       'Категория':'Суша','Тип местности':'Лес','Основной ресурс':'Дерево',
       'Плодородие':str(q),'Тип владельца':'Игрок','Владелец':'2'} for q in range(3)]
state={'account':{'login':'test-player','email':'test@example.invalid'},
       'barony':{'id':7,'name':'Тестовая барония','title':'Барон','crest':'gerb_1.png','color':'#b51f24','hexes':rows,'statistics':statistics(rows)},
       'crests':[f'gerb_{i}.png' for i in range(1,6)],'hex_fields':FIELDS}
errors=[];mutations=[];csrf='synthetic'
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.on('pageerror',lambda error:errors.append(str(error)))
    def handle(route):
        global csrf
        path=urlsplit(route.request.url).path
        if path=='/api/me':route.fulfill(json={'csrf':csrf,'login':state['account']['login']})
        elif path=='/api/cabinet':route.fulfill(json=state)
        elif path.startswith('/api/cabinet/'):
            data=json.loads(route.request.post_data)
            assert route.request.headers['x-csrf-token']==csrf
            mutations.append((path,data))
            if path.endswith('/account'):
                assert data['expected']==state['account']
                state['account']={key:data[key] for key in ('login','email')};csrf='rotated'
                route.fulfill(json={'saved':True,'account':state['account'],'csrf':csrf})
            elif path.endswith('/crest'):
                state['barony'].update(crest=data['crest'],color=data['color']);route.fulfill(json={'saved':True})
            elif path.endswith('/name'):
                assert data['expected_name']==state['barony']['name'] and data['barony_id']==7
                state['barony']['name']=data['name'];route.fulfill(json={'saved':True})
            else:
                assert route.request.method=='DELETE' and data=={'barony_id':7,'confirmation':'Новая барония','confirmed':True}
                state['barony']=None;route.fulfill(json={'abandoned':True,'released_hexes':3})
        else:route.fulfill(path=str(ROOT/'app/frontend'/path.removeprefix('/interactive-map/')))
    page.route('https://rhisseth.test/**',handle)
    page.goto('https://rhisseth.test/interactive-map/cabinet.html')
    page.wait_for_selector('#barony-content:not([hidden])')
    assert page.locator('#map-viewport').count()==0
    assert page.locator('[role=tab]').all_text_contents()==['Барония','Экономика','Дипломатия','Настройки']
    assert page.locator('#barony-hexes details').count()==3
    page.locator('#barony-hexes summary').first.click()
    assert 'Северные земли' in page.locator('#barony-hexes details').first.inner_text()
    for tab in ('economy','diplomacy'):
        page.locator('#tab-'+tab).click();assert page.locator('#panel-'+tab).is_visible()
    page.locator('#tab-settings').click()
    form=page.locator('#account-form')
    form.locator('[name=login]').fill('renamed-player')
    form.locator('[name=email]').fill('renamed@example.invalid')
    form.locator('[name=current_password]').fill('synthetic-password')
    form.locator('[name=password]').fill('synthetic-new-password')
    form.locator('[name=password_confirm]').fill('synthetic-new-password')
    form.locator('[type=submit]').click()
    page.wait_for_function("document.querySelector('#cabinet-status').textContent.startsWith('Аккаунт сохранён')")
    assert form.locator('[name=current_password]').input_value()==''
    assert form.locator('[name=password]').input_value()==''
    page.locator('#barony-name-form [name=name]').fill('Новая барония')
    page.locator('#barony-name-form [type=submit]').click()
    page.wait_for_function("document.querySelector('#cabinet-name').textContent==='Новая барония'")
    page.locator('input[name=crest][value="gerb_2.png"]').check()
    page.locator('#crest-form [type=submit]').click()
    page.wait_for_function("document.querySelector('#cabinet-status').textContent==='Герб и цвет баронии сохранены.'")
    assert page.locator('#cabinet-crest').get_attribute('src')=='crests/gerb_2.png'
    page.screenshot(path=str(ROOT/'reports/player-cabinet-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(ROOT/'reports/player-cabinet-mobile.png'),full_page=True)
    page.locator('#open-abandon').click()
    assert page.locator('#confirm-abandon').is_disabled()
    page.locator('#abandon-confirmation').fill('wrong')
    page.locator('#abandon-confirmed').check()
    assert page.locator('#confirm-abandon').is_disabled()
    page.locator('#cancel-abandon').click()
    assert len(mutations)==3
    page.locator('#open-abandon').click()
    page.keyboard.press('Escape')
    assert len(mutations)==3
    page.locator('#open-abandon').click()
    page.locator('#abandon-confirmation').fill('Новая барония')
    assert page.locator('#confirm-abandon').is_disabled()
    page.locator('#abandon-confirmed').check()
    assert page.locator('#confirm-abandon').is_enabled()
    page.locator('#confirm-abandon').click()
    page.wait_for_selector('#no-barony:not([hidden])')
    assert not page.locator('#barony-summary').is_visible()
    assert page.locator('[role=tab]:visible').all_text_contents()==['Настройки']
    assert page.locator('#no-barony a').get_attribute('href')=='create-barony.html'
    page.locator('#tab-settings').focus();page.keyboard.press('ArrowRight')
    assert page.locator('#panel-settings').is_visible()
    assert form.locator('[name=login]').input_value()=='renamed-player'
    page.reload();page.wait_for_function("document.querySelector('#user-status').textContent==='renamed-player'")
    page.wait_for_selector('#no-barony:not([hidden])')
    assert page.locator('[role=tab]:visible').all_text_contents()==['Настройки']
    assert len(mutations)==4
    assert not errors,errors
    browser.close()
print('PASS: separate page, full statistics, tabs, profile, session rotation, crest, mobile, required confirmation, cancel, release, account retained')
