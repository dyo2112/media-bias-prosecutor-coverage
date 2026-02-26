"""
Run the full transformer pipeline: 04 → 05 → 06 → 07 (+ optional 08).

Double-click this file or run: python run_pipeline.py
  Add --with-langextract to also run Step 08 (requires LANGEXTRACT_API_KEY).
Output is displayed live AND saved to pipeline_log.txt.
"""

import subprocess
import sys
import os
import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "pipeline_log.txt")

STEPS = [
    ("1/4", "Bias detection (Methods A,B,C,D)", ["python", "04_bias_detection.py"]),
    ("2/4", "Framing analysis",                 ["python", "05_framing_analysis.py"]),
    ("3/4", "Statistical analysis",             ["python", "06_statistics.py"]),
    ("4/4", "Generating figures",               ["python", "07_visualize.py"]),
]

LANGEXTRACT_STEP = ("5/5", "langextract grounded extraction", ["python", "08_langextract_analysis.py"])


def log(msg: str, f):
    """Print to console and write to log file."""
    print(msg)
    f.write(msg + "\n")
    f.flush()


def run_step(label: str, desc: str, cmd: list[str], log_f):
    """Run a pipeline step, streaming output to both console and log."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log(f"\n[{label}] {desc}", log_f)
    log(f"         Started at: {now}", log_f)

    proc = subprocess.Popen(
        cmd,
        cwd=SCRIPT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,  # line-buffered
    )

    for line in proc.stdout:
        line = line.rstrip("\n")
        print(line)
        log_f.write(line + "\n")
        log_f.flush()

    proc.wait()

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if proc.returncode != 0:
        log(f"  ERROR: [{label}] failed with exit code {proc.returncode} at {now}", log_f)
        return False
    else:
        log(f"  [{label}] Finished at: {now}", log_f)
        return True


def main():
    os.chdir(SCRIPT_DIR)

    run_langextract = "--with-langextract" in sys.argv

    steps = list(STEPS)
    if run_langextract:
        steps.append(LANGEXTRACT_STEP)

    total = len(steps)
    # Relabel step numbers
    labeled_steps = [
        (f"{i+1}/{total}", desc, cmd) for i, (_, desc, cmd) in enumerate(steps)
    ]

    with open(LOG_FILE, "a", encoding="utf-8") as log_f:
        log("=" * 50, log_f)
        log("  Media Bias Pipeline - Transformer Analysis", log_f)
        if run_langextract:
            log("  (with langextract grounded extraction)", log_f)
        log("=" * 50, log_f)
        log(f"  Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", log_f)
        log(f"  Log file: {LOG_FILE}", log_f)
        log("", log_f)

        for label, desc, cmd in labeled_steps:
            ok = run_step(label, desc, cmd, log_f)
            if not ok:
                log(f"\nPipeline STOPPED due to error in step [{label}].", log_f)
                log("Check the output above and pipeline_log.txt for details.", log_f)
                input("\nPress Enter to close...")
                sys.exit(1)

        log("\n" + "=" * 50, log_f)
        log("  ALL DONE! Results are in output/", log_f)
        log("=" * 50, log_f)
        log("  - output/04_bias_scores.parquet", log_f)
        log("  - output/05_frames.parquet", log_f)
        log("  - output/06_stats_results.json", log_f)
        log("  - output/figures/*.png", log_f)
        if run_langextract:
            log("  - output/08_extractions.jsonl", log_f)
            log("  - output/08_extractions_summary.parquet", log_f)
            log("  - output/08_extraction_stats.json", log_f)
            log("  - output/08_visualization.html", log_f)
        log("=" * 50, log_f)

    input("\nPress Enter to close...")


if __name__ == "__main__":
    main()
