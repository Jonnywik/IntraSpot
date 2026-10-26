"""Explicit media observations; default output is a non-destructive dry run."""
import argparse
import json

from app.domains.media.reconciliation import reconcile_media


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record-observations', action='store_true',
                        help='Record sightings only; never delete files or release quota.')
    args = parser.parse_args()
    print(json.dumps({'dry_run': not args.record_observations,
                      'objects': reconcile_media(apply=args.record_observations)}, sort_keys=True))


if __name__ == '__main__':
    main()
