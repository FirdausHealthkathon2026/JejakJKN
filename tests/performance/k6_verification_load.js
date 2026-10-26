import http from "k6/http";
import {check} from "k6";

export const options = {
  scenarios: {gateway_readiness: {executor: "constant-vus", vus: 20, duration: "30s"}},
  thresholds: {http_req_duration: ["p(95)<500"], checks: ["rate>0.99"]},
};

export default function () {
  const response = http.get(`${__ENV.PUBLIC_BASE_URL || "http://localhost:18080"}/health`);
  check(response, {"gateway healthy": value => value.status === 200});
}
