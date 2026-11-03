"""Operator CLI for encrypted IntraSpot backup and isolated restore workflows."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from app.core.config import get_settings
from app.recovery import (
    RecoveryError,
    create_backup,
    export_erasure_ledger,
    list_snapshots,
    load_backup_key,
    restore_backup,
    retire_snapshot,
    verify_backup,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Encrypted IntraSpot backup and restore")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="create and verify a backup")
    create.add_argument("--output-root", required=True, type=Path)
    create.add_argument("--purpose", choices=("weekly", "premigration"), default="weekly")
    create.add_argument("--timeout", type=int, default=1800)
    create.add_argument("--key-file", type=Path)

    ledger = commands.add_parser("export-ledger", help="export current erasure tombstones separately")
    ledger.add_argument("--output-file", required=True, type=Path)
    ledger.add_argument("--key-file", type=Path)

    verify = commands.add_parser("verify", help="authenticate and verify a backup")
    verify.add_argument("--bundle", required=True, type=Path)
    verify.add_argument("--key-file", type=Path)

    restore = commands.add_parser(
        "restore", help="restore into an isolated local target after erasure cutoff confirmation",
    )
    restore.add_argument("--bundle", required=True, type=Path)
    restore.add_argument("--erasure-ledger", required=True, type=Path)
    restore.add_argument("--erasure-cutoff-at", required=True, help="timezone-aware ISO timestamp after quiescing erasures and writes")
    restore.add_argument(
        "--confirm-erasure-quiescence", action="store_true", required=True,
        help="confirm erasure fulfillment and relevant writes are quiesced",
    )
    restore.add_argument(
        "--target-database-url", default=os.environ.get("INTRASPOT_RESTORE_DATABASE_URL"),
        help="prefer protected INTRASPOT_RESTORE_DATABASE_URL to keep credentials out of process arguments",
    )
    restore.add_argument("--target-media-root", required=True, type=Path)
    restore.add_argument("--timeout", type=int, default=1800)
    restore.add_argument("--key-file", type=Path)

    commands.add_parser("snapshots", help="list retained backup snapshots")

    retire = commands.add_parser("retire", help="inspect or retire one snapshot")
    retire.add_argument("--snapshot-id", required=True)
    retire.add_argument("--output-root", required=True, type=Path)
    retire.add_argument("--apply", action="store_true", help="delete archive bytes and release media references")
    retire.add_argument("--confirm-no-archive", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            result = create_backup(
                get_settings().database_url,
                args.output_root,
                load_backup_key(args.key_file),
                purpose=args.purpose,
                timeout=args.timeout,
            )
        elif args.command == "export-ledger":
            result = export_erasure_ledger(
                get_settings().database_url,
                args.output_file,
                load_backup_key(args.key_file),
            )
        elif args.command == "verify":
            manifest = verify_backup(args.bundle, load_backup_key(args.key_file))
            result = {
                "snapshot_id": manifest["snapshot_id"],
                "created_at": manifest["created_at"],
                "purpose": manifest["purpose"],
                "database_sha256": manifest["database"]["sha256"],
                "objects_verified": sum(item["exists"] for item in manifest["objects"]),
            }
        elif args.command == "restore":
            if not args.target_database_url:
                raise RecoveryError("Set INTRASPOT_RESTORE_DATABASE_URL for the isolated target")
            result = restore_backup(
                args.bundle,
                load_backup_key(args.key_file),
                args.target_database_url,
                args.target_media_root,
                erasure_ledger_file=args.erasure_ledger,
                erasure_cutoff_at=args.erasure_cutoff_at,
                confirm_erasure_quiescence=args.confirm_erasure_quiescence,
                timeout=args.timeout,
            )
        elif args.command == "snapshots":
            result = list_snapshots(get_settings().database_url)
        else:
            result = retire_snapshot(
                get_settings().database_url,
                args.output_root,
                args.snapshot_id,
                apply=args.apply,
                confirm_no_archive=args.confirm_no_archive,
            )
    except RecoveryError as exc:
        print(f"backup: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
