from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_FILE = ROOT / "epl-2026-GMTStandardTime.xlsx"
BUILD_SCRIPT = ROOT / "scripts" / "build_data.py"
ENV_FILE = ROOT / ".env"
API_RESULTS_FILE = ROOT / "data" / "api-results.json"
SCORE_OBSERVATIONS_FILE = ROOT / "data" / "score-observations.json"
GENERATED_DATA_FILE = ROOT / "generated-data.js"
FIXTURE_TIMEZONE = ZoneInfo("Europe/London")
NATIVE_STATS_URL = "https://native-stats.org/competition/PL/"
OBSERVATION_START_DELAY = timedelta(hours=2)
OBSERVATION_STABILITY_WINDOW = timedelta(hours=1)
OBSERVATION_MIN_SEEN_COUNT = 2

TEAM_ALIASES = {
    "afc bournemouth": "bournemouth",
    "aston villa": "aston villa",
    "arsenal fc": "arsenal",
    "arsenal": "arsenal",
    "aston villa fc": "aston villa",
    "brentford fc": "brentford",
    "brentford": "brentford",
    "brighton & hove albion fc": "brighton",
    "brighton and hove albion fc": "brighton",
    "brighton": "brighton",
    "bournemouth": "bournemouth",
    "burnley fc": "burnley",
    "chelsea fc": "chelsea",
    "chelsea": "chelsea",
    "coventry city fc": "coventry",
    "coventry city": "coventry",
    "coventry": "coventry",
    "crystal palace fc": "crystal palace",
    "crystal palace": "crystal palace",
    "everton fc": "everton",
    "everton": "everton",
    "fulham fc": "fulham",
    "fulham": "fulham",
    "hull city afc": "hull",
    "hull city": "hull",
    "hull": "hull",
    "ipswich town fc": "ipswich",
    "ipswich town": "ipswich",
    "ipswich": "ipswich",
    "leeds united fc": "leeds",
    "leeds united": "leeds",
    "leeds": "leeds",
    "liverpool fc": "liverpool",
    "liverpool": "liverpool",
    "manchester city fc": "man city",
    "manchester city": "man city",
    "man city": "man city",
    "manchester united fc": "man utd",
    "manchester united": "man utd",
    "man utd": "man utd",
    "newcastle united fc": "newcastle",
    "newcastle united": "newcastle",
    "newcastle": "newcastle",
    "nottingham forest fc": "nott'm forest",
    "nottingham forest": "nott'm forest",
    "sunderland afc": "sunderland",
    "sunderland": "sunderland",
    "tottenham hotspur fc": "spurs",
    "tottenham hotspur": "spurs",
    "spurs": "spurs",
    "west ham united fc": "west ham",
    "west ham united": "west ham",
    "west ham": "west ham",
    "wolverhampton wanderers fc": "wolves",
    "wolves": "wolves",
}


def normalise_team(value):
    text = str(value or "").lower().strip()
    text = text.replace("’", "'")
    text = re.sub(r"\s*\(\d+\)\s*$", "", text).strip()
    return TEAM_ALIASES.get(text, text)


def parse_excel_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = from_excel(value)
    else:
        raise ValueError(f"Unsupported Excel date value: {value!r}")

    if parsed.tzinfo:
        return parsed.astimezone(timezone.utc)
    return parsed.replace(tzinfo=FIXTURE_TIMEZONE).astimezone(timezone.utc)


def football_data_matches(token, season):
    if not token:
        print("FOOTBALL_DATA_API_TOKEN is not set; skipping football-data.org and using fallback sources.")
        return []

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
        print(f"football-data.org request failed: HTTP {error.code} {body}")
        return []
    except URLError as error:
        print(f"football-data.org request failed: {error}")
        return []

    return payload.get("matches", [])


def strip_tags(value):
    return html.unescape(re.sub(r"<[^>]+>", " ", value)).strip()


