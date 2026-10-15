"""Two-phase live restart evidence; invoke before and after restarting local Uvicorn."""
import json
import sys

import httpx

from app.core.config import ROOT, get_settings


def main():
    if get_settings().environment != 'local' or sys.argv[1:] not in [['before'], ['after']]:
        raise RuntimeError('Use before/after phases only in local mode')
    phase = sys.argv[1]
    accounts = json.loads((ROOT.parent / 'Frontend/public/local-accounts.json').read_text(encoding='utf-8'))
    token = next(row['token'] for row in accounts if row['label'] == 'Fictional student 4')
    ids = json.loads((ROOT / '.local/fixture-ids.json').read_text(encoding='utf-8'))
    event_id = ids['heritage-gathering']
    headers = {'Authorization': f'Bearer {token}', 'Idempotency-Key': f'restart-proof-{event_id}'}
    with httpx.Client(base_url='http://127.0.0.1:8001', timeout=30) as client:
        health = client.get('/health').raise_for_status().json()
        result = client.post(f'/api/v1/events/{event_id}/registrations', headers=headers).raise_for_status().json()
        mine = client.get('/api/v1/me/registrations', headers=headers).raise_for_status().json()
        detail = client.get(f'/api/v1/events/{event_id}').raise_for_status().json()
    snapshot = {'instance_id': health['instance_id'], 'original_result': result, 'current_registration': next(r for r in mine if r['event_id'] == event_id),
                'confirmed_count': detail['confirmed_count'], 'remaining_spots': detail['remaining_spots']}
    target = ROOT / '.local/restart-before.json'
    if phase == 'before':
        target.write_text(json.dumps(snapshot), encoding='utf-8')
        print('Before-restart registration evidence stored; no credentials printed.')
    else:
        before = json.loads(target.read_text(encoding='utf-8'))
        assert before['instance_id'] != snapshot['instance_id'], 'Backend application instance did not restart'
        assert before['original_result'] == snapshot['original_result'], 'Idempotent replay changed'
        assert before['current_registration'] == snapshot['current_registration'], 'Persisted registration changed'
        assert before['confirmed_count'] == snapshot['confirmed_count'] and before['remaining_spots'] == snapshot['remaining_spots']
        evidence = {'process_restart': 'pass', 'idempotent_replay': 'pass', 'registration_persistence': 'pass',
                    'counts_persisted': 'pass', 'before_instance': before['instance_id'], 'after_instance': snapshot['instance_id']}
        (ROOT.parents[1] / 'docs/backend/restart-evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        print('Live restart/replay/count persistence passed; evidence saved to docs/backend/restart-evidence.json')


if __name__ == '__main__':
    main()
