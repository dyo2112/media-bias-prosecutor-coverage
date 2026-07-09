"""
Step 10: Prosecutor-Attributed Theme Detection.

Ports the old R manuscript's multi-method theme detection algorithm to Python.
The key innovation: themes must be **explicitly attributed to prosecutors** via
co-occurring regex patterns (not just keyword proximity).

Four methods, combined with multi-method validation:
  1. Context-aware dictionary — compound regex requiring prosecutor + theme (0.30)
  2. Relationship-based regex — causal structures linking prosecutor to outcomes (0.35)
  3. Targeted criticism detection — high-confidence blame/failure patterns (0.15)
  4. Sentence-level co-occurrence — prosecutor + criticism in same sentence (0.20)

Input:  output/03_attributed.parquet
Output: output/10_theme_attribution.parquet
        output/10_theme_stats.json
"""

import argparse
import json
import re
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import chi2_contingency, mannwhitneyu, ttest_ind
from tqdm import tqdm

from config import (
    ATTRIBUTED_PARQUET,
    PROSECUTORS,
    NEGATION_WORDS,
    THEME_ATTR_PARQUET,
    THEME_STATS_JSON,
    OUTPUT_DIR,
)
from utils import (
    setup_logging,
    load_parquet,
    save_parquet,
    split_sentences,
    is_negated,
    find_quote_spans,
    pos_in_spans,
    timer,
    logger,
)


# ═══════════════════════════════════════════════════════════════════════════
# PATTERN DICTIONARIES
# ═══════════════════════════════════════════════════════════════════════════

# Placeholder token that gets replaced with per-article prosecutor regex.
# Word-boundary lookarounds prevent short terms matching inside longer words
# (bare "da" previously matched "day", "data", "agenda", ...).
_P = r"(?<!\w)(?:da|district\s+attorney|prosecutor|d\.a\.)(?!\w)"

# ── Method 1: Context-Aware Dictionary Patterns ──────────────────────────
# Each pattern requires BOTH a prosecutor mention AND a theme keyword
# in the SAME regex expression. Ported from RMD lines 104-158.

CONTEXTUAL_THEME_PATTERNS: dict[str, list[str]] = {
    "crime_rising": [
        rf"(?:crime|violence).{{0,20}}(?:up\b|rising|increase|spike|surge|soar).{{0,30}}{_P}",
        rf"{_P}.{{0,30}}(?:causing|responsible for|fault|blamed for).{{0,20}}(?:crime|violence)",
        rf"soft.{{0,5}}on.{{0,5}}crime.{{0,20}}{_P}",
        rf"{_P}.{{0,20}}soft.{{0,5}}on.{{0,5}}crime",
        rf"lenient.{{0,20}}{_P}.{{0,20}}(?:crime|spike|surge)",
    ],
    "releasing_criminals": [
        rf"{_P}.{{0,20}}(?:emptying|releasing from|releasing).{{0,10}}jail",
        rf"jail.{{0,10}}(?:beds?.{{0,5}})?empty.{{0,20}}because of.{{0,10}}{_P}",
        rf"{_P}.{{0,20}}won'?t keep.{{0,20}}(?:criminals?|inmates?|defendants?).{{0,10}}(?:locked|incarcerated|behind bars)",
        rf"(?:revolving door|catch and release|back on (?:the )?street).{{0,30}}{_P}",
    ],
    "victim_neglect": [
        rf"{_P}.{{0,20}}(?:ignoring|neglect\w*|doesn'?t care about|abandoned).{{0,10}}victim",
        rf"victim.{{0,20}}(?:abandoned|ignored|neglected|forgotten).{{0,20}}by.{{0,10}}{_P}",
        rf"{_P}.{{0,20}}prioritiz\w*.{{0,10}}criminal.{{0,10}}over.{{0,10}}victim",
    ],
    "police_conflict": [
        rf"(?:police|officers?|cops?).{{0,20}}(?:frustrated with|blame|criticize|angry at).{{0,20}}{_P}",
        rf"(?:officers?|police).{{0,20}}say.{{0,20}}{_P}.{{0,20}}won'?t prosecute",
        rf"pointless to arrest.{{0,20}}because of.{{0,10}}{_P}",
        rf"(?:police|officers?).{{0,20}}(?:morale|pushback).{{0,20}}{_P}",
    ],
    "office_dysfunction": [
        rf"(?:prosecutors?|attorneys?).{{0,20}}(?:leaving|quitting|resigning).{{0,20}}{_P}.{{0,5}}(?:'s )?office",
        rf"(?:mass exodus|hemorrhaging staff|high turnover).{{0,20}}{_P}.{{0,5}}(?:'s )?office",
        rf"{_P}.{{0,20}}(?:staff|prosecutors?).{{0,20}}(?:leaving|quitting|exodus|departures?)",
        rf"gender discrimination.{{0,20}}{_P}.{{0,5}}(?:'s )?office",
        rf"female prosecutors?.{{0,20}}leaving.{{0,20}}because of.{{0,10}}{_P}",
    ],
    "soft_on_crime": [
        rf"{_P}.{{0,20}}(?:seeking|asking for|offering).{{0,20}}(?:lenient|light|easy).{{0,10}}(?:sentence|punishment|deal)",
        rf"{_P}.{{0,10}}plea deal.{{0,10}}too (?:soft|lenient|easy)",
        rf"{_P}.{{0,20}}going easy on.{{0,10}}criminal",
    ],
    "case_dismissal": [
        rf"{_P}.{{0,20}}(?:dismiss\w*|dropping|declin\w*|refus\w* to).{{0,10}}(?:case|charge|prosecution)",
        rf"{_P}.{{0,20}}refuses?\s+to\s+prosecute",
    ],
    "recall": [
        rf"recall.{{0,20}}{_P}",
        rf"{_P}.{{0,20}}recall",
        rf"remove.{{0,20}}{_P}.{{0,20}}from office",
        rf"{_P}.{{0,10}}recall.{{0,10}}(?:election|effort|petition|campaign|movement)",
    ],
    "public_safety_failure": [
        rf"{_P}.{{0,30}}(?:failed|failing|bungled|mismanaged)",
        rf"public safety.{{0,20}}(?:crisis|failure|deteriorat\w*).{{0,20}}{_P}",
        rf"{_P}.{{0,20}}(?:endanger|jeopardiz|risk).{{0,20}}(?:public|safety|resident)",
    ],
}

