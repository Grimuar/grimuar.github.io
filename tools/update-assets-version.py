#!/usr/bin/env python3
"""Synchronize local CSS/JS URLs in HTML; Python standard library only."""
import argparse
import html
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote_plus, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = Path(__file__).with_name('assets-version.txt')
ATTRIBUTES = re.compile(
    r'''(?P<name>[\w:-]+)\s*=\s*(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)'|(?P<bare>[^\s>]+))'''
)


def versioned_url(raw, version):
    """Return a local CSS/JS URL with exactly one v, retaining other parameters."""
    url = html.unescape(raw)
    parts = urlsplit(url)
    if parts.scheme or parts.netloc or not parts.path.lower().endswith(('.css', '.js')):
        return raw
    parameters = [part for part in parts.query.split('&') if part]
    versions = [part for part in parameters if unquote_plus(part.partition('=')[0]) == 'v']
    if versions == ['v=' + version]:
        return raw
    parameters = [part for part in parameters if unquote_plus(part.partition('=')[0]) != 'v']
    parameters.append('v=' + version)
    updated = urlunsplit((parts.scheme, parts.netloc, parts.path, '&'.join(parameters), parts.fragment))
    return html.escape(updated, quote=True)


class ResourceParser(HTMLParser):
    def __init__(self, source, version):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.version = version
        self.edits = []
        self.line_offsets = [0]
        self.line_offsets.extend(match.end() for match in re.finditer('\n', source))

    def handle_starttag(self, tag, attrs):
        attribute = {'link': 'href', 'script': 'src'}.get(tag)
        if attribute is None:
            return
        if tag == 'link':
            values = dict(attrs)
            relations = (values.get('rel') or '').lower().split()
            is_resource = 'stylesheet' in relations or 'modulepreload' in relations or (
                'preload' in relations and values.get('as') in ('style', 'script')
            )
            if not is_resource:
                return
        line, column = self.getpos()
        offset = self.line_offsets[line - 1] + column
        for match in ATTRIBUTES.finditer(self.get_starttag_text()):
            if match['name'].lower() != attribute:
                continue
            group = next(name for name in ('double', 'single', 'bare') if match[name] is not None)
            replacement = versioned_url(match[group], self.version)
            if replacement != match[group]:
                # Unquoted URLs may gain &, so quote the new value in that case.
                if group == 'bare':
                    replacement = '"' + replacement + '"'
                self.edits.append((offset + match.start(group), offset + match.end(group), replacement))

    handle_startendtag = handle_starttag


def update_html(source, version):
    parser = ResourceParser(source, version)
    parser.feed(source)
    parser.close()
    for start, end, replacement in reversed(parser.edits):
        source = source[:start] + replacement + source[end:]
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Report mismatches without changing files; exit 1 if found.')
    mode.add_argument('--set', metavar='X.Y.Z', help='Set the shared version and update all HTML in one command.')
    args = parser.parse_args()
    version = args.set if args.set is not None else VERSION_FILE.read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        parser.error('Version must have the form X.Y.Z, for example 1.0.1.')

    changes = []
    for path in sorted(ROOT.rglob('*.html')):
        if any(part.startswith('.') for part in path.relative_to(ROOT).parts):
            continue
        original = path.read_bytes().decode('utf-8')
        updated = update_html(original, version)
        if original != updated:
            changes.append((path, updated))

    for path, updated in changes:
        print(('Mismatch: ' if args.check else 'Updated: ') + path.relative_to(ROOT).as_posix())
        if not args.check:
            path.write_bytes(updated.encode('utf-8'))
    if args.check:
        print(f'Version {version}: {len(changes)} HTML file(s) need updating.')
        return 1 if changes else 0
    if args.set is not None:
        VERSION_FILE.write_text(version + '\n', encoding='utf-8')
    print(f'Version {version}: updated {len(changes)} HTML file(s).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
