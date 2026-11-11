import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api";
import { useApp } from "./context";
import { ago } from "./format";
import Crafts from "./pages/Crafts";
import Gathering from "./pages/Gathering";
import Glossary from "./pages/Glossary";
import ItemPage from "./pages/ItemPage";
import MarketMap from "./pages/MarketMap";
import Opportunities from "./pages/Opportunities";
import Overview from "./pages/Overview";
import Setup from "./pages/Setup";
import StatusPage from "./pages/StatusPage";

const NAV = [
  ["/", "Overview"],
  ["/opportunities", "Opportunities"],
  ["/crafts", "Crafts"],
  ["/gathering", "Gathering"],
  ["/map", "Market map"],
  ["/status", "Data status"],
  ["/glossary", "Glossary"],
  ["/setup", "Settings"],
] as const;

function Header() {
  const { status, refreshStatus } = useApp();
  const [busy, setBusy] = useState(false);
  const realm = status?.sources.find((s) => s.key === "tsm_realm") ?? status?.sources.find((s) => s.key === "tsm_region");
  const problems = status?.warnings.filter((w) => w.level === "error" || w.level === "warn").length ?? 0;

  const refresh = async () => {
    setBusy(true);
    try {
      await api.refresh();
      setTimeout(refreshStatus, 4000);
    } finally {
      setTimeout(() => setBusy(false), 4000);
    }
  };

  return (
    <header className="topbar">
      <div className="brand">
        <span className="logo">S</span>
        <span className="brand-text">
          <span>Simsar Forever</span>
          <span className="muted small">{status?.realm_label ?? "WoW Forever market"}</span>
        </span>
      </div>
      <nav>
        {NAV.map(([to, label]) => (
          <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>
            {label}
            {to === "/status" && problems > 0 && <span className="dot warn" />}
          </NavLink>
        ))}
      </nav>
      <div className="topbar-right">
        {status && (
          <span className="chip" title="Time of the TSM scan the numbers are based on">
            Data: {ago(realm?.updated_at)}
          </span>
        )}
        {status && status.alerts_unseen > 0 && (
          <NavLink to="/status#alerts" className="chip alert-chip">{status.alerts_unseen} new alerts</NavLink>
        )}
        {!status?.demo && (
          <button onClick={refresh} disabled={busy}>{busy ? "Refreshing..." : "Refresh now"}</button>
        )}
      </div>
    </header>
  );
}

function Banners() {
  const { status, error } = useApp();
  return (
    <>
      {status?.demo && (
        <div className="demo-banner">
          DEMO MODE: all data on this page is synthetic. Nothing here describes the real WoW Forever market.
        </div>
      )}
      {error && <div className="error-banner">{error}</div>}
    </>
  );
}

function FirstRunRedirect() {
  const { status } = useApp();
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => {
    if (status && !status.configured && location.pathname !== "/setup") navigate("/setup");
  }, [status, location.pathname, navigate]);
  return null;
}

export default function App() {
  return (
    <div className="app">
      <FirstRunRedirect />
      <Banners />
      <Header />
      <main>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/opportunities" element={<Opportunities />} />
          <Route path="/crafts" element={<Crafts />} />
          <Route path="/gathering" element={<Gathering />} />
          <Route path="/map" element={<MarketMap />} />
          <Route path="/status" element={<StatusPage />} />
          <Route path="/glossary" element={<Glossary />} />
          <Route path="/item/:id" element={<ItemPage />} />
          <Route path="/setup" element={<Setup />} />
        </Routes>
      </main>
      <footer>
        Decision support only. Prices move; nothing here guarantees a profit. Data: TradeSkillMaster public files and
        your own Auctionator scans.
      </footer>
    </div>
  );
}