# ── Method 2: Relationship-Based Patterns ─────────────────────────────────
# Causal structures with wider proximity (.{0,50}). Ported from RMD lines 236-244.

RELATIONSHIP_PATTERNS: dict[str, str] = {
    "prosecutor_causing_crime": rf"{_P}.{{0,50}}(?:causing|responsible\s+for|blamed\s+for|fault).{{0,50}}(?:crime|violence|increase)",
    "prosecutor_not_prosecuting": rf"{_P}.{{0,50}}(?:won'?\s*t|refuses?\s+to|declining\s+to|fail\w*\s+to).{{0,50}}(?:prosecute|charge|file)",
    "prosecutor_releasing": rf"{_P}.{{0,50}}(?:releasing|letting\s+out|freeing|empty\w*).{{0,50}}(?:criminals?|defendants?|inmates?|jail)",
    "victims_vs_prosecutor": rf"(?:victims?|survivors?).{{0,50}}(?:angry\s+at|frustrated\s+with|abandoned\s+by|ignored\s+by).{{0,50}}{_P}",
    "police_vs_prosecutor": rf"(?:police|officers?|cops?).{{0,50}}(?:frustrated\s+with|blame|criticize|angry\s+at).{{0,50}}{_P}",
    "prosecutor_soft": rf"(?:soft.{{0,20}}crime).{{0,50}}{_P}|{_P}.{{0,50}}(?:soft.{{0,20}}crime|lenient|weak\s+on\s+crime)",
    "recall_prosecutor": rf"recall.{{0,50}}{_P}|{_P}.{{0,50}}recall",
}

# Map relationship patterns → canonical theme names
RELATIONSHIP_TO_THEME: dict[str, str] = {
    "prosecutor_causing_crime": "crime_rising",
    "prosecutor_not_prosecuting": "case_dismissal",
    "prosecutor_releasing": "releasing_criminals",
    "victims_vs_prosecutor": "victim_neglect",
    "police_vs_prosecutor": "police_conflict",
    "prosecutor_soft": "soft_on_crime",
    "recall_prosecutor": "recall",
}

# ── Method 3: Targeted Criticism Patterns ─────────────────────────────────
# High-confidence criticism patterns. Ported from RMD lines 325-331.

CRITICISM_PATTERNS: dict[str, str] = {
    "blame": rf"{_P}.{{0,30}}(?:blamed|fault|responsible for|causing)",
    "soft_on_crime": rf"(?:soft.{{0,10}}crime|lenient|pro-criminal).{{0,30}}{_P}",
    "failure": rf"{_P}.{{0,30}}(?:failed|failing|bungled|mismanaged)",
    "revolving_door": rf"(?:revolving door|repeat offender|released.{{0,20}}bail).{{0,50}}{_P}",
    "dismissing": rf"{_P}.{{0,30}}(?:dismiss\w*|drop\w*|refuse.{{0,10}}prosecut)",
}

# Map criticism patterns → canonical theme names
CRITICISM_TO_THEME: dict[str, str] = {
    "blame": "crime_rising",
    "soft_on_crime": "soft_on_crime",
    "failure": "public_safety_failure",
    "revolving_door": "releasing_criminals",
    "dismissing": "case_dismissal",
}

# ── Method 4: Co-occurrence keywords ──────────────────────────────────────
COOCCURRENCE_PROSECUTOR_RE = re.compile(
    r"\b(?:district\s+attorney|da|prosecutor|d\.a\.)\b", re.IGNORECASE
)
COOCCURRENCE_CRITICISM_RE = re.compile(
    r"\b(?:crime|victim|recall|soft|lenient|release|dismiss|violence|unsafe|failing)\b",
    re.IGNORECASE,
)

# Co-occurrence keyword → theme mapping
COOCCURRENCE_TO_THEME: dict[str, str] = {
    "crime": "crime_rising",
    "violence": "crime_rising",
    "victim": "victim_neglect",
    "recall": "recall",
    "soft": "soft_on_crime",
    "lenient": "soft_on_crime",
    "release": "releasing_criminals",
    "dismiss": "case_dismissal",
    "unsafe": "public_safety_failure",
    "failing": "public_safety_failure",
}

