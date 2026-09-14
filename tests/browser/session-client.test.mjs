import test from "node:test";
import assert from "node:assert/strict";
import {DashboardSessionClient} from "../../clients/dashboard/session-client.mjs";

const pair = {access_token: "test-access", refresh_token: "r".repeat(32), token_type: "bearer", expires_in: 60};
const response = (data = pair, status = 200) => ({ok: status >= 200 && status < 300, status,
  text: async () => JSON.stringify(data)});
function fixture(fetcher = async () => response()) {
  const jobs = new Map(); let next = 0;
  const states = []; const starts = []; let stops = 0;
  const client = new DashboardSessionClient({fetcher, stream: {
    start: token => starts.push(token), stop: () => stops++
  }, onState: state => states.push(state), clock: {
    setTimeout: (fn, ms) => { jobs.set(++next, {fn, ms}); return next; },
    clearTimeout: id => jobs.delete(id)
  }});
  return {client, jobs, states, starts, stops: () => stops};
}

test("login uses same-origin form contract and exposes no credentials in state", async () => {
  let request;
  const f = fixture(async (...args) => { request = args; return response(); });
  assert.equal(await f.client.login("qa@example.com", "private-password"), true);
  assert.equal(request[0], "/api/v1/auth/token");
  assert.equal(new URLSearchParams(request[1].body).get("password"), "private-password");
  for (const [key, value] of Object.entries({credentials: "omit", cache: "no-store", redirect: "error", mode: "same-origin"})) {
    assert.equal(request[1][key], value);
  }
  assert.deepEqual(f.starts, [pair.access_token]);
  assert.equal(f.client.state.status, "signed_in");
  assert.ok(Object.isFrozen(f.client.state));
  assert.doesNotMatch(JSON.stringify(f.states), /private-password|test-access|rrrr/);
  assert.equal(await f.client.login("qa", "password"), false);
  f.client.dispose(); assert.equal(f.jobs.size, 0);
});

for (const [status, reason] of [[401, "invalid_credentials"], [403, "forbidden"], [429, "rate_limited"], [500, "request_failed"]]) {
  test(`HTTP ${status} yields stable error without reading error body`, async () => {
    const f = fixture(async () => ({ok: false, status, text: () => { throw new Error("must not read"); }}));
    assert.equal(await f.client.login("qa", "password"), false);
    assert.equal(f.client.state.reason, reason); assert.equal(f.starts.length, 0);
  });
}

test("invalid input sends no request", async () => {
  const f = fixture(() => { throw new Error("unexpected request"); });
  for (const args of [["", "pw"], ["qa", ""], ["qa", "x".repeat(257)], [null, "pw"]]) {
    assert.equal(await f.client.login(...args), false);
    assert.equal(f.client.state.reason, "invalid_input");
  }
});

test("logout cancels pending login, ignores late responses and duplicate submissions", async () => {
  let resolve; let calls = 0;
  const f = fixture(() => { calls++; return new Promise(done => { resolve = done; }); });
  const login = f.client.login("qa", "password");
  assert.equal(await f.client.login("qa", "password"), false);
  await f.client.logout();
  resolve(response()); await login;
  assert.equal(calls, 1); assert.equal(f.starts.length, 0);
  assert.equal(f.client.state.status, "signed_out"); assert.equal(f.jobs.size, 0);
});

test("request deadline terminates even when fetch ignores abort", async () => {
  const f = fixture(() => new Promise(() => {}));
  const login = f.client.login("qa", "password");
  const deadline = [...f.jobs.values()][0]; assert.equal(deadline.ms, 10000); deadline.fn();
  assert.equal(await login, false); assert.equal(f.client.state.reason, "request_failed");
  assert.equal(f.jobs.size, 0);
});

test("expiry stops stream and clears session without automatic refresh", async () => {
  const f = fixture(); await f.client.login("qa", "pw");
  const expiry = [...f.jobs.values()][0]; assert.equal(expiry.ms, 50000); expiry.fn();
  assert.equal(f.client.state.reason, "session_expired"); assert.equal(f.stops(), 2);
});

test("logout clears stream before server reply and revokes with refresh token", async () => {
  let request; let resolve;
  const f = fixture(async (url, options) => {
    if (url.endsWith("token")) return response();
    request = options; return new Promise(done => { resolve = done; });
  });
  await f.client.login("qa", "pw"); const logout = f.client.logout();
  assert.equal(f.stops(), 2); assert.equal(f.client.state.status, "signing_out");
  assert.equal(await f.client.logout(), false);
  assert.deepEqual(JSON.parse(request.body), {refresh_token: pair.refresh_token});
  resolve(response(null, 204)); assert.equal(await logout, true);
  assert.equal(f.client.state.reason, null); assert.equal(f.jobs.size, 0);
});

test("offline logout is local only and explicitly reports unconfirmed revocation", async () => {
  const f = fixture(async url => { if (url.endsWith("token")) return response(); throw new Error("secret"); });
  await f.client.login("qa", "pw"); assert.equal(await f.client.logout(), false);
  assert.equal(f.client.state.reason, "revocation_unconfirmed"); assert.equal(f.jobs.size, 0);
});

test("malformed token contracts cannot start transport", async () => {
  for (const value of [null, {}, {...pair, expires_in: 0}, {...pair, expires_in: 86401},
    {...pair, refresh_token: "short"}, {...pair, access_token: "x".repeat(4096)}, {...pair, token_type: "cookie"}]) {
    const f = fixture(async () => response(value));
    assert.equal(await f.client.login("qa", "pw"), false);
    assert.equal(f.starts.length, 0); assert.equal(f.jobs.size, 0);
  }
});

test("terminal transport rejection clears session and permits a new login", async () => {
  for (const status of ["auth_required", "forbidden"]) {
    const f = fixture(); await f.client.login("qa", "pw");
    f.client.handleStreamState({status: "reconnecting"});
    assert.equal(f.client.state.status, "signed_in");
    f.client.handleStreamState({status});
    assert.equal(f.client.state.reason, status); assert.equal(f.jobs.size, 0);
    assert.equal(await f.client.login("qa", "pw"), true); f.client.dispose();
  }
});

test("disposal during logout cannot be overwritten by a late reply", async () => {
  let resolve;
  const f = fixture(async url => url.endsWith("token") ? response() : new Promise(done => { resolve = done; }));
  await f.client.login("qa", "pw"); const logout = f.client.logout();
  f.client.dispose(); resolve(response(null, 204)); await logout;
  assert.equal(f.client.state.reason, "disposed"); assert.equal(f.jobs.size, 0);
});
