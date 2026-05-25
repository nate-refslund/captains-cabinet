#!/usr/bin/env python3
"""Compile sanitized learning digests from experience records.

Reads experience records from JSONL log files or a JSON sample file,
applies sanitization rules to strip secrets and product-specific details,
and outputs a public-safe markdown digest.

Usage:
  python3 compile-digest.py                          # from log files
  python3 compile-digest.py --sample-data FILE       # from JSON sample
  python3 compile-digest.py --output /path/to/out.md # specify output path
  python3 compile-digest.py --week 2026-W22          # specific week
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from compile_digest_lib import (
    load_sanitize_config,
    load_records_from_logs,
    load_records_from_sample,
    compile_digest,
)


def main():
    parser = argparse.ArgumentParser(description='Compile sanitized learning digest')
    parser.add_argument('--sample-data', help='JSON file with sample records')
    parser.add_argument('--config', help='Sanitization config YAML path')
    parser.add_argument('--output', help='Output file path (default: stdout)')
    parser.add_argument('--week', help='Week to compile (e.g., 2026-W22)')
    parser.add_argument('--log-dir', help='Directory containing JSONL log files')
    args = parser.parse_args()

    config = load_sanitize_config(args.config)

    if args.sample_data:
        records = load_records_from_sample(args.sample_data)
    else:
        cabinet_root = os.environ.get('CABINET_ROOT', '/opt/founders-cabinet')
        log_dir = args.log_dir or os.path.join(cabinet_root, 'memory/logs')
        records = load_records_from_logs(log_dir, args.week)

    digest = compile_digest(records, config, args.week)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
        with open(args.output, 'w') as f:
            f.write(digest)
        print(f'Digest written to {args.output}', file=sys.stderr)
    else:
        print(digest)


if __name__ == '__main__':
    main()
