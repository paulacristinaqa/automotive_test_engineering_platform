/** Same-origin login controller. Credentials exist only in private memory. */
export class DashboardSessionClient {
  #refresh = null;
  #generation = 0;
  #pending = null;
  #expiry = null;
  #state = Object.freeze({status: "signed_out", reason: null});

  constructor({stream, onState = () => {}, fetcher = (...args) => fetch(...args),
    clock = {setTimeout: (fn, ms) => setTimeout(fn, ms), clearTimeout: id => clearTimeout(id)}}) {
    this.stream = stream;
    this.onState = onState;
    this.fetcher = fetcher;
    this.clock = clock;
  }

  get state() { return this.#state; }

  handleStreamState(state) {
    if (this.#state.status !== "signed_in" || !["auth_required", "forbidden"].includes(state.status)) return;
    this.#clear();
    this.#emit("signed_out", state.status);
  }

  #emit(status, reason = null) {
    this.#state = Object.freeze({status, reason});
    this.onState(this.#state);
  }

  #clear() {
    this.#generation++;
    this.#pending?.abort();
    this.#pending = null;
    if (this.#expiry !== null) this.clock.clearTimeout(this.#expiry);
    this.#expiry = null;
    this.#refresh = null;
    this.stream.stop();
  }

  async #request(path, body, contentType) {
    const controller = new AbortController();
    this.#pending = controller;
    let timer;
    const aborted = new Promise((_, reject) => {
      controller.signal.addEventListener("abort", () => reject(new Error("Request cancelled")), {once: true});
      timer = this.clock.setTimeout(() => controller.abort(), 10000);
    });
    try {
      return await Promise.race([aborted, (async () => {
        const response = await this.fetcher(`/api/v1/auth/${path}`, {
          method: "POST", headers: {"Content-Type": contentType}, body,
          credentials: "omit", cache: "no-store", redirect: "error", mode: "same-origin",
          signal: controller.signal
        });
        if (!response.ok) {
          return {error: ({401: "invalid_credentials", 403: "forbidden", 429: "rate_limited"})[response.status] ?? "request_failed"};
        }
        if (path === "logout") return {ok: response.status === 204};
        const text = await response.text();
        if (text.length > 16384) throw new Error("Invalid response");
        return {pair: JSON.parse(text)};
      })()]);
    } finally {
      this.clock.clearTimeout(timer);
      if (this.#pending === controller) this.#pending = null;
    }
  }

  async login(username, password) {
    // Duplicate submissions never create another server session.
    if (["signing_in", "signed_in", "signing_out"].includes(this.#state.status)) return false;
    if (typeof username !== "string" || !username.trim() || username.length > 320 ||
        typeof password !== "string" || !password || password.length > 256) {
      this.#emit("signed_out", "invalid_input");
      return false;
    }
    this.#clear();
    const generation = this.#generation;
    this.#emit("signing_in");
    try {
      const result = await this.#request("token", new URLSearchParams({username, password}).toString(),
        "application/x-www-form-urlencoded");
      if (generation !== this.#generation) return false;
      if (result.error) { this.#emit("signed_out", result.error); return false; }
      const pair = result.pair;
      if (!pair || pair.token_type !== "bearer" || typeof pair.access_token !== "string" ||
          !pair.access_token || new TextEncoder().encode(JSON.stringify({
            type: "atep.dashboard.authenticate.v1", access_token: pair.access_token
          })).length > 4096 || typeof pair.refresh_token !== "string" ||
          pair.refresh_token.length < 32 || pair.refresh_token.length > 512 ||
          !Number.isInteger(pair.expires_in) || pair.expires_in < 1 || pair.expires_in > 86400) {
        throw new Error("Invalid response");
      }
      this.#refresh = pair.refresh_token;
      this.stream.start(pair.access_token);
      // Deduct the entire request deadline: never extend the server's advertised lifetime.
      this.#expiry = this.clock.setTimeout(() => {
        this.#clear();
        this.#emit("signed_out", "session_expired");
      }, Math.max(0, pair.expires_in * 1000 - 10000));
      this.#emit("signed_in");
      return true;
    } catch {
      if (generation === this.#generation) {
        this.#clear();
        this.#emit("signed_out", "request_failed");
      }
      return false;
    }
  }

  async logout() {
    if (this.#state.status === "signing_out") return false;
    const refresh = this.#refresh;
    this.#clear(); // Clear snapshots and cancel login before attempting remote revocation.
    const generation = this.#generation;
    if (!refresh) { this.#emit("signed_out"); return true; }
    this.#emit("signing_out");
    let confirmed = false;
    try {
      confirmed = (await this.#request("logout", JSON.stringify({refresh_token: refresh}),
        "application/json")).ok === true;
    } catch { /* Local logout succeeds even while offline; revocation is unconfirmed. */ }
    if (generation === this.#generation) this.#emit("signed_out", confirmed ? null : "revocation_unconfirmed");
    return confirmed;
  }

  dispose() {
    this.#clear();
    this.#emit("signed_out", "disposed");
  }
}
