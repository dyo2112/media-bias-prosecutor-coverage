"""Central configuration for the media bias analysis pipeline."""

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────
# Paths are derived from this file's location so the repository is portable.
# Outputs always live beside the code. The raw corpus is not redistributable
# and lives outside the repository; set MEDIA_BIAS_DATA_DIR to the directory
# holding it (defaults to the repository's parent).
REPO_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("MEDIA_BIAS_DATA_DIR", REPO_DIR.parent))
RAW_TSV = DATA_DIR / "24.07.29_complete_corpus_api_lexis_combined.tsv"
OUTPUT_DIR = REPO_DIR / "output"
FIGURES_DIR = OUTPUT_DIR / "figures"

# Intermediate files
CLEAN_PARQUET = OUTPUT_DIR / "01_clean.parquet"
RELEVANT_PARQUET = OUTPUT_DIR / "02_relevant.parquet"
ATTRIBUTED_PARQUET = OUTPUT_DIR / "03_attributed.parquet"
BIAS_PARQUET = OUTPUT_DIR / "04_bias_scores.parquet"
FRAMES_PARQUET = OUTPUT_DIR / "05_frames.parquet"
STATS_JSON = OUTPUT_DIR / "06_stats_results.json"
REGRESSION_CSV = OUTPUT_DIR / "06_regression_tables.csv"

# Step 08: langextract grounded extraction
EXTRACTIONS_JSONL = OUTPUT_DIR / "08_extractions.jsonl"
EXTRACTIONS_PARQUET = OUTPUT_DIR / "08_extractions_summary.parquet"
EXTRACTION_STATS_JSON = OUTPUT_DIR / "08_extraction_stats.json"
EXTRACTION_VIZ_HTML = OUTPUT_DIR / "08_visualization.html"

# Step 09: bias-focused langextract extraction
BIAS_EXTRACTIONS_JSONL = OUTPUT_DIR / "09_bias_extractions.jsonl"
BIAS_SUMMARY_PARQUET = OUTPUT_DIR / "09_bias_summary.parquet"
BIAS_STATS_JSON = OUTPUT_DIR / "09_bias_stats.json"

# Step 10: prosecutor-attributed theme detection
THEME_ATTR_PARQUET = OUTPUT_DIR / "10_theme_attribution.parquet"
THEME_STATS_JSON = OUTPUT_DIR / "10_theme_stats.json"

# Gemini model for langextract
GEMINI_MODEL = "gemini-2.5-flash"

# ── Model names ────────────────────────────────────────────────────────────
# Zero-shot classification (relevance filter + stance detection)
ZEROSHOT_MODEL = "facebook/bart-large-mnli"
# Lighter fallback — use same model since typeform/distilbart requires auth
ZEROSHOT_MODEL_LIGHT = "facebook/bart-large-mnli"

# Sentiment analysis
SENTIMENT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"

# ── Inference settings ─────────────────────────────────────────────────────
BATCH_SIZE = 16
MAX_TOKENS_RELEVANCE = 200   # words sent to relevance classifier (lede only)
MAX_TOKENS_SENTIMENT = 512   # tokens for sentiment model
RANDOM_SEED = 42

# ── Prosecutor metadata ───────────────────────────────────────────────────

@dataclass
class Prosecutor:
    name: str
    county: str
    ideology: str  # "Progressive" or "Traditional"
    start_date: date
    end_date: Optional[date]
    name_variants: list[str] = field(default_factory=list)


PROSECUTORS = [
    Prosecutor(
        name="Chesa Boudin",
        county="San Francisco",
        ideology="Progressive",
        start_date=date(2020, 1, 8),
        end_date=date(2022, 7, 7),
        name_variants=["boudin", "chesa boudin", "chesa"],
    ),
    Prosecutor(
        name="Brooke Jenkins",
        county="San Francisco",
        ideology="Traditional",
        start_date=date(2022, 7, 8),
        end_date=None,
        name_variants=["jenkins", "brooke jenkins"],
    ),
    Prosecutor(
        name="Nancy O'Malley",
        county="Alameda",
        ideology="Traditional",
        start_date=date(2009, 9, 8),
        end_date=date(2023, 1, 2),
        name_variants=["o'malley", "o\u2019malley", "omalley", "nancy o'malley",
                        "nancy o\u2019malley"],
    ),
    Prosecutor(
        name="Pamela Price",
        county="Alameda",
        ideology="Progressive",
        start_date=date(2023, 1, 3),
        end_date=None,
        name_variants=["pamela price"],
        # NOTE: bare "price" handled separately with disambiguation logic
    ),
    Prosecutor(
        name="Steve Wagstaffe",
        county="San Mateo",
        ideology="Traditional",
        start_date=date(2010, 4, 12),
        end_date=None,
        name_variants=["wagstaffe", "steve wagstaffe"],
    ),
]

# Lookup helpers
PROSECUTOR_BY_NAME = {p.name: p for p in PROSECUTORS}
COUNTIES = sorted(set(p.county for p in PROSECUTORS))

