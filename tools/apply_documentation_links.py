"""Link settings to verified current PostgreSQL documentation.

Default: apply the saved catalogue without network access.
--refresh: fetch the current Server Configuration chapter first.
"""
import argparse
import concurrent.futures
from datetime import date
import html
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://www.postgresql.org/docs/current/'
CATALOGUE = ROOT / 'data/postgresql_documentation.json'


def parameters(settings):
    result = {}

    def walk(node):
        if node['type'] == 'parameter':
            if node['name'] in result:
                raise ValueError(f"Duplicate parameter: {node['name']}")
            result[node['name']] = node
        for child in node.get('children', []):
            walk(child)

    walk(settings)
    return result


def collect(settings, pages, toc):
    """Use actual definition names and anchors, including shared definitions."""
    definitions = {}
    for filename, content in sorted(pages.items()):
        for anchor, definition in re.findall(
                r'<dt\s+id="(GUC-[^"]+)"[^>]*>(.*?)</dt>', content, re.S):
            names = re.findall(r'<code class="varname">(.*?)</code>', definition, re.S)
            for name in names:
                name = html.unescape(re.sub('<[^>]+>', '', name))
                if name in definitions:
                    raise ValueError(f'Duplicate documentation definition: {name}')
                definitions[name] = {
                    'title': f'PostgreSQL: {name}',
                    'url': BASE + filename + '#' + anchor,
                    'documented_name': name,
                    'match_type': 'shared-definition' if len(names) > 1 else 'exact-definition',
                }
    # PG18 documents the old spelling explicitly in the ssl_groups definition.
    connection = pages.get('runtime-config-connection.html', '')
    alias = re.search(r'<dt id="GUC-SSL-GROUPS".*?</dt>\s*<dd>(.*?)</dd>', connection, re.S)
    if alias and 'ssl_ecdh_curve' in alias[1] and 'ssl_groups' in definitions:
        definitions['ssl_ecdh_curve'] = dict(
            definitions['ssl_groups'],
            title='PostgreSQL: ssl_groups (ранее ssl_ecdh_curve)',
            match_type='documented-rename',
        )
    names = parameters(settings)
    links = {name: definitions[name] for name in names if name in definitions}
    version = re.search(r'<title>PostgreSQL: Documentation: ([^:]+):', toc)
    return {
        'checked_on': date.today().isoformat(),
        'source': BASE + 'runtime-config.html',
        'resolved_release_at_check': version[1] if version else None,
        'pages_checked': sorted(pages),
        'method': 'Exact names in official parameter definitions; shared definition anchors retained. The ssl_ecdh_curve rename is explicitly documented under ssl_groups. URLs intentionally use /docs/current/.',
        'linked_parameters': len(links),
        'links': links,
        'parameters_without_description': sorted(set(names) - set(links)),
    }


def apply(settings, catalogue):
    names = parameters(settings)
    for name, link in catalogue['links'].items():
        url = urlsplit(link['url'])
        if (name not in names or not link['title'].strip() or url.scheme != 'https'
                or url.netloc != 'www.postgresql.org'
                or not url.path.startswith('/docs/current/')
                or not url.path.endswith('.html') or not url.fragment):
            raise ValueError(f'Invalid documentation mapping: {name}')
    for name, node in names.items():
        link = catalogue['links'].get(name)
        if link:
            node['documentation_link'] = {'title': link['title'], 'url': link['url']}
        else:
            node.pop('documentation_link', None)
    return settings


def refresh(settings):
    with TemporaryDirectory(prefix='pg-settings-docs-') as temp:
        def fetch(filename):
            path = Path(temp) / filename
            subprocess.run(['curl', '-fsSL', '--max-time', '30', '--retry', '2',
                            BASE + filename, '-o', str(path)], check=True)
            return filename, path.read_text()

        _, toc = fetch('runtime-config.html')
        files = sorted(set(re.findall(
            r'href="((?:runtime-config[^"#]*|config-setting)\.html)(?:#[^"]*)?"', toc)))
        if not files:
            raise ValueError('Documentation chapter contents not found')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            pages = dict(executor.map(fetch, files))
        return collect(settings, pages, toc)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    path = ROOT / 'pg_settings.json'
    settings = json.loads(path.read_text())
    catalogue = refresh(settings) if args.refresh else json.loads(CATALOGUE.read_text())
    apply(settings, catalogue)
    if args.refresh:
        CATALOGUE.write_text(json.dumps(catalogue, ensure_ascii=False, indent=2) + '\n')
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=4) + '\n')
    print(f"Applied {len(catalogue['links'])} documentation links")
