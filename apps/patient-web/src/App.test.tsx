// @vitest-environment node
import {renderToString} from "react-dom/server";
import {describe, expect, it} from "vitest";
import App from "./App";
import {formatQuantity} from "./api/client";
import {View} from "./design/View";

const VISIT = {
  id: "e1", isOpen: false, fac: "RS Demo Satu", date: "30 Okt 2026", inT: "09.00", outT: "10.00", ref: "JJK-AAAA-BBBB", presence: "QR", conf: "READY", month: "Oktober 2026", rev: 1,
  deadline: "2 Nov 2026, 10.00", snapshotId: "s1",
  items: [{id: "i1", kind: "DIAGNOSIS", name: "Konjungtivitis", qty: ""}, {id: "i2", kind: "MEDICATION_DISPENSE", name: "Paracetamol 500 mg", qty: "10 tablet"}],
};
const auth = {token: () => "t", fresh: async () => "t", login: () => undefined, logout: () => undefined};

function render(state: Record<string, unknown>) {
  const app = new App({auth});
  Object.assign(app.state, state);
  app.setState = () => undefined;
  return renderToString(<View v={app.renderVals()} />);
}

describe("patient screens", () => {
  const loaded = {visits: [VISIT], visitId: "e1"};
  it.each([
    ["login", {screen: "login"}], ["loading", {screen: "loading"}], ["empty home", {screen: "home"}], ["home", {...loaded, screen: "home"}], ["history", {...loaded, screen: "history"}],
    ["qr", {...loaded, screen: "qr", qrValue: "token-value"}], ["expired qr", {screen: "qr", remaining: 0, qrValue: "x"}], ["in", {...loaded, screen: "in"}], ["out", {...loaded, screen: "out"}],
    ["detail", {...loaded, screen: "detail"}], ["summary", {...loaded, screen: "summary"}], ["review", {...loaded, screen: "review", answers: {i1: {r: "ok"}, i2: {r: "no", reason: "OTHER"}}}],
    ["sent", {...loaded, screen: "sent"}], ["profile", {screen: "profile"}], ["expired", {screen: "expired"}], ["qr failed", {screen: "qrfail"}],
    ["empty detail", {screen: "detail"}],
  ])("%s", (_, state) => {
    expect(render(state)).toContain("<");
  });

  it("formats quantities without trailing zeros", () => {
    expect(formatQuantity("10.0000", "tablet")).toBe("10 tablet");
    expect(formatQuantity("1.0000", "bottle")).toBe("1 botol");
    expect(formatQuantity(null, null)).toBe("");
  });
});