# ── Publication-to-county mapping ──────────────────────────────────────────
# Maps publication domain substrings to primary county.
# Articles may cover multiple counties; this captures the editorial home base.
PUBLICATION_COUNTY: dict[str, str] = {
    # San Francisco focused
    "sfgate.com": "San Francisco",
    "san francisco chronicle": "San Francisco",
    "sfexaminer.com": "San Francisco",
    "sfstandard.com": "San Francisco",
    "sfist.com": "San Francisco",
    "missionlocal.org": "San Francisco",
    "kron4.com": "San Francisco",
    "sanfrancisco.cbslocal.com": "San Francisco",
    "nbcbayarea.com": "San Francisco",  # Bay Area wide, HQ in SF
    "abc7news.com": "San Francisco",    # Bay Area wide, HQ in SF
    "kqed.org": "San Francisco",        # Bay Area wide, HQ in SF
    "sfbayview.com": "San Francisco",
    "ktvu.com": "San Francisco",        # Bay Area wide, HQ in Oakland/SF
    # Alameda focused
    "oaklandside.org": "Alameda",
    "berkeleyside.org": "Alameda",
    "east bay times": "Alameda",
    "alamedapost.com": "Alameda",
    "independentnews.com": "Alameda",   # Livermore Independent
    # San Mateo focused
    "san mateo daily journal": "San Mateo",
    # National / multi-region (no county assignment)
    # "nytimes.com" and "politico.com" are intentionally excluded
}

# ── Crime/Justice keywords for pre-filtering ──────────────────────────────
CRIME_JUSTICE_KEYWORDS = [
    # Crime types
    "murder", "homicide", "manslaughter", "assault", "robbery", "burglary",
    "theft", "larceny", "arson", "carjacking", "shooting", "stabbing",
    "rape", "sexual assault", "domestic violence", "kidnapping", "fraud",
    "drug trafficking", "fentanyl", "overdose", "gang",
    # Legal system
    "prosecutor", "district attorney", "da ", "d.a.", "arraignment",
    "indictment", "felony", "misdemeanor", "sentencing", "plea deal",
    "plea bargain", "conviction", "acquittal", "parole", "probation",
    "incarceration", "prison", "jail", "inmate", "bail",
    # Law enforcement
    "police", "officer", "detective", "arrest", "suspect", "crime",
    "criminal", "victim", "law enforcement", "investigation",
    # Reform-specific
    "reform prosecutor", "progressive prosecutor", "tough on crime",
    "soft on crime", "recall", "public safety", "recidivism",
    "diversion", "restorative justice",
]

# ── Anti-prosecutor theme dictionaries (from R code, enhanced) ────────────
# Used in Method C (enhanced keyword analysis) of 04_bias_detection.py.
# Keywords are matched within a 3-sentence window of a prosecutor mention.

THEME_KEYWORDS: dict[str, list[str]] = {
    "crime_rising": [
        "crime up", "crime rate", "rising crime", "surge in crime",
        "crime spike", "escalating crime", "crime wave", "soaring crime",
        "crime crisis", "crime explosion", "crime increase", "uptick in crime",
    ],
    "soft_on_crime": [
        "soft on crime", "lenient", "light sentence", "slap on wrist",
        "weak sentencing", "minimal punishment", "too easy on",
        "not tough enough", "coddling criminals",
    ],
    "releasing_criminals": [
        "revolving door", "back on street", "catch and release",
        "early release", "freeing criminals", "let out", "released",
        "no bail", "zero bail",
    ],
    "case_dismissal": [
        "dismissing cases", "case dropped", "charges dismissed",
        "refusing to prosecute", "declined to prosecute", "not prosecuting",
        "mass dismissals", "dropped charges",
    ],
    "victim_neglect": [
        "victim neglect", "ignoring victims", "forgotten victims",
        "abandoning victims", "victims overlooked", "victims left behind",
        "re-victimized",
    ],
    "police_conflict": [
        "police frustrated", "officers frustrated", "police morale",
        "police won't arrest", "no point in arresting", "cops frustrated",
        "police pushback", "law enforcement frustrated",
    ],
    "office_dysfunction": [
        "staff leaving", "exodus", "attorneys quit", "prosecutors resigning",
        "mass departures", "staffing crisis", "high turnover",
        "low morale", "office dysfunction",
    ],
    "recall": [
        "recall effort", "recall election", "recall petition",
        "recall campaign", "recall movement", "remove from office",
        "recalled",
    ],
    "public_safety_failure": [
        "public safety crisis", "unsafe", "dangerous streets",
        "residents fear", "people don't feel safe", "quality of life",
        "open air drug", "street conditions",
    ],
}

# Words that negate a keyword match within a 3-word window
NEGATION_WORDS = {
    "not", "no", "never", "isn't", "doesn't", "won't", "haven't",
    "didn't", "wasn't", "aren't", "none", "without", "hardly",
    "barely", "denies", "denied", "debunked", "false", "disproven",
    "refutes", "no evidence",
}
