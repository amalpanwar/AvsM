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

## GitHub Pages Deployment

One-time setup in GitHub:

1. Open `amalpanwar/AvsM`.
2. Go to Settings -> Pages.
3. Under Build and deployment, set Source to GitHub Actions.
4. Save the setting, then rerun the `Publish GitHub Pages` workflow.

The workflow publishes the static app from the repository root.

## Android Release Artifacts

The repo includes a small Android WebView wrapper in `android/`. It loads the live app at `https://amalpanwar.github.io/AvsM/`, so the Android build stays current with the deployed web app.

Google Play requires every uploaded `.aab` to be signed. The GitHub workflow signs the bundle and APK when these repository secrets exist:

- `ANDROID_KEYSTORE_BASE64`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`

Create the upload keystore locally with Android Studio or `keytool`, then base64 encode the `.jks` file and save that encoded text as `ANDROID_KEYSTORE_BASE64`. Keep the original `.jks` file and passwords private because the same upload key is needed for future app updates.

To generate Android release files in GitHub:

1. Open the repo's Actions tab.
2. Select `Build Android Release Artifacts`.
3. Run the workflow on `main`.
4. Download `avsm-release-aab` for Google Play.
5. Download `avsm-release-apk` for direct Android sharing.

The Play Console upload file is `app-release.aab`. The direct-install file is `app-release.apk`.

## Automatic Result Sync

Google match cards are not a stable public data API, so the app does not scrape Google Search results. Use a football results API instead.

On GitHub, the `Sync Premier League Results` workflow uses the repository secret named `FOOTBALL_DATA_API_TOKEN`. The workflow runs four times per day, writes finished Premier League scores into `data/api-results.json`, regenerates `generated-data.js`, and pushes the update back to this repo. The Excel workbook remains the fixture source and does not need to be modified for API settlement.

To run the same sync locally, either export the token in your shell or create a private `.env` file:

```bash
cp .env.example .env
# Edit .env and replace your_api_token_here with your real key.
python3 scripts/sync_results.py
```

The `.env` file is ignored by Git and should stay private.

That script pulls finished Premier League matches, writes final scores into `data/api-results.json`, then regenerates `generated-data.js`. Refresh the app afterwards. Any saved pick for a newly finished fixture is settled automatically.

## MVP Scope

- Private Amal/Matt login.
- Fixture cards generated from `epl-2026-GMTStandardTime.xlsx`, starting after the current date/time.
- Fixture times in the Excel files are interpreted as UK local time (`Europe/London`) so BST/GMT daylight saving changes are handled before the app stores UTC kickoff times. The app displays those UTC kickoff times in the viewer's device timezone, so London viewers see London time and Delhi viewers see IST.
- Team strengths calculated from completed `epl-2025-GMTStandardTime.xlsx` results.
- Weighted Poisson match probabilities converted to locked 1/2/3 pint values.
- Pick flow where the first picker chooses one team and the other player is auto-assigned the opposite team.
- API results added to `data/api-results.json` auto-settle matching saved picks after `python3 scripts/build_data.py` is rerun.
- Draws settle as void for 0 pints each.
- Leaderboard is calculated from the ledger, not stored as a separate total.
- No bookmaker odds or model probabilities are displayed.

This local MVP uses generated Excel data plus localStorage persistence for private picks and settlements. The code keeps hidden model fields separate from the UI so a future FastAPI/PostgreSQL backend can replace the local store.

## Session and Settlement Notes

The current local app stores the signed-in user, picks, settlements and ledger in this browser's `localStorage`. Refreshing the page keeps the session. Pressing `Reset my picks` keeps the current login and clears only that user's resettable test/future picks and manual settlements.

For automatic settlement, run `python3 scripts/sync_results.py`, then refresh the app. If Amal or Matt had already made a pick for that fixture, the app settles it automatically using the locked pint values. Manual scoring is only a local fallback while testing. API results are stored in `data/api-results.json`, so the settlement flow does not require Excel write access.

Picks can be reset only before kickoff, and only by the logged-in user who placed the first pick for that fixture. The other user cannot reset someone else's pick.

Manual scores can only be entered before the estimated full-time lock window and are treated as test settlements. The app uses kickoff time plus two hours because the fixture workbook does not contain final-whistle timestamps. Once that window has passed, the app waits for API/Excel sync instead of accepting a manual score. When an API/Excel result appears, it overrides any earlier manual test score for that fixture, writes the official ledger entry, and locks settlement permanently.
