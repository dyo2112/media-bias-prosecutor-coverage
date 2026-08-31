"""
Boudin salience pull for the Center talk (slide 13, idea #1: "when did this
become the story?").

Adapted from gdelt_data_pull.py -- the rate-limit handling (8s pacing,
unbounded exponential backoff on 429, legacy-TLS adapter, 250-cap
auto-splitting) is kept verbatim because that is the part that works.

Two changes from the original:

1. TIMELINE vs ARTICLE windows are now separate. timelinevolraw returns the
   whole series in ONE call no matter how long the window, so the timeline
   covers the full 2021-2022 panel for free. Only the artlist pull is chunked
   week by week, so that is restricted to the weeks that actually matter --
   Feb through Aug 2022, spanning the SFPD MOU withdrawal (Feb 2), the recall
   vote (Jun 7), and the Jenkins appointment (Jul 7).

2. TWO topic series instead of one:
     "Chesa Boudin"          - all coverage of him (full-name phrase, so it
                               does not collect Kathy Boudin's May 2022
                               obituary coverage)
     near20:"Boudin recall"  - recall-framed coverage (original query)
   Plotting both is the point: it separates "he is in the news" from "the
   recall is the story."

Produces, in ./gdelt_output_boudin/:
  timeline_daily.csv - one row per day: raw matches for each series, the US
                       and global denominators, and both % normalizations
  articles.csv       - every matching recall article in the Feb-Aug window,
                       with headline_mention and outlet_type (local/national)
  run_log.txt        - every URL called and what came back
"""

import requests
import json
import time
import csv
import os
import ssl
from collections import Counter
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter

# ============================== CONFIG ==================================

# Topic series. Key is the column name written to timeline_daily.csv.
TOPIC_SERIES = {
    "chesa_boudin": '"Chesa Boudin"',
    "boudin_recall": 'near20:"Boudin recall"',
}
# Which series drives the article-level pull.
ARTICLE_SERIES = "boudin_recall"

COUNTRY_FILTER = "sourcecountry:unitedstates"

# Timeline window: the full panel. One API call per series regardless of length.
TL_START = "20210101000000"
TL_END = "20221226000000"

# Article window: only the weeks that matter. This is the expensive part
# (one call per week, more where the 250-record cap forces a split).
#   2022-02-02  SFPD chief withdraws from the use-of-force MOU
#   2022-06-07  recall election
#   2022-07-07  Jenkins appointed interim DA
ART_START = "20220201000000"
ART_END = "20220901000000"

OUTDIR = "gdelt_output_boudin"
SLEEP_BETWEEN_CALLS = 8.0
ARTLIST_CHUNK_DAYS = 7

# Bay Area outlets from the media-bias project's publication map, plus the
# national outlets already hand-classified in the original script.
OUTLET_TYPE = {
    # local / Bay Area
    "kalw.org": "local",
    "sfchronicle.com": "local",
    "sfgate.com": "local",
    "smdailyjournal.com": "local",
    "nbcbayarea.com": "local",
    "ktvu.com": "local",
    "kron4.com": "local",
    "abc7news.com": "local",
    "kqed.org": "local",
    "sfexaminer.com": "local",
    "sfstandard.com": "local",
    "sfist.com": "local",
    "missionlocal.org": "local",
    "oaklandside.org": "local",
    "berkeleyside.org": "local",
    "eastbaytimes.com": "local",
    "mercurynews.com": "local",
    "sfbayview.com": "local",
    "alamedapost.com": "local",
    "marinij.com": "local",
    "sanfrancisco.cbslocal.com": "local",
    # national
    "cityandstateny.com": "national",
    "realclearpolitics.com": "national",
    "foxnews.com": "national",
    "streetinsider.com": "national",
    "powerlineblog.com": "national",
    "freerepublic.com": "national",
    "thefederalist.com": "national",
    "dailycaller.com": "national",
    "nymag.com": "national",
    "washingtontimes.com": "national",
    "9and10news.com": "national",
    "nytimes.com": "national",
    "washingtonpost.com": "national",
    "wsj.com": "national",
    "cnn.com": "national",
    "nbcnews.com": "national",
    "cbsnews.com": "national",
    "abcnews.go.com": "national",
    "politico.com": "national",
    "theguardian.com": "national",
    "apnews.com": "national",
    "reuters.com": "national",
    "usatoday.com": "national",
    "newsweek.com": "national",
    "thehill.com": "national",
    "breitbart.com": "national",
    "nypost.com": "national",
    "latimes.com": "national",
    "vox.com": "national",
    "slate.com": "national",
    "theatlantic.com": "national",
}
# ==========================================================================

BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
HEADERS = {"User-Agent": "BERQ-J research script (contact: dyo@berkeley.edu)"}


class _LegacyRenegotiationAdapter(HTTPAdapter):
    """
    Some servers (or something in the network path) request an old-style TLS
    renegotiation mid-handshake. Windows' native Schannel (what curl.exe uses)
    handles this automatically; recent OpenSSL -- what Python's own ssl module
    uses -- refuses it by default and the connection just hangs instead of
    erroring cleanly. This option (Python 3.12+) opts back into allowing it.
    """
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


SESSION = requests.Session()
SESSION.mount("https://", _LegacyRenegotiationAdapter())


def safe_get_json(params, log, max_char_fixes=100, max_retries=None):
    """
    Call the DOC API and parse JSON, retrying indefinitely by default on
    HTTP 429 (rate limited) or a transient connection/timeout error, with
    exponential backoff capped at 120 seconds between attempts.
    """
    attempt = 0
    total_wait = 0.0

    while True:
        try:
            r = SESSION.get(BASE, params=params, headers=HEADERS, timeout=30)
            if r.status_code != 429:
                break
            problem, detail = "rate limited (HTTP 429)", r.text[:200]
        except requests.exceptions.RequestException as e:
            problem, detail = f"connection error ({type(e).__name__})", str(e)

        attempt += 1
        if max_retries is not None and attempt > max_retries:
            log.write(f"  -> gave up after {max_retries} retries: {problem}: {detail}\n")
            print(f"  [!] Giving up after {max_retries} retries: {problem}", flush=True)
            return {}

        wait = min(10 * (2 ** (attempt - 1)), 120)
        total_wait += wait
        print(f"  [!] {problem} -- attempt {attempt}, waiting {wait}s "
              f"(~{total_wait / 60:.1f} min waited on this request so far)...", flush=True)
        log.write(f"  -> {problem}: {detail}; waiting {wait}s (attempt {attempt})\n")
        log.flush()
        time.sleep(wait)

    log.write(f"{r.status_code}  {r.url}\n")
    log.flush()
    if r.status_code != 200 or "html" in r.headers.get("content-type", ""):
        log.write(f"  -> unexpected response: {r.text[:200]}\n")
        return {}

    text = r.text
    for _ in range(max_char_fixes):
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            idx = e.pos
            text = text[:idx] + " " + text[idx + 1:]
    log.write("  -> JSON unparseable even after cleanup\n")
    return {}


def daterange_chunks(start, end, days):
    cur = datetime.strptime(start, "%Y%m%d%H%M%S")
    stop = datetime.strptime(end, "%Y%m%d%H%M%S")
    while cur < stop:
        nxt = min(cur + timedelta(days=days), stop)
        yield cur.strftime("%Y%m%d%H%M%S"), nxt.strftime("%Y%m%d%H%M%S")
        cur = nxt


def classify_headline(title, terms=("boudin", "recall")):
    t = (title or "").lower()
    return any(term in t for term in terms)


def timeline_rows(query, log):
    """One timelinevolraw call -> {date: (value, norm)}."""
    data = safe_get_json({"query": query, "mode": "timelinevolraw", "format": "json",
                          "startdatetime": TL_START, "enddatetime": TL_END}, log)
    time.sleep(SLEEP_BETWEEN_CALLS)
    rows = (data.get("timeline") or [{}])[0].get("data") or []
    return {d["date"]: (d["value"], d.get("norm")) for d in rows}


