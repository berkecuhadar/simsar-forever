import { createContext, type ReactNode, useContext, useEffect, useRef, useState } from "react";
import { type Group, type Status, api } from "./api";

interface AppState {
  status: Status | null;
  groups: Group[];
  version: number;
  error: string | null;
  refreshStatus: () => void;
}

const Ctx = createContext<AppState>({ status: null, groups: [], version: 0, error: null, refreshStatus: () => {} });

export function useApp() {
  return useContext(Ctx);
}

function notify(title: string, body: string) {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  try {
    new Notification(title, { body, tag: title });
  } catch {
    // some browsers only allow notifications from a service worker
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [groups, setGroups] = useState<Group[]>([]);
  const [version, setVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const builtAt = useRef<number | null>(null);
  const unseen = useRef<number | null>(null);

  const refreshStatus = () => {
    api.status().then(
      (s) => {
        setError(null);
        setStatus(s);
        if (builtAt.current !== null && s.built_at !== builtAt.current) setVersion((v) => v + 1);
        builtAt.current = s.built_at;
        if (unseen.current !== null && s.alerts_unseen > unseen.current) {
          api.alerts().then((alerts) => {
            alerts.filter((a) => !a.seen).slice(0, s.alerts_unseen - (unseen.current ?? 0))
              .forEach((a) => notify(a.title, a.message));
          });
        }
        unseen.current = s.alerts_unseen;
      },
      () => setError("Cannot reach the Simsar Forever server. Is it still running?"),
    );
  };

  useEffect(() => {
    refreshStatus();
    api.groups().then(setGroups, () => {});
    const t = setInterval(refreshStatus, 30000);
    return () => clearInterval(t);
  }, []);

  return <Ctx.Provider value={{ status, groups, version, error, refreshStatus }}>{children}</Ctx.Provider>;
}

export function groupTitle(groups: Group[], key: string | null) {
  return groups.find((g) => g.key === key)?.title ?? (key || "Other");
}

export function groupColor(groups: Group[], key: string | null) {
  return groups.find((g) => g.key === key)?.color ?? "#6b7280";
}
