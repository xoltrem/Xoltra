import { create } from 'zustand';
import { getStatus } from '@/lib/api';
interface UIState {
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (v: boolean) => void;
  searchOpen: boolean;
  setSearchOpen: (v: boolean) => void;
}
export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
  searchOpen: false,
  setSearchOpen: (v) => set({ searchOpen: v }),
}));
interface SystemState {
  status: any;
  loading: boolean;
  error: string | null;
  fetchStatus: () => Promise<void>;
}
export const useSystemStore = create<SystemState>((set) => ({
  status: null,
  loading: true,
  error: null,
  fetchStatus: async () => {
    try {
      const data = await getStatus();
      set({ status: data, error: null, loading: false });
    } catch (e: any) {
      set({ error: e.message, loading: false });
    }
  }
}));
