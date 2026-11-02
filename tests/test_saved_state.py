"""Browser regression checks. Requires Python Playwright and system Chromium.
Run: python3 tests/test_saved_state.py
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

HTML = (Path(__file__).resolve().parents[1] / 'pg_settings_full.html').read_text()
URL = 'http://map.test/'
KEY = 'pg_settings_map.state.v1'


def snapshot(page):
    return page.evaluate('''() => data.map(n=>({name:stateKeys.get(n.id),
      collapsed:n.collapsed, hidden:hiddenGroups.has(n.id),
      dx:n.x-n.autoX,dy:n.y-n.autoY}))''')


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
    context = browser.new_context(reduced_motion='reduce')
    context.route(URL, lambda route: route.fulfill(body=HTML, content_type='text/html'))
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(URL)
    assert page.locator('.node').count() == 13
    # Every QHB reference is first, before PostgreSQL and blog references.
    qhb_count = page.evaluate('''() => {
      let count=0;
      for(const n of data.filter(n=>n.kind==='parameter')){
        select(n.id);
        const links=[...document.querySelectorAll('#details section a')];
        if(n.qhb_documentation_link){
          if(links[0]?.href!==n.qhb_documentation_link.url)throw new Error('QHB link is not first: '+n.label);
          if(links[0].target!=='_blank'||links[0].rel!=='noopener noreferrer')throw new Error('Unsafe link');
          count++;
        }else if(document.querySelector('#details .qhb-documentation-reference'))throw new Error('Unexpected QHB link');
      }
      select('root');closeDetails();return count;
    }''')
    assert qhb_count == 420
    assert page.evaluate('() => [...hiddenGroups].map(id=>byId.get(id).label).sort()') == sorted([
        'Error Handling', 'Lock Management', 'QHB Options', 'Ungrouped',
        'Developer Options'])
    assert page.locator('#group-list input').count() == 17
    for width in [1440, 1024, 700, 390]:
        page.set_viewport_size({'width': width, 'height': 900})
        tops = page.locator('.header-controls .toolbar button').evaluate_all('(buttons)=>buttons.map(b=>b.getBoundingClientRect().top)')
        assert max(tops) - min(tops) < 1
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.set_viewport_size({'width': 1280, 'height': 900})
    page.locator('#groups-toggle').click()
    for box in page.locator('#group-list input').all():
        box.check()
    page.locator('#groups-toggle').click()
    page.locator('#search').fill('work_mem')
    page.locator('#search').press('Enter')
    parameter = page.locator('.node.parameter').filter(has_text='work_mem').first
    parameter.press('Enter')
    assert page.locator('#details h2 + .type').count() == 1
    assert page.locator('#details .setting-value').count() == 1
    assert page.locator('#details .setting-value').evaluate('(el)=>getComputedStyle(el).backgroundColor') == page.locator('#details .parameter-title > .type').evaluate('(el)=>getComputedStyle(el).backgroundColor')
    page.keyboard.press('Escape')
    parameter.press('ArrowRight')
    parameter.press('ArrowDown')
    # Move a whole branch with actual pointer input.
    root = page.locator('.node.root')
    bounds = root.bounding_box()
    page.mouse.move(bounds['x'] + bounds['width']/2, bounds['y'] + bounds['height']/2)
    page.mouse.down()
    page.mouse.move(bounds['x'] + bounds['width']/2 + 30, bounds['y'] + bounds['height']/2 + 20, steps=3)
    page.mouse.up()
    page.locator('#groups-toggle').click()
    page.locator('#group-list input').last.uncheck()
    expected = snapshot(page)
    # pagehide must flush edits even before the debounce expires.
    page.reload()
    assert snapshot(page) == expected
    assert not page.locator('#group-list input').last.is_checked()
    # Subgroups can remain collapsed while their parent group stays expanded.
    subgroup = page.locator('.node.subgroup').first
    if subgroup.count():
        subgroup.locator('.toggle').click()
        expected = snapshot(page)
        page.reload()
        assert snapshot(page) == expected
    # Export reads live coordinates, then import replaces and persists settings.
    with page.expect_download() as download_info:
        page.locator('#export-state').click()
    download = download_info.value
    assert download.suggested_filename == 'pg_settings_map.json'
    exported = Path(download.path()).read_bytes()
    assert json.loads(exported)['version'] == 1
    page.locator('#reset').click()
    assert snapshot(page) != expected
    def import_file(contents):
        page.locator('#state-file').set_input_files({
            'name': 'pg_settings_map.json', 'mimeType': 'application/json',
            'buffer': contents})
        page.wait_for_function("document.querySelector('#state-file').value === ''")
    import_file(exported)
    assert 'импортированы' in page.locator('#state-status').inner_text()
    assert snapshot(page) == expected
    page.reload()
    assert snapshot(page) == expected
    # Invalid JSON, schema, version and unrelated nodes leave the map intact.
    invalid_states = [b'{broken', b'{}', b'{"version":2,"nodes":{}}',
        b'{"version":1,"nodes":{"unknown":{"collapsed":false,"hidden":false,"dx":0,"dy":0}}}']
    broken_entry = json.loads(exported)
    next(iter(broken_entry['nodes'].values()))['dx'] = 'invalid'
    invalid_states.append(json.dumps(broken_entry).encode())
    for invalid in invalid_states:
        import_file(invalid)
        assert page.locator('#state-status').get_attribute('data-error') == 'true'
        assert snapshot(page) == expected
    # The same file can be selected again after an error.
    import_file(exported)
    assert page.locator('#state-status').get_attribute('data-error') == 'false'
    assert snapshot(page) == expected
    # Legacy subgroup visibility preferences must no longer hide subgroups.
    legacy = json.loads(exported)
    for key, entry in legacy['nodes'].items():
        if 'Previous PostgreSQL Versions' in key:
            entry['hidden'] = True
    import_file(json.dumps(legacy).encode())
    assert snapshot(page) == expected
    # Same-origin new page reads the same preferences.
    other = context.new_page()
    other.goto(URL)
    assert snapshot(other) == expected
    other.close()
    page.locator('#expand').click()
    page.reload()
    assert all(not n['collapsed'] for n in snapshot(page))
    page.locator('#collapse').click()
    page.reload()
    assert page.locator('.node').count() == 17
    page.locator('#reset').click()
    page.reload()
    assert all(n['dx'] == 0 and n['dy'] == 0 for n in snapshot(page))
    assert not page.locator('#group-list input').last.is_checked()
    # Invalid JSON falls back to the default map.
    context.add_init_script(f"localStorage.setItem('{KEY}', '{{broken');")
    page.goto(URL)
    assert page.locator('.node').count() == 13
    assert all(n['dx'] == 0 and n['dy'] == 0 for n in snapshot(page))
    assert not errors, errors
    context.close()
    # Search hidden groups without changing filters until a result is chosen.
    context = browser.new_context(reduced_motion='reduce')
    context.route(URL, lambda route: route.fulfill(body=HTML, content_type='text/html'))
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(URL)
    for group_name, method in [('Developer Options', 'click'), ('Write-Ahead Log', 'enter')]:
        target = page.evaluate('''name => {
          const group=data.find(n=>n.kind==='group'&&n.label===name);
          const parameter=descendants(group.id).find(n=>n.kind==='parameter'&&(name!=='Write-Ahead Log'||byId.get(n.parent).kind==='subgroup'));
          return {group:group.id,id:parameter.id,name:parameter.label};
        }''', group_name)
        page.locator('#groups-toggle').click()
        checkbox = page.locator(f'#group-list input[data-group="{target["group"]}"]')
        checkbox.uncheck()
        page.locator('#groups-toggle').click()
        hidden_before = page.evaluate('() => [...hiddenGroups]')
        page.locator('#search').fill(target['name'])
        assert page.locator('#results button').filter(has_text=target['name']).count() >= 1
        assert page.evaluate('() => [...hiddenGroups]') == hidden_before
        if method == 'click':
            page.locator('#results button').filter(has_text=target['name']).first.click()
        else:
            page.locator('#search').press('Enter')
        assert checkbox.is_checked()
        assert page.locator(f'.node[data-id="{target["id"]}"]').is_visible()
        assert page.evaluate('selected') == target['id']
        assert page.evaluate('document.activeElement.dataset.id') == target['id']
        assert page.evaluate('() => [...hiddenGroups]') == [g for g in hidden_before if g != target['group']]
        assert page.locator('#group-count').text_content() == f'{17-len(hidden_before)+1} / 17'
        expected_search = snapshot(page)
        page.reload()
        assert snapshot(page) == expected_search
    assert not errors, errors
    context.close()
    # Denied local storage must not break rendering or interactions.
    context = browser.new_context()
    context.route(URL, lambda route: route.fulfill(body=HTML, content_type='text/html'))
    context.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new Error('denied')}})")
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(URL)
    page.locator('#groups-toggle').click()
    for box in page.locator('#group-list input').all():
        box.check()
    page.locator('#expand').click()
    assert page.locator('.node.parameter').count() == 436
    page.wait_for_timeout(200)
    assert not errors, errors
    browser.close()
    print('PASS: restore coordinates, branch drag, expansion, filters, reload, new page, reset, export/import, invalid files, corrupt/denied storage')