# All 9 canonical theme names
THEME_NAMES = [
    "crime_rising", "releasing_criminals", "victim_neglect", "police_conflict",
    "office_dysfunction", "soft_on_crime", "case_dismissal", "recall",
    "public_safety_failure",
]

# Method weights (same as RMD)
WEIGHTS = {"dictionary": 0.30, "regex": 0.35, "criticism": 0.15, "cooccurrence": 0.20}


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def build_prosecutor_alternation(prosecutor_name: str) -> str:
    """Build a regex alternation matching generic DA terms + specific prosecutor name variants.

    Returns the raw alternation string (not compiled), suitable for substituting into
    pattern templates in place of _P.
    """
    p = next((p for p in PROSECUTORS if p.name == prosecutor_name), None)
    if p is None:
        return _P

    terms = ["da", r"district\s+attorney", "prosecutor", r"d\.a\."]
    for v in p.name_variants:
        terms.append(re.escape(v))
    terms.append(re.escape(p.name))
    # Sort longest first to prevent partial matches
    terms.sort(key=len, reverse=True)
    # Word-boundary lookarounds: without them bare "da" matched inside
    # "day"/"data"/"agenda" and short name variants inside longer words.
    return r"(?<!\w)(?:" + "|".join(terms) + r")(?!\w)"


# Cache compiled patterns per prosecutor
_PATTERN_CACHE: dict[str, dict] = {}


def get_compiled_patterns(prosecutor_name: str) -> dict:
    """Get or build cached compiled patterns for a given prosecutor."""
    if prosecutor_name in _PATTERN_CACHE:
        return _PATTERN_CACHE[prosecutor_name]

    p_alt = build_prosecutor_alternation(prosecutor_name)

    # Replace the generic _P placeholder with prosecutor-specific alternation
    def sub_p(pattern: str) -> re.Pattern:
        # Replace the _P token in the pattern string
        replaced = pattern.replace(_P, p_alt)
        return re.compile(replaced, re.IGNORECASE)

    compiled = {
        "contextual": {
            theme: [sub_p(pat) for pat in pats]
            for theme, pats in CONTEXTUAL_THEME_PATTERNS.items()
        },
        "relationship": {
            name: sub_p(pat) for name, pat in RELATIONSHIP_PATTERNS.items()
        },
        "criticism": {
            name: sub_p(pat) for name, pat in CRITICISM_PATTERNS.items()
        },
    }

    _PATTERN_CACHE[prosecutor_name] = compiled
    return compiled


def pattern_hit(
    body: str, pat: re.Pattern, quote_spans: list[tuple[int, int]]
) -> tuple[bool, bool]:
    """Scan all matches of pat in body, skipping negated ones.

    Returns (found, found_outside_quotes). A match inside quoted speech counts
    toward `found` but not `found_outside_quotes` — the no-quote variant
    separates the outlet's own voice from language it merely quotes.
    """
    found = False
    for m in pat.finditer(body):
        if is_negated(body, m.start(), NEGATION_WORDS):
            continue
        found = True
        if not pos_in_spans(m.start(), quote_spans):
            return True, True
    return found, False


# ═══════════════════════════════════════════════════════════════════════════
# METHOD 1: Context-Aware Dictionary Detection
# ═══════════════════════════════════════════════════════════════════════════

def method_1_contextual_dictionary(df: pd.DataFrame) -> pd.DataFrame:
    """Detect themes using compound regex requiring prosecutor + theme co-occurrence.

    Returns DataFrame with columns: ta_dict_score, ta_dict_themes, ta_dict_{theme} flags.
    """
    logger.info("Method 1: Context-aware dictionary detection")
    results = []

    for _, row in tqdm(df.iterrows(), total=len(df), desc="Method 1"):
        prosecutor = row["primary_prosecutor"]
        if pd.isna(prosecutor):
            results.append({
                "ta_dict_score": 0, "ta_dict_score_noquote": 0, "ta_dict_themes": "",
            })
            continue

        body = row["body"].lower() if isinstance(row["body"], str) else ""
        quote_spans = find_quote_spans(body)
        compiled = get_compiled_patterns(prosecutor)
        themes_found = []
        themes_found_noquote = []

        for theme_name, patterns in compiled["contextual"].items():
            found = False
            found_nq = False
            for pat in patterns:
                hit, hit_nq = pattern_hit(body, pat, quote_spans)
                found = found or hit
                found_nq = found_nq or hit_nq
                if found_nq:
                    break
            if found:
                themes_found.append(theme_name)
            if found_nq:
                themes_found_noquote.append(theme_name)

        result = {
            "ta_dict_score": min(len(themes_found) * 5, 25),
            "ta_dict_score_noquote": min(len(themes_found_noquote) * 5, 25),
            "ta_dict_themes": ", ".join(themes_found),
        }
        for t in THEME_NAMES:
            result[f"ta_dict_{t}"] = t in themes_found
        results.append(result)

    return pd.DataFrame(results, index=df.index)


# ═══════════════════════════════════════════════════════════════════════════
# METHOD 2: Relationship-Based Regex
# ═══════════════════════════════════════════════════════════════════════════

