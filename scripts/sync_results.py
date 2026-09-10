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
ENV_FILE = ROOT / ".env"
API_RESULTS_FILE = ROOT / "data" / "api-results.json"

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
    return {"home": int(home_score), "away": int(away_score)}


def format_score(score):
    return f"{score['home']} - {score['away']}"


def load_env_file(path):
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_api_result_cache():
    if not API_RESULTS_FILE.exists():
        return {}

    payload = json.loads(API_RESULTS_FILE.read_text(encoding="utf-8"))
    return {item["id"]: item for item in payload.get("results", [])}


def write_api_result_cache(results):
    API_RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "football-data.org",
        "results": sorted(results.values(), key=lambda item: item["sequence"]),
    }
    API_RESULTS_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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
        sheet_rows[key] = {
            "row_number": row_number,
            "id": f"epl2026-{int(ws.cell(row_number, col['Match Number']).value)}",
            "sequence": int(ws.cell(row_number, col["Match Number"]).value),
            "gameweek": int(ws.cell(row_number, col["Round Number"]).value),
            "kickoff": kickoff.isoformat().replace("+00:00", "Z"),
            "home": home,
            "away": away,
        }

    cached_results = load_api_result_cache()
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
        fixture = next((sheet_rows[key] for key in candidates if key in sheet_rows), None)
        if not fixture:
            continue

        cached = cached_results.get(fixture["id"])
        if cached and cached.get("score") == result:
            continue

        previous = format_score(cached["score"]) if cached else "blank"
        updates.append((fixture["home"], fixture["away"], previous, format_score(result)))
        if not dry_run:
            cached_results[fixture["id"]] = {
                "id": fixture["id"],
                "season": "2026/27",
                "gameweek": fixture["gameweek"],
                "sequence": fixture["sequence"],
                "kickoff": fixture["kickoff"],
                "home": fixture["home"],
                "away": fixture["away"],
                "score": result,
                "source": "football-data.org",
                "sourceMatchId": match.get("id"),
                "settledAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }

    if updates and not dry_run:
        write_api_result_cache(cached_results)
        subprocess.run([sys.executable, str(BUILD_SCRIPT)], cwd=ROOT, check=True)

    return updates


def main():
    parser = argparse.ArgumentParser(description="Sync Premier League final scores into the generated API result cache.")
    parser.add_argument("--season", default="2026", help="Season start year for football-data.org, e.g. 2026 for 2026/27.")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing the workbook.")
    args = parser.parse_args()

    load_env_file(ENV_FILE)
    token = os.environ.get("FOOTBALL_DATA_API_TOKEN")
    if not token:
        raise SystemExit("Set FOOTBALL_DATA_API_TOKEN in your shell or in a private .env file before running this script.")

    updates = sync_results(token, args.season, args.dry_run)
    if not updates:
        print("No new final scores found.")
        return

    verb = "Would update" if args.dry_run else "Updated"
    print(f"{verb} {len(updates)} result(s):")
    for home, away, previous, new in updates:
        print(f"- {home} vs {away}: {previous} -> {new}")


if __name__ == "__main__":
    main()
