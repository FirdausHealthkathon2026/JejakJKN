// @vitest-environment node
import {renderToString} from "react-dom/server";
import {describe, expect, it} from "vitest";
import App from "./App";
import {View} from "./design/View";

const RECORD = {rid: "r1", jenis: "OBAT", kode: "OB-PCT500-STR", jumlah: 1, ver: 1, status: "ACTIVE", canonical: {event_type: "MEDICATION_DISPENSED", content: {code_system: "JJKN-MED-V1", code: "MED-PARACETAMOL-500", display: "Paracetamol 500 mg", quantity: 10, unit: "tablet"}}, hist: [{v: 1, action: "RECORDED", time: "09.10", desc: "Paracetamol", note: "", who: "Petugas"}]};
const VISIT = {id: "e1", pn: "SYNTHETIC-10001", ref: "RJ-1", startedAt: "2026-10-30T02:00:00Z", endedAt: "2026-10-30T03:00:00Z", inT: "09.00", outT: "10.00", status: "CHECKED_OUT", presence: "QR", sync: "SYNC_COMPLETE", pending: 0, failed: 0, delivered: 2, marking: false, claimId: null, records: [RECORD], deliveries: []};
const CLAIM = {id: "C1", vid: "e1", ref: "RJ-1", visitDate: "30 Okt 2026", pn: "SYNTHETIC-10001", care: "RJ", amount: 1000, st: "VERIFYING", items: [{jenis: "OBAT", kode: "OB-PCT500-STR", jumlah: 1}], at: ["a", "a", "b", ""]};

function render(state: Record<string, unknown>) {
  const app = new App({});
  Object.assign(app.state, state);
  app.setState = () => undefined;
  return renderToString(<View v={app.renderVals()} />);
}

describe("simrs b screens", () => {
  const loaded = {visits: [VISIT], bclaims: [CLAIM], deliveries: [{id: "d", time: "09.10", vid: "e1", what: "x", kind: "y", st: "DELIVERED", note: ""}], sel: "e1", cid: "C1"};
  it.each([
    ["empty list", {}], ["list", loaded], ["scan", {...loaded, screen: "scan"}], ["scan ok", {...loaded, screen: "scan", result: {kind: "ok", vid: "e1", mode: "IN"}}],
    ["visit", {...loaded, screen: "visit", tab: "OBAT", pick: "OB-PCT500-STR"}], ["sync", {...loaded, screen: "sync"}], ["claims", {...loaded, screen: "claims"}],
    ["claim form", {...loaded, screen: "claimForm", draft: {vid: "e1", pn: "x", care: "RJ", sel: {r1: true}, amount: "", ack: false}}], ["claim view", {...loaded, screen: "claimView"}], ["empty visit", {screen: "visit"}],
  ])("%s", (_, state) => {
    expect(render(state)).toContain("<");
  });

  it("shows the canonical translation of a strip", () => {
    expect(render({...loaded, screen: "visit"})).toContain("10 tablet");
  });

  it("renders camera and gallery controls on the scan screen", () => {
    const app = new App({});
    Object.assign(app.state, {screen: "scan"});
    app.setState = () => undefined;
    const html = renderToString(app.render());
    expect(html).toContain("Buka kamera");
    expect(html).toContain("Pilih dari galeri");
  });
});
