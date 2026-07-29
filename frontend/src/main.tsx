import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { GlobalActionTooltip } from "./components/GlobalActionTooltip";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
    <GlobalActionTooltip />
  </StrictMode>
);
