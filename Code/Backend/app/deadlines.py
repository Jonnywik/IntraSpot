"""Compatibility entry point for the bounded maintenance pass."""
import argparse
import time

from app.maintenance import run_pass


def run_once() -> int:
    return run_pass()["processed"]


def main() -> None:
    parser = argparse.ArgumentParser(description='Run bounded deadline and retention maintenance.')
    parser.add_argument('--once', action='store_true', help='Process once and exit.')
    parser.add_argument('--interval', type=int, default=30, help='Polling interval in seconds (1–3600).')
    args = parser.parse_args()
    if not 1 <= args.interval <= 3600:
        parser.error('interval must be between 1 and 3600 seconds')
    try:
        while True:
            run_once()
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
