#!/usr/bin/env python3.12
"""
Research script for discovering new sports/events not yet tracked by crossfit-agent.

Compares the sports landscape knowledge base against the current competition data
and generates research findings — categories and events that could be added.

Output: data/research_findings.json
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LANDSCAPE_FILE = DATA_DIR / "sports_landscape.json"
COMPETITIONS_FILE = DATA_DIR / "competitions.json"
FINDINGS_FILE = DATA_DIR / "research_findings.json"


def load_json(path: Path) -> dict:
    """Load and parse a JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_tracked_series(competitions: list) -> set:
    """
    Extract the set of series/event types currently tracked.
    Maps from event_type values to landscape series keys.
    """
    tracked = set()

    type_to_series = {
        "crossfit_games": "crossfit_games",
        "crossfit_semifinal": "crossfit_games",
        "wfp_tour": "wfp",
        "wfp_partner": "wfp",
        "hyrox": "hyrox",
        "finnish": "reppi_fi",
        "independent_elite": "independent_elite",
    }

    for comp in competitions:
        etype = comp.get("event_type", "")
        mapped = type_to_series.get(etype)
        if mapped:
            tracked.add(mapped)

    return tracked


def count_tracked_events(competitions: list, series: str) -> int:
    """Count how many events match a given series."""
    series_to_types = {
        "crossfit_games": {"crossfit_games", "crossfit_semifinal"},
        "wfp": {"wfp_tour", "wfp_partner"},
        "hyrox": {"hyrox"},
        "reppi_fi": {"finnish"},
        "independent_elite": {"independent_elite"},
    }

    types = series_to_types.get(series, set())
    return sum(1 for c in competitions if c.get("event_type") in types)


def analyze_gaps(landscape: dict, tracked_series: set, competitions: list) -> dict:
    """
    Compare the landscape knowledge base against tracked series.
    Returns findings structured by main category.
    """
    categories = landscape.get("categories", {})
    findings = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_categories": len(categories),
            "tracked_series": sorted(tracked_series),
            "new_categories": [],
            "partial_categories": [],
            "total_new_series": 0,
        },
        "by_category": {},
    }

    new_series_count = 0

    for cat_key, cat_data in sorted(categories.items()):
        cat_label = cat_data.get("label", cat_key)
        series_data = cat_data.get("series", {})

        new_series = []
        partial_series = []

        for series_key, series in sorted(series_data.items()):
            tracked_status = series.get("tracked")

            if tracked_status is True and series_key in tracked_series:
                # Fully tracked — skip
                continue
            elif tracked_status == "partial":
                # Partially tracked — report the gap
                gap = series.get("gap", "Partial coverage")
                event_count = count_tracked_events(competitions, series_key)
                partial_series.append({
                    "key": series_key,
                    "label": series.get("label", series_key),
                    "description": gap,
                    "priority": series.get("priority", "medium"),
                    "sources": series.get("sources", []),
                    "current_coverage": event_count,
                    "notes": series.get("notes", ""),
                })
            elif tracked_status is False:
                # Not tracked at all
                new_series_count += 1
                new_series.append({
                    "key": series_key,
                    "label": series.get("label", series_key),
                    "description": series.get("gap", series.get("notes", "")),
                    "priority": series.get("priority", "medium"),
                    "sources": series.get("sources", []),
                    "notes": series.get("notes", ""),
                })

        if new_series or partial_series:
            findings["by_category"][cat_key] = {
                "label": cat_label,
                "description": cat_data.get("description", ""),
                "new_series": new_series,
                "partial_series": partial_series,
                "total_new": len(new_series),
                "total_partial": len(partial_series),
            }

            if new_series:
                findings["summary"]["new_categories"].append(cat_key)
            if partial_series:
                findings["summary"]["partial_categories"].append(cat_key)

    findings["summary"]["total_new_series"] = new_series_count

    # Add recommendations from landscape
    findings["recommendations"] = landscape.get("recommendations", [])

    return findings


def generate_human_summary(findings: dict) -> str:
    """Generate a human-readable summary of findings."""
    summary = findings["summary"]
    lines = [
        "=" * 60,
        "CROSSFIT-AGENT — TUTKIMUSRAPORTTI",
        f"Generoitu: {findings['generated_at']}",
        "=" * 60,
        "",
        f"Seurattuja sarjoja: {len(summary['tracked_series'])}",
        f"  {', '.join(sorted(summary['tracked_series']))}",
        "",
        f"Löydetty {summary['total_new_series']} uutta sarjaa {len(summary['new_categories'])} kategoriassa.",
    ]

    if summary["partial_categories"]:
        lines.append(f"Osittainen kattavuus {len(summary['partial_categories'])} kategoriassa.")

    lines.append("")

    by_cat = findings.get("by_category", {})

    for cat_key, cat_data in sorted(by_cat.items()):
        lines.append(f"--- {cat_data['label']} ---")
        lines.append(f"  {cat_data['description']}")
        lines.append("")

        for series in cat_data["new_series"]:
            lines.append(f"  ★ {series['label']} [{series['priority']}]")
            lines.append(f"    {series['description']}")
            if series.get("sources"):
                lines.append(f"    Lähteitä: {', '.join(series['sources'])}")
            lines.append("")

        for series in cat_data["partial_series"]:
            lines.append(f"  ◐ {series['label']} (osittain, {series['current_coverage']} eventtiä) [{series['priority']}]")
            lines.append(f"    {series['description']}")
            lines.append("")

    # Recommendations
    if findings.get("recommendations"):
        lines.append("--- SUOSITUKSET ---")
        for i, rec in enumerate(findings["recommendations"], 1):
            lines.append(f"  {i}. [{rec['priority'].upper()}] {rec['category']}")
            lines.append(f"     {rec['reason']}")
        lines.append("")

    lines.append("=" * 60)

    return "\n".join(lines)


def main():
    """Main entry point."""
    if not LANDSCAPE_FILE.exists():
        print(f"ERROR: Landscape DB not found at {LANDSCAPE_FILE}", file=sys.stderr)
        sys.exit(1)

    if not COMPETITIONS_FILE.exists():
        print(f"ERROR: Competitions data not found at {COMPETITIONS_FILE}", file=sys.stderr)
        sys.exit(1)

    landscape = load_json(LANDSCAPE_FILE)
    competitions = load_json(COMPETITIONS_FILE)

    tracked_series = get_tracked_series(competitions)

    findings = analyze_gaps(landscape, tracked_series, competitions)

    # Write findings
    with open(FINDINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2, ensure_ascii=False)
    print(f"Findings written to {FINDINGS_FILE}")

    # Print human summary
    summary_text = generate_human_summary(findings)
    print(summary_text)

    # Return summary for cron output
    return summary_text


if __name__ == "__main__":
    main()
