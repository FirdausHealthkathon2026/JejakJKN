import React from "react";
import ReactDOM from "react-dom/client";
import Keycloak from "keycloak-js";
import App from "./App";

const keycloak = new Keycloak({url: "http://localhost:8081", realm: "jejakjkn-dev", clientId: "patient-web"});

keycloak.init({onLoad: "login-required", pkceMethod: "S256"}).then((authenticated) => {
  if (!authenticated || !keycloak.token) return;
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode><App accessToken={() => keycloak.token!} logout={() => keycloak.logout()} /></React.StrictMode>,
  );
});
