import create from "zustand";

// Cursor: UI state store (skeleton for Phase 1)
type UIState = {
  sidebarOpen: boolean;
  setSidebarOpen: (v: boolean) => void;
};

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: false,
  setSidebarOpen: (v: boolean) => set({ sidebarOpen: v })
}));
