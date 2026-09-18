"""Local browser verification with synthetic data; no infrastructure access."""
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
user={'id':123,'login':'test-player','email':'player@example.invalid','role':'user'}
errors=[];mutations=[]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.on('pageerror',lambda error:errors.append(str(error)))
    def handle(route):
        path=urlsplit(route.request.url).path
        if path=='/api/me': route.fulfill(json={'csrf':'synthetic','role':'admin'})
        elif path=='/api/admin/users': route.fulfill(json={'total':1,'page':1,'page_size':50,'users':[user]})
        elif path=='/api/admin/users/123':
            if route.request.method=='DELETE':
                mutations.append('delete');route.fulfill(json={'deleted':True,'released_hexes':2})
            else:
                data=json.loads(route.request.post_data);mutations.append(data)
                assert data['expected']=={k:user[k] for k in ('login','email','role')}
                user.update({k:data[k] for k in ('login','email','role')});route.fulfill(json={'saved':True})
        else:
            name='users.html' if path=='/admin/users' else path.removeprefix('/interactive-map/')
            route.fulfill(path=str(ROOT/'app/frontend'/name))
    page.route('https://rhisseth.test/**',handle)
    page.goto('https://rhisseth.test/admin/users')
    page.get_by_role('button',name='Редактировать test-player',exact=True).click()
    page.locator('#edit [name=login]').fill('renamed-player')
    page.locator('#edit [name=role]').select_option('moderator')
    page.locator('#edit [name=password]').fill('synthetic-password')
    page.locator('#edit [name=password_confirm]').fill('synthetic-password')
    page.get_by_role('button',name='Сохранить',exact=True).click()
    page.wait_for_function("document.querySelector('#status').textContent==='Изменения сохранены'")
    assert mutations[0]['role']=='moderator'
    assert mutations[0]['password']=='synthetic-password'
    assert page.locator('#edit [name=password]').input_value()==''
    page.screenshot(path=str(ROOT/'reports/user-admin-desktop.png'))
    page.set_viewport_size({'width':390,'height':844})
    page.get_by_role('button',name='Редактировать renamed-player',exact=True).click()
    assert page.locator('#editor').bounding_box()['width']<=390
    page.screenshot(path=str(ROOT/'reports/user-admin-mobile.png'))
    page.keyboard.press('Escape');assert not page.locator('#editor').is_visible()
    page.set_viewport_size({'width':1440,'height':1000})
    page.get_by_role('button',name='Редактировать renamed-player',exact=True).click()
    page.once('dialog',lambda dialog:dialog.accept())
    page.get_by_role('button',name='Удалить пользователя',exact=True).click()
    page.wait_for_function("document.querySelector('#status').textContent==='Пользователь удалён. Освобождено гексов: 2.'")
    assert mutations[-1]=='delete'
    assert not errors,errors
    browser.close()
print('PASS: account table; edit dialog; optimistic version; role change; save; mobile dialog; Escape; no JavaScript errors')
