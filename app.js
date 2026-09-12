const STORAGE_KEY = "avsm-state-v2";
const MATCH_SETTLEMENT_LOCK_MS = 2 * 60 * 60 * 1000;

const USERS = {
  A: { code: "A", name: "Amal" },
  M: { code: "M", name: "Matt" },
};

const generated = window.AVSM_DATA || {
  generatedAt: new Date().toISOString(),
  predictionStartsAt: new Date().toISOString(),
  sourceFiles: { strengths: "missing", fixtures: "missing" },
  model: {},
  fixtures: [],
  recordedResults: [],
};

let state = loadState();
reconcileRecordedResults();

function loadState() {
  const saved = localStorage.getItem(STORAGE_KEY);
  const persisted = saved ? JSON.parse(saved) : {};

  return {
    currentUser: persisted.currentUser || null,
    activeView: persisted.activeView || "dashboard",
    picks: persisted.picks || {},
    ledger: persisted.ledger || [],
    localResults: persisted.localResults || {},
  };
}

function saveState() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      currentUser: state.currentUser,
      activeView: state.activeView,
      picks: state.picks,
      ledger: state.ledger,
      localResults: state.localResults,
    }),
  );
}

function allFixtures() {
  return generated.fixtures.map((fixture) => {
    const localResult = state.localResults[fixture.id];
    if (!localResult) return fixture;
    return {
      ...fixture,
      status: localResult.status,
      score: localResult.score,
    };
  });
}

function recordedFixtures() {
  return generated.recordedResults.map((fixture) => {
    const localResult = state.localResults[fixture.id];
    if (!localResult) return { ...fixture, source: "api" };
    return { ...fixture, status: localResult.status, score: localResult.score, source: localResult.source || "manual" };
  });
}

function openFixtures() {
  return allFixtures().filter((fixture) => fixture.status === "open");
}

function historyFixtures() {
  return [
    ...recordedFixtures(),
    ...allFixtures().filter((fixture) => fixture.status === "settled" || fixture.status === "void"),
  ].sort((a, b) => new Date(b.kickoff) - new Date(a.kickoff));
}

function otherUser(code) {
  return code === "A" ? "M" : "A";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatKickoff(value) {
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(value));
}

function shortDateTime(value) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(value));
}

function totals() {
  return state.ledger.reduce(
    (acc, item) => {
      acc[item.userId] += item.pintsChange;
      return acc;
    },
    { A: 0, M: 0 },
  );
}

function leaderText() {
  const score = totals();
  const diff = score.A - score.M;
  if (diff === 0) return "Level on pints";
  const leader = diff > 0 ? "A" : "M";
  return `${leader} leads by ${Math.abs(diff)} ${Math.abs(diff) === 1 ? "pint" : "pints"}`;
}

function fixturePick(fixture) {
  return state.picks[fixture.id] || null;
}

function teamPints(fixture, team) {
  return team === fixture.home ? fixture.homePints : fixture.awayPints;
}

function teamOwner(fixture, team) {
  const pick = fixturePick(fixture);
  if (!pick) return null;
  if (pick.chosenTeam === team) return pick.firstPickerUserId;
  if (pick.autoAssignedTeam === team) return pick.otherUserId;
  return null;
}

function canPick(fixture) {
  return (
    state.currentUser === fixture.firstPicker &&
    fixture.status === "open" &&
    !fixturePick(fixture) &&
    !hasLedgerEntry(fixture.id) &&
    !kickoffHasStarted(fixture)
  );
}

function hasLedgerEntry(fixtureId) {
  return state.ledger.some((item) => item.fixtureId === fixtureId);
}

function fixtureLedger(fixtureId) {
  return state.ledger.filter((item) => item.fixtureId === fixtureId);
}

function isSettledFixture(fixture) {
  return hasLedgerEntry(fixture.id) || fixture.status === "settled" || fixture.status === "void" || fixture.status === "recorded";
}

function matchHasPassed(fixture) {
  return Date.now() >= new Date(fixture.kickoff).getTime() + MATCH_SETTLEMENT_LOCK_MS;
}

function kickoffHasStarted(fixture) {
  return Date.now() >= new Date(fixture.kickoff).getTime();
}

