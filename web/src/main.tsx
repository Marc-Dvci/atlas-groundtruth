import { createRoot } from "react-dom/client";
import "./styles.css";
import App from "./App";

// No StrictMode: it mounts effects twice in development and the map is a heavyweight singleton.
createRoot(document.getElementById("root")!).render(<App />);
