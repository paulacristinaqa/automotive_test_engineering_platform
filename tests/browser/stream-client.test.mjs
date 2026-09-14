import test from "node:test";
import assert from "node:assert/strict";
import {DashboardStreamClient} from "../../clients/dashboard/stream-client.mjs";

const url = "ws://localhost:18000/api/v1/dashboard/browser-stream/evidence-readiness";
const frame = sequence => JSON.stringify({type:"atep.dashboard.snapshot.v1",sequence,
  refresh_interval_seconds:30,freshness_basis:"server_query_not_vehicle_measurement",
  observed_at:"2026-09-14T08:00:00Z",refresh_not_before:"2026-09-14T08:00:30Z",
  snapshot:{view:"evidence-readiness",data:{assessment:"not_assessed"}}});
function fixture(random = () => 0) {
  let now = 0, nextId = 0;
  const timers = new Map(), sockets = [], states = [];
  const clock = {setTimeout(fn, ms) {timers.set(++nextId,{fn,at:now+ms}); return nextId;},
    clearTimeout(id) {timers.delete(id);}};
  const advance = ms => {
    const end = now + ms;
    while(true) {
      const next = [...timers.entries()].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];
      if(!next) break;
      now=next[1].at; timers.delete(next[0]); next[1].fn();
    }
    now=end;
  };
  const client = new DashboardStreamClient({url,clock,random,onState:state=>states.push(state),socketFactory:()=>{
    const socket={sent:[],send(value){this.sent.push(value);},close(){this.closed=true;}};
    sockets.push(socket); return socket;
  }});
  return {client,sockets,states,advance,timers};
}

test("credentials stay out of state and first valid snapshot becomes live",()=>{
  const {client,sockets,states}=fixture(); client.start("secret");
  sockets[0].onopen(); assert.equal(JSON.parse(sockets[0].sent[0]).access_token,"secret");
  sockets[0].onmessage({data:frame(1)}); assert.equal(client.state.status,"live");
  assert.equal(client.state.stale,false); assert.ok(!JSON.stringify(states).includes("secret")); client.stop();
});
test("disconnect marks retained snapshot stale and waits 30 seconds before reconnect",()=>{
  const {client,sockets,advance}=fixture(); client.start("secret"); sockets[0].onmessage({data:frame(1)});
  sockets[0].onclose({code:1006}); assert.equal(client.state.stale,true); assert.ok(client.state.snapshot);
  advance(29999); assert.equal(sockets.length,1); advance(1); assert.equal(sockets.length,2);
  sockets[1].onmessage({data:frame(1)}); assert.equal(client.state.status,"live"); client.stop();
});
test("overdue snapshot becomes stale after 35 seconds and next sequence restores live",()=>{
  const {client,sockets,advance}=fixture(); client.start("secret"); sockets[0].onmessage({data:frame(1)});
  advance(34999); assert.equal(client.state.stale,false); advance(1); assert.equal(client.state.status,"stale");
  sockets[0].onmessage({data:frame(2)}); assert.equal(client.state.stale,false); client.stop();
});
for(const [code,status] of [[4401,"auth_required"],[4403,"forbidden"],[1008,"stopped"]]) {
  test(`close ${code} clears snapshot and prevents retry`,()=>{
    const {client,sockets,advance,timers}=fixture(); client.start("secret"); sockets[0].onmessage({data:frame(1)});
    sockets[0].onclose({code}); assert.equal(client.state.status,status); assert.equal(client.state.snapshot,null);
    advance(1000000); assert.equal(sockets.length,1); assert.equal(timers.size,0);
  });
}
test("normal bounded-session close reconnects and resets per-connection sequence",()=>{
  const {client,sockets,advance}=fixture(); client.start("secret");
  for(let n=1;n<=10;n++) sockets[0].onmessage({data:frame(n)});
  sockets[0].onclose({code:1000}); advance(30000); sockets[1].onmessage({data:frame(1)});
  assert.equal(client.state.status,"live"); client.stop();
});
test("backoff is exponential, capped, and ends after five retries",()=>{
  const {client,sockets,advance}=fixture(); client.start("secret");
  for(const delay of [30000,60000,120000,120000,120000]) {
    sockets.at(-1).onclose({code:1013}); assert.equal(client.state.retryAfterMs,delay); advance(delay);
  }
  sockets.at(-1).onclose({code:1006}); assert.equal(client.state.reason,"retry_limit");
  advance(1000000); assert.equal(sockets.length,6);
});
test("jitter never shortens minimum wait",()=>{
  const {client,sockets}=fixture(()=>1); client.start("secret"); sockets[0].onclose({code:1006});
  assert.equal(client.state.retryAfterMs,36000); client.stop();
});
test("stop cancels all timers and ignores callbacks from retired sockets",()=>{
  const {client,sockets,advance,timers}=fixture(); client.start("secret"); const late=sockets[0].onmessage;
  client.stop(); late({data:frame(1)}); advance(1000000);
  assert.equal(client.state.status,"stopped"); assert.equal(sockets.length,1); assert.equal(timers.size,0);
});
test("missing first snapshot triggers bounded retry",()=>{
  const {client,advance}=fixture(); client.start("secret"); advance(30000);
  assert.equal(client.state.status,"reconnecting"); client.stop();
});
test("malformed or repeated frames fail closed",()=>{
  for(const value of ["bad",frame(2)]) {
    const {client,sockets}=fixture(); client.start("secret"); sockets[0].onmessage({data:value});
    assert.equal(client.state.reason,"protocol_error"); assert.equal(client.state.snapshot,null);
  }
});
test("URLs cannot carry credentials and cleartext remote endpoints are rejected",()=>{
  for(const value of [url+"?token=x",url+"#secret",url.replace("localhost","remote.example")])
    assert.throws(()=>new DashboardStreamClient({url:value}),/Invalid dashboard browser endpoint/);
});
test("oversized credentials and duplicate sequence numbers are rejected",()=>{
  const {client,sockets}=fixture();
  assert.throws(()=>client.start("x".repeat(4097)),/Invalid dashboard credentials/);
  assert.equal(sockets.length,0);
  client.start("secret"); sockets[0].onmessage({data:frame(1)}); sockets[0].onmessage({data:frame(1)});
  assert.equal(client.state.reason,"protocol_error"); assert.equal(client.state.snapshot,null);
});