def native_stats_results():
    request = Request(
        NATIVE_STATS_URL,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"},
    )

    try:
        with urlopen(request, timeout=30) as response:
            page = response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        print(f"native-stats.org request failed: HTTP {error.code} {body}")
        return []
    except URLError as error:
        print(f"native-stats.org request failed: {error}")
        return []

    results = []
    for row in re.findall(r'<tr id="last-(\d+)">(.*?)</tr>', page, flags=re.DOTALL):
        native_id, row_html = row
        provisional = "animate-pulse" in row_html

        date_match = re.search(r"<th>(\d{4})/(\d{2})/(\d{2}),\s*(\d{1,2})h(\d{2})</th>", row_html)
        score_match = re.search(r">\s*(\d+):(\d+)\s*</div>", row_html)
        teams = [
            strip_tags(match)
            for match in re.findall(r'<span class="hidden text-gray-200 align-middle md:inline-block">\s*(.*?)\s*</span>', row_html, flags=re.DOTALL)
        ]
        if not date_match or not score_match or len(teams) < 2:
            continue

        year, month, day, *_ = date_match.groups()
        results.append(
            {
                "utcDate": f"{year}-{month}-{day}T00:00:00Z",
                "home": normalise_team(teams[0]),
                "away": normalise_team(teams[1]),
                "score": {"home": int(score_match.group(1)), "away": int(score_match.group(2))},
                "source": "native-stats.org",
                "sourceMatchId": int(native_id),
                "provisional": provisional,
            }
        )

    return results


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


def load_score_observations():
    if not SCORE_OBSERVATIONS_FILE.exists():
        return {}

    payload = json.loads(SCORE_OBSERVATIONS_FILE.read_text(encoding="utf-8"))
    return {item["id"]: item for item in payload.get("observations", [])}


