#!/usr/bin/env python3
"""Generate static EN/RU pages from English markup and restricted JS dictionaries."""
import argparse
import html
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
PAIRS = ['index.html'] + [f'projects/{slug}/{file}' for slug in (
    'gramma-first-words', 'gramma-words-from-words') for file in ('index.html', 'support.html')]
ORIGIN = 'https://grimuar.github.io'


class DictionaryReader:
    """Accept only objects with identifier keys and JSON-compatible quoted strings.

    Not a general JavaScript parser: expressions, functions, arrays and duplicate
    keys are rejected. No JavaScript is evaluated and no translations are rewritten.
    """
    def __init__(self, source):
        self.source, self.pos = source, 0

    def skip(self):
        while self.pos < len(self.source):
            if self.source[self.pos].isspace():
                self.pos += 1
            elif self.source.startswith('//', self.pos):
                end = self.source.find('\n', self.pos)
                self.pos = len(self.source) if end < 0 else end + 1
            elif self.source.startswith('/*', self.pos):
                end = self.source.find('*/', self.pos + 2)
                if end < 0:
                    raise ValueError('Unclosed dictionary comment')
                self.pos = end + 2
            else:
                return

    def take(self, literal):
        self.skip()
        if not self.source.startswith(literal, self.pos):
            raise ValueError(f'Expected {literal!r} at position {self.pos}')
        self.pos += len(literal)

    def value(self):
        self.skip()
        if self.source.startswith('"', self.pos):
            value, end = json.JSONDecoder().raw_decode(self.source, self.pos)
            self.pos = end
            return value
        self.take('{')
        result = {}
        while True:
            self.skip()
            if self.source.startswith('}', self.pos):
                self.pos += 1
                return result
            match = re.match(r'[A-Za-z_$][A-Za-z0-9_$]*', self.source[self.pos:])
            if not match:
                raise ValueError(f'Expected a dictionary key at position {self.pos}')
            key = match[0]
            self.pos += len(key)
            if key in result:
                raise ValueError(f'Duplicate dictionary key: {key}')
            self.take(':')
            result[key] = self.value()
            self.skip()
            if self.source.startswith('}', self.pos):
                continue
            self.take(',')


def dictionary(lang):
    reader = DictionaryReader((ROOT / f'assets/js/locales/{lang}.js').read_text(encoding='utf-8'))
    reader.take('window.GorbanLocales = window.GorbanLocales || {};')
    reader.take(f'window.GorbanLocales.{lang} =')
    result = reader.value()
    reader.take(';')
    reader.skip()
    if reader.pos != len(reader.source):
        raise ValueError('Unsupported code after dictionary')
    return result


def flatten(obj, prefix=''):
    result = {}
    for key, value in obj.items():
        if isinstance(value, dict):
            result.update(flatten(value, prefix + key + '.'))
        else:
            result[prefix + key] = value
    return result


def url(path):
    return '/' + path.removesuffix('index.html')


def language_links(en, ru, lang):
    return '<div class="languages" aria-label="' + ('Язык' if lang == 'ru' else 'Language') + '">' + ''.join(
        f'<a href="{address}" data-lang="{code}" lang="{code}" hreflang="{code}"'
        + (' aria-current="page"' if code == lang else '') + f'>{code.upper()}</a>'
        + ('<span>/</span>' if code == 'en' else '') for code, address in [('en', en), ('ru', ru)]) + '</div>'


class TextLeaf(HTMLParser):
    def handle_starttag(self, tag, attrs):
        if tag != 'br':
            raise ValueError('data-i18n must mark a text-only leaf, not nested UI')

    handle_startendtag = handle_starttag


# The studio wordmark is fixed artwork, not the translated navigation brand.
# Its two lines and nested accent/dot containers must survive every generation.
HERO_WORDMARK = '<h1><span style="color:inherit">GORBAN</span><br><span><span>STUDIO</span><span class="gold-dot">.</span></span></h1>'


class WordmarkStructure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tokens = []

    def handle_starttag(self, tag, attrs):
        self.tokens.append(('start', tag, tuple(sorted(attrs))))

    def handle_endtag(self, tag):
        self.tokens.append(('end', tag))

    def handle_data(self, data):
        if data.strip():
            self.tokens.append(('text', data.strip()))


def validate_hero_wordmark(source):
    match = re.search(r'<section class="hero wrap">.*?(<h1>.*?</h1>)', source, re.S)
    if not match:
        raise ValueError('Studio Hero wordmark is missing')
    actual, expected = WordmarkStructure(), WordmarkStructure()
    actual.feed(match[1])
    expected.feed(HERO_WORDMARK)
    if actual.tokens != expected.tokens:
        raise ValueError('Studio Hero must preserve GORBAN / STUDIO with its nested accent and gold-dot containers; do not translate its wordmark leaves')


