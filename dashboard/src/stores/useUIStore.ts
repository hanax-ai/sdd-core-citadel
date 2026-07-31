import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ConnectionMode = "demo" | "live";
export type ReplaySpeed = 1 | 2 | 5;

type UIState = {
  mode: ConnectionMode;
  bridgeUrl: string;
  bridgeKey: string;
  replaySpeed: ReplaySpeed;
  setMode: (mode: ConnectionMode) => void;
  setBridgeUrl: (url: string) => void;
  setBridgeKey: (key: string) => void;
  setReplaySpeed: (speed: ReplaySpeed) => void;
};

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      mode: "demo",
      bridgeUrl: "http://127.0.0.1:8000",
      bridgeKey: "",
      replaySpeed: 1,
      setMode: (mode) => set({ mode }),
      setBridgeUrl: (bridgeUrl) => set({ bridgeUrl }),
      setBridgeKey: (bridgeKey) => set({ bridgeKey }),
      setReplaySpeed: (replaySpeed) => set({ replaySpeed }),
    }),
    { name: "citadel-ui" },
  ),
);