function canManualSettle(fixture) {
  return fixture.status === "open" && !hasLedgerEntry(fixture.id) && !matchHasPassed(fixture);
}

function canResetPick(fixture) {
  const pick = fixturePick(fixture);
  const result = state.localResults[fixture.id];
  return Boolean(
    pick &&
      state.currentUser === pick.firstPickerUserId &&
      !kickoffHasStarted(fixture) &&
      result?.source !== "api" &&
      !result?.locked,
  );
}

function sameScore(left, right) {
  return Boolean(left && right && left.home === right.home && left.away === right.away);
}

function ledgerRowsForResult(fixture, pick, createdAt, source) {
  const homeScore = fixture.score.home;
  const awayScore = fixture.score.away;

  if (homeScore === awayScore) {
    return [
      { id: `${fixture.id}-A-void`, fixtureId: fixture.id, userId: "A", pintsChange: 0, reason: "Draw void", source, createdAt },
      { id: `${fixture.id}-M-void`, fixtureId: fixture.id, userId: "M", pintsChange: 0, reason: "Draw void", source, createdAt },
    ];
  }

  const winningTeam = homeScore > awayScore ? fixture.home : fixture.away;
  const winningUser =
    pick.chosenTeam === winningTeam ? pick.firstPickerUserId : pick.otherUserId;

  return [
    {
      id: `${fixture.id}-${winningUser}-win`,
      fixtureId: fixture.id,
      userId: winningUser,
      pintsChange: teamPints(fixture, winningTeam),
      reason: `${winningTeam} won`,
      source,
      createdAt,
    },
  ];
}

function reconcileRecordedResults() {
  let changed = false;
  const createdAt = generated.generatedAt || new Date().toISOString();

  for (const fixture of generated.recordedResults) {
    const pick = state.picks[fixture.id];
    const localResult = state.localResults[fixture.id];
    const ledger = fixtureLedger(fixture.id);
    const alreadyApiSettled =
      localResult?.source === "api" &&
      sameScore(localResult.score, fixture.score) &&
      ledger.length > 0 &&
      ledger.every((item) => item.source === "api");

    if (!pick || !fixture.score || alreadyApiSettled) continue;

    state.localResults[fixture.id] = {
      status: fixture.score.home === fixture.score.away ? "void" : "settled",
      score: fixture.score,
      source: "api",
      locked: true,
    };
    state.ledger = state.ledger.filter((item) => item.fixtureId !== fixture.id);
    state.ledger.push(...ledgerRowsForResult(fixture, pick, createdAt, "api"));
    changed = true;
  }

  if (changed) saveState();
}

function placePick(fixtureId, team) {
  const fixture = allFixtures().find((item) => item.id === fixtureId);
  if (!fixture || !canPick(fixture)) return;

  state.picks[fixtureId] = {
    fixtureId,
    firstPickerUserId: state.currentUser,
    chosenTeam: team,
    otherUserId: otherUser(state.currentUser),
    autoAssignedTeam: team === fixture.home ? fixture.away : fixture.home,
    placedAt: new Date().toISOString(),
  };
  saveState();
  render();
}

function resetFixturePick(fixtureId) {
  const fixture = allFixtures().find((item) => item.id === fixtureId);
  if (!fixture || !canResetPick(fixture)) return;

  delete state.picks[fixtureId];
  delete state.localResults[fixtureId];
  state.ledger = state.ledger.filter((item) => item.fixtureId !== fixtureId);
  saveState();
  render();
}

function settleFixture(fixtureId, homeScore, awayScore) {
  const fixture = allFixtures().find((item) => item.id === fixtureId);
  const pick = state.picks[fixtureId];
  if (!fixture || !pick || !canManualSettle(fixture)) return;

  const score = { home: homeScore, away: awayScore };
  const createdAt = new Date().toISOString();
  state.ledger = state.ledger.filter((item) => item.fixtureId !== fixtureId);
  const fixtureWithScore = { ...fixture, score };

  if (homeScore === awayScore) {
    state.localResults[fixtureId] = { status: "void", score, source: "manual", locked: false };
    state.ledger.push(...ledgerRowsForResult(fixtureWithScore, pick, createdAt, "manual"));
  } else {
    state.localResults[fixtureId] = { status: "settled", score, source: "manual", locked: false };
    state.ledger.push(...ledgerRowsForResult(fixtureWithScore, pick, createdAt, "manual"));
  }

  saveState();
  render();
}

