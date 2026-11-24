"use client";

import {
  createContext,
  useCallback,
  useContext,
  useSyncExternalStore,
  type ReactNode,
} from "react";

export type WorkbenchTheme = "light" | "dark";

type ThemeContextValue = Readonly<{
  theme: WorkbenchTheme;
  toggleTheme: () => void;
  setTheme: (next: WorkbenchTheme) => void;
}>;

const STORAGE_KEY = "if-theme";
const listeners = new Set<() => void>();

function notifyListeners() {
  listeners.forEach((listener) => listener());
}

function readStoredTheme(): WorkbenchTheme {
  if (typeof window === "undefined") return "light";
  const fromDom = document.documentElement.dataset.theme;
  if (fromDom === "dark" || fromDom === "light") return fromDom;
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

function subscribeTheme(callback: () => void): () => void {
  listeners.add(callback);
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) {
      const next: WorkbenchTheme = event.newValue === "dark" ? "dark" : "light";
      document.documentElement.dataset.theme = next;
      callback();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(callback);
    window.removeEventListener("storage", onStorage);
  };
}

function applyTheme(next: WorkbenchTheme) {
  document.documentElement.dataset.theme = next;
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // Ignore storage failures in restricted browser modes.
  }
  notifyListeners();
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: "light",
  toggleTheme: () => {},
  setTheme: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useSyncExternalStore<WorkbenchTheme>(
    subscribeTheme,
    readStoredTheme,
    () => "light",
  );

  const setTheme = useCallback((next: WorkbenchTheme) => {
    applyTheme(next);
  }, []);

  const toggleTheme = useCallback(() => {
    const current = readStoredTheme();
    applyTheme(current === "dark" ? "light" : "dark");
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
