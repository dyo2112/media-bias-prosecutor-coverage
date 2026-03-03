from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "output"
OUT_TEX = Path(__file__).resolve().parent / "generated_stats.tex"


def latex_int(value: int | float) -> str:
    return f"{int(round(value)):,}".replace(",", "{,}")


def latex_float(value: float, digits: int = 3, signed: bool = False) -> str:
    fmt = f"{{:{'+' if signed else ''}.{digits}f}}"
    return fmt.format(value)


def latex_ratio(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}\\times"


def latex_pvalue(value: float) -> str:
    if value == 0 or value < 1e-300:
        return "\\approx 0"
    if value < 1e-3:
        exp = int(math.floor(math.log10(value)))
        mant = value / (10 ** exp)
        return f"{mant:.2f}\\times 10^{{{exp}}}"
    return f"{value:.3f}"


def latex_pvalue_table(value: float) -> str:
    """Compact p-value formatter for table cells (used as p<... or p=...)."""
    if value < 1e-3:
        return "<.001"
    return f"={value:.3f}"


def cohens_d(progressive: pd.Series, traditional: pd.Series) -> float:
    p = progressive.to_numpy(dtype=float)
    t = traditional.to_numpy(dtype=float)
    n1, n2 = len(p), len(t)
    v1 = np.var(p, ddof=1)
    v2 = np.var(t, ddof=1)
    pooled = ((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2)
    return float((np.mean(p) - np.mean(t)) / np.sqrt(pooled))


def metric_stats(df: pd.DataFrame, col: str) -> dict[str, float]:
    prog = df.loc[df["prosecutor_type"] == "Progressive", col].dropna()
    trad = df.loc[df["prosecutor_type"] == "Traditional", col].dropna()
    t_stat, p_val = stats.ttest_ind(prog, trad, equal_var=False)
    return {
        "n_prog": float(len(prog)),
        "n_trad": float(len(trad)),
        "mean_prog": float(prog.mean()),
        "mean_trad": float(trad.mean()),
        "d": cohens_d(prog, trad),
        "p": float(p_val),
        "t": float(t_stat),
    }


def source_rate(count: int, n_articles: int) -> float:
    return count / n_articles if n_articles else float("nan")


def main() -> None:
    stats06 = json.loads((OUTPUT_DIR / "06_stats_results.json").read_text(encoding="utf-8"))
    stats08 = json.loads((OUTPUT_DIR / "08_extraction_stats.json").read_text(encoding="utf-8"))
    stats12 = json.loads((OUTPUT_DIR / "12_segmented_its_results.json").read_text(encoding="utf-8"))

    df = pd.read_parquet(OUTPUT_DIR / "04_bias_scores.parquet")
    df = df[df["prosecutor_type"].isin(["Progressive", "Traditional"])].copy()

    no_jenkins = df[df["primary_prosecutor"] != "Brooke Jenkins"].copy()

    full_comp = stats06["group_comparison"]
    full_aspect = stats06["per_method"]["score_aspect_sentiment"]
    full_stance = stats06["per_method"]["score_stance"]
    full_keywords = stats06["per_method"]["score_keywords"]
    full_doc = stats06["per_method"]["score_doc_sentiment"]

    nj_comp = metric_stats(no_jenkins, "composite_bias_score")
    nj_stance = metric_stats(no_jenkins, "score_stance")
    nj_keywords = metric_stats(no_jenkins, "score_keywords")
    nj_aspect = metric_stats(no_jenkins, "score_aspect_sentiment")
    nj_doc = metric_stats(no_jenkins, "score_doc_sentiment")

    source_types = stats08["source_type_distribution"]
    stance_dist = stats08["source_stance_distribution"]
    causal_dist = stats08["causal_direction_distribution"]
    claim_dist = stats08["claim_type_distribution"]

    n_prog = int(full_comp["progressive_n"])
    n_trad = int(full_comp["traditional_n"])
    n_total = n_prog + n_trad

    prog_sources_total = int(source_types["Progressive"]["total"])
    trad_sources_total = int(source_types["Traditional"]["total"])

    per_prosecutor = stats08["per_prosecutor"]
    extraction_total = int(
        round(
            sum(
                float(v["n_articles"]) * float(v["mean_total_extractions"])
                for v in per_prosecutor.values()
            )
        )
    )
    extraction_mean = extraction_total / n_total

    def st_rate(group: str, key: str) -> float:
        return source_rate(int(source_types[group][key]), n_prog if group == "Progressive" else n_trad)

    def stance_rate(group: str, key: str) -> float:
        return source_rate(int(stance_dist[group][key]), n_prog if group == "Progressive" else n_trad)

    def causal_rate(group: str, key: str) -> float:
        return source_rate(int(causal_dist[group][key]), n_prog if group == "Progressive" else n_trad)

    def claim_rate(group: str, key: str) -> float:
        return source_rate(int(claim_dist[group][key]), n_prog if group == "Progressive" else n_trad)

    no_fallback = stats06["sensitivity_no_fallback"]

    def its_result(transition: str, outcome: str) -> dict:
        return stats12[transition][outcome]

    sf_comp = its_result("SF: Boudin to Jenkins", "composite_bias_score")
    sf_stance = its_result("SF: Boudin to Jenkins", "score_stance")
    sf_keywords = its_result("SF: Boudin to Jenkins", "score_keywords")
    al_comp = its_result("Alameda: O'Malley to Price", "composite_bias_score")
    al_stance = its_result("Alameda: O'Malley to Price", "score_stance")
    al_keywords = its_result("Alameda: O'Malley to Price", "score_keywords")

    macros: list[tuple[str, str]] = [
        ("NAttributedTotal", latex_int(n_total)),
        ("NProgAttributed", latex_int(n_prog)),
        ("NTradAttributed", latex_int(n_trad)),
        ("NBoudin", latex_int(per_prosecutor["Chesa Boudin"]["n_articles"])),
        ("NJenkins", latex_int(per_prosecutor["Brooke Jenkins"]["n_articles"])),
        ("NOmalley", latex_int(per_prosecutor["Nancy O'Malley"]["n_articles"])),
        ("NPrice", latex_int(per_prosecutor["Pamela Price"]["n_articles"])),
        ("NWagstaffe", latex_int(per_prosecutor["Steve Wagstaffe"]["n_articles"])),
        ("NExtractionsTotal", latex_int(extraction_total)),
        ("MeanExtractionsPerArticle", latex_float(extraction_mean, digits=1)),
        ("SourceChiSq", latex_float(float(stats08["source_type_chi2"]), digits=1)),
        ("SourceChiSqDf", latex_int(stats08["source_type_chi2_dof"])),
        ("SourceChiSqP", latex_pvalue(float(stats08["source_type_chi2_p"]))),
        ("AdvocacyRatio", latex_float(st_rate("Progressive", "advocacy_group") / st_rate("Traditional", "advocacy_group"), digits=1)),
        ("JournalistRatio", latex_float(st_rate("Progressive", "journalist") / st_rate("Traditional", "journalist"), digits=1)),
        ("PoliticianRatio", latex_float(st_rate("Progressive", "politician") / st_rate("Traditional", "politician"), digits=1)),
        ("ExpertRatio", latex_float(st_rate("Progressive", "expert") / st_rate("Traditional", "expert"), digits=1)),
        ("DefenseRateRatio", latex_float(st_rate("Progressive", "defense_attorney") / st_rate("Traditional", "defense_attorney"), digits=1)),
        ("SelfQuoteRateRatio", latex_float(st_rate("Progressive", "prosecutor") / st_rate("Traditional", "prosecutor"), digits=1)),
        ("ProgSelfQuoteRate", latex_float(st_rate("Progressive", "prosecutor"), digits=2)),
        ("TradSelfQuoteRate", latex_float(st_rate("Traditional", "prosecutor"), digits=2)),
        ("ProgCriticalPerArticle", latex_float(stance_rate("Progressive", "critical"), digits=2)),
        ("TradCriticalPerArticle", latex_float(stance_rate("Traditional", "critical"), digits=2)),
        ("CriticalRateRatio", latex_float(stance_rate("Progressive", "critical") / stance_rate("Traditional", "critical"), digits=1)),
        ("ProgSupportivePerArticle", latex_float(stance_rate("Progressive", "supportive"), digits=2)),
        ("TradSupportivePerArticle", latex_float(stance_rate("Traditional", "supportive"), digits=2)),
        ("SupportiveRateRatio", latex_float(stance_rate("Progressive", "supportive") / stance_rate("Traditional", "supportive"), digits=1)),
        ("ProgNeutralPerArticle", latex_float(stance_rate("Progressive", "neutral"), digits=2)),
        ("TradNeutralPerArticle", latex_float(stance_rate("Traditional", "neutral"), digits=2)),
        ("NeutralRateRatio", latex_float(stance_rate("Progressive", "neutral") / stance_rate("Traditional", "neutral"), digits=1)),
        ("ProgHarmPerArticle", latex_float(causal_rate("Progressive", "prosecutor_caused_harm"), digits=2)),
        ("TradHarmPerArticle", latex_float(causal_rate("Traditional", "prosecutor_caused_harm"), digits=2)),
        ("HarmRatio", latex_float(causal_rate("Progressive", "prosecutor_caused_harm") / causal_rate("Traditional", "prosecutor_caused_harm"), digits=1)),
        ("ProgHelpedPerArticle", latex_float(causal_rate("Progressive", "prosecutor_helped"), digits=2)),
        ("TradHelpedPerArticle", latex_float(causal_rate("Traditional", "prosecutor_helped"), digits=2)),
        ("HelpedRatio", latex_float(causal_rate("Progressive", "prosecutor_helped") / causal_rate("Traditional", "prosecutor_helped"), digits=1)),
        ("ProgPolicyClaimRate", latex_float(claim_rate("Progressive", "policy"), digits=2)),
        ("TradPolicyClaimRate", latex_float(claim_rate("Traditional", "policy"), digits=2)),
        ("PolicyClaimRatio", latex_float(claim_rate("Progressive", "policy") / claim_rate("Traditional", "policy"), digits=1)),
        ("ProgPerformanceClaimRate", latex_float(claim_rate("Progressive", "performance"), digits=2)),
        ("TradPerformanceClaimRate", latex_float(claim_rate("Traditional", "performance"), digits=2)),
        ("PerformanceClaimRatio", latex_float(claim_rate("Progressive", "performance") / claim_rate("Traditional", "performance"), digits=1)),
        ("ProgCharacterClaimRate", latex_float(claim_rate("Progressive", "character"), digits=2)),
        ("TradCharacterClaimRate", latex_float(claim_rate("Traditional", "character"), digits=2)),
        ("CharacterClaimRatio", latex_float(claim_rate("Progressive", "character") / claim_rate("Traditional", "character"), digits=1)),
        ("ProgCompetenceClaimRate", latex_float(claim_rate("Progressive", "competence"), digits=2)),
        ("TradCompetenceClaimRate", latex_float(claim_rate("Traditional", "competence"), digits=2)),
        ("CompetenceClaimRatio", latex_float(claim_rate("Progressive", "competence") / claim_rate("Traditional", "competence"), digits=1)),
        ("FullCompositeD", latex_float(float(full_comp["cohens_d"]), digits=3)),
        ("FullCompositeP", latex_pvalue(float(full_comp["welch_p"]))),
        ("FullAspectD", latex_float(float(full_aspect["cohens_d"]), digits=3)),
        ("FullAspectP", latex_pvalue(float(full_aspect["p_value"]))),
        ("FullStanceD", latex_float(float(full_stance["cohens_d"]), digits=3)),
        ("FullStanceP", latex_pvalue(float(full_stance["p_value"]))),
        ("FullKeywordsD", latex_float(float(full_keywords["cohens_d"]), digits=3)),
        ("FullKeywordsP", latex_pvalue(float(full_keywords["p_value"]))),
        ("FullDocD", latex_float(float(full_doc["cohens_d"]), digits=3)),
        ("FullDocP", latex_pvalue(float(full_doc["p_value"]))),
        ("NoJenkinsNProg", latex_int(nj_comp["n_prog"])),
        ("NoJenkinsNTrad", latex_int(nj_comp["n_trad"])),
        ("NoJenkinsCompositeD", latex_float(nj_comp["d"], digits=3)),
        ("NoJenkinsCompositeP", latex_pvalue(nj_comp["p"])),
        ("NoJenkinsStanceD", latex_float(nj_stance["d"], digits=3)),
        ("NoJenkinsStanceP", latex_pvalue(nj_stance["p"])),
        ("NoJenkinsKeywordsD", latex_float(nj_keywords["d"], digits=3)),
        ("NoJenkinsKeywordsP", latex_pvalue(nj_keywords["p"])),
        ("NoJenkinsAspectD", latex_float(nj_aspect["d"], digits=3)),
        ("NoJenkinsAspectP", latex_pvalue(nj_aspect["p"])),
        ("NoJenkinsDocD", latex_float(nj_doc["d"], digits=3)),
        ("NoJenkinsDocP", latex_pvalue(nj_doc["p"])),
        ("NoFallbackNTotal", latex_int(no_fallback["n_total"])),
        ("NoFallbackExcludedN", latex_int(no_fallback["n_excluded_fallback"])),
        ("NoFallbackExcludedPct", latex_float(float(no_fallback["excluded_pct"]), digits=1)),
        ("NoFallbackRemainingN", latex_int(no_fallback["n_remaining"])),
        ("NoFallbackNProg", latex_int(no_fallback["progressive_n"])),
        ("NoFallbackNTrad", latex_int(no_fallback["traditional_n"])),
        ("NoFallbackCompositeD", latex_float(float(no_fallback["cohens_d"]), digits=3)),
        ("NoFallbackCompositeP", latex_pvalue(float(no_fallback["welch_p"]))),
        ("NoFallbackBootDiff", latex_float(float(no_fallback["bootstrap_diff"]), digits=4, signed=True)),
        ("NoFallbackBootCiLo", latex_float(float(no_fallback["bootstrap_ci_lower"]), digits=4, signed=True)),
        ("NoFallbackBootCiHi", latex_float(float(no_fallback["bootstrap_ci_upper"]), digits=4, signed=True)),
        ("SFItsCompLevelBeta", latex_float(float(sf_comp["coefficients"]["post"]), digits=3, signed=True)),
        ("SFItsCompLevelP", latex_pvalue_table(float(sf_comp["p_values"]["post"]))),
        ("SFItsCompSlopeBeta", latex_float(float(sf_comp["coefficients"]["time_after"]), digits=4, signed=True)),
        ("SFItsCompSlopeP", latex_pvalue_table(float(sf_comp["p_values"]["time_after"]))),
        ("SFItsCompEffect12m", latex_float(float(sf_comp["effect_at_horizon"]), digits=3, signed=True)),
        ("SFItsCompEffectP", latex_pvalue_table(float(sf_comp["effect_at_horizon_p"]))),
        ("SFItsStanceLevelBeta", latex_float(float(sf_stance["coefficients"]["post"]), digits=3, signed=True)),
        ("SFItsStanceLevelP", latex_pvalue_table(float(sf_stance["p_values"]["post"]))),
        ("SFItsStanceSlopeBeta", latex_float(float(sf_stance["coefficients"]["time_after"]), digits=4, signed=True)),
        ("SFItsStanceSlopeP", latex_pvalue_table(float(sf_stance["p_values"]["time_after"]))),
        ("SFItsStanceEffect12m", latex_float(float(sf_stance["effect_at_horizon"]), digits=3, signed=True)),
        ("SFItsStanceEffectP", latex_pvalue_table(float(sf_stance["effect_at_horizon_p"]))),
        ("SFItsKeywordsLevelBeta", latex_float(float(sf_keywords["coefficients"]["post"]), digits=3, signed=True)),
        ("SFItsKeywordsLevelP", latex_pvalue_table(float(sf_keywords["p_values"]["post"]))),
        ("SFItsKeywordsSlopeBeta", latex_float(float(sf_keywords["coefficients"]["time_after"]), digits=4, signed=True)),
        ("SFItsKeywordsSlopeP", latex_pvalue_table(float(sf_keywords["p_values"]["time_after"]))),
        ("SFItsKeywordsEffect12m", latex_float(float(sf_keywords["effect_at_horizon"]), digits=3, signed=True)),
        ("SFItsKeywordsEffectP", latex_pvalue_table(float(sf_keywords["effect_at_horizon_p"]))),
        ("AlItsCompLevelBeta", latex_float(float(al_comp["coefficients"]["post"]), digits=3, signed=True)),
        ("AlItsCompLevelP", latex_pvalue_table(float(al_comp["p_values"]["post"]))),
        ("AlItsCompSlopeBeta", latex_float(float(al_comp["coefficients"]["time_after"]), digits=4, signed=True)),
        ("AlItsCompSlopeP", latex_pvalue_table(float(al_comp["p_values"]["time_after"]))),
        ("AlItsCompEffect12m", latex_float(float(al_comp["effect_at_horizon"]), digits=3, signed=True)),
        ("AlItsCompEffectP", latex_pvalue_table(float(al_comp["effect_at_horizon_p"]))),
        ("AlItsStanceLevelBeta", latex_float(float(al_stance["coefficients"]["post"]), digits=3, signed=True)),
        ("AlItsStanceLevelP", latex_pvalue_table(float(al_stance["p_values"]["post"]))),
        ("AlItsStanceSlopeBeta", latex_float(float(al_stance["coefficients"]["time_after"]), digits=4, signed=True)),
        ("AlItsStanceSlopeP", latex_pvalue_table(float(al_stance["p_values"]["time_after"]))),
        ("AlItsStanceEffect12m", latex_float(float(al_stance["effect_at_horizon"]), digits=3, signed=True)),
        ("AlItsStanceEffectP", latex_pvalue_table(float(al_stance["effect_at_horizon_p"]))),
        ("AlItsKeywordsLevelBeta", latex_float(float(al_keywords["coefficients"]["post"]), digits=3, signed=True)),
        ("AlItsKeywordsLevelP", latex_pvalue_table(float(al_keywords["p_values"]["post"]))),
        ("AlItsKeywordsSlopeBeta", latex_float(float(al_keywords["coefficients"]["time_after"]), digits=4, signed=True)),
        ("AlItsKeywordsSlopeP", latex_pvalue_table(float(al_keywords["p_values"]["time_after"]))),
        ("AlItsKeywordsEffect12m", latex_float(float(al_keywords["effect_at_horizon"]), digits=3, signed=True)),
        ("AlItsKeywordsEffectP", latex_pvalue_table(float(al_keywords["effect_at_horizon_p"]))),
    ]

    lines = [
        "% Auto-generated by paper/build_stats_tex.py. Do not edit by hand.",
        "% Generated from output/06_stats_results.json, output/08_extraction_stats.json,",
        "% output/12_segmented_its_results.json, output/04_bias_scores.parquet",
    ]
    for name, value in macros:
        lines.append(f"\\newcommand{{\\{name}}}{{{value}}}")

    OUT_TEX.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_TEX}")


if __name__ == "__main__":
    main()
