"""
Run the core analysis pipeline: 04 -> 05 -> 06 -> 07.

Usage:
  py -3 run_pipeline.py
    Core analyses and figures only.

  py -3 run_pipeline.py --with-langextract
    Core + Step 08 structural extraction (requires LANGEXTRACT_API_KEY).

  py -3 run_pipeline.py --paper
    Core + publication-lock extras:
      - Step 10 theme attribution
      - Step 12 segmented ITS
      - paper/build_stats_tex.py

  py -3 run_pipeline.py --paper --with-langextract
    Full publication run including structural extraction.

Output is displayed live and saved to pipeline_log.txt.
"""

import datetime
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "pipeline_log.txt")
PYTHON_EXE = sys.executable or "python"

BASE_STEPS = [
    ("", "Bias detection (Methods A,B,C,D)", [PYTHON_EXE, "04_bias_detection.py"]),
    ("", "Framing analysis", [PYTHON_EXE, "05_framing_analysis.py"]),
    ("", "Statistical analysis", [PYTHON_EXE, "06_statistics.py"]),
    ("", "Generating figures", [PYTHON_EXE, "07_visualize.py"]),
]

LANGEXTRACT_STEP = (
    "",
    "langextract grounded extraction",
    [PYTHON_EXE, "08_langextract_analysis.py"],
)

PAPER_STEPS = [
    ("", "Theme attribution analysis", [PYTHON_EXE, "10_theme_attribution.py"]),
    ("", "Segmented ITS robustness", [PYTHON_EXE, "12_segmented_its.py"]),
    ("", "Generate manuscript stats macros", [PYTHON_EXE, "paper/build_stats_tex.py"]),
]


def log(msg: str, f) -> None:
    """Print to console and write to log file."""
    print(msg)
    f.write(msg + "\n")
    f.flush()


def run_step(label: str, desc: str, cmd: list[str], log_f) -> bool:
    """Run one pipeline step while streaming output."""
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
        bufsize=1,
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

    log(f"  [{label}] Finished at: {now}", log_f)
    return True


def main() -> None:
    os.chdir(SCRIPT_DIR)

    run_langextract = "--with-langextract" in sys.argv
    run_paper = "--paper" in sys.argv

    steps = list(BASE_STEPS)
    if run_langextract:
        steps.append(LANGEXTRACT_STEP)
    if run_paper:
        steps.extend(PAPER_STEPS)

    total = len(steps)
    labeled_steps = [
        (f"{i + 1}/{total}", desc, cmd) for i, (_, desc, cmd) in enumerate(steps)
    ]

    with open(LOG_FILE, "a", encoding="utf-8") as log_f:
        log("=" * 50, log_f)
        log("  Media Bias Pipeline", log_f)
        if run_langextract:
            log("  (with langextract grounded extraction)", log_f)
        if run_paper:
            log("  (paper mode: theme + segmented ITS + stats macros)", log_f)
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
        if run_paper:
            log("  - output/10_theme_stats.json", log_f)
            log("  - output/12_segmented_its_results.json", log_f)
            log("  - output/12_segmented_its_table.csv", log_f)
            log("  - paper/generated_stats.tex", log_f)
        log("=" * 50, log_f)

    input("\nPress Enter to close...")


if __name__ == "__main__":
    main()
