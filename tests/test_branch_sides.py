"""Browser checks for moving first-level branches across the root."""
from pathlib import Path
from playwright.sync_api import sync_playwright

HTML = (Path(__file__).resolve().parents[1] / 'pg_settings_full.html').read_text()
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
    context.route('http://map.test/', lambda r: r.fulfill(body=HTML, content_type='text/html'))
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://map.test/')
    group_id = page.evaluate('''() => {
      const g=data.find(n=>n.label==='Client Connection Defaults');
      for(const n of children('root'))if(n.id!==g.id)hiddenGroups.add(n.id);
      g.manualSide=1;g.collapsed=false;children(g.id)[0].collapsed=false;
      layout(true);render();fit();
      const c=children(g.id)[0];c.x+=25;
      position();return g.id;
    }''')
    def drag_to(side):
        page.evaluate("stopCamera();zoom=.3;pan={x:canvas.clientWidth/2-(byId.get('root').x+nodeWidths.get('root')/2)*zoom,y:canvas.clientHeight/2};transform();")
        before = page.evaluate('''id => [byId.get(id),...descendants(id)].filter(visible).map(n=>({id:n.id,x:n.x,w:nodeWidths.get(n.id)}))''', group_id)
        node = page.locator(f'.node[data-id="{group_id}"]')
        box = node.bounding_box()
        target = page.evaluate('''({id,side})=>{
          const root=byId.get('root'),g=byId.get(id);
          return {dx:(root.x+nodeWidths.get('root')/2+side*320-g.x-nodeWidths.get(g.id)/2)*zoom};
        }''', {'id': group_id, 'side': side})
        page.mouse.move(box['x']+box['width']/2, box['y']+box['height']/2)
        page.mouse.down()
        page.mouse.move(box['x']+box['width']/2+target['dx'], box['y']+box['height']/2, steps=8)
        page.mouse.up()
        actual = page.evaluate('''id => ({side:byId.get(id).side,manual:byId.get(id).manualSide,
          center:byId.get(id).x+nodeWidths.get(id)/2,
          nodes:[byId.get(id),...descendants(id)].filter(visible).map(n=>({id:n.id,x:n.x,side:n.side}))})''', group_id)
        assert actual['side'] == side and actual['manual'] == side
        for old, new in zip(before, actual['nodes']):
            assert new['side'] == side
            if old['id'] != group_id:
                mirrored = 2*actual['center']-(old['x']+target['dx']/.3)-old['w']
                assert abs(new['x']-mirrored) < .01, (old, new, mirrored)
        assert node.evaluate('(el)=>getComputedStyle(el).textAlign') == ('right' if side == -1 else 'start')
        return page.evaluate('currentState()')
    left_state = drag_to(-1)
    page.reload()
    assert page.evaluate('currentState()') == left_state
    # Hidden descendants use the new side when their subgroup is opened.
    page.evaluate('''id=>{for(const n of descendants(id))n.collapsed=false;layout();render();}''', group_id)
    assert page.evaluate('''id=>descendants(id).every(n=>n.side===-1)''', group_id)
    right_state = drag_to(1)
    page.evaluate('state=>{applyState(state);render();}', right_state)
    assert page.evaluate('currentState()') == right_state
    page.reload()
    assert page.evaluate('currentState()') == right_state
    page.locator('#reset').click()
    assert page.evaluate("children('root').every(n=>!n.manualSide)")
    assert not errors, errors
    browser.close()
    print('PASS: branch mirror both directions, alignment, child offsets, reload, import, reset')
