"""Reject private local files in the tracked delivery; never prints their content."""
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
paths = subprocess.check_output(['git', '-c', f'safe.directory={root.as_posix()}', 'ls-files'], cwd=root, text=True).splitlines()
for name in paths:
    path = Path(name)
    if any(part in {'.local', '.cache', '.venv', '.mvp-venv', 'node_modules', 'out', 'out-real', 'out-hosted'} for part in path.parts):
        raise SystemExit('Private or generated file is tracked: ' + name)
    if path.name.startswith('.env') and path.name != '.env.example':
        raise SystemExit('Environment credentials are tracked: ' + name)
    if path.name in {'private.pem', 'local-accounts.json', 'accounts.json'}:
        raise SystemExit('Local identities are tracked: ' + name)
    if path.suffix in {'.py', '.ts', '.tsx', '.mjs', '.json', '.yml', '.yaml'} and not any(part in {'tests', 'auth_tests'} for part in path.parts):
        value = (root / path).read_text(encoding='utf8')
        if re.search(r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----\s+[A-Za-z0-9+/=\s]{64,}-----END|GOCSPX-[A-Za-z0-9_-]{16,}|sb_secret_[A-Za-z0-9_-]{24,}', value):
            raise SystemExit('Possible secret in delivery: ' + name)
print('Tracked delivery excludes local credentials and build output.')
