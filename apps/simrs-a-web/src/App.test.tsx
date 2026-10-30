// @vitest-environment node
import {renderToString} from "react-dom/server";
import {describe, expect, it} from "vitest";
import App from "./App";
import {View} from "./design/View";

const VISIT = {
  id: "e1", pn: "SYNTHETIC-10001", ref: "VISIT-1", enc: "e1aaaaaa-0000", startedAt: "2026-10-30T02:00:00Z", endedAt: "2026-10-30T03:00:00Z", inT: "09.00", outT: "10.00",
  status: "CHECKED_OUT", presence: "QR_VERIFIED", sync: "SYNC_COMPLETE", err: null, pending: 0, failed: 0, delivered: 2, marking: false, claimId: null,
  records: [{rid: "r1", type: "MEDICATION_DISPENSED", cs: "LOCAL", code: "MED-1", display: "Paracetamol 500 mg", qty: "10", unit: "tablet", ver: 1, status: "ACTIVE", hist: [{v: 1, action: "RECORDED", time: "09.10", desc: "Paracetamol", note: ""}]}],
  deliveries: [],
};
const CLAIM = {id: "C1", vid: "e1", ref: "VISIT-1", visitDate: "30 Okt 2026", pn: "SYNTHETIC-10001", care: "RJ", amount: 1000, st: "RECEIVED", items: [{type: "MEDICATION_DISPENSED", cs: "LOCAL", code: "MED-1", display: "Paracetamol", qty: "10", unit: "tablet"}], at: ["a", "a", "", ""]};
const DELIVERY = {id: "d1", time: "09.10", vid: "e1", what: "Paracetamol", kind: "Catatan baru", st: "FAILED", note: "Ditolak"};

function render(state: Record<string, unknown>) {
  const app = new App({});
  Object.assign(app.state, state);
  app.setState = () => undefined;
  return renderToString(<View v={app.renderVals()} />);
}

describe("simrs a screens", () => {
  const loaded = {visits: [VISIT], bclaims: [CLAIM], deliveries: [DELIVERY], sel: "e1", cid: "C1"};
  const draft = {vid: "e1", pn: "SYNTHETIC-10001", care: "RJ", sel: {r1: {on: true, qty: "10"}}, amount: "1000", ack: true, error: false};
  it.each([
    ["empty list", {}], ["list", {...loaded}], ["scan", {...loaded, screen: "scan"}], ["scan ok", {...loaded, screen: "scan", result: {kind: "ok", vid: "e1", purpose: "CHECK_IN"}}],
    ["scan error", {...loaded, screen: "scan", result: {kind: "err", code: "QR_ALREADY_CONSUMED"}}], ["visit", {...loaded, screen: "visit"}], ["sync", {...loaded, screen: "sync"}],
    ["claims", {...loaded, screen: "claims"}], ["claim form", {...loaded, screen: "claimForm", draft}], ["claim view", {...loaded, screen: "claimView"}],
    ["empty visit", {screen: "visit"}], ["correct dialog", {...loaded, screen: "visit", dialog: {type: "correct", rid: "r1", cs: "LOCAL", code: "MED-1", display: "x", qty: "1", unit: "tablet", reason: ""}}],
  ])("%s", (_, state) => {
    expect(render(state)).toContain("<");
  });
});
