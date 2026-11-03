"""Bounded media GC; dry-run by default and deletes require a saved manifest."""
import argparse
import json
from pathlib import Path

from app.domains.media.reconciliation import (
    MAX_MANIFEST_TARGETS,
    apply_media_manifest,
    reconcile_media,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        '--record-observations',
        action='store_true',
        help='Record weekly orphan sightings without deleting objects.',
    )
    action.add_argument(
        '--apply-manifest',
        type=Path,
        help='Revalidate and apply only eligible targets in this saved JSON manifest.',
    )
    parser.add_argument('--after-id', help='Continue after this media ID when scanning.')
    parser.add_argument(
        '--limit', type=int, default=MAX_MANIFEST_TARGETS,
        help=f'Maximum objects to inspect (1-{MAX_MANIFEST_TARGETS}).',
    )
    args = parser.parse_args()
    if args.apply_manifest is not None:
        with args.apply_manifest.open('r', encoding='utf-8') as manifest_file:
            manifest = json.load(manifest_file)
        payload = {
            'dry_run': False,
            'results': apply_media_manifest(manifest),
        }
    else:
        objects = reconcile_media(
            apply=args.record_observations,
            after_id=args.after_id,
            limit=args.limit,
        )
        payload = {
            'dry_run': not args.record_observations,
            'objects': objects,
            'next_after': objects[-1]['id'] if len(objects) == args.limit else None,
        }
    print(json.dumps(payload, sort_keys=True))


if __name__ == '__main__':
    main()
