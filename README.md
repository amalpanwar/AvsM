# A vs M

Private Premier League pint prediction app for Amal and Matt, built from `A_vs_M_App_Development_Blueprint.docx`.

## Run Locally

Build the Excel-driven prediction data, then run the local app:

```bash
python3 scripts/build_data.py
python3 -m http.server 4174
```

Then visit `http://localhost:4174`.

If you have `npm` installed, `npm run build:data` and `npm run serve` are also wired up.

## Automatic Result Sync

Google match cards are not a stable public data API, so the app does not scrape Google Search results. Use a football results API instead.

On GitHub, the `Sync Premier League Results` workflow uses the repository secret named `football-data-api-token`. The workflow runs four times per day, writes finished Premier League scores into `epl-2026-GMTStandardTime.xlsx`, regenerates `generated-data.js`, and pushes the update back to this repo.

To run the same sync locally, either export the token in your shell or create a private `.env` file:

```bash
cp .env.example .env
# Edit .env and replace your_api_token_here with your real key.
python3 scripts/sync_results.py
```

The `.env` file is ignored by Git and should stay private.

That script pulls finished Premier League matches, writes final scores into `epl-2026-GMTStandardTime.xlsx`, then regenerates `generated-data.js`. Refresh the app afterwards. Any saved pick for a newly finished fixture is settled automatically.

## MVP Scope

- Private Amal/Matt login.
- Fixture cards generated from `epl-2026-GMTStandardTime.xlsx`, starting after the current date/time.
- Team strengths calculated from completed `epl-2025-GMTStandardTime.xlsx` results.
- Weighted Poisson match probabilities converted to locked 1/2/3 pint values.
- Pick flow where the first picker chooses one team and the other player is auto-assigned the opposite team.
- New results added to `epl-2026-GMTStandardTime.xlsx` auto-settle matching saved picks after `python3 scripts/build_data.py` is rerun.
- Draws settle as void for 0 pints each.
- Leaderboard is calculated from the ledger, not stored as a separate total.
- No bookmaker odds or model probabilities are displayed.

This local MVP uses generated Excel data plus localStorage persistence for private picks and settlements. The code keeps hidden model fields separate from the UI so a future FastAPI/PostgreSQL backend can replace the local store.

## Session and Settlement Notes

The current local app stores the signed-in user, picks, settlements and ledger in this browser's `localStorage`. Refreshing the page keeps the session. Pressing `Reset local picks` now clears picks and ledger but keeps the current login.

For automatic settlement, run `python3 scripts/sync_results.py`, then refresh the app. If Amal or Matt had already made a pick for that fixture, the app settles it automatically using the locked pint values. Manual scoring is only a local fallback while testing.

Once a fixture has a ledger entry, settlement is locked and will not be recalculated by later score changes.
