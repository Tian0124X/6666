import { create } from "zustand";

type Theme = "light" | "dark";

interface ThemeStore {
  theme: Theme;
  toggle: () => void;
  setTheme: (t: Theme) => void;
}

const getInitialTheme = (): Theme => {
  try { return (localStorage.getItem("theme") as Theme) || "light"; }
  catch { return "light"; }
};

export const useThemeStore = create<ThemeStore>((set) => ({
  theme: getInitialTheme(),
  toggle: () =>
    set((s) => {
      const next = s.theme === "light" ? "dark" : "light";
      try { localStorage.setItem("theme", next); } catch { /* privacy mode */ }
      document.documentElement.classList.toggle("dark", next === "dark");
      return { theme: next };
    }),
  setTheme: (t) => {
    try { localStorage.setItem("theme", t); } catch { /* privacy mode */ }
    document.documentElement.classList.toggle("dark", t === "dark");
    set({ theme: t });
  },
}));
