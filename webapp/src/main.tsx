import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { I18nextProvider } from "react-i18next";
import "./styles/tokens.css";
import i18n from "./i18n";
import { initTelegram } from "./telegram";
import ThemeProvider from "./theme/ThemeProvider";
import App from "./App";

// Initialise Telegram SDK before first render (expands viewport, etc.)
initTelegram();

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element not found. Ensure index.html has <div id='root'>.");
}

createRoot(rootElement).render(
  <StrictMode>
    <I18nextProvider i18n={i18n}>
      <ThemeProvider>
        <HashRouter>
          <App />
        </HashRouter>
      </ThemeProvider>
    </I18nextProvider>
  </StrictMode>,
);
