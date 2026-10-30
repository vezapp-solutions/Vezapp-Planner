import { useEffect, useState } from "react";

import { api } from "./api";

interface Result<T> {
  key: string;
  data?: T;
  error?: Error;
}

/** GET a path once per (path, reload). `loading` is derived, so it is never stale. */
export function useApi<T>(path: string) {
  const [tick, setTick] = useState(0);
  const [result, setResult] = useState<Result<T> | null>(null);
  const key = `${path}#${tick}`;

  useEffect(() => {
    let live = true;
    api<T>(path)
      .then((data) => live && setResult({ key, data }))
      .catch((error: Error) => live && setResult({ key, error }));
    return () => {
      live = false;
    };
  }, [path, key]);

  const current = result?.key === key ? result : null;
  return {
    data: current?.data,
    error: current?.error,
    loading: current === null,
    reload: () => setTick((t) => t + 1),
  };
}