def write_api_result_cache(results):
    API_RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "football-data.org,native-stats.org",
        "results": sorted(results.values(), key=lambda item: item["sequence"]),
    }
    API_RESULTS_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_score_observations(observations):
    SCORE_OBSERVATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "native-stats.org",
        "policy": {
            "observeAfterKickoffMinutes": int(OBSERVATION_START_DELAY.total_seconds() / 60),
            "stableForMinutes": int(OBSERVATION_STABILITY_WINDOW.total_seconds() / 60),
            "minimumSeenCount": OBSERVATION_MIN_SEEN_COUNT,
        },
        "observations": sorted(observations.values(), key=lambda item: item["sequence"]),
    }
    SCORE_OBSERVATIONS_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_generated_cutoff():
    if not GENERATED_DATA_FILE.exists():
        return None

    text = GENERATED_DATA_FILE.read_text(encoding="utf-8")
    prefix = "window.AVSM_DATA = "
    if not text.startswith(prefix):
        return None

    payload = json.loads(text.removeprefix(prefix).removesuffix(";\n"))
    value = payload.get("predictionStartsAt")
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def sync_results(token, season, dry_run):
    now = datetime.now(timezone.utc)
    wb = load_workbook(FIXTURE_FILE)
    ws = wb[wb.sheetnames[0]]
    header = [cell.value for cell in ws[1]]
    col = {name: index + 1 for index, name in enumerate(header)}

    sheet_rows = {}
    fixtures = []
    for row_number in range(2, ws.max_row + 1):
        home = ws.cell(row_number, col["Home Team"]).value
        away = ws.cell(row_number, col["Away Team"]).value
        kickoff = parse_excel_datetime(ws.cell(row_number, col["Date"]).value)
        key = (normalise_team(home), normalise_team(away), kickoff.date())
        fixture = {
            "row_number": row_number,
            "id": f"epl2026-{int(ws.cell(row_number, col['Match Number']).value)}",
            "sequence": int(ws.cell(row_number, col["Match Number"]).value),
            "gameweek": int(ws.cell(row_number, col["Round Number"]).value),
            "kickoff_dt": kickoff,
            "kickoff": kickoff.isoformat().replace("+00:00", "Z"),
            "home": home,
            "away": away,
        }
        sheet_rows[key] = fixture
        fixtures.append(fixture)

    cached_results = load_api_result_cache()
    score_observations = load_score_observations()
    previous_cutoff = load_generated_cutoff()
    crossed_kickoff = previous_cutoff is None or any(previous_cutoff < fixture["kickoff_dt"] <= now for fixture in fixtures)
    updates = []
    observations_changed = False

    def remove_observation(fixture_id):
        nonlocal observations_changed
        if fixture_id in score_observations:
            observations_changed = True
            if not dry_run:
                score_observations.pop(fixture_id, None)

    def write_cached_result(fixture, result, source_result, source_name=None):
        cached_results[fixture["id"]] = {
            "id": fixture["id"],
            "season": "2026/27",
            "gameweek": fixture["gameweek"],
            "sequence": fixture["sequence"],
            "kickoff": fixture["kickoff"],
            "home": fixture["home"],
            "away": fixture["away"],
            "score": result,
            "source": source_name or source_result["source"],
            "sourceMatchId": source_result.get("sourceMatchId"),
            "settledAt": now.isoformat().replace("+00:00", "Z"),
        }

    def observe_score(fixture, result, source_result):
        nonlocal observations_changed
        if now < fixture["kickoff_dt"] + OBSERVATION_START_DELAY:
            return False

        current = score_observations.get(fixture["id"])
        if not current or current.get("score") != result:
            observation = {
                "id": fixture["id"],
                "season": "2026/27",
                "gameweek": fixture["gameweek"],
                "sequence": fixture["sequence"],
                "kickoff": fixture["kickoff"],
                "home": fixture["home"],
                "away": fixture["away"],
                "score": result,
                "source": source_result["source"],
                "sourceMatchId": source_result.get("sourceMatchId"),
                "firstSeenAt": now.isoformat().replace("+00:00", "Z"),
                "lastSeenAt": now.isoformat().replace("+00:00", "Z"),
                "seenCount": 1,
            }
            observations_changed = True
            if not dry_run:
                score_observations[fixture["id"]] = observation
            return False

        first_seen = datetime.fromisoformat(current["firstSeenAt"].replace("Z", "+00:00")).astimezone(timezone.utc)
        seen_count = int(current.get("seenCount", 1)) + 1
        observations_changed = True
        if not dry_run:
            current["lastSeenAt"] = now.isoformat().replace("+00:00", "Z")
            current["seenCount"] = seen_count
            current["sourceMatchId"] = source_result.get("sourceMatchId")

        return now - first_seen >= OBSERVATION_STABILITY_WINDOW and seen_count >= OBSERVATION_MIN_SEEN_COUNT

    def cache_result(source_result):
        utc_date = datetime.fromisoformat(source_result["utcDate"].replace("Z", "+00:00")).astimezone(timezone.utc)
        result = source_result["score"]
        candidates = [
            (source_result["home"], source_result["away"], utc_date.date()),
            (source_result["home"], source_result["away"], (utc_date - timedelta(days=1)).date()),
            (source_result["home"], source_result["away"], (utc_date + timedelta(days=1)).date()),
        ]
        fixture = next((sheet_rows[key] for key in candidates if key in sheet_rows), None)
        if not fixture:
            return

        cached = cached_results.get(fixture["id"])
        if cached and cached.get("score") == result:
            remove_observation(fixture["id"])
            return

        source_name = source_result["source"]
        if source_result.get("provisional"):
            if not observe_score(fixture, result, source_result):
                return
            source_name = f"{source_name}-stable-score"

        previous = format_score(cached["score"]) if cached else "blank"
        updates.append((fixture["home"], fixture["away"], previous, format_score(result), source_name))
        if not dry_run:
            write_cached_result(fixture, result, source_result, source_name)
            remove_observation(fixture["id"])

    for match in football_data_matches(token, season):
        if match.get("status") != "FINISHED":
            continue

        result = result_from_match(match)
        if not result:
            continue

        cache_result(
            {
                "utcDate": match["utcDate"],
                "home": normalise_team(match.get("homeTeam", {}).get("name")),
                "away": normalise_team(match.get("awayTeam", {}).get("name")),
                "score": result,
                "source": "football-data.org",
                "sourceMatchId": match.get("id"),
            }
        )

    for result in native_stats_results():
        cache_result(result)

    if not dry_run and updates:
        write_api_result_cache(cached_results)

    if not dry_run and observations_changed:
        write_score_observations(score_observations)

    if not dry_run and (updates or crossed_kickoff):
        subprocess.run([sys.executable, str(BUILD_SCRIPT)], cwd=ROOT, check=True)

    return updates, crossed_kickoff, observations_changed


def main():
    parser = argparse.ArgumentParser(description="Sync Premier League final scores into the generated API result cache.")
    parser.add_argument("--season", default="2026", help="Season start year for football-data.org, e.g. 2026 for 2026/27.")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing the workbook.")
    args = parser.parse_args()

    load_env_file(ENV_FILE)
    token = os.environ.get("FOOTBALL_DATA_API_TOKEN")

    updates, crossed_kickoff, observations_changed = sync_results(token, args.season, args.dry_run)
    if not updates:
        print("No new final scores found.")
        if crossed_kickoff and not args.dry_run:
            print("Regenerated app data for fixture kickoff changes.")
        if observations_changed and not args.dry_run:
            print("Updated post-match score observations.")
        return

    verb = "Would update" if args.dry_run else "Updated"
    print(f"{verb} {len(updates)} result(s):")
    for home, away, previous, new, source in updates:
        print(f"- {home} vs {away}: {previous} -> {new} ({source})")


if __name__ == "__main__":
    main()
