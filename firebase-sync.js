import { initializeApp } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js";
import { getAuth, signInAnonymously } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js";
import {
  getDatabase,
  onValue,
  ref,
  runTransaction,
} from "https://www.gstatic.com/firebasejs/12.19.0/firebase-database.js";

const SCHEMA_VERSION = 1;
const ROOT_PATH = "avsm/seasons/epl-2026-27";

function ledgerMap(ledger) {
  return Object.fromEntries((ledger || []).map((item) => [item.id, item]));
}

function normalizeSharedState(value = {}) {
  return {
    schemaVersion: SCHEMA_VERSION,
    picks: value.picks || {},
    localResults: value.localResults || {},
    ledger: Array.isArray(value.ledger) ? ledgerMap(value.ledger) : value.ledger || {},
    updatedAt: value.updatedAt || Date.now(),
  };
}

function mergeForMigration(remoteValue, localValue) {
  const remote = normalizeSharedState(remoteValue);
  const local = normalizeSharedState(localValue);

  return {
    ...remote,
    picks: { ...local.picks, ...remote.picks },
    localResults: { ...local.localResults, ...remote.localResults },
    ledger: { ...local.ledger, ...remote.ledger },
    updatedAt: Date.now(),
  };
}

function fixturePayload(sharedState, fixtureId) {
  return {
    pick: sharedState.picks[fixtureId] || null,
    localResult: sharedState.localResults[fixtureId] || null,
    ledger: sharedState.ledger.filter((item) => item.fixtureId === fixtureId),
  };
}

export async function connectSharedStore({ config, initialState, migrateLocal, onState, onStatus }) {
  onStatus("connecting");

  const app = initializeApp(config);
  const auth = getAuth(app);
  await signInAnonymously(auth);

  const database = getDatabase(app);
  const rootRef = ref(database, ROOT_PATH);
  let connected = false;

  onValue(ref(database, ".info/connected"), (snapshot) => {
    connected = snapshot.val() === true;
    onStatus(connected ? "online" : "offline");
  });

  const bootstrap = await runTransaction(rootRef, (current) => {
    if (!current) return normalizeSharedState(initialState);
    return migrateLocal ? mergeForMigration(current, initialState) : current;
  });

  const bootstrappedState = normalizeSharedState(bootstrap.snapshot.val());
  onState({
    picks: bootstrappedState.picks,
    localResults: bootstrappedState.localResults,
    ledger: Object.values(bootstrappedState.ledger),
  });

  onValue(
    rootRef,
    (snapshot) => {
      const shared = normalizeSharedState(snapshot.val());
      onState({
        picks: shared.picks,
        localResults: shared.localResults,
        ledger: Object.values(shared.ledger),
      });
    },
    () => onStatus("error"),
  );

  async function writeFixture(fixtureId, sharedState, { onlyIfMissing = false } = {}) {
    onStatus("syncing");
    const payload = fixturePayload(sharedState, fixtureId);

    await runTransaction(rootRef, (currentValue) => {
      const current = normalizeSharedState(currentValue);
      if (onlyIfMissing && current.picks[fixtureId]) return;

      if (payload.pick) current.picks[fixtureId] = payload.pick;
      else delete current.picks[fixtureId];

      if (payload.localResult) current.localResults[fixtureId] = payload.localResult;
      else delete current.localResults[fixtureId];

      for (const [entryId, item] of Object.entries(current.ledger)) {
        if (item.fixtureId === fixtureId) delete current.ledger[entryId];
      }
      Object.assign(current.ledger, ledgerMap(payload.ledger));
      current.updatedAt = Date.now();
      return current;
    });

    onStatus(connected ? "online" : "offline");
  }

  return { writeFixture };
}
