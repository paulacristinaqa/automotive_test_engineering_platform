/** In-memory, read-only dashboard transport. No storage, logs, login or UI framework. */
export class DashboardStreamClient {
  #token = null;
  #socket = null;
  #timers = new Set();
  #attempt = 0;
  #sequence = 0;
  #state = Object.freeze({status: "idle", stale: true, snapshot: null, retryAfterMs: null, reason: null});

  constructor({url, onState = () => {}, socketFactory = value => new WebSocket(value),
    clock = {setTimeout: (fn, ms) => setTimeout(fn, ms), clearTimeout: id => clearTimeout(id)},
    random = Math.random}) {
    const parsed = new URL(url);
    if (!/^\/api\/v1\/dashboard\/browser-stream\/(operations|mobility|evidence-readiness)$/.test(parsed.pathname) ||
        parsed.search || parsed.hash || parsed.username || parsed.password ||
        !["ws:", "wss:"].includes(parsed.protocol) ||
        (parsed.protocol === "ws:" && !["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname))) {
      throw new Error("Invalid dashboard browser endpoint");
    }
    this.url = parsed.href;
    this.view = parsed.pathname.split("/").at(-1);
    this.onState = onState;
    this.socketFactory = socketFactory;
    this.clock = clock;
    this.random = random;
  }

  get state() { return this.#state; }

  start(token) {
    if (typeof token !== "string" || !token || token.length > 4096 || new TextEncoder().encode(JSON.stringify({
      type: "atep.dashboard.authenticate.v1", access_token: token
    })).length > 4096) throw new Error("Invalid dashboard credentials");
    this.stop();
    this.#token = token;
    this.#attempt = 0;
    this.#connect();
  }

  stop() { this.#terminate("stopped", "client_stop"); }

  #emit(patch) {
    this.#state = Object.freeze({...this.#state, ...patch});
    this.onState(this.#state);
  }

  #timer(fn, ms) {
    const id = this.clock.setTimeout(() => { this.#timers.delete(id); fn(); }, ms);
    this.#timers.add(id);
    return id;
  }

  #clearTimers() {
    for (const id of this.#timers) this.clock.clearTimeout(id);
    this.#timers.clear();
  }

  #disposeSocket() {
    const socket = this.#socket;
    this.#socket = null;
    if (!socket) return;
    socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null;
    try { socket.close(); } catch { /* Never expose exception data or credentials. */ }
  }

  #terminate(status, reason) {
    this.#clearTimers();
    this.#disposeSocket();
    this.#token = null;
    this.#emit({status, reason, stale: true, snapshot: null, retryAfterMs: null});
  }

  #retry() {
    this.#clearTimers();
    this.#disposeSocket();
    if (!this.#token) return;
    if (this.#attempt >= 5) return this.#terminate("stopped", "retry_limit");
    const base = Math.min(120000, 30000 * 2 ** this.#attempt++);
    const jitter = Math.max(0, Math.min(1, Number(this.random()) || 0));
    const delay = Math.min(120000, base + Math.floor(base * 0.2 * jitter));
    this.#emit({status: "reconnecting", reason: "connection_lost", stale: true, retryAfterMs: delay});
    this.#timer(() => this.#connect(), delay);
  }

  #connect() {
    if (!this.#token) return;
    this.#sequence = 0;
    this.#emit({status: "connecting", stale: true, retryAfterMs: null, reason: null});
    let socket;
    try { socket = this.socketFactory(this.url); } catch { this.#retry(); return; }
    this.#socket = socket;
    this.#timer(() => { if (this.#socket === socket) this.#retry(); }, 30000);
    socket.onopen = () => {
      if (this.#socket !== socket) return;
      this.#emit({status: "authenticating"});
      try { socket.send(JSON.stringify({type: "atep.dashboard.authenticate.v1", access_token: this.#token})); }
      catch { this.#retry(); }
    };
    socket.onerror = () => {}; // The close event or deadline drives one retry, never both.
    socket.onclose = event => {
      if (this.#socket !== socket) return;
      if (event.code === 4401) return this.#terminate("auth_required", "authentication_rejected");
      if (event.code === 4403) return this.#terminate("forbidden", "permission_rejected");
      if ([1002, 1003, 1008, 1009].includes(event.code)) return this.#terminate("stopped", "protocol_error");
      this.#retry();
    };
    socket.onmessage = event => {
      if (this.#socket !== socket) return;
      try {
        if (typeof event.data !== "string" || event.data.length > 300000) throw new Error();
        const frame = JSON.parse(event.data);
        const observed = Date.parse(frame.observed_at);
        if (frame.type !== "atep.dashboard.snapshot.v1" || frame.sequence !== this.#sequence + 1 ||
            frame.sequence > 10 || frame.refresh_interval_seconds !== 30 ||
            frame.freshness_basis !== "server_query_not_vehicle_measurement" || !Number.isFinite(observed) ||
            Date.parse(frame.refresh_not_before) !== observed + 30000 ||
            frame.snapshot?.view !== this.view || !frame.snapshot.data || typeof frame.snapshot.data !== "object" ||
            Array.isArray(frame.snapshot.data)) throw new Error();
        this.#sequence = frame.sequence;
        this.#attempt = 0;
        this.#clearTimers();
        this.#timer(() => this.#emit({status: "stale", stale: true, reason: "snapshot_overdue"}), 35000);
        this.#emit({status: "live", stale: false, snapshot: frame, reason: null, retryAfterMs: null});
      } catch { this.#terminate("stopped", "protocol_error"); }
    };
  }
}
