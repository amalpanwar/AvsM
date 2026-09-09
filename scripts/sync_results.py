from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_FILE = ROOT / "epl-2026-GMTStandardTime.xlsx"
BUILD_SCRIPT = ROOT / "scripts" / "build_data.py"

TEAM_ALIASES = {
    "afc bournemouth": "bournemouth",
    "arsenal fc": "arsenal",
    "aston villa fc": "aston villa",
    "brentford fc": "brentford",
    "brighton & hove albion fc": "brighton",
    "brighton and hove albion fc": "brighton",
    "burnley fc": "burnley",
    "chelsea fc": "chelsea",
    "coventry city fc": "coventry",
    "crystal palace fc": "crystal palace",
    "everton fc": "everton",
    "fulham fc": "fulham",
    "hull city afc": "hull",
    "ipswich town fc": "ipswich",
    "leeds united fc": "leeds",
    "liverpool fc": "liverpool",
    "manchester city fc": "man city",
    "manchester united fc": "man utd",
    "newcastle united fc": "newcastle",
    "nottingham forest fc": "nott'm forest",
    "sunderland afc": "sunderland",
    "tottenham hotspur fc": "spurs",
    "west ham united fc": "west ham",
    "wolverhampton wanderers fc": "wolves",
}


def normalise_team(value):
    text = str(value or "").lower().strip()
    text = text.replace("’", "'")
    return TEAM_ALIASES.get(text, text)


def parse_excel_datetime(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return from_excel(value).replace(tzinfo=timezone.utc)
    raise ValueError(f"Unsupported Excel date value: {value!r}")


def football_data_matches(token, season):
    params = urlencode({"season": season})
    request = Request(
        f"https://api.football-data.org/v4/competitions/PL/matches?{params}",
        headers={"X-Auth-Token": token, "Accept": "application/json"},
    )

    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"football-data.org request failed: HTTP {error.code} {body}") from error

    return payload.get("matches", [])


def result_from_match(match):
    full_time = match.get("score", {}).get("fullTime", {})
    home_score = full_time.get("home")
    away_score = full_time.get("away")
    if home_score is None or away_score is None:
        return None
    return f"{home_score} - {away_score}"


def sync_results(token, season, dry_run):
    wb = load_workbook(FIXTURE_FILE)
    ws = wb[wb.sheetnames[0]]
    header = [cell.value for cell in ws[1]]
    col = {name: index + 1 for index, name in enumerate(header)}

    sheet_rows = {}
    for row_number in range(2, ws.max_row + 1):
        home = ws.cell(row_number, col["Home Team"]).value
        away = ws.cell(row_number, col["Away Team"]).value
        kickoff = parse_excel_datetime(ws.cell(row_number, col["Date"]).value)
        key = (normalise_team(home), normalise_team(away), kickoff.date())
        sheet_rows[key] = row_number

    updates = []
    for match in football_data_matches(token, season):
        if match.get("status") != "FINISHED":
            continue

        utc_date = datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00")).astimezone(timezone.utc)
        home = normalise_team(match.get("homeTeam", {}).get("name"))
        away = normalise_team(match.get("awayTeam", {}).get("name"))
        result = result_from_match(match)
        if not result:
            continue

        candidates = [
            (home, away, utc_date.date()),
            (home, away, (utc_date - timedelta(days=1)).date()),
            (home, away, (utc_date + timedelta(days=1)).date()),
        ]
        row_number = next((sheet_rows[key] for key in candidates if key in sheet_rows), None)
        if not row_number:
            continue

        current = ws.cell(row_number, col["Result"]).value
        if str(current or "").strip() == result:
            continue

        updates.append((row_number, ws.cell(row_number, col["Home Team"]).value, ws.cell(row_number, col["Away Team"]).value, current, result))
        if not dry_run:
            ws.cell(row_number, col["Result"]).value = result

    if updates and not dry_run:
        wb.save(FIXTURE_FILE)
        subprocess.run([sys.executable, str(BUILD_SCRIPT)], cwd=ROOT, check=True)

    return updates


def main():
    parser = argparse.ArgumentParser(description="Sync Premier League final scores into the local EPL2026 workbook.")
    parser.add_argument("--season", default="2026", help="Season start year for football-data.org, e.g. 2026 for 2026/27.")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing the workbook.")
    args = parser.parse_args()

    token = os.environ.get("FOOTBALL_DATA_API_TOKEN")
    if not token:
        raise SystemExit("Set FOOTBALL_DATA_API_TOKEN before running this script.")

    updates = sync_results(token, args.season, args.dry_run)
    if not updates:
        print("No new final scores found.")
        return

    verb = "Would update" if args.dry_run else "Updated"
    print(f"{verb} {len(updates)} result(s):")
    for _, home, away, old, new in updates:
        previous = old if old else "blank"
        print(f"- {home} vs {away}: {previous} -> {new}")


if __name__ == "__main__":
    main()