function resetLocalGame() {
  const currentUser = state.currentUser;
  const resettableFixtureIds = new Set(
    allFixtures()
      .filter((fixture) => canResetPick(fixture))
      .map((fixture) => fixture.id),
  );

  state = {
    currentUser,
    activeView: "fixtures",
    picks: Object.fromEntries(Object.entries(state.picks).filter(([fixtureId]) => !resettableFixtureIds.has(fixtureId))),
    ledger: state.ledger.filter((item) => !resettableFixtureIds.has(item.fixtureId)),
    localResults: Object.fromEntries(Object.entries(state.localResults).filter(([fixtureId]) => !resettableFixtureIds.has(fixtureId))),
  };
  saveState();
  render();
}

function setView(view) {
  state.activeView = view;
  saveState();
  render();
}

function login(code) {
  state.currentUser = code;
  state.activeView = "dashboard";
  saveState();
  render();
}

function logout() {
  state.currentUser = null;
  saveState();
  render();
}

function appShell(content) {
  const user = state.currentUser ? USERS[state.currentUser] : null;
  return `
    <header class="topbar">
      <div class="brand">
        <img src="assets/pint.svg" alt="" />
        <div>
          <strong>A vs M</strong>
          <span>Premier League pint picks</span>
        </div>
      </div>
      ${user ? `<div class="user-pill"><span>${user.code}</span>${user.name}</div>` : ""}
    </header>
    ${content}
  `;
}

function renderLogin() {
  return appShell(`
    <main class="login-screen">
      <section class="login-panel">
        <div class="mark"><img src="assets/pint.svg" alt="" /></div>
        <h1>A vs M</h1>
        <p>Private pint predictions for Amal and Matt.</p>
        <div class="login-actions">
          <button class="primary" data-action="login" data-user="A">Continue as Amal</button>
          <button class="secondary" data-action="login" data-user="M">Continue as Matt</button>
        </div>
      </section>
    </main>
  `);
}

function nav() {
  const items = [
    ["dashboard", "Dashboard"],
    ["fixtures", "Fixtures"],
    ["history", "History"],
    ["leaderboard", "Leaderboard"],
  ];

  return `
    <nav class="tabs" aria-label="Primary">
      ${items
        .map(
          ([id, label]) =>
            `<button class="${state.activeView === id ? "active" : ""}" data-action="view" data-view="${id}">${label}</button>`,
        )
        .join("")}
    </nav>
  `;
}

function dataNote() {
  return `
      <section class="data-note">
      <strong>${generated.fixtures.length} upcoming fixtures</strong>
      <span>Predictions start ${shortDateTime(generated.predictionStartsAt)} from ${escapeHtml(generated.sourceFiles.fixtures)}. New Excel results auto-settle saved picks.</span>
    </section>
  `;
}

function renderDashboard() {
  const score = totals();
  const fixtures = openFixtures();
  const nextRequired = fixtures.find((fixture) => !fixturePick(fixture) && fixture.firstPicker === state.currentUser);
  const nextFixtures = fixtures.slice(0, 3);

  return `
    <main class="layout">
      ${nav()}
      <section class="scoreboard">
        <div>
          <span class="label">Season lead</span>
          <h1 class="scoreboard-title"><img src="assets/pint.svg" alt="" />${leaderText()}</h1>
        </div>
        <div class="totals">
          <div><span>A</span><strong>${score.A}</strong><small>Amal</small></div>
          <div><span>M</span><strong>${score.M}</strong><small>Matt</small></div>
        </div>
      </section>
      ${dataNote()}
      ${
        nextRequired
          ? `<section class="notice">
              <span class="status-dot"></span>
              <div><strong>Your next first pick</strong><p>${escapeHtml(nextRequired.home)} vs ${escapeHtml(nextRequired.away)} closes before kickoff.</p></div>
              <button data-action="view" data-view="fixtures">Pick</button>
            </section>`
          : `<section class="notice muted">
              <span class="status-dot"></span>
              <div><strong>No first pick waiting</strong><p>Open fixtures can still be reviewed from the fixture list.</p></div>
            </section>`
      }
      <section class="section-heading">
        <h2>Next Fixtures</h2>
      </section>
      <div class="fixture-grid">
        ${nextFixtures.map(renderFixtureCard).join("") || `<p class="empty-state">No upcoming fixtures after the current cutoff.</p>`}
      </div>
    </main>
  `;
}

