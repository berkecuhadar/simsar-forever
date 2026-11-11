import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { type Install, type SetupInfo, api } from "../api";
import { Hint } from "../components/Hint";
import { useApp } from "../context";
import { ago } from "../format";

function splitSlug(slug: string | null): [string, string] {
  if (!slug) return ["normal", "alliance"];
  const m = slug.match(/^(.*)-(alliance|horde)$/);
  return m ? [m[1], m[2]] : ["normal", "alliance"];
}

function InstallCard({ inst, selected, onPick }: { inst: Install; selected: boolean; onPick: () => void }) {
  return (
    <label className={`install ${selected ? "selected" : ""}`}>
      <input type="radio" checked={selected} onChange={onPick} />
      <div>
        <div><b>{inst.path}</b></div>
        <div className="muted small">
          {inst.is_forever ? "WoW Forever" : "Not a _forever_ folder"}
          {inst.auctionator_version ? `, Auctionator ${inst.auctionator_version}` : ", Auctionator not installed"}
          {inst.export_addon_installed ? ", SimsarForeverExport installed" : ""}
          {`, ${inst.accounts.length} account${inst.accounts.length === 1 ? "" : "s"}`}
        </div>
      </div>
    </label>
  );
}

export default function Setup() {
  const { refreshStatus, status } = useApp();
  const navigate = useNavigate();
  const [info, setInfo] = useState<SetupInfo | null>(null);
  const [region, setRegion] = useState("eu");
  const [realmType, setRealmType] = useState("normal");
  const [faction, setFaction] = useState("alliance");
  const [regionOnly, setRegionOnly] = useState(false);
  const [gameDir, setGameDir] = useState("");
  const [manualDir, setManualDir] = useState("");
  const [inspected, setInspected] = useState<Install | null>(null);
  const [account, setAccount] = useState("");
  const [atoRealm, setAtoRealm] = useState("");
  const [professions, setProfessions] = useState<string[]>([]);
  const [house, setHouse] = useState<"faction" | "neutral">("faction");
  const [check, setCheck] = useState<Record<string, { ok: boolean; status: number | null; rate_limited?: boolean }> | null>(null);
  const [saving, setSaving] = useState(false);
  const [addonMsg, setAddonMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.setup().then((s) => {
      setInfo(s);
      setRegion(s.current.region);
      const [t, f] = splitSlug(s.current.realm);
      setRealmType(t);
      setFaction(f);
      setRegionOnly(!s.current.realm);
      setProfessions(s.current.professions);
      setHouse(s.current.auction_house ?? "faction");
      setAccount(s.current.account ?? "");
      setAtoRealm(s.current.auctionator_realm ?? "");
      const dir = s.current.game_dir ?? s.installs[0]?.path ?? "";
      setGameDir(dir);
      setManualDir(dir);
    }, (e) => setError(String(e)));
  }, []);

  const regionInfo = info?.catalog.regions.find((r) => r.key === region);
  useEffect(() => {
    if (regionInfo && !regionInfo.realms.includes(realmType)) setRealmType(regionInfo.realms[0]);
  }, [regionInfo, realmType]);

  const realm = regionOnly ? null : `${realmType}-${faction}`;

  useEffect(() => {
    if (!gameDir) { setInspected(null); return; }
    api.setupInspect(gameDir).then((d) => {
      setInspected(d);
      if (d.accounts.length && !d.accounts.some((a) => a.name === account)) {
        const withAto = d.accounts.filter((a) => a.has_auctionator);
        setAccount((withAto[0] ?? d.accounts[0]).name);
      }
    }, () => setInspected(null));
  }, [gameDir]); // eslint-disable-line react-hooks/exhaustive-deps

  const [atoRealms, setAtoRealms] = useState<{ key: string; items: number }[]>([]);
  useEffect(() => {
    if (!gameDir || !account) { setAtoRealms([]); return; }
    api.setupInspect(gameDir, account).then((d) => setAtoRealms(d.auctionator_realms ?? []), () => setAtoRealms([]));
  }, [gameDir, account]);

  useEffect(() => {
    setCheck(null);
    const t = setTimeout(() => api.setupCheck(region, realm).then(setCheck, () => setCheck(null)), 400);
    return () => clearTimeout(t);
  }, [region, realm]);

  const installs = useMemo(() => {
    const list = [...(info?.installs ?? [])];
    if (inspected && !list.some((i) => i.path === inspected.path)) list.push(inspected);
    return list;
  }, [info, inspected]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.setupSave({
        region, realm, game_dir: inspected?.path ?? (gameDir || null), account: account || null,
        auctionator_realm: atoRealm || null, professions, auction_house: house,
      });
      refreshStatus();
      navigate("/");
      setTimeout(() => window.location.reload(), 300);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  if (status?.demo) return <div className="card">Setup is not available in demo mode.</div>;
  if (!info) return <div className="loading">{error ?? "Looking for WoW Forever on this computer..."}</div>;

  const checkLine = (kind: string) => {
    const c = check?.[kind];
    if (!c) return <span className="muted">checking...</span>;
    if (c.ok) return <span className="pos">available</span>;
    if (c.rate_limited) return <span className="muted">TSM is busy, could not check (will still work)</span>;
    return <span className="neg">not found (HTTP {c.status ?? "error"})</span>;
  };

  return (
    <section className="setup">
      <div className="page-head">
        <h1>{info.config_exists ? "Settings" : "Welcome to Simsar Forever"}</h1>
        <p className="lead">
          Pick your auction house and your game folder. Everything here can be changed later; each realm keeps its
          own price history.
        </p>
      </div>

      <div className="card">
        <h3>1. Your auction house</h3>
        <div className="filters">
          <label>Region
            <select value={region} onChange={(e) => setRegion(e.target.value)}>
              {info.catalog.regions.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
            </select>
          </label>
          <label>Realm
            <select value={realmType} disabled={regionOnly} onChange={(e) => setRealmType(e.target.value)}>
              {regionInfo?.realms.map((k) => <option key={k} value={k}>{info.catalog.realm_types[k]}</option>)}
            </select>
          </label>
          <label>Faction
            <select value={faction} disabled={regionOnly} onChange={(e) => setFaction(e.target.value)}>
              {Object.entries(info.catalog.factions).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="check">
            <input type="checkbox" checked={regionOnly} onChange={(e) => setRegionOnly(e.target.checked)} />
            Region only
            <Hint text="Use only region-wide prices. Choose this if TSM has no file for your auction house." />
          </label>
        </div>
        <div className="filters">
          <label className="check">
            <input type="radio" checked={house === "faction"} onChange={() => setHouse("faction")} />
            I sell on the {regionOnly ? "faction" : info.catalog.factions[faction]} auction house (5% cut)
          </label>
          <label className="check">
            <input type="radio" checked={house === "neutral"} onChange={() => setHouse("neutral")} />
            I sell on the neutral auction house (15% cut)
          </label>
          <Hint text="The cut is what the auction house keeps from each sale. Prices still come from TSM's faction auction house data; TSM publishes no neutral data." />
        </div>
        <div className="small">
          TSM region file: {checkLine("region")}
          {!regionOnly && <> · auction house file <code>{realm}</code>: {checkLine("realm")}</>}
        </div>
      </div>

      <div className="card">
        <h3>2. Game folder <span className="muted small">(optional, for your own Auctionator scans and recipes)</span></h3>
        {installs.length === 0 && <p className="muted">No WoW Forever install was found automatically. Enter the folder below.</p>}
        <div className="installs">
          {installs.map((inst) => (
            <InstallCard key={inst.path} inst={inst} selected={inspected?.path === inst.path}
              onPick={() => { setGameDir(inst.path); setManualDir(inst.path); }} />
          ))}
        </div>
        <div className="filters">
          <input style={{ flex: 1, minWidth: 320 }} placeholder="e.g. D:\World of Warcraft\_forever_"
            value={manualDir} onChange={(e) => setManualDir(e.target.value)} />
          <button onClick={() => setGameDir(manualDir.trim())}>Use this folder</button>
          {gameDir && <button onClick={() => { setGameDir(""); setManualDir(""); }}>No game folder</button>}
        </div>
        {inspected && !inspected.exists && <p className="neg">That folder does not exist.</p>}
        {inspected?.exists && inspected.has_wtf && (
          <div className="filters">
            <span className="small">
              SimsarForeverExport addon:{" "}
              {!inspected.export_addon_installed ? <span className="neg">not installed</span>
                : inspected.export_addon_version !== info.addon_version
                  ? <span className="neg">version {inspected.export_addon_version}, {info.addon_version} available</span>
                  : <span className="pos">installed ({inspected.export_addon_version})</span>}
              <Hint text="The addon saves your recipes, vendor prices, bags and bank so the dashboard does not have to guess them. It only reads; it never posts, buys or clicks." />
            </span>
            {(!inspected.export_addon_installed || inspected.export_addon_version !== info.addon_version) && (
              <button onClick={() => api.installAddon(inspected.path).then(
                (r) => { setAddonMsg(`Installed to ${r.path}. Enable it in the game's AddOns list, then /reload.`); setGameDir(""); setTimeout(() => setGameDir(inspected.path), 50); },
                (e) => setAddonMsg(String(e)))}>
                {inspected.export_addon_installed ? "Update addon" : "Install addon"}
              </button>
            )}
            {addonMsg && <span className="small muted">{addonMsg}</span>}
          </div>
        )}
        {inspected?.exists && !inspected.has_wtf && <p className="neg">No WTF folder there. Pick the folder that contains Wow.exe and WTF (usually ..._forever_).</p>}
        {inspected?.accounts.length ? (
          <div className="filters">
            <label>Account
              <select value={account} onChange={(e) => setAccount(e.target.value)}>
                {inspected.accounts.map((a) => (
                  <option key={a.name} value={a.name}>
                    {a.name}{a.has_auctionator ? ` (Auctionator data ${ago(a.auctionator_mtime)})` : " (no Auctionator data)"}
                  </option>
                ))}
              </select>
            </label>
            {atoRealms.length > 1 && (
              <label>Auctionator realm
                <select value={atoRealm} onChange={(e) => setAtoRealm(e.target.value)}>
                  <option value="">Largest</option>
                  {atoRealms.map((r) => <option key={r.key} value={r.key}>{r.key} ({r.items} items)</option>)}
                </select>
              </label>
            )}
          </div>
        ) : null}
      </div>

      <div className="card">
        <h3>3. Your professions</h3>
        <p className="muted small">They are shown first. Every profession is still analysed.</p>
        <div className="prof-grid">
          {info.professions.map((p) => (
            <label key={p} className="check">
              <input type="checkbox" checked={professions.includes(p)}
                onChange={(e) => setProfessions(e.target.checked ? [...professions, p] : professions.filter((x) => x !== p))} />
              {p}
            </label>
          ))}
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}
      <div className="filters">
        <button className="primary" onClick={save} disabled={saving}>{saving ? "Saving..." : "Save and start"}</button>
      </div>
    </section>
  );
}
