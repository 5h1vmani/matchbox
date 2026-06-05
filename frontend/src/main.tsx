import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// Self-hosted webfonts (bundled — no runtime CDN, matchbox is local-first).
import "@fontsource/hanken-grotesk/400.css";
import "@fontsource/hanken-grotesk/400-italic.css";
import "@fontsource/hanken-grotesk/500.css";
import "@fontsource/hanken-grotesk/600.css";
import "@fontsource/hanken-grotesk/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/600.css";

// Design-team tokens + component styles, copied verbatim from designs/v1[.1].
import "./styles/colors_and_type.css";
import "./styles/mb.css";
// Discovery surfaces' component styles (verbatim from designs/v1.1).
import "./styles/discovery.css";
// App layer (loaded last): locks light scheme for v1 (dark was not designed).
import "./styles/app.css";

import { Shell } from "./Shell";

const root = document.getElementById("root");
if (!root) throw new Error("missing #root");

// One unified shell (Track + Discover + a Workspace group), internally routed.
// FastAPI serves this index.html at /, /tracker, and /discover[/*]; the shell
// picks the initial screen from the path. `?sample` puts Discover in fixture
// mode (for screenshots / offline).
createRoot(root).render(
  <StrictMode>
    <Shell />
  </StrictMode>,
);