def method_2_relationship_regex(df: pd.DataFrame) -> pd.DataFrame:
    """Detect causal relationship patterns between prosecutors and outcomes.

    Returns DataFrame with columns: ta_regex_score, ta_regex_themes, ta_regex_{theme} flags.
    """
    logger.info("Method 2: Relationship-based regex patterns")
    results = []

    for _, row in tqdm(df.iterrows(), total=len(df), desc="Method 2"):
        prosecutor = row["primary_prosecutor"]
        if pd.isna(prosecutor):
            results.append({
                "ta_regex_score": 0, "ta_regex_score_noquote": 0, "ta_regex_themes": "",
            })
            continue

        body = row["body"].lower() if isinstance(row["body"], str) else ""
        quote_spans = find_quote_spans(body)
        compiled = get_compiled_patterns(prosecutor)
        themes_found = set()
        patterns_matched = []
        patterns_matched_noquote = []

        for pat_name, pat in compiled["relationship"].items():
            hit, hit_nq = pattern_hit(body, pat, quote_spans)
            if hit:
                patterns_matched.append(pat_name)
                theme = RELATIONSHIP_TO_THEME.get(pat_name)
                if theme:
                    themes_found.add(theme)
            if hit_nq:
                patterns_matched_noquote.append(pat_name)

        result = {
            "ta_regex_score": min(len(patterns_matched) * 5, 25),
            "ta_regex_score_noquote": min(len(patterns_matched_noquote) * 5, 25),
            "ta_regex_themes": ", ".join(sorted(themes_found)),
        }
        for t in THEME_NAMES:
            result[f"ta_regex_{t}"] = t in themes_found
        results.append(result)

    return pd.DataFrame(results, index=df.index)


# ═══════════════════════════════════════════════════════════════════════════
# METHOD 3: Targeted Criticism Detection
# ═══════════════════════════════════════════════════════════════════════════

def method_3_criticism(df: pd.DataFrame) -> pd.DataFrame:
    """Detect high-confidence criticism patterns linking blame to prosecutors.

    Returns DataFrame with columns: ta_crit_score, ta_crit_themes, ta_crit_{theme} flags.
    """
    logger.info("Method 3: Targeted criticism detection")
    results = []

    for _, row in tqdm(df.iterrows(), total=len(df), desc="Method 3"):
        prosecutor = row["primary_prosecutor"]
        if pd.isna(prosecutor):
            results.append({
                "ta_crit_score": 0, "ta_crit_score_noquote": 0, "ta_crit_themes": "",
            })
            continue

        body = row["body"].lower() if isinstance(row["body"], str) else ""
        quote_spans = find_quote_spans(body)
        compiled = get_compiled_patterns(prosecutor)
        themes_found = set()
        patterns_matched = []
        patterns_matched_noquote = []

        for pat_name, pat in compiled["criticism"].items():
            hit, hit_nq = pattern_hit(body, pat, quote_spans)
            if hit:
                patterns_matched.append(pat_name)
                theme = CRITICISM_TO_THEME.get(pat_name)
                if theme:
                    themes_found.add(theme)
            if hit_nq:
                patterns_matched_noquote.append(pat_name)

        result = {
            "ta_crit_score": min(len(patterns_matched) * 5, 25),
            "ta_crit_score_noquote": min(len(patterns_matched_noquote) * 5, 25),
            "ta_crit_themes": ", ".join(sorted(themes_found)),
        }
        for t in THEME_NAMES:
            result[f"ta_crit_{t}"] = t in themes_found
        results.append(result)

    return pd.DataFrame(results, index=df.index)


# ═══════════════════════════════════════════════════════════════════════════
# METHOD 4: Sentence-Level Co-occurrence
# ═══════════════════════════════════════════════════════════════════════════

def method_4_cooccurrence(df: pd.DataFrame) -> pd.DataFrame:
    """Detect sentences where both prosecutor references and criticism keywords appear.

    Returns DataFrame with columns: ta_cooc_score, ta_cooc_themes, ta_cooc_count, ta_cooc_{theme} flags.
    """
    logger.info("Method 4: Sentence-level co-occurrence")
    results = []

    for _, row in tqdm(df.iterrows(), total=len(df), desc="Method 4"):
        prosecutor = row["primary_prosecutor"]
        body = row["body"] if isinstance(row["body"], str) else ""

        if pd.isna(prosecutor) or not body:
            results.append({
                "ta_cooc_score": 0, "ta_cooc_score_noquote": 0,
                "ta_cooc_themes": "", "ta_cooc_count": 0,
            })
            continue

        # Also match prosecutor's name variants at sentence level
        p = next((p for p in PROSECUTORS if p.name == prosecutor), None)
        extra_terms = []
        if p:
            extra_terms = [
                r"(?<!\w)" + re.escape(v) + r"(?!\w)" for v in p.name_variants
            ] + [r"(?<!\w)" + re.escape(p.name) + r"(?!\w)"]

        sentences = split_sentences(body)
        cooc_count = 0
        cooc_count_noquote = 0
        themes_found = set()

        for sent in sentences:
            sent_lower = sent.lower()
            # Check for prosecutor mention
            has_prosecutor = bool(COOCCURRENCE_PROSECUTOR_RE.search(sent_lower))
            if not has_prosecutor and extra_terms:
                for term in extra_terms:
                    if re.search(term, sent_lower, re.IGNORECASE):
                        has_prosecutor = True
                        break

            if not has_prosecutor:
                continue

            # Check for criticism keywords. Quote detection is per-sentence
            # here (offsets into the full body are lost by the splitter), so
            # multi-sentence quotes are only partially masked — conservative.
            sent_quote_spans = find_quote_spans(sent_lower)
            for m in COOCCURRENCE_CRITICISM_RE.finditer(sent_lower):
                keyword = m.group().lower()
                theme = COOCCURRENCE_TO_THEME.get(keyword)
                if theme:
                    themes_found.add(theme)
                    cooc_count += 1
                    if not pos_in_spans(m.start(), sent_quote_spans):
                        cooc_count_noquote += 1

        result = {
            "ta_cooc_score": min((cooc_count / 5) * 25, 25),
            "ta_cooc_score_noquote": min((cooc_count_noquote / 5) * 25, 25),
            "ta_cooc_themes": ", ".join(sorted(themes_found)),
            "ta_cooc_count": cooc_count,
        }
        for t in THEME_NAMES:
            result[f"ta_cooc_{t}"] = t in themes_found
        results.append(result)

    return pd.DataFrame(results, index=df.index)


