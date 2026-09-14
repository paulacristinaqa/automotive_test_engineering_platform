import {DashboardStreamClient} from "./stream-client.mjs";
import {DashboardSessionClient} from "./session-client.mjs";

const byId = id => document.getElementById(id);
const form = byId("login-form");
const email = byId("email");
const password = byId("password");
const view = byId("view");
const signIn = byId("sign-in");
const signOut = byId("sign-out");
const messages = {
  invalid_credentials: "Email or password was not accepted.",
  invalid_input: "Enter a valid email and password.",
  forbidden: "Your account does not have dashboard access.",
  auth_required: "Your session was rejected. Sign in again.",
  rate_limited: "Too many attempts. Wait before trying again.",
  request_failed: "The request could not be completed. Check your connection and try again.",
  session_expired: "Your session expired. Sign in again.",
  revocation_unconfirmed: "Signed out locally. Server revocation could not be confirmed.",
  disposed: "Session cleared. Sign in to continue."
};
let session;

function showSession(state) {
  const busy = ["signing_in", "signing_out"].includes(state.status);
  const signedIn = state.status === "signed_in";
  form.hidden = signedIn || state.status === "signing_out";
  for (const element of [email, password, view, signIn]) element.disabled = busy;
  signOut.hidden = state.status === "signed_out";
  signOut.disabled = state.status === "signing_out";
  signOut.textContent = state.status === "signing_in" ? "Cancel sign-in" : "Sign out";
  byId("session-status").textContent = messages[state.reason] ?? ({
    signed_out: "Sign in to continue.", signing_in: "Signing in…", signed_in: "Signed in. Checking dashboard access…", signing_out: "Signing out…"
  })[state.status];
  if (state.status === "signed_out") { password.value = ""; email.focus(); }
  if (signedIn) { email.value = ""; signOut.focus(); }
}

function showStream(state) {
  session?.handleStreamState(state);
  if (state.status === "live" && session?.state.status === "signed_in") {
    byId("session-status").textContent = "Signed in. Read-only dashboard access confirmed.";
  }
  const snapshot = byId("snapshot");
  snapshot.textContent = state.snapshot ? JSON.stringify(state.snapshot.snapshot, null, 2) : "";
  snapshot.hidden = !state.snapshot;
  byId("freshness").textContent = !state.snapshot ? "No data" : state.stale ? "Stale snapshot" : "Current server snapshot";
  byId("stream-status").textContent = ({
    idle: "Waiting for authentication.", stopped: "Stream stopped.", connecting: "Connecting to the dashboard…",
    authenticating: "Checking dashboard permission…", live: "Receiving aggregate server snapshots.",
    stale: "Snapshot overdue. Displayed data may be out of date.",
    reconnecting: "Connection lost. Waiting before a bounded reconnect.",
    auth_required: "Authentication rejected.", forbidden: "Dashboard permission denied."
  })[state.status] ?? "Stream unavailable.";
}

function createSession() {
  const url = new URL(`/api/v1/dashboard/browser-stream/${view.value}`, location.origin);
  url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const stream = new DashboardStreamClient({url: url.href, onState: showStream});
  return new DashboardSessionClient({stream, onState: showSession});
}

form.addEventListener("submit", event => {
  event.preventDefault();
  if (session && session.state.status !== "signed_out") return;
  if (!form.reportValidity()) return;
  const username = email.value;
  const secret = password.value;
  password.value = "";
  session?.dispose();
  session = createSession();
  void session.login(username, secret);
});

signOut.addEventListener("click", () => { void session?.logout(); });
window.addEventListener("pagehide", () => { session?.dispose(); password.value = ""; email.value = ""; });
