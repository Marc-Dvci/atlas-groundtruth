import { useEffect, useState } from "react";
import { CaseView } from "./case/CaseView";
import { Mission } from "./mission/Mission";
import { EvalView } from "./eval/EvalView";
import { LedgerView } from "./ledger/LedgerView";
import { Card } from "./Card";
import { LiveView } from "./live/LiveView";
import { LIVE } from "./api";

function useHash() {
  const [h, setH] = useState(window.location.hash);
  useEffect(() => {
    const on = () => setH(window.location.hash);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return h;
}

export default function App() {
  const hash = useHash();
  const m = hash.match(/^#\/case\/([\w-]+)\/([\w-]+)/);
  if (m) return <CaseView key={hash} run={m[1]} id={m[2]} onBack={() => (window.location.hash = "")} />;
  const lg = hash.match(/^#\/ledger\/([\w-]+)\/([\w-]+)/);
  if (lg) return <LedgerView run={lg[1]} id={lg[2]} />;
  const card = hash.match(/^#\/card\/([^/]+)/);
  if (card) return <Card id={card[1]} />;
  const ev = hash.match(/^#\/eval\/([\w-]+)(?:\/([\w-]+))?/);
  if (ev) return <EvalView key={hash} run={ev[1]} answerKey={ev[2] ?? "cases"} />;
  if (hash.startsWith("#/live") || (LIVE && !hash)) return <LiveView />;
  return <Mission />;
}
