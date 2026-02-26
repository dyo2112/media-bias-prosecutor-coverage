"""Helper: Run 09_bias_extraction.py in a loop until all 200 articles are done.

Works around the background task timeout by running extraction in batches,
checking progress, and re-launching with --resume until complete.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

JSONL_PATH = Path(r"C:\Users\dviry\My Drive\Papers and ClassReading\Berkeley\postdoc\media\media_bias_python\output\09_bias_extractions.jsonl")
SCRIPT = Path(r"C:\Users\dviry\My Drive\Papers and ClassReading\Berkeley\postdoc\media\media_bias_python\09_bias_extraction.py")
TARGET = 200
API_KEY = sys.argv[1] if len(sys.argv) > 1 else None

if not API_KEY:
    print("Usage: python run_09_loop.py <API_KEY>")
    sys.exit(1)


def count_articles():
    if not JSONL_PATH.exists():
        return 0
    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def run_batch():
    """Run extraction with --sample 200 --resume. Returns when process exits."""
    cmd = [
        sys.executable, str(SCRIPT),
        "--sample", "200",
        "--resume",
        "--delay", "0.3",
        "--api-key", API_KEY,
    ]
    print(f"  Launching: {' '.join(cmd[-6:])}")
    result = subprocess.run(cmd, capture_output=False, text=True)
    return result.returncode


iteration = 0
while True:
    n = count_articles()
    print(f"\n=== Iteration {iteration} | Articles: {n}/{TARGET} ===")

    if n >= TARGET:
        print(f"Done! {n} articles extracted.")
        break

    run_batch()
    iteration += 1

    new_n = count_articles()
    if new_n == n:
        print(f"WARNING: No progress (still {n}). Stopping.")
        break

    print(f"  Progress: {n} -> {new_n} (+{new_n - n})")

print(f"\nFinal count: {count_articles()} articles")
