import React from "react";
import ReactDOM from "react-dom/client";
import Keycloak from "keycloak-js";
import App from "./App";

const keycloak = new Keycloak({url: "http://localhost:8081", realm: "jejakjkn-dev", clientId: "patient-web"});

const auth = {
  token: () => keycloak.token,
  fresh: async () => {
    await keycloak.updateToken(30);
    return keycloak.token!;
  },
  login: () => keycloak.login(),
  logout: () => keycloak.logout(),
};

function render() {
  ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><App auth={auth} /></React.StrictMode>);
}

keycloak.init({onLoad: "check-sso", pkceMethod: "S256", checkLoginIframe: false}).then(render, render);
