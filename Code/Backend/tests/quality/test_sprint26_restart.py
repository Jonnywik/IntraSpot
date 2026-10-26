"""A fresh process reads the ledger and bytes written by a terminated process."""
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID

from app.core.config import ROOT


CHILD = '''
import sys
from pathlib import Path
from app.core.config import get_settings
from app.domains.media.storage import store_webp, read_webp
s = get_settings()
assert s.environment == 'test' and s.database_url.endswith('/intraspot_mvp_test')
s.media_root = Path(sys.argv[2])
if sys.argv[1] == 'write':
    print(store_webp(b'static restart fixture', org_id=sys.argv[3]))
else:
    assert read_webp(sys.argv[3]) == b'static restart fixture'
    print('Fresh-process durable read passed')
'''


def test_media_survives_writer_restart_and_a_second_process(db, make_org, tmp_path):
    org = make_org()
    db.commit()
    arguments = [sys.executable, '-c', CHILD]
    writer = subprocess.run(arguments + ['write', str(tmp_path), org.id], cwd=ROOT,
                            env=os.environ.copy(), capture_output=True, text=True, timeout=30)
    assert writer.returncode == 0, 'Isolated writer failed'
    media_id = writer.stdout.strip()
    assert str(UUID(media_id)) == media_id
    reader = subprocess.run(arguments + ['read', str(tmp_path), media_id], cwd=ROOT,
                            env=os.environ.copy(), capture_output=True, text=True, timeout=30)
    assert reader.returncode == 0, 'Isolated reader failed'
    assert reader.stdout.strip() == 'Fresh-process durable read passed'
