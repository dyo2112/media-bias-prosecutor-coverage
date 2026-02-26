"""Shared utilities for the media bias analysis pipeline."""

import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from tqdm import tqdm

logger = logging.getLogger("media_bias")


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging for the pipeline."""
    # Use utf-8 on Windows to avoid charmap encoding errors
    if sys.platform == "win32":
        import io
        stream = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    else:
        stream = sys.stdout
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
    )
    root = logging.getLogger("media_bias")
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(handler)


def load_parquet(path: Path) -> pd.DataFrame:
    """Load a Parquet file with a summary log message."""
    df = pd.read_parquet(path)
    logger.info(f"Loaded {len(df):,} rows from {path.name}")
    return df


def save_parquet(df: pd.DataFrame, path: Path) -> None:
    """Save a DataFrame to Parquet with a summary log message."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    logger.info(f"Saved {len(df):,} rows to {path.name}")


def clean_text(text: str) -> str:
    """Lowercase, normalize apostrophes/quotes, collapse whitespace."""
    if not isinstance(text, str):
        return ""
    text = text.lower()
    # Normalize curly quotes and apostrophes
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate_words(text: str, max_words: int) -> str:
    """Truncate text to the first max_words words."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])


def split_sentences(text: str) -> list[str]:
    """Simple sentence splitter using regex. Not perfect but fast."""
    # Split on period/question/exclamation followed by space + capital letter or end
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"])', text)
    return [s.strip() for s in parts if s.strip()]


def get_sentence_windows(
    text: str, target: str, window_size: int = 3
) -> list[str]:
    """Get sentence windows around occurrences of target in text.

    Returns list of text excerpts consisting of `window_size` sentences
    centered on each sentence that contains `target`.
    """
    sentences = split_sentences(text)
    target_lower = target.lower()
    windows = []
    for i, sent in enumerate(sentences):
        if target_lower in sent.lower():
            start = max(0, i - window_size // 2)
            end = min(len(sentences), i + window_size // 2 + 1)
            window_text = " ".join(sentences[start:end])
            windows.append(window_text)
    return windows


def batched_inference(
    texts: list[str],
    pipeline_fn: Any,
    batch_size: int = 16,
    desc: str = "Inference",
) -> list[Any]:
    """Run a HuggingFace pipeline in batches with a progress bar.

    Args:
        texts: List of input texts.
        pipeline_fn: A HuggingFace pipeline object (called with a list of strings).
        batch_size: Number of texts per batch.
        desc: Progress bar description.

    Returns:
        Flat list of results, one per input text.
    """
    results = []
    for i in tqdm(range(0, len(texts), batch_size), desc=desc):
        batch = texts[i : i + batch_size]
        batch_results = pipeline_fn(batch)
        results.extend(batch_results)
    return results


def batched_zeroshot(
    texts: list[str],
    classifier: Any,
    candidate_labels: list[str],
    batch_size: int = 16,
    desc: str = "Zero-shot",
) -> list[dict]:
    """Run zero-shot classification in batches.

    Returns list of dicts with 'labels' and 'scores' keys.
    """
    results = []
    for i in tqdm(range(0, len(texts), batch_size), desc=desc):
        batch = texts[i : i + batch_size]
        batch_results = classifier(
            batch,
            candidate_labels=candidate_labels,
            multi_label=False,
        )
        # classifier returns a single dict for single input, list for multiple
        if isinstance(batch_results, dict):
            batch_results = [batch_results]
        results.extend(batch_results)
    return results


def checkpoint_save(df: pd.DataFrame, path: Path, processed_col: str = "_processed") -> None:
    """Save checkpoint for resumable processing.

    Adds a _processed column set to True for rows that have been processed.
    """
    if processed_col not in df.columns:
        df[processed_col] = False
    save_parquet(df, path)


def checkpoint_load(path: Path, processed_col: str = "_processed") -> tuple[pd.DataFrame, int]:
    """Load checkpoint and return (dataframe, n_already_processed)."""
    if not path.exists():
        return pd.DataFrame(), 0
    df = load_parquet(path)
    if processed_col in df.columns:
        n_done = int(df[processed_col].sum())
    else:
        n_done = 0
    return df, n_done


def timer(label: str):
    """Context manager that logs elapsed time."""
    class Timer:
        def __enter__(self):
            self.start = time.time()
            logger.info(f"Starting: {label}")
            return self
        def __exit__(self, *args):
            elapsed = time.time() - self.start
            if elapsed < 60:
                logger.info(f"Finished: {label} ({elapsed:.1f}s)")
            elif elapsed < 3600:
                logger.info(f"Finished: {label} ({elapsed/60:.1f}min)")
            else:
                logger.info(f"Finished: {label} ({elapsed/3600:.1f}hr)")
    return Timer()
