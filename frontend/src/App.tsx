import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api";
import { Toasts, toast } from "./components/Feedback";
import { useApp } from "./context";
import { ago } from "./format";
import Crafts from "./pages/Crafts";
import Gathering from "./pages/Gathering";
import Glossary from "./pages/Glossary";
import Inventory from "./pages/Inventory";
import ItemPage from "./pages/ItemPage";
import Ledger from "./pages/Ledger";
import SellPlan from "./pages/SellPlan";
import Shopping from "./pages/Shopping";
import Professions from "./pages/Professions";
import Accuracy from "./pages/Accuracy";
import MarketMap from "./pages/MarketMap";
import Opportunities from "./pages/Opportunities";
import Overview from "./pages/Overview";
import Setup from "./pages/Setup";
import StatusPage from "./pages/StatusPage";

const NAV: { title: string; links: [string, string][] }[] = [
  { title: "Market", links: [["/", "Overview"], ["/opportunities", "Opportunities"], ["/gathering", "What to sell"],
    ["/map", "Market map"]] },
  { title: "Crafting", links: [["/crafts", "Crafts"], ["/professions", "Professions"], ["/shopping", "Shopping list"]] },
  { title: "Your characters", links: [["/inventory", "Bags & bank"], ["/sell", "Sell plan"], ["/ledger", "Gold ledger"]] },
  { title: "About the data", links: [["/accuracy", "Forecast accuracy"], ["/status", "Data status"],
    ["/glossary", "Glossary"], ["/setup", "Settings"]] },
];

function Header() {
  const { status, refreshStatus } = useApp();
  const [busy, setBusy] = useState(false);
  const realm = status?.sources.find((s) => s.key === "tsm_realm") ?? status?.sources.find((s) => s.key === "tsm_region");

  const refresh = async () => {
    setBusy(true);
    try {
      const r = await api.refresh();
      toast(r.busy ? "A refresh is already running." : "Checking TSM and your game files...", "info");
      setTimeout(refreshStatus, 4000);
    } catch {
      toast("Could not reach the Simsar Forever server.", "error");
    } finally {
      setTimeout(() => setBusy(false), 4000);
    }
  };

  return (
    <header className="topbar">
      <div className="brand">
        <span className="logo" aria-hidden="true">S</span>
        <span className="brand-text">
          <span>Simsar Forever</span>
          <span className="muted small">{status?.realm_label ?? "WoW Forever market"}</span>
        </span>
      </div>
      <div className="topbar-right">
        {status && (
          <span className="freshness" title="Time of the TSM scan the numbers are based on">
            <span className={`dot ${realm?.ok ? "ok" : "warn"}`} />
            Prices from {ago(realm?.updated_at)}
          </span>
        )}
        {status && status.alerts_unseen > 0 && (
          <NavLink to="/status#alerts" className="alert-link">
            {status.alerts_unseen} new alert{status.alerts_unseen === 1 ? "" : "s"}
          </NavLink>
        )}
        {!status?.demo && (
          <button onClick={refresh} disabled={busy}>{busy ? "Refreshing..." : "Refresh"}</button>
        )}
      </div>
    </header>
  );
}

function SideNav() {
  const { status } = useApp();
  const problems = status?.warnings.filter((w) => w.level === "error" || w.level === "warn").length ?? 0;
  return (
    <aside className="sidenav">
      {NAV.map((group) => (
        <div key={group.title} className="nav-group">
          <div className="nav-title">{group.title}</div>
          {group.links.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>
              {label}
              {to === "/status" && problems > 0 && <span className="dot warn" />}
            </NavLink>
          ))}
        </div>
      ))}
    </aside>
  );
}

function Banners() {
  const { status, error } = useApp();
  return (
    <>
      {status?.demo && (
        <div className="demo-banner">
          Demo mode: every number here is made up and says nothing about the real WoW Forever market.
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
      <Toasts />
      <Banners />
      <Header />
      <div className="layout">
      <SideNav />
      <main>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/opportunities" element={<Opportunities />} />
          <Route path="/crafts" element={<Crafts />} />
          <Route path="/gathering" element={<Gathering />} />
          <Route path="/inventory" element={<Inventory />} />
          <Route path="/ledger" element={<Ledger />} />
          <Route path="/sell" element={<SellPlan />} />
          <Route path="/shopping" element={<Shopping />} />
          <Route path="/professions" element={<Professions />} />
          <Route path="/accuracy" element={<Accuracy />} />
          <Route path="/map" element={<MarketMap />} />
          <Route path="/status" element={<StatusPage />} />
          <Route path="/glossary" element={<Glossary />} />
          <Route path="/item/:id" element={<ItemPage />} />
          <Route path="/setup" element={<Setup />} />
        </Routes>
      </main>
      </div>
      <footer>
        Decision support only. Prices move; nothing here guarantees a profit. Data: TradeSkillMaster public files and
        your own Auctionator scans.
      </footer>
    </div>
  );
}