def generate(source, path, lang, words):
    en, ru = url(path), '/ru' + url(path)
    current = ru if lang == 'ru' else en
    source = re.sub(r'<html lang="[^"]+">', f'<html lang="{lang}">', source, count=1)
    source = re.sub(r'<script[^>]+src="/assets/js/(?:locales/(?:en|ru)|localization)\.js[^\"]*"[^>]*></script>\s*', '', source)
    source = re.sub(r'<div class="languages".*?</div>', lambda _: language_links(en, ru, lang), source, flags=re.S)
    # data-i18n marks text-only leaves; fail rather than silently flatten nested UI.
    pattern = r'(<(?P<tag>span|b|h1|h2|h3|strong|a|p)\b[^>]*\bdata-i18n="(?P<key>[^"]+)"[^>]*>)(?P<text>.*?)(</(?P=tag)>)'
    def translate(match):
        leaf = TextLeaf()
        leaf.feed(match['text'])
        leaf.close()
        value = html.escape(words[match['key']], quote=False)
        if 'data-i18n-lines' in match[1]:
            value = value.replace('\n', '<br>')
        return match[1] + value + '</' + match['tag'] + '>'
    source = re.sub(pattern, translate, source, flags=re.S)
    # Page links remain ordinary links; assets, shops and document URLs are shared.
    english_urls = {url(p) for p in PAIRS}
    def link(match):
        address = html.unescape(match[1])
        base, sep, fragment = address.partition('#')
        if '/privacy.html' in base or '/terms.html' in base:
            address = base.removeprefix('/ru') + '#' + lang
        elif lang == 'ru' and base in english_urls:
            address = '/ru' + base + (sep + fragment if sep else '')
        return 'href="' + html.escape(address, quote=True) + '"'
    # Exclude language switch links and head metadata from navigation rewriting.
    start, end = source.index('<body>'), source.index('</body>')
    body = source[start:end]
    switch = re.search(r'<div class="languages".*?</div>', body, re.S)[0]
    body = body.replace(switch, '<!-- LANGUAGE_SWITCH -->')
    body = re.sub(r'href="([^"]+)"', link, body).replace('<!-- LANGUAGE_SWITCH -->', switch)
    source = source[:start] + body + source[end:]
    source = source.replace('<div lang="en">', f'<div lang="{lang}">')
    if lang == 'ru':
        labels = {'Main': 'Основная навигация', 'Project documents': 'Документы проекта'}
        for before, after in labels.items():
            source = source.replace(f'aria-label="{before}"', f'aria-label="{after}"')
        source = source.replace('alt="Gramma: First Words — illustrated word learning"', 'alt="' + words['firstWords.title'] + ' — изучение слов по картинкам"')
        source = source.replace('alt="Gramma: Words from Word — letter tiles"', 'alt="' + words['wordsFromWords.title'] + ' — буквенные плитки"')
    if lang == 'ru':
        if path == 'index.html':
            title, description = 'Gorban Studio — Игры и приложения', words['studio.description']
        else:
            group = 'firstWords' if 'gramma-first-words' in path else 'wordsFromWords'
            title = (words['common.support'] + ' — ' + words[group + '.title']) if path.endswith('support.html') else words[group + '.title'] + ' — Gorban Studio'
            description = (words[group + '.supportDescription'] + (' ' + words[group + '.title'] + words['firstWords.supportAfter'] if group == 'firstWords' else '')) if path.endswith('support.html') else words[group + '.description']
        source = re.sub(r'<title>.*?</title>', lambda _: '<title>' + html.escape(title) + '</title>', source)
        for attribute, value in [('name="description"', description), ('property="og:title"', title), ('property="og:description"', description)]:
            source = re.sub(r'(<meta ' + attribute + r' content=")[^"]*', lambda m: m[1] + html.escape(value, quote=True), source)
    for pattern in [r'(<link rel="canonical" href=")[^"]*', r'(<meta property="og:url" content=")[^"]*']:
        source = re.sub(pattern, lambda m: m[1] + ORIGIN + current, source)
    source = re.sub(r'<link rel="alternate" hreflang="[^"]+" href="[^"]+">\s*', '', source)
    alternates = ''.join(f'<link rel="alternate" hreflang="{code}" href="{ORIGIN + address}">\n' for code, address in [('en', en), ('ru', ru), ('x-default', en)])
    source = source.replace('</head>', alternates + '</head>')
    if path == 'index.html':
        validate_hero_wordmark(source)
    return source


