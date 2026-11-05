#!/bin/sh
cd "$(dirname "$0")" || exit 1
python3 run_all_pairs.py
