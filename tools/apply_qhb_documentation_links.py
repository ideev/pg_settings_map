"""Apply reviewed QHB 1.5.3 links offline; --refresh checks the published manual."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import quote, unquote, urljoin, urlsplit
from zoneinfo import ZoneInfo

from apply_documentation_links import parameters

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://repo.quantom.info/qhb/std-1/doc/1.5.3/ru/'
SOURCE = 'Configuration/runtime-config.html'
CATALOGUE = ROOT / 'data/qhb_documentation.json'
# Reviewed configuration sections outside the Server Configuration chapter.
SUPPLEMENTS = {
    'SQL/autonomous-transactions.html#Конфигурирование': ['autonomous_pool_capacity', 'autonomous_session_max_uses'],
    'Configuration/monitoring/monitoring-qhb.html#sys': ['qhb_os_monitoring', 'qhb_os_stat_period'],
    'Internal/metricsd.html#Настройка-сервера-метрик': ['metrics_collector_path'],
    'Configuration/qbackup.html#Настройка-кластера-баз-данных': ['qcdc_registry_size'],
    'Internal/qhb-plan-cache.html#Параметры-разделяемого-кеша-в-qhbconf': ['qhb_plan_cache_size'],
    'Internal/qsched.html#Число-допустимых-параллельных-процессов': ['qsched_parallel_slaves'],
    'Internal/profile.html#Подготовка': ['query_profiling', 'query_profiling_queue_size'],
    'Internal/qhb_queryid.html#Параметры-конфигурации-для-настройки-работы-метрик-queryid': ['queryid_auto_register', 'queryid_max_saved', 'queryid_update_threshold'],
    'Configuration/resource-groups.html#Управление-ресурсами': ['resource_management'],
}


class Headings(HTMLParser):
    def __init__(self):
        super().__init__()
        self.headings = []
        self.current = None
        self.ids = set()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.hrefs.append(attrs['href'])
        if re.fullmatch(r'h[1-6]', tag):
            self.current = {'level': int(tag[1]), 'id': attrs.get('id'), 'text': ''}
        if self.current and 'id' in attrs:
            self.current['id'] = attrs['id']

    def handle_data(self, data):
        if self.current:
            self.current['text'] += data

    def handle_endtag(self, tag):
        if self.current and tag == f"h{self.current['level']}":
            self.headings.append(self.current)
            self.current = None


def parse(content):
    parser = Headings()
    parser.feed(content)
    return parser


def section_text(content, anchor):
    """Require the actual heading and inspect only its section, not sidebar text."""
    parser = parse(content)
    heading = next((h for h in parser.headings if h['id'] == anchor), None)
    if not heading:
        raise ValueError(f'Missing section heading: {anchor}')
    start = content.index(f'id="{anchor}"')
    rest = content[start:]
    end = re.search(r'<h[1-' + str(heading['level']) + r']\b', rest)
    return re.sub('<[^>]+>', ' ', rest[:end.start()] if end else rest)


def collect(settings, pages):
    names = parameters(settings)
    definitions = {}
    duplicates = {}
    for filename, content in sorted(pages.items()):
        if not filename.startswith('Configuration/runtime-config/'):
            continue
        for heading in parse(content).headings:
            match = re.fullmatch(r'([A-Za-z][A-Za-z0-9_.]*)\s*(?:\([^)]+\)|=\s*\'immediate\')', heading['text'].strip())
            if not match or not heading['id']:
                continue
            name = match[1]
            link = {'title': f'QHB 1.5.3: {name}',
                    'url': BASE + filename + '#' + quote(heading['id'], safe=''),
                    'documented_name': name, 'match_type': 'exact-heading'}
            if name in definitions:
                duplicates.setdefault(name, [definitions[name]['url']]).append(link['url'])
            else:
                definitions[name] = link
    for location, section_names in SUPPLEMENTS.items():
        filename, anchor = location.split('#', 1)
        text = section_text(pages[filename], anchor)
        for name in section_names:
            if not re.search(r'(?<![\w.])' + re.escape(name) + r'(?![\w.])', text):
                raise ValueError(f'Parameter absent from reviewed section: {name}')
            if name in definitions:
                raise ValueError(f'Supplement duplicates definition: {name}')
            definitions[name] = {'title': f'QHB 1.5.3: {name}',
                                 'url': BASE + filename + '#' + quote(anchor, safe=''),
                                 'documented_name': name, 'match_type': 'reviewed-configuration-section'}
    links = {name: definitions[name] for name in sorted(names) if name in definitions}
    for link in links.values():
        url = urlsplit(link['url'])
        filename = url.path.removeprefix(urlsplit(BASE).path)
        if unquote(url.fragment) not in parse(pages[filename]).ids:
            raise ValueError(f"Missing anchor: {link['url']}")
    return {'checked_on': datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat(),
            'source': BASE + SOURCE, 'release': '1.5.3', 'pages_checked': sorted(pages),
            'method': 'Exact names in parameter headings, plus reviewed configuration sections outside the chapter. Actual HTML anchors verified. First heading used for duplicate definitions.',
            'duplicate_definitions': duplicates, 'linked_parameters': len(links), 'links': links,
            'parameters_without_description': sorted(set(names) - set(links)),
            'documented_parameters_not_in_map': sorted(set(definitions) - set(names))}


def apply(settings, catalogue):
    names = parameters(settings)
    for name, link in catalogue['links'].items():
        url = urlsplit(link['url'])
        if (name not in names or not link['title'].strip() or url.scheme != 'https'
                or url.netloc != 'repo.quantom.info' or not link['url'].startswith(BASE)
                or not url.path.endswith('.html') or not url.fragment
                or any(part in ('.', '..') for part in unquote(url.path).split('/'))):
            raise ValueError(f'Invalid QHB documentation mapping: {name}')
    for name, node in names.items():
        link = catalogue['links'].get(name)
        if link:
            node['qhb_documentation_link'] = {'title': link['title'], 'url': link['url']}
        else:
            node.pop('qhb_documentation_link', None)
    return settings


def refresh(settings):
    with TemporaryDirectory(prefix='qhb-docs-') as temp:
        def fetch(filename):
            path = Path(temp) / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['curl', '-fsSL', '--max-time', '40', '--retry', '2',
                            BASE + filename, '-o', str(path)], check=True)
            return filename, path.read_text()
        _, toc = fetch(SOURCE)
        files = set()
        for href in parse(toc).hrefs:
            url = urlsplit(urljoin(BASE + SOURCE, href))
            if url.scheme == 'https' and url.netloc == 'repo.quantom.info' and url.path.startswith(urlsplit(BASE).path + 'Configuration/runtime-config/') and url.path.endswith('.html'):
                files.add(url.path.removeprefix(urlsplit(BASE).path))
        if not files:
            raise ValueError('QHB configuration chapter contents not found')
        files.update(location.split('#')[0] for location in SUPPLEMENTS)
        with ThreadPoolExecutor(max_workers=4) as executor:
            pages = dict(executor.map(fetch, sorted(files)))
        pages[SOURCE] = toc
        return collect(settings, pages)


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
    print(f"Applied {len(catalogue['links'])} QHB documentation links")