# ═══════════════════════════════════════════════════════════════════════════
# MULTI-METHOD VALIDATION AND SCORING
# ═══════════════════════════════════════════════════════════════════════════

def compute_validated_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Combine four method scores with multi-method validation.

    Adds columns: ta_composite_score, ta_methods_detected, ta_confidence,
                  ta_theme_{name} (union across methods), ta_any_theme.
    """
    logger.info("Computing validated composite scores")

    def composite_from(suffix: str) -> tuple[pd.Series, pd.Series]:
        base = (
            df[f"ta_dict_score{suffix}"] * WEIGHTS["dictionary"]
            + df[f"ta_regex_score{suffix}"] * WEIGHTS["regex"]
            + df[f"ta_crit_score{suffix}"] * WEIGHTS["criticism"]
            + df[f"ta_cooc_score{suffix}"] * WEIGHTS["cooccurrence"]
        )
        n_detected = (
            (df[f"ta_dict_score{suffix}"] > 0).astype(int)
            + (df[f"ta_regex_score{suffix}"] > 0).astype(int)
            + (df[f"ta_crit_score{suffix}"] > 0).astype(int)
            + (df[f"ta_cooc_score{suffix}"] > 0).astype(int)
        )
        conditions = [n_detected < 2, n_detected == 2, n_detected >= 3]
        choices = [
            base.clip(upper=15),   # cap single-method
            base * 1.1,            # medium confidence
            base * 1.25,           # high confidence
        ]
        composite = pd.Series(
            np.select(conditions, choices, default=0.0), index=df.index
        ).clip(upper=100).round(2)
        return composite, n_detected

    df["ta_base_score"] = (
        df["ta_dict_score"] * WEIGHTS["dictionary"]
        + df["ta_regex_score"] * WEIGHTS["regex"]
        + df["ta_crit_score"] * WEIGHTS["criticism"]
        + df["ta_cooc_score"] * WEIGHTS["cooccurrence"]
    )
    df["ta_composite_score"], df["ta_methods_detected"] = composite_from("")
    # Quote-masked variant: matches inside quoted speech are excluded, so this
    # score reflects the outlet's own voice rather than quoted sources.
    df["ta_composite_score_noquote"], _ = composite_from("_noquote")

    # Confidence labels
    conditions = [
        df["ta_methods_detected"] < 2,
        df["ta_methods_detected"] == 2,
        df["ta_methods_detected"] >= 3,
    ]
    df["ta_confidence"] = np.select(
        conditions,
        ["Low", "Medium", "High"],
        default="None",
    )

    # Union theme flags across all methods
    for theme in THEME_NAMES:
        dict_col = f"ta_dict_{theme}"
        regex_col = f"ta_regex_{theme}"
        crit_col = f"ta_crit_{theme}"
        cooc_col = f"ta_cooc_{theme}"
        df[f"ta_theme_{theme}"] = (
            df[dict_col].astype(bool) if dict_col in df.columns else False
        ) | (
            df[regex_col].astype(bool) if regex_col in df.columns else False
        ) | (
            df[crit_col].astype(bool) if crit_col in df.columns else False
        ) | (
            df[cooc_col].astype(bool) if cooc_col in df.columns else False
        )

    # Any theme detected
    df["ta_any_theme"] = df[[f"ta_theme_{t}" for t in THEME_NAMES]].any(axis=1)

    return df


# ═══════════════════════════════════════════════════════════════════════════
# STATISTICAL ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def cohens_d(g1: np.ndarray, g2: np.ndarray) -> float:
    """Cohen's d with pooled standard deviation."""
    n1, n2 = len(g1), len(g2)
    var1, var2 = np.var(g1, ddof=1), np.var(g2, ddof=1)
    pooled = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    if pooled == 0:
        return 0.0
    return float((np.mean(g1) - np.mean(g2)) / pooled)


