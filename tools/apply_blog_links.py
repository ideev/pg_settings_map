"""Apply the reviewed The Build article catalogue to pg_settings.json, offline."""
import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def apply(settings, catalogue):
    parameters = {}

    def walk(node):
        if node['type'] == 'parameter':
            if node['name'] in parameters:
                raise ValueError(f"Duplicate parameter: {node['name']}")
            parameters[node['name']] = node
        for child in node.get('children', []):
            walk(child)

    walk(settings)
    links = {name: [] for name in parameters}
    seen = set()
    for article in catalogue['articles']:
        url = urlsplit(article['url'])
        if (url.scheme != 'https' or url.netloc != 'thebuild.com'
                or not url.path.startswith('/blog/') or not article['title'].strip()):
            raise ValueError(f"Invalid reference: {article['url']}")
        if article['url'] in seen:
            raise ValueError(f"Duplicate article: {article['url']}")
        seen.add(article['url'])
        for name in article['parameters']:
            if name not in parameters:
                raise ValueError(f'Catalogue parameter absent from settings: {name}')
            link = {'title': article['title'], 'url': article['url']}
            if link not in links[name]:
                links[name].append(link)
    # Mutate only after the complete catalogue has passed validation.
    for name, parameter in parameters.items():
        retained = [link for link in parameter.get('blog_links', [])
                    if urlsplit(link['url']).hostname != 'thebuild.com']
        combined = retained + links[name]
        if combined:
            parameter['blog_links'] = combined
        else:
            parameter.pop('blog_links', None)
    return settings


if __name__ == '__main__':
    path = ROOT / 'pg_settings.json'
    settings = json.loads(path.read_text())
    catalogue = json.loads((ROOT / 'data/thebuild_articles.json').read_text())
    apply(settings, catalogue)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=4) + '\n')
    print('Applied reviewed The Build links')
