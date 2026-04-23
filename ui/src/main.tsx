import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import SovereignOrb from "./SovereignOrb";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <SovereignOrb />
  </StrictMode>
);
