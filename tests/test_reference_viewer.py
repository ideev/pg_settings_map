"""Modal reference viewer checks. Run with Python Playwright and system Chromium."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

HTML = (Path(__file__).resolve().parents[1] / 'pg_settings_full.html').read_text()
URL = 'http://map.test/'
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
    requests = []
    def serve(route):
        requests.append(route.request.url)
        if route.request.url == URL:
            route.fulfill(body=HTML, content_type='text/html')
        elif route.request.url.startswith('https://repo.quantom.info/'):
            route.fulfill(body='<h1>QHB documentation</h1><p>Parameter description</p>', content_type='text/html')
        elif route.request.url.startswith(('https://www.postgresql.org/', 'https://thebuild.com/')):
            route.fulfill(body='<h1>External reference</h1>', content_type='text/html')
        else:
            route.abort()
    context.route('**/*', serve)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(URL)
    page.locator('#search').fill('work_mem')
    page.locator('#search').press('Enter')
    page.locator('.node.parameter').filter(has_text='work_mem').first.press('Enter')
    before = page.evaluate('JSON.stringify(currentState())')
    qhb = page.locator('#details .qhb-documentation-reference a')
    qhb.click()
    dialog = page.locator('#reference-viewer')
    assert dialog.is_visible()
    assert len(context.pages) == 1
    assert page.locator('#reference-content iframe').get_attribute('sandbox') == 'allow-scripts allow-same-origin'
    assert page.frame_locator('#reference-content iframe').locator('h1').inner_text() == 'QHB documentation'
    bounds = dialog.bounding_box()
    assert 1300 < bounds['width'] < 1440
    assert 850 < bounds['height'] < 1000
    page.screenshot(path='/tmp/qhb-reference-viewer.png')
    page.locator('#reference-close').click()
    assert not dialog.is_visible()
    expect(page.locator('#reference-content iframe')).to_have_count(0)
    expect(qhb).to_be_focused()
    assert page.locator('#details').is_visible()
    assert page.evaluate('JSON.stringify(currentState())') == before
    # Escape closes only the viewer, keeping the parameter card open.
    qhb.click()
    page.keyboard.press('Escape')
    assert not dialog.is_visible()
    assert page.locator('#details').is_visible()
    expect(qhb).to_be_focused()
    # PostgreSQL and blog links open directly in a new tab, without a modal.
    for selector in ['#details .documentation-reference:not(.qhb-documentation-reference) a', '#details .blog-references a']:
        link = page.locator(selector).first
        assert link.count() == 1
        with context.expect_page() as popup_info:
            link.click()
        popup = popup_info.value
        popup.wait_for_load_state()
        assert popup.url == link.get_attribute('href')
        assert not dialog.is_visible()
        expect(page.locator('#reference-content iframe')).to_have_count(0)
        assert page.locator('#details').is_visible()
        assert page.evaluate('JSON.stringify(currentState())') == before
        assert popup.evaluate('window.opener === null')
        popup.close()
    # Compact viewport: controls fit, content remains usable, focus stays modal.
    page.set_viewport_size({'width': 390, 'height': 844})
    qhb.click()
    for control in ['#reference-close', '#reference-external']:
        bounds = page.locator(control).bounding_box()
        assert bounds['x'] >= 0 and bounds['x']+bounds['width'] <= 390
    page.screenshot(path='/tmp/qhb-reference-viewer-mobile.png')
    for _ in range(5):
        page.keyboard.press('Tab')
        assert page.evaluate("document.activeElement===document.body || document.querySelector('#reference-viewer').contains(document.activeElement)")
    page.evaluate("document.querySelector('#search').focus()")
    assert page.evaluate("document.activeElement!==document.querySelector('#search')")
    page.locator('#reference-close').click()
    assert not errors, errors
    browser.close()
    print('PASS: modal QHB viewer, close/Escape/focus, direct external tabs, unchanged map, narrow viewport')
