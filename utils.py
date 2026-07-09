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
    text: str, target: str, window_size: int = 3, whole_word: bool = True
) -> list[str]:
    """Get sentence windows around occurrences of target in text.

    Returns list of text excerpts consisting of `window_size` sentences
    centered on each sentence that contains `target`.

    With whole_word=True (default), the target must not be embedded inside a
    longer word — prevents e.g. "the da" matching "the day" or "the dark".
    """
    sentences = split_sentences(text)
    target_lower = target.lower()
    if whole_word:
        target_re = re.compile(
            r"(?<!\w)" + re.escape(target_lower) + r"(?!\w)"
        )
        def matches(sent: str) -> bool:
            return bool(target_re.search(sent.lower()))
    else:
        def matches(sent: str) -> bool:
            return target_lower in sent.lower()

    windows = []
    for i, sent in enumerate(sentences):
        if matches(sent):
            start = max(0, i - window_size // 2)
            end = min(len(sentences), i + window_size // 2 + 1)
            window_text = " ".join(sentences[start:end])
            windows.append(window_text)
    return windows


def is_negated(
    text: str,
    match_start: int,
    negation_words: set[str],
    window: int = 4,
) -> bool:
    """Check whether a match at match_start is negated by a preceding word.

    Compares whole tokens (not substrings) in the `window` words before the
    match, so "no" does not fire inside "know" or "not" inside "notably".
    Multi-word negators (e.g. "no evidence") are matched as phrases against
    the joined token window.
    """
    preceding_tokens = re.findall(r"[\w']+", text[:match_start].lower())
    token_window = preceding_tokens[-window:]
    window_str = " ".join(token_window)
    for neg in negation_words:
        if " " in neg:
            if neg in window_str:
                return True
        elif neg in token_window:
            return True
    return False


# Quoted-speech spans: straight or curly double quotes. Span length is capped
# so a stray unmatched quote cannot swallow the rest of the article.
_QUOTE_SPAN_RE = re.compile(r'"[^"]{2,600}"|“[^“”]{2,600}”')


def find_quote_spans(text: str) -> list[tuple[int, int]]:
    """Return (start, end) character spans of quoted speech in text."""
    if not isinstance(text, str) or '"' not in text and "“" not in text:
        return []
    return [(m.start(), m.end()) for m in _QUOTE_SPAN_RE.finditer(text)]


def pos_in_spans(pos: int, spans: list[tuple[int, int]]) -> bool:
    """Check whether a character position falls inside any (start, end) span."""
    return any(start <= pos < end for start, end in spans)


def fraction_quoted(text: str, spans: list[tuple[int, int]] | None = None) -> float:
    """Fraction of characters in text that sit inside quoted speech."""
    if not isinstance(text, str) or not text:
        return 0.0
    if spans is None:
        spans = find_quote_spans(text)
    quoted = sum(end - start for start, end in spans)
    return quoted / len(text)


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
