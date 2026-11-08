#!/usr/bin/env python3
"""Evaluate System ERS against Human ERS on human-judged event pairs.

Requires Python 3.10+, standard library for CSV; optional openpyxl for XLSX.
Never assigns zero relevance to unjudged pairs. Evaluation is judged-only.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

STORY_ALIASES = {
    "inception": ("inception", "incep", "인셉션"),
    "interstellar": ("interstellar", "인터스텔라"),
    "lalaland": ("lalaland", "la_la_land", "la-la-land", "라라랜드"),
    "titanic": ("titanic", "타이타닉"),
    "threeman": ("threeman", "three_man", "three men", "세남자"),
    "olivertwist": ("olivertwist", "oliver_twist", "올리버트위스트"),
}
SOURCE_NAMES = ("source_event_id", "query_event_id", "event_id_a", "event_a", "event1_id", "event_1_id", "event1", "event_1", "source_id", "id_1", "id1", "first_event_id")
TARGET_NAMES = ("target_event_id", "candidate_event_id", "event_id_b", "event_b", "event2_id", "event_2_id", "event2", "event_2", "target_id", "id_2", "id2", "second_event_id")
HUMAN_NAMES = ("human_ers", "humaners", "mean_human_ers", "average_human_ers", "avg_human_ers", "ers_human", "ers_score", "final_ers", "ers", "weighted_ers", "human_score", "ground_truth", "relevance", "relatedness")
SYSTEM_NAMES = ("relatedness", "system_ers", "ers", "score", "final_ers")


def norm(s: object) -> str:
    return re.sub(r"[^a-z0-9가-힣]", "", str(s).lower())


def story_of(filename: str) -> str | None:
    name = norm(Path(filename).stem)
    for story, aliases in STORY_ALIASES.items():
        if any(norm(a) in name for a in aliases):
            return story
    return None


def detect(headers: list[str], aliases: tuple[str, ...], explicit: str | None, what: str, path: Path) -> str:
    if explicit:
        matches = [h for h in headers if norm(h) == norm(explicit)]
        if len(matches) == 1:
            return matches[0]
        raise ValueError(f"{path.name}: {what} column '{explicit}' not found. Available: {headers}")
    for name in aliases:
        matches = [h for h in headers if norm(h) == norm(name)]
        if len(matches) == 1:
            return matches[0]
    raise ValueError(f"{path.name}: could not identify {what} column. Available: {headers}. Use --{what.replace(' ', '-')}-col.")


def read_table(path: Path) -> tuple[list[str], list[dict[str, object]]]:
    if path.suffix.lower() in (".csv", ".tsv"):
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            sample = f.read(4096)
            f.seek(0)
            delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
            if path.suffix.lower() == ".csv" and sample.count(";") > sample.count(","):
                delimiter = ";"
            reader = csv.DictReader(f, delimiter=delimiter)
            if not reader.fieldnames:
                raise ValueError(f"{path}: empty or missing header")
            return list(reader.fieldnames), list(reader)
    if path.suffix.lower() == ".xlsx":
        try:
            from openpyxl import load_workbook
        except ImportError as e:
            raise RuntimeError("To read XLSX files, install openpyxl: pip install openpyxl") from e
        book = load_workbook(path, read_only=True, data_only=True)
        sheet = book.active
        values = sheet.iter_rows(values_only=True)
        header_values = next(values, None)
        if not header_values:
            raise ValueError(f"{path}: empty sheet")
        headers = [str(v).strip() if v is not None else f"UNNAMED_{i}" for i, v in enumerate(header_values)]
        records = [dict(zip(headers, row)) for row in values if any(v is not None and str(v).strip() for v in row)]
        book.close()
        return headers, records
    raise ValueError(f"Unsupported format: {path.suffix}")


def finite_score(value: object, filename: str, row: int) -> float:
    if value is None or str(value).strip() == "":
        raise ValueError(f"{filename} row {row}: missing score")
    try:
        v = float(str(value).strip())
    except ValueError as e:
        raise ValueError(f"{filename} row {row}: invalid score {value!r}") from e
    if not math.isfinite(v):
        raise ValueError(f"{filename} row {row}: non-finite score")
    return v


def event_id(value: object) -> str:
    if value is None:
        return ""
    v = str(value).strip()
    return v[:-2] if re.fullmatch(r"\d+\.0", v) else v


def pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def write_csv(path: Path, records: list[dict], cols: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(records)


def dcg(rels: list[float], k: int, gain: str) -> float:
    return sum(((2.0 ** r - 1.0) if gain == "exponential" else r) / math.log2(i + 2) for i, r in enumerate(rels[:k]))


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 2:
        return None
    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        result = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i + 1
            while j < len(order) and values[order[j]] == values[order[i]]:
                j += 1
            avg = (i + 1 + j) / 2
            for index in order[i:j]:
                result[index] = avg
            i = j
        return result
    a, b = ranks(x), ranks(y)
    am, bm = statistics.mean(a), statistics.mean(b)
    num = sum((u-am)*(v-bm) for u, v in zip(a, b))
    den = math.sqrt(sum((u-am)**2 for u in a) * sum((v-bm)**2 for v in b))
    return num/den if den else None


def files_at(path: Path, include_xlsx: bool) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(str(path))
    extensions = {".csv", ".tsv", ".xlsx"} if include_xlsx else {".csv"}
    return sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in extensions)


def load_human(files: list[Path], args) -> tuple[dict, list[dict]]:
    raw: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    issues: list[dict] = []
    for path in files:
        story = story_of(path.name)
        if story is None:
            if args.story and len(files) == 1:
                story = args.story
            else:
                issues.append({"file": path.name, "row": "", "issue": "unknown_story", "detail": "Cannot infer story from filename"})
                continue
        if args.story and story != args.story:
            continue
        headers, rows = read_table(path)
        source_col = detect(headers, SOURCE_NAMES, args.human_source_col, "human source", path)
        target_col = detect(headers, TARGET_NAMES, args.human_target_col, "human target", path)
        score_col = detect(headers, HUMAN_NAMES, args.human_score_col, "human score", path)
        for number, row in enumerate(rows, 2):
            a, b = event_id(row.get(source_col)), event_id(row.get(target_col))
            if not a or not b or a == b:
                issues.append({"file": path.name, "row": number, "issue": "bad_pair", "detail": f"{a} / {b}"})
                continue
            if row.get(score_col) is None or str(row.get(score_col)).strip() == "":
                issues.append({"file": path.name, "row": number, "issue": "missing_human_score", "detail": f"{a} / {b}"})
                continue
            score = finite_score(row[score_col], path.name, number)
            raw[(story, *pair_key(a, b))].append(score)
    return {k: statistics.mean(v) for k, v in raw.items()}, issues


def load_system(files: list[Path], args) -> dict:
    scores: dict[tuple[str, str, str], float] = {}
    for path in files:
        if args.system.is_dir() and "all_pairs" not in path.stem.lower() and not args.system_score_col:
            # Skip rank/top5/summary by default when scanning an output directory.
            continue
        story = story_of(path.name)
        if story is None:
            if args.story and len(files) == 1:
                story = args.story
            else:
                continue
        if args.story and story != args.story:
            continue
        headers, rows = read_table(path)
        a_col = detect(headers, SOURCE_NAMES, args.system_source_col, "system source", path)
        b_col = detect(headers, TARGET_NAMES, args.system_target_col, "system target", path)
        s_col = detect(headers, SYSTEM_NAMES, args.system_score_col, "system score", path)
        for number, row in enumerate(rows, 2):
            a, b = event_id(row.get(a_col)), event_id(row.get(b_col))
            if not a or not b or a == b:
                continue
            score = finite_score(row.get(s_col), path.name, number)
            key = story, *pair_key(a, b)
            if key in scores and not math.isclose(scores[key], score, rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError(f"Conflicting System ERS for {key}: {scores[key]} vs {score} in {path}")
            scores[key] = score
    return scores


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--human", type=Path, required=True, help="Human ERS CSV/XLSX file or folder")
    p.add_argument("--system", type=Path, required=True, help="System ERS all_pairs CSV or folder")
    p.add_argument("--out", type=Path, default=Path("evaluation_results"))
    p.add_argument("--story", choices=sorted(STORY_ALIASES), help="For single files with no story name, or to filter")
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--threshold", type=float, required=True, help="Human ERS >= threshold means relevant (same scale as input)")
    p.add_argument("--gain", choices=("linear", "exponential"), default="linear")
    p.add_argument("--human-source-col")
    p.add_argument("--human-target-col")
    p.add_argument("--human-score-col")
    p.add_argument("--system-source-col")
    p.add_argument("--system-target-col")
    p.add_argument("--system-score-col")
    p.add_argument("--min-judged", type=int, default=2, help="Minimum annotated candidates per query to include in macro metrics")
    args = p.parse_args()
    if args.k < 1 or args.min_judged < 1:
        p.error("--k and --min-judged must be positive")
    human_files = files_at(args.human, include_xlsx=True)
    system_files = files_at(args.system, include_xlsx=False)
    human, issues = load_human(human_files, args)
    system = load_system(system_files, args)
    if not human:
        raise SystemExit("No Human ERS pairs loaded. Check filenames and column names.")
    if not system:
        raise SystemExit("No System ERS pairs loaded. Expected *_ERS_all_pairs.csv files.")

    args.out.mkdir(parents=True, exist_ok=True)
    matched: list[dict] = []
    query_data: dict[tuple[str, str], list[tuple[str, float, float]]] = defaultdict(list)
    unmatched: list[dict] = []
    for (story, a, b), h in sorted(human.items()):
        key = (story, a, b)
        s = system.get(key)
        if s is None:
            unmatched.append({"story": story, "event_a": a, "event_b": b, "human_ers": h, "reason": "no_matching_system_pair"})
            continue
        matched.append({"story": story, "event_a": a, "event_b": b, "human_ers": h, "system_ers": s, "relevant": int(h >= args.threshold)})
        # ERS is a symmetric pair score. Both endpoints serve as queries.
        query_data[(story, a)].append((b, h, s))
        query_data[(story, b)].append((a, h, s))

    per_query: list[dict] = []
    rankings: list[dict] = []
    for (story, query), entries in sorted(query_data.items()):
        ranked = sorted(entries, key=lambda v: (-v[2], v[0]))
        ideal = sorted(entries, key=lambda v: (-v[1], v[0]))
        top = ranked[:args.k]
        ndcg_denom = dcg([h for _, h, _ in ideal], args.k, args.gain)
        ndcg_num = dcg([h for _, h, _ in ranked], args.k, args.gain)
        # Undefined if there is no relevance mass; don't silently convert to 0.
        ndcg = ndcg_num / ndcg_denom if ndcg_denom > 0 else None
        relevant_count = sum(h >= args.threshold for _, h, _ in entries)
        hit_count = sum(h >= args.threshold for _, h, _ in top)
        recall = hit_count / relevant_count if relevant_count else None
        eligible = len(entries) >= args.min_judged
        per_query.append({"story": story, "query_event_id": query, "judged_candidates": len(entries), "k": args.k,
                          "relevant_judged": relevant_count, "relevant_in_topk": hit_count,
                          "ndcg_at_k": ndcg if eligible else None, "recall_at_k": recall if eligible else None,
                          "spearman_rho": spearman([h for _, h, _ in entries], [s for _, _, s in entries]) if eligible else None,
                          "eligible": int(eligible), "reason": "" if eligible else "too_few_judged_candidates"})
        for rank, (candidate, h, s) in enumerate(ranked, 1):
            rankings.append({"story": story, "query_event_id": query, "rank": rank,
                             "candidate_event_id": candidate, "system_ers": s, "human_ers": h,
                             "relevant": int(h >= args.threshold), "in_topk": int(rank <= args.k)})

    summary: list[dict] = []
    for story in sorted({k[0] for k in human}):
        hcount = sum(k[0] == story for k in human)
        mcount = sum(r["story"] == story for r in matched)
        qs = [q for q in per_query if q["story"] == story]
        eligible = [q for q in qs if q["eligible"]]
        def mean_col(field: str):
            vals = [q[field] for q in eligible if q[field] is not None]
            return statistics.mean(vals) if vals else None
        summary.append({"story": story, "human_unique_pairs": hcount, "matched_unique_pairs": mcount,
                        "unmatched_unique_pairs": hcount - mcount, "pair_coverage": mcount / hcount if hcount else None,
                        "evaluated_queries": len(eligible), "all_queries": len(qs),
                        "queries_with_fewer_than_k_judgments": sum(q["judged_candidates"] < args.k for q in eligible),
                        "queries_without_relevant_judgments": sum(q["relevant_judged"] == 0 for q in eligible),
                        "macro_ndcg_at_k": mean_col("ndcg_at_k"), "macro_recall_at_k": mean_col("recall_at_k"),
                        "macro_spearman_rho": mean_col("spearman_rho")})

    write_csv(args.out / "matched_pairs.csv", matched, ["story", "event_a", "event_b", "human_ers", "system_ers", "relevant"])
    write_csv(args.out / "unmatched_pairs.csv", unmatched, ["story", "event_a", "event_b", "human_ers", "reason"])
    write_csv(args.out / "input_issues.csv", issues, ["file", "row", "issue", "detail"])
    write_csv(args.out / "ranked_judged_candidates.csv", rankings, ["story", "query_event_id", "rank", "candidate_event_id", "system_ers", "human_ers", "relevant", "in_topk"])
    write_csv(args.out / "per_query_metrics.csv", per_query, ["story", "query_event_id", "judged_candidates", "k", "relevant_judged", "relevant_in_topk", "ndcg_at_k", "recall_at_k", "spearman_rho", "eligible", "reason"])
    write_csv(args.out / "summary.csv", summary, ["story", "human_unique_pairs", "matched_unique_pairs", "unmatched_unique_pairs", "pair_coverage", "evaluated_queries", "all_queries", "queries_with_fewer_than_k_judgments", "queries_without_relevant_judgments", "macro_ndcg_at_k", "macro_recall_at_k", "macro_spearman_rho"])
    config = {"evaluation": "judged-only", "human": str(args.human), "system": str(args.system), "k": args.k, "threshold": args.threshold,
              "gain": args.gain, "min_judged": args.min_judged, "pair_symmetry": True,
              "notes": ["Unjudged candidates are excluded, not treated as irrelevant.",
                        "Both event IDs are treated as query endpoints, as System ERS is symmetric.",
                        "Queries without relevant judged pairs have undefined Recall and are omitted from macro Recall.",
                        "Mean score across duplicate human rows/annotators is used for the same unordered pair.",
                        "Results do not estimate full-corpus retrieval Recall@k."]}
    (args.out / "evaluation_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Human pairs: {len(human)} | matched: {len(matched)} | unmatched: {len(unmatched)}")
    for row in summary:
        print(f"{row['story']}: queries={row['evaluated_queries']}, coverage={row['pair_coverage']:.1%}, "
              f"nDCG@{args.k}={row['macro_ndcg_at_k']}, Recall@{args.k}={row['macro_recall_at_k']}")
    print(f"Saved results to {args.out.resolve()}")


if __name__ == "__main__":
    main()
