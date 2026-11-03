"""Audit every locked public PyPI dependency against OSV; fail closed on outage."""
from pathlib import Path
import json
import re
import urllib.request


def main():
    lock = Path(__file__).resolve().parents[1] / 'Code/Backend/requirements.lock'
    packages = re.findall(r'^([A-Za-z0-9_.-]+)==([^\s\\]+)', lock.read_text(), re.M)
    if not packages:
        raise SystemExit('No locked dependencies found')
    payload = {'queries': [{'package': {'name': name, 'ecosystem': 'PyPI'}, 'version': version}
                           for name, version in packages]}
    request = urllib.request.Request('https://api.osv.dev/v1/querybatch',
        data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read(4 * 1024 * 1024))
        results = body['results']
        if len(results) != len(packages) or any(result.get('next_page_token') for result in results):
            raise ValueError('Incomplete advisory response')
        findings = [(package[0], vulnerability['id']) for package, result in zip(packages, results)
                    for vulnerability in result.get('vulns', [])]
    except Exception:
        raise SystemExit('Dependency advisory service unavailable; verification remains blocked') from None
    for package, advisory in findings:
        print(f'{package}: {advisory}')
    if findings:
        raise SystemExit('Known backend dependency advisories require review')
    print(f'No known OSV advisories for {len(packages)} locked PyPI dependencies.')


if __name__ == '__main__':
    main()
