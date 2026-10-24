"""Opt-in current accessibility matrix, on the isolated browser scratch database."""
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from app.core.config import ROOT, get_settings
from app.local_identities import ensure_users
from tests.conftest import assert_test_target
from tests.shared.test_sprint5_browser import wait_for


@pytest.mark.skipif(os.environ.get('RUN_SPRINT24_BROWSER') != '1', reason='Opt-in isolated rendered accessibility matrix')
def test_current_accessibility_matrix(db, make_event):
    assert_test_target()
    ensure_users(db)
    db.commit()
    make_event(title='Fictional accessibility gathering')
    project = ROOT.parents[1]
    frontend = project / 'Code/Frontend'
    driver = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'
    assert driver.is_dir()
    export = frontend / 'out'
    assert any('http://127.0.0.1:8002' in file.read_text(encoding='utf8')
               for file in (export / '_next').rglob('*.js')), 'Build the isolated API 8002 browser export'
    environment = os.environ | {
        'ENVIRONMENT':'local', 'FIXTURE_AUTH':'true', 'DATABASE_URL':get_settings().database_url,
        'SPRINT24_PLAYWRIGHT':str(driver),
        'SPRINT24_EVIDENCE_DIR':str(ROOT / '.cache/s24-accessibility-evidence'),
    }
    for port in (8002, 3000):
        with socket.socket() as probe:
            assert probe.connect_ex(('127.0.0.1', port)) != 0, 'Browser test ports must be unused'
    processes = []
    try:
        api = subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1',
            '--port','8002','--no-access-log','--log-level','warning'], cwd=ROOT, env=environment,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(api)
        wait_for('http://127.0.0.1:8002/ready',api)
        web = subprocess.Popen(['node','scripts/serve-static.mjs'],cwd=frontend,env=environment,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        processes.append(web)
        wait_for('http://127.0.0.1:3000',web)
        subprocess.run(['node','docs/validation/sprint24-accessibility-check.mjs'],cwd=project,
            env=environment,check=True,timeout=300)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