def bootstrap_diff_ci(
    g1: np.ndarray, g2: np.ndarray,
    n_boot: int = 10000, ci: float = 0.95, seed: int = 42,
) -> tuple[float, float, float]:
    """Bootstrap CI for mean difference."""
    rng = np.random.default_rng(seed)
    observed = float(np.mean(g1) - np.mean(g2))
    diffs = []
    for _ in range(n_boot):
        s1 = rng.choice(g1, size=len(g1), replace=True)
        s2 = rng.choice(g2, size=len(g2), replace=True)
        diffs.append(np.mean(s1) - np.mean(s2))
    alpha = (1 - ci) / 2
    return observed, float(np.percentile(diffs, 100 * alpha)), float(np.percentile(diffs, 100 * (1 - alpha)))


def run_statistics(df: pd.DataFrame) -> dict:
    """Run all statistical comparisons and return structured results."""
    logger.info("\n" + "=" * 70)
    logger.info("STATISTICAL ANALYSIS: Prosecutor-Attributed Theme Detection")
    logger.info("=" * 70)

    results = {}

    # Filter to articles with a primary prosecutor
    adf = df[df["primary_prosecutor"].notna()].copy()
    prog = adf[adf["prosecutor_type"] == "Progressive"]
    trad = adf[adf["prosecutor_type"] == "Traditional"]

    # ── 1. Overall composite score comparison ─────────────────────────
    logger.info("\n── Overall Composite Score ──")
    g_prog = prog["ta_composite_score"].values
    g_trad = trad["ta_composite_score"].values

    t_stat, p_ttest = ttest_ind(g_prog, g_trad, equal_var=False)
    u_stat, p_mann = mannwhitneyu(g_prog, g_trad, alternative="two-sided")
    d = cohens_d(g_prog, g_trad)
    diff, lo, hi = bootstrap_diff_ci(g_prog, g_trad)

    logger.info(f"  Progressive: n={len(g_prog)}, mean={np.mean(g_prog):.4f}, sd={np.std(g_prog, ddof=1):.4f}")
    logger.info(f"  Traditional: n={len(g_trad)}, mean={np.mean(g_trad):.4f}, sd={np.std(g_trad, ddof=1):.4f}")
    logger.info(f"  Welch's t={t_stat:.4f}, p={p_ttest:.6e}")
    logger.info(f"  Mann-Whitney U={u_stat:.0f}, p={p_mann:.6e}")
    logger.info(f"  Cohen's d={d:.4f}")
    logger.info(f"  Bootstrap 95% CI for diff: {diff:.4f} [{lo:.4f}, {hi:.4f}]")

    results["overall"] = {
        "progressive_n": len(g_prog),
        "progressive_mean": float(np.mean(g_prog)),
        "progressive_sd": float(np.std(g_prog, ddof=1)),
        "traditional_n": len(g_trad),
        "traditional_mean": float(np.mean(g_trad)),
        "traditional_sd": float(np.std(g_trad, ddof=1)),
        "welch_t": float(t_stat),
        "welch_p": float(p_ttest),
        "mannwhitney_u": float(u_stat),
        "mannwhitney_p": float(p_mann),
        "cohens_d": d,
        "bootstrap_diff": diff,
        "bootstrap_ci_lower": lo,
        "bootstrap_ci_upper": hi,
    }

    # ── 1b. Quote-masked sensitivity ──────────────────────────────────
    if "ta_composite_score_noquote" in adf.columns:
        logger.info("\n── Quote-Masked Composite (outlet voice only) ──")
        gq_prog = prog["ta_composite_score_noquote"].values
        gq_trad = trad["ta_composite_score_noquote"].values
        tq, pq = ttest_ind(gq_prog, gq_trad, equal_var=False)
        dq = cohens_d(gq_prog, gq_trad)
        diff_q, lo_q, hi_q = bootstrap_diff_ci(gq_prog, gq_trad)
        logger.info(
            f"  Progressive mean={np.mean(gq_prog):.4f}, "
            f"Traditional mean={np.mean(gq_trad):.4f}, d={dq:.4f}, p={pq:.4e}"
        )
        results["overall_noquote"] = {
            "progressive_mean": float(np.mean(gq_prog)),
            "traditional_mean": float(np.mean(gq_trad)),
            "welch_t": float(tq),
            "welch_p": float(pq),
            "cohens_d": dq,
            "bootstrap_diff": diff_q,
            "bootstrap_ci_lower": lo_q,
            "bootstrap_ci_upper": hi_q,
            "note": (
                "Theme matches inside quoted speech excluded; compares the "
                "outlet's own voice across prosecutor types."
            ),
        }

    # ── 2. Theme presence rate: any theme ─────────────────────────────
    logger.info("\n── Theme Presence ──")
    prog_any = prog["ta_any_theme"].mean()
    trad_any = trad["ta_any_theme"].mean()
    logger.info(f"  Progressive with ≥1 theme: {100 * prog_any:.1f}%")
    logger.info(f"  Traditional with ≥1 theme: {100 * trad_any:.1f}%")

    results["theme_presence"] = {
        "progressive_any_theme_pct": float(prog_any),
        "traditional_any_theme_pct": float(trad_any),
    }

    # ── 3. Per-theme chi-square tests ─────────────────────────────────
    logger.info("\n── Per-Theme Differential (Chi-Square) ──")
    per_theme = {}
    for theme in THEME_NAMES:
        col = f"ta_theme_{theme}"
        prog_present = int(prog[col].sum())
        prog_absent = len(prog) - prog_present
        trad_present = int(trad[col].sum())
        trad_absent = len(trad) - trad_present

        ct = np.array([[prog_present, prog_absent], [trad_present, trad_absent]])

        prog_rate = prog_present / len(prog) if len(prog) > 0 else 0
        trad_rate = trad_present / len(trad) if len(trad) > 0 else 0
        risk_ratio = (prog_rate / trad_rate) if trad_rate > 0 else float("inf")

        # Chi-square (only if expected counts are sufficient)
        total = ct.sum()
        if total > 0 and ct.min() >= 0:
            try:
                chi2, p_chi, dof, expected = chi2_contingency(ct, correction=True)
                cramers_v = float(np.sqrt(chi2 / total)) if total > 0 else 0
            except ValueError:
                chi2, p_chi, dof, cramers_v = 0, 1.0, 1, 0
        else:
            chi2, p_chi, dof, cramers_v = 0, 1.0, 1, 0

        sig = "***" if p_chi < 0.001 else "**" if p_chi < 0.01 else "*" if p_chi < 0.05 else ""
        logger.info(
            f"  {theme:25s}: Prog={100 * prog_rate:5.1f}%  Trad={100 * trad_rate:5.1f}%  "
            f"RR={risk_ratio:5.2f}  χ²={chi2:7.1f}  p={p_chi:.4e}  V={cramers_v:.3f} {sig}"
        )

        per_theme[theme] = {
            "progressive_n": prog_present,
            "progressive_rate": float(prog_rate),
            "traditional_n": trad_present,
            "traditional_rate": float(trad_rate),
            "risk_ratio": float(risk_ratio),
            "chi2": float(chi2),
            "p_value": float(p_chi),
            "cramers_v": cramers_v,
        }

    # Benjamini-Hochberg adjustment across the 9 per-theme tests (one family)
    theme_keys = list(per_theme)
    pvals = np.asarray([per_theme[t]["p_value"] for t in theme_keys], dtype=float)
    order = np.argsort(pvals)
    ranked = pvals[order] * len(pvals) / (np.arange(len(pvals)) + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1]
    adjusted = np.empty(len(pvals))
    adjusted[order] = np.clip(adj, 0, 1)
    for t, p_adj in zip(theme_keys, adjusted):
        per_theme[t]["p_value_bh"] = float(p_adj)

    results["per_theme"] = per_theme

    # ── 4. Paired county comparisons ──────────────────────────────────
    logger.info("\n── Paired County Comparisons ──")
    pairs = [
        ("Chesa Boudin", "Brooke Jenkins", "San Francisco"),
        ("Pamela Price", "Nancy O'Malley", "Alameda"),
    ]
    paired = {}
    for prog_name, trad_name, county in pairs:
        g1 = adf.loc[adf["primary_prosecutor"] == prog_name, "ta_composite_score"].values
        g2 = adf.loc[adf["primary_prosecutor"] == trad_name, "ta_composite_score"].values

        if len(g1) < 5 or len(g2) < 5:
            logger.warning(f"  {county}: insufficient data ({prog_name}={len(g1)}, {trad_name}={len(g2)})")
            continue

        t_s, p_v = ttest_ind(g1, g2, equal_var=False)
        d_val = cohens_d(g1, g2)
        diff_v, lo_v, hi_v = bootstrap_diff_ci(g1, g2)

        # Per-theme breakdown for this pair
        theme_rates = {}
        for theme in THEME_NAMES:
            col = f"ta_theme_{theme}"
            r1 = adf.loc[adf["primary_prosecutor"] == prog_name, col].mean()
            r2 = adf.loc[adf["primary_prosecutor"] == trad_name, col].mean()
            theme_rates[theme] = {"progressive_rate": float(r1), "traditional_rate": float(r2)}

        logger.info(f"  {county}: {prog_name} mean={np.mean(g1):.4f} vs {trad_name} mean={np.mean(g2):.4f}")
        logger.info(f"    t={t_s:.4f}, p={p_v:.6f}, d={d_val:.4f}, CI=[{lo_v:.4f}, {hi_v:.4f}]")

        paired[county] = {
            "progressive": prog_name,
            "traditional": trad_name,
            "n_prog": len(g1),
            "n_trad": len(g2),
            "mean_prog": float(np.mean(g1)),
            "mean_trad": float(np.mean(g2)),
            "welch_t": float(t_s),
            "welch_p": float(p_v),
            "cohens_d": d_val,
            "bootstrap_diff": diff_v,
            "bootstrap_ci_lower": lo_v,
            "bootstrap_ci_upper": hi_v,
            "per_theme_rates": theme_rates,
        }

    results["paired_county"] = paired

    # ── 5. Per-prosecutor breakdown ───────────────────────────────────
    logger.info("\n── Per-Prosecutor Summary ──")
    per_prosecutor = {}
    for p in PROSECUTORS:
        subset = adf[adf["primary_prosecutor"] == p.name]
        if len(subset) == 0:
            continue
        mean_score = float(subset["ta_composite_score"].mean())
        any_theme_pct = float(subset["ta_any_theme"].mean())
        theme_rates = {}
        for theme in THEME_NAMES:
            theme_rates[theme] = float(subset[f"ta_theme_{theme}"].mean())

        logger.info(f"  {p.name:20s} ({p.ideology:12s}): n={len(subset):5d}, "
                     f"mean_score={mean_score:.3f}, any_theme={100 * any_theme_pct:.1f}%")

        per_prosecutor[p.name] = {
            "ideology": p.ideology,
            "county": p.county,
            "n": len(subset),
            "mean_score": mean_score,
            "any_theme_pct": any_theme_pct,
            "theme_rates": theme_rates,
        }

    results["per_prosecutor"] = per_prosecutor

    # ── 6. Method agreement analysis ──────────────────────────────────
    logger.info("\n── Method Agreement ──")
    for n_methods in range(5):
        count = int((adf["ta_methods_detected"] == n_methods).sum())
        pct = 100 * count / len(adf) if len(adf) > 0 else 0
        logger.info(f"  {n_methods} methods detected: {count:6d} ({pct:.1f}%)")

    # Among articles with score > 0, how many have 2+ methods?
    scored = adf[adf["ta_composite_score"] > 0]
    multi_method = scored[scored["ta_methods_detected"] >= 2]
    logger.info(f"\n  Articles with score > 0: {len(scored)}")
    logger.info(f"  Of those, 2+ methods agree: {len(multi_method)} ({100 * len(multi_method) / max(len(scored), 1):.1f}%)")

    results["method_agreement"] = {
        "distribution": {
            str(n): int((adf["ta_methods_detected"] == n).sum()) for n in range(5)
        },
        "scored_articles": len(scored),
        "multi_method_articles": len(multi_method),
        "multi_method_pct": float(len(multi_method) / max(len(scored), 1)),
    }

    # ── 7. Per-method breakdown ───────────────────────────────────────
    logger.info("\n── Per-Method Detection Rates ──")
    method_scores = {
        "dictionary": "ta_dict_score",
        "regex": "ta_regex_score",
        "criticism": "ta_crit_score",
        "cooccurrence": "ta_cooc_score",
    }
    per_method = {}
    for method_name, col in method_scores.items():
        detected = int((adf[col] > 0).sum())
        pct = 100 * detected / len(adf) if len(adf) > 0 else 0
        logger.info(f"  {method_name:15s}: {detected:6d} articles ({pct:.1f}%)")
        per_method[method_name] = {"detected": detected, "pct": float(pct / 100)}

    results["per_method"] = per_method

    return results


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(description="Prosecutor-attributed theme detection")
    parser.add_argument(
        "--sample", type=int, default=0,
        help="Process a random sample of N articles (0 = all)",
    )
    args = parser.parse_args()

    # Load data
    df = load_parquet(ATTRIBUTED_PARQUET)
    logger.info(f"Loaded {len(df):,} prosecutor-attributed articles")

    if args.sample > 0:
        df = df.sample(n=min(args.sample, len(df)), random_state=42)
        logger.info(f"Sampled {len(df):,} articles for testing")

    # ── Run four methods ──────────────────────────────────────────────
    with timer("Method 1: Contextual dictionary"):
        m1 = method_1_contextual_dictionary(df)

    with timer("Method 2: Relationship regex"):
        m2 = method_2_relationship_regex(df)

    with timer("Method 3: Targeted criticism"):
        m3 = method_3_criticism(df)

    with timer("Method 4: Sentence co-occurrence"):
        m4 = method_4_cooccurrence(df)

    # Merge method results
    for m_df in [m1, m2, m3, m4]:
        for col in m_df.columns:
            df[col] = m_df[col].values

    # ── Multi-method validation ───────────────────────────────────────
    with timer("Multi-method validation"):
        df = compute_validated_scores(df)

    # ── Statistics ────────────────────────────────────────────────────
    with timer("Statistical analysis"):
        stats_results = run_statistics(df)

    # ── Save outputs ──────────────────────────────────────────────────
    # Select output columns (original + ta_ columns)
    ta_cols = [c for c in df.columns if c.startswith("ta_")]
    keep_cols = ["article_id", "primary_prosecutor", "prosecutor_type", "date",
                 "publication", "title"] + ta_cols
    # Only keep columns that exist
    keep_cols = [c for c in keep_cols if c in df.columns]
    output_df = df[keep_cols].copy()

    save_parquet(output_df, THEME_ATTR_PARQUET)
    logger.info(f"Saved {len(output_df):,} articles to {THEME_ATTR_PARQUET.name}")

    with open(THEME_STATS_JSON, "w") as f:
        json.dump(stats_results, f, indent=2, default=str)
    logger.info(f"Saved statistics to {THEME_STATS_JSON.name}")

    # ── Quick summary ─────────────────────────────────────────────────
    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)
    overall = stats_results.get("overall", {})
    logger.info(f"Progressive mean score: {overall.get('progressive_mean', 0):.4f}")
    logger.info(f"Traditional mean score: {overall.get('traditional_mean', 0):.4f}")
    logger.info(f"Cohen's d: {overall.get('cohens_d', 0):.4f}")
    logger.info(f"p-value: {overall.get('welch_p', 1):.6e}")

    tp = stats_results.get("theme_presence", {})
    logger.info(f"\nProgressive with ≥1 theme: {100 * tp.get('progressive_any_theme_pct', 0):.1f}%")
    logger.info(f"Traditional with ≥1 theme: {100 * tp.get('traditional_any_theme_pct', 0):.1f}%")

    logger.info("\nDone.")


if __name__ == "__main__":
    main()
