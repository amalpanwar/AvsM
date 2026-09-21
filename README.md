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

## Shared Picks Between Android and Web

The app can use Firebase Realtime Database to keep picks, test settlements and the official ledger synchronized between the Android WebView and every browser. Login choice and the selected tab remain local to each device.

One-time Firebase setup:

1. Create a Firebase project and register a Web app.
2. Create a Realtime Database. Start in locked mode and copy its database URL.
3. In Authentication -> Sign-in method, enable Anonymous authentication.
4. In Realtime Database -> Rules, paste the contents of `database.rules.json` and publish the rules.
5. Copy the Firebase Web app configuration values into `firebase-config.js`.
6. Commit and push `firebase-config.js`, then wait for GitHub Pages to deploy.

Firebase Web configuration values are identifiers, not private credentials, and are expected to be present in client code. The database rules require a Firebase-authenticated session. The football-data.org API token remains a private GitHub Actions secret and must never be placed in `firebase-config.js`.

On the first launch after Firebase is enabled, each device merges its existing local picks into the shared database once. The header displays `Synced` when the live connection is active. A pick made in the APK should then appear on GitHub Pages immediately without rebuilding the APK; the other open client receives the change through Firebase's real-time listener.

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

On GitHub, the `Sync Premier League Results` workflow uses the repository secret named `FOOTBALL_DATA_API_TOKEN`. The workflow runs every 30 minutes, writes finished Premier League scores into `data/api-results.json`, regenerates `generated-data.js`, and pushes the update back to this repo. It uses football-data.org first and Native Stats as a fallback. If Native Stats still marks a score as live/uncertain, the workflow starts observing it two hours after kickoff, checks again on each 30-minute run, and only promotes that score to a settled result after it has remained unchanged for at least one hour. If football-data.org is unavailable or the token is missing, the fallback still runs so past fixtures can continue to update. The Excel workbook remains the fixture source and does not need to be modified for API settlement.

GitHub Actions cannot create true per-fixture dynamic timers from a static GitHub Pages app. Instead, the 30-minute sync cadence checks football-data.org for finished matches, observes Native Stats fallback scores after the estimated full-time window, and regenerates app data when fixtures cross kickoff. In practice, a past fixture appears in History as awaiting final score first, then updates after football-data.org marks the match `FINISHED` or after the Native Stats fallback score passes the stability check, the next scheduled sync runs, and GitHub Pages redeploys.

The page loads `generated-data.js` with a cache-busting query string so browsers and Android WebView fetch the latest generated fixture/history data after each refresh.

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

The app keeps a local cache for resilience and uses Firebase Realtime Database for cross-device picks and settlements when `firebase-config.js` is configured.

## Session and Settlement Notes

The signed-in user and selected view remain in this browser's `localStorage`. Picks, settlements and ledger are also cached locally, then synchronized through Firebase when configured. Refreshing the page keeps the session. Pressing `Reset my picks` keeps the current login and clears only that user's resettable test/future picks and manual settlements. The active storage namespace is `avsm-state-v3`, which resets older test leaderboard data.

For automatic settlement, run `python3 scripts/sync_results.py`, then refresh the app. If Amal or Matt had already made a pick for that fixture, the app settles it automatically using the locked pint values. Manual scoring is only a local fallback while testing. API results are stored in `data/api-results.json`, so the settlement flow does not require Excel write access.

Picks can be reset only before kickoff, and only by the logged-in user who placed the first pick for that fixture. The other user cannot reset someone else's pick.

Manual scores can only be entered before the estimated full-time lock window and are treated as test settlements. The app uses kickoff time plus two hours because the fixture workbook does not contain final-whistle timestamps. Once that window has passed, the app waits for API/Excel sync instead of accepting a manual score. When an API/Excel result appears, it overrides any earlier manual test score for that fixture, writes the official ledger entry, and locks settlement permanently.

Only official result sync entries count toward the leaderboard. Manual test settlements do not affect the season totals.