def pull_timeline(log):
    """Daily raw matches for every topic series, plus the US and global
    denominators, in one wide CSV."""
    series = {}
    for name, topic in TOPIC_SERIES.items():
        print(f"  series '{name}': {topic}", flush=True)
        series[name] = timeline_rows(f"{topic} {COUNTRY_FILTER}", log)
        print(f"    -> {len(series[name])} days", flush=True)

    print("  denominator: all US-sourced coverage", flush=True)
    us_total = timeline_rows(COUNTRY_FILTER, log)
    print(f"    -> {len(us_total)} days", flush=True)

    all_dates = sorted(set().union(*[set(s) for s in series.values()], set(us_total)))
    if not all_dates:
        print("  [!] No timeline rows returned -- check run_log.txt.", flush=True)
        return

    # `value` on the denominator call is the raw count of ALL US-sourced
    # articles that day (no topical term in the query), which is the US-volume
    # denominator we want. Its `norm` is the global total (see the original
    # script's Test A) and is carried separately.
    out_path = os.path.join(OUTDIR, "timeline_daily.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        header = ["date"]
        for name in TOPIC_SERIES:
            header += [f"{name}_matches", f"{name}_pct_of_us", f"{name}_pct_of_global"]
        header += ["us_total_monitored", "global_norm"]
        w.writerow(header)

        for date in all_dates:
            us_n, global_norm = us_total.get(date, (None, None))
            row = [date]
            for name in TOPIC_SERIES:
                matches, series_global = series[name].get(date, (0, None))
                gnorm = series_global or global_norm
                row += [
                    matches,
                    round(100 * matches / us_n, 6) if us_n else None,
                    round(100 * matches / gnorm, 6) if gnorm else None,
                ]
            row += [us_n, global_norm]
            w.writerow(row)
    print(f"  wrote {out_path} ({len(all_dates)} days)", flush=True)


def fetch_chunk(full_query, chunk_start, chunk_end, log, depth=0):
    """
    Fetch every article in [chunk_start, chunk_end). If the API returns
    exactly 250 records (its per-request cap), the window is probably
    truncated -- so split it in half and fetch each half separately.
    """
    data = safe_get_json({"query": full_query, "mode": "artlist", "format": "json",
                          "maxrecords": 250, "startdatetime": chunk_start,
                          "enddatetime": chunk_end}, log)
    time.sleep(SLEEP_BETWEEN_CALLS)
    articles = data.get("articles") or []

    if len(articles) < 250:
        return articles

    start_dt = datetime.strptime(chunk_start, "%Y%m%d%H%M%S")
    end_dt = datetime.strptime(chunk_end, "%Y%m%d%H%M%S")
    if (end_dt - start_dt) <= timedelta(hours=1) or depth >= 8:
        print(f"  [!] {chunk_start}-{chunk_end} still returns 250 even at ~1h "
              f"resolution; keeping what we have for this sliver.", flush=True)
        return articles

    mid_dt = start_dt + (end_dt - start_dt) / 2
    mid = mid_dt.strftime("%Y%m%d%H%M%S")
    print(f"  chunk {chunk_start}-{chunk_end} hit the 250-record cap -- "
          f"splitting at {mid} and re-fetching each half...", flush=True)
    log.write(f"  -> cap hit for {chunk_start}-{chunk_end}, splitting at {mid}\n")
    return (fetch_chunk(full_query, chunk_start, mid, log, depth + 1)
            + fetch_chunk(full_query, mid, chunk_end, log, depth + 1))


def pull_articles(log):
    """Every matching article across the article window, chunked to respect
    the 250-record cap, deduplicated by URL, classified by headline and
    outlet type."""
    full_query = f"{TOPIC_SERIES[ARTICLE_SERIES]} {COUNTRY_FILTER}"
    out_path = os.path.join(OUTDIR, "articles.csv")
    total = 0
    seen_urls = set()
    domain_counts = Counter()
    unclassified_counts = Counter()

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["url", "title", "seendate", "domain", "language",
                    "sourcecountry", "headline_mention", "outlet_type"])
        for chunk_start, chunk_end in daterange_chunks(ART_START, ART_END, ARTLIST_CHUNK_DAYS):
            print(f"  week {chunk_start[:8]} ...", flush=True)
            articles = fetch_chunk(full_query, chunk_start, chunk_end, log)
            for a in articles:
                url = a.get("url")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                domain = (a.get("domain") or "").lower()
                domain_counts[domain] += 1
                outlet_type = OUTLET_TYPE.get(domain, "unclassified")
                if outlet_type == "unclassified":
                    unclassified_counts[domain] += 1
                w.writerow([
                    url, a.get("title"), a.get("seendate"), domain,
                    a.get("language"), a.get("sourcecountry"),
                    classify_headline(a.get("title")), outlet_type,
                ])
                total += 1
            f.flush()

    print(f"  wrote {out_path} ({total} unique articles, {len(domain_counts)} distinct domains)", flush=True)
    if unclassified_counts:
        print("  Most common UNCLASSIFIED domains -- add these to OUTLET_TYPE and re-run "
              "if you want full national/local coverage:", flush=True)
        for domain, count in unclassified_counts.most_common(20):
            print(f"    {count:>4}  {domain}", flush=True)


if __name__ == "__main__":
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, "run_log.txt"), "w", encoding="utf-8") as log:
        print("Pulling timeline series (full 2021-2022 panel)...", flush=True)
        pull_timeline(log)
        print(f"Pulling article-level data for '{ARTICLE_SERIES}' "
              f"({ART_START[:8]} to {ART_END[:8]}, week by week)...", flush=True)
        pull_articles(log)
    print(f"\nDone. Check {OUTDIR}/ for timeline_daily.csv, articles.csv, run_log.txt", flush=True)
