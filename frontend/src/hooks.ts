import { useCallback, useEffect, useRef, useState } from "react";

export function useData<T>(load: () => Promise<T>, deps: unknown[] = [], refreshKey = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;

  const reload = useCallback(() => {
    loadRef.current().then(
      (d) => {
        setData(d);
        setError(null);
      },
      (e) => setError(String(e)),
    );
  }, []);

  useEffect(reload, [...deps, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps
  return { data, error, reload };
}

export function useStored<T>(key: string, initial: T): [T, (v: T | ((old: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(`simsar-forever:${key}`);
      if (raw === null) return initial;
      const parsed = JSON.parse(raw);
      if (Array.isArray(initial) || typeof initial !== "object" || initial === null) return parsed;
      return { ...initial, ...parsed };
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(`simsar-forever:${key}`, JSON.stringify(value));
    } catch {
      // storage may be unavailable; filters just will not persist
    }
  }, [key, value]);
  return [value, setValue];
}