function renderFixtures() {
  const fixtures = openFixtures();
  return `
    <main class="layout">
      ${nav()}
      <section class="section-heading">
        <h1>Fixtures</h1>
        <button class="ghost" data-action="reset">Reset my picks</button>
      </section>
      ${dataNote()}
      <div class="fixture-grid">
        ${fixtures.map(renderFixtureCard).join("") || `<p class="empty-state">No upcoming fixtures after the current cutoff.</p>`}
      </div>
    </main>
  `;
}

function renderFixtureCard(fixture) {
  const pick = fixturePick(fixture);
  const locked = Boolean(fixture.pintsLockedAt);
  const firstPickerName = USERS[fixture.firstPicker].name;
  const settled = isSettledFixture(fixture);

  return `
    <article class="fixture-card">
      <div class="fixture-meta">
        <span>#${fixture.sequence} - GW${fixture.gameweek}</span>
        <span>${formatKickoff(fixture.kickoff)}</span>
      </div>
      <div class="fixture-title">
        <h3>${escapeHtml(fixture.home)} vs ${escapeHtml(fixture.away)}</h3>
        <span class="${locked ? "badge locked" : "badge"}">${locked ? "Pints locked" : "Pending"}</span>
      </div>
      <div class="venue">${escapeHtml(fixture.location || "Premier League")}</div>
      <div class="teams">
        ${renderTeamRow(fixture, fixture.home, fixture.homePints)}
        ${renderTeamRow(fixture, fixture.away, fixture.awayPints)}
      </div>
      <div class="fixture-footer">
        <strong>${fixture.firstPicker} picks first</strong>
        <span>${firstPickerName}</span>
      </div>
      ${
        pick
          ? `<div class="assignment">
              <strong>${USERS[pick.firstPickerUserId].name} picked ${escapeHtml(pick.chosenTeam)}</strong>
              <span>${USERS[pick.otherUserId].name} auto-assigned ${escapeHtml(pick.autoAssignedTeam)}</span>
              ${canResetPick(fixture) ? `<button class="link-button" data-action="reset-pick" data-fixture-id="${fixture.id}">Reset my pick</button>` : ""}
            </div>
            ${
              settled
                ? `<div class="assignment locked-final">${fixture.status === "recorded" || state.localResults[fixture.id]?.source === "api" ? "API settlement locked." : "Test settlement active."}</div>`
                : canManualSettle(fixture)
                  ? renderSettleControls(fixture)
                  : `<div class="assignment empty">Awaiting final score sync.</div>`
            }`
          : canPick(fixture)
            ? `<div class="pick-actions">
                <button data-action="pick" data-fixture-id="${fixture.id}" data-team="${escapeHtml(fixture.home)}">Pick ${escapeHtml(fixture.home)}</button>
                <button data-action="pick" data-fixture-id="${fixture.id}" data-team="${escapeHtml(fixture.away)}">Pick ${escapeHtml(fixture.away)}</button>
              </div>`
            : `<div class="assignment empty">Waiting for ${firstPickerName}'s first pick.</div>`
      }
    </article>
  `;
}

function renderTeamRow(fixture, team, pints) {
  const owner = teamOwner(fixture, team);
  return `
    <div class="team-row">
      <div>
        <strong>${escapeHtml(team)}</strong>
        ${owner ? `<span>${USERS[owner].name}</span>` : ""}
      </div>
      <b>${pints} ${pints === 1 ? "pint" : "pints"}</b>
    </div>
  `;
}

function renderSettleControls(fixture) {
  return `
    <form class="settle-form" data-action="settle" data-fixture-id="${fixture.id}">
      <label>${escapeHtml(fixture.home)}<input name="home" type="number" min="0" value="1" /></label>
      <label>${escapeHtml(fixture.away)}<input name="away" type="number" min="0" value="0" /></label>
      <button type="submit">Settle</button>
    </form>
  `;
}

function renderHistory() {
  const fixtures = historyFixtures();
  return `
    <main class="layout">
      ${nav()}
      <section class="section-heading">
        <h1>History</h1>
      </section>
      <div class="history-list">
        ${fixtures.map(renderHistoryRow).join("") || `<p class="empty-state">No completed fixtures yet.</p>`}
      </div>
    </main>
  `;
}

function renderHistoryRow(fixture) {
  const result = fixture.score ? `${fixture.score.home}-${fixture.score.away}` : "-";
  const ledger = state.ledger.filter((item) => item.fixtureId === fixture.id && item.pintsChange > 0);
  let outcome = "Recorded result";
  let outcomeClass = "";
  if (fixture.status === "void") {
    outcome = "VOID";
    outcomeClass = "void";
  } else if (ledger.length) {
    outcome = `${USERS[ledger[0].userId].name} +${ledger[0].pintsChange}`;
  }

  return `
    <article class="history-row">
      <div>
        <strong>${escapeHtml(fixture.home)} ${result} ${escapeHtml(fixture.away)}</strong>
        <span>${formatKickoff(fixture.kickoff)}</span>
      </div>
      <b class="${outcomeClass}">${outcome}</b>
    </article>
  `;
}

function renderLeaderboard() {
  const score = totals();
  const byGameweek = state.ledger.reduce((acc, item) => {
    const fixture = allFixtures().find((match) => match.id === item.fixtureId);
    const key = fixture ? `Gameweek ${fixture.gameweek}` : "Other";
    acc[key] ||= { A: 0, M: 0 };
    acc[key][item.userId] += item.pintsChange;
    return acc;
  }, {});

  return `
    <main class="layout">
      ${nav()}
      <section class="scoreboard compact">
        <div>
          <span class="label">Ledger total</span>
          <h1 class="scoreboard-title"><img src="assets/pint.svg" alt="" />${leaderText()}</h1>
        </div>
        <div class="totals">
          <div><span>A</span><strong>${score.A}</strong><small>Amal</small></div>
          <div><span>M</span><strong>${score.M}</strong><small>Matt</small></div>
        </div>
      </section>
      <section class="table-wrap">
        <table>
          <thead><tr><th>Period</th><th>Amal</th><th>Matt</th><th>Lead</th></tr></thead>
          <tbody>
            ${
              Object.entries(byGameweek)
                .map(([label, values]) => {
                  const diff = values.A - values.M;
                  const lead = diff === 0 ? "Level" : `${diff > 0 ? "A" : "M"} +${Math.abs(diff)}`;
                  return `<tr><td>${label}</td><td>${values.A}</td><td>${values.M}</td><td>${lead}</td></tr>`;
                })
                .join("") || `<tr><td colspan="4">No ledger entries yet.</td></tr>`
            }
          </tbody>
        </table>
      </section>
    </main>
  `;
}

function renderAuthed() {
  const views = {
    dashboard: renderDashboard,
    fixtures: renderFixtures,
    history: renderHistory,
    leaderboard: renderLeaderboard,
  };

  return appShell(`
    <button class="logout" data-action="logout">Sign out</button>
    ${views[state.activeView]()}
  `);
}

function render() {
  document.getElementById("app").innerHTML = state.currentUser ? renderAuthed() : renderLogin();
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;

  const { action } = button.dataset;
  if (action === "login") login(button.dataset.user);
  if (action === "logout") logout();
  if (action === "view") setView(button.dataset.view);
  if (action === "reset") resetLocalGame();
  if (action === "reset-pick") resetFixturePick(button.dataset.fixtureId);
  if (action === "pick") placePick(button.dataset.fixtureId, button.dataset.team);
});

document.addEventListener("submit", (event) => {
  const form = event.target.closest("form[data-action='settle']");
  if (!form) return;
  event.preventDefault();
  settleFixture(form.dataset.fixtureId, Number(form.home.value), Number(form.away.value));
});

render();