def seo(source, path, lang, words, paired=True):
    """Rebuild social metadata and our JSON-LD deterministically, never legal copy."""
    config = json.loads((ROOT / 'tools/seo-metadata.json').read_text(encoding='utf-8'))
    group = ('firstWords' if 'gramma-first-words' in path else
             'wordsFromWords' if 'gramma-words-from-words' in path else 'studio')
    game = group != 'studio' and path.endswith('index.html')
    if game:
        description = config['descriptions'][group][lang]
        source = re.sub(r'(<meta name="description" content=")[^"]*',
                        lambda m: m[1] + html.escape(description, quote=True), source)
    title = html.unescape(re.search(r'<title>(.*?)</title>', source, re.S)[1])
    description = html.unescape(re.search(r'<meta name="description" content="([^"]*)', source)[1])
    canonical = html.unescape(re.search(r'<link rel="canonical" href="([^"]*)', source)[1])
    image = config['images'][group]
    image_url = ORIGIN + image['path']
    source = re.sub(r'<meta (?:property|name)="(?:og:|twitter:)[^"]+"[^>]*>\s*', '', source)
    metadata = {
        'og:title': title, 'og:description': description, 'og:url': canonical,
        'og:type': 'website', 'og:image': image_url, 'og:image:type': 'image/png',
        'og:image:alt': image['alt'][lang], 'og:image:width': str(image['width']),
        'og:image:height': str(image['height']),
        'og:locale': 'ru_RU' if lang == 'ru' else 'en_US',
    }
    if paired:
        metadata['og:locale:alternate'] = 'en_US' if lang == 'ru' else 'ru_RU'
    metadata.update({'twitter:card': 'summary_large_image', 'twitter:title': title,
                     'twitter:description': description, 'twitter:image': image_url,
                     'twitter:image:alt': image['alt'][lang]})
    head = ''.join('<meta ' + ('name' if key.startswith('twitter:') else 'property')
                   + '="' + key + '" content="' + html.escape(value, quote=True) + '">\n'
                   for key, value in metadata.items())
    source = re.sub(r'<script type="application/ld\+json" id="site-schema">.*?</script>\s*', '', source, flags=re.S)
    if path == 'index.html' or game:
        organization = {
            '@type': 'Organization', '@id': ORIGIN + '/#organization',
            'name': 'Gorban Studio', 'url': ORIGIN + '/',
            'logo': ORIGIN + '/assets/images/studio/monogram.svg',
            'description': words['studio.description'], 'email': 'egorban.studio@gmail.com',
        }
        graph = [organization]
        if game:
            application = {
                '@type': 'MobileApplication', '@id': ORIGIN + url(path) + '#application',
                'name': words[group + '.title'], 'description': description,
                'url': canonical, 'image': image_url, 'applicationCategory': 'GameApplication',
                'inLanguage': lang, 'author': {'@id': organization['@id']},
            }
            if group == 'firstWords':
                application['installUrl'] = re.findall(r'<a[^>]+href="(https://(?:play.google.com|www.rustore.ru|appgallery.huawei.com)[^"]+)"', source)
            graph.append(application)
        data = {'@context': 'https://schema.org', '@graph': graph}
        head += '<script type="application/ld+json" id="site-schema">' + json.dumps(data, ensure_ascii=False, indent=2).replace('<', '\u003c') + '</script>\n'
    return source.replace('</head>', head + '</head>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check generated pages without writing them')
    args = parser.parse_args()
    words = {lang: flatten(dictionary(lang)) for lang in ('en', 'ru')}
    if words['en'].keys() != words['ru'].keys():
        raise ValueError('EN/RU dictionary keys differ')
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('asset_version', ROOT / 'tools/update-assets-version.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    version = (ROOT / 'tools/assets-version.txt').read_text().strip()
    outputs = {}
    for path in PAIRS:
        source = (ROOT / path).read_text(encoding='utf-8')
        for lang in ('en', 'ru'):
            target = path if lang == 'en' else 'ru/' + path
            outputs[target] = module.update_html(seo(generate(source, path, lang, words[lang]), path, lang, words[lang]), version)
    # Shared legal HTML is updated only in its head; document bodies are untouched.
    for path in [f'projects/{slug}/{kind}.html' for slug in (
            'gramma-first-words', 'gramma-words-from-words') for kind in ('privacy', 'terms')] + ['404.html']:
        source = (ROOT / path).read_text(encoding='utf-8')
        outputs[path] = module.update_html(seo(source, path, 'en', words['en'], paired=False), version)
    changed = [path for path, value in outputs.items() if not (ROOT / path).exists() or (ROOT / path).read_text(encoding='utf-8') != value]
    for path in changed:
        print(('Stale: ' if args.check else 'Updated: ') + path)
        if not args.check:
            (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
            (ROOT / path).write_text(outputs[path], encoding='utf-8')
    print(f'{len(changed)} page(s) {"stale" if args.check else "updated"}.')
    return int(bool(changed)) if args.check else 0


if __name__ == '__main__':
    raise SystemExit(main())
