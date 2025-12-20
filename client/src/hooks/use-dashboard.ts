import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@shared/routes";
import { Signal, Trade, Setting, PortfolioBalance } from "@shared/schema";

// Helper to handle API responses safely
async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: "include" });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

// === Signals Hooks ===
export function useSignals() {
  return useQuery({
    queryKey: [api.signals.list.path],
    queryFn: () => fetchApi<Signal[]>(api.signals.list.path),
    refetchInterval: 10000, // Refresh every 10s for new signals
  });
}

// === Trades Hooks ===
export function useTrades() {
  return useQuery({
    queryKey: [api.trades.list.path],
    queryFn: () => fetchApi<Trade[]>(api.trades.list.path),
    refetchInterval: 15000,
  });
}

// === Portfolio Hooks ===
export function usePortfolio() {
  return useQuery({
    queryKey: [api.portfolio.get.path],
    queryFn: () => fetchApi<PortfolioBalance[]>(api.portfolio.get.path),
    refetchInterval: 30000,
  });
}

// === Settings Hooks ===
export function useSettings() {
  return useQuery({
    queryKey: [api.settings.list.path],
    queryFn: () => fetchApi<Setting[]>(api.settings.list.path),
  });
}

export function useUpdateSetting() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { key: string; value: string }) => {
      const res = await fetch(api.settings.update.path, {
        method: api.settings.update.method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
        credentials: "include",
      });
      if (!res.ok) throw new Error("Failed to update setting");
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [api.settings.list.path] });
    },
  });
}

// === Bot Control Hooks ===
export function useBotStatus() {
  return useQuery({
    queryKey: [api.bot.status.path],
    queryFn: () => fetchApi<{ isRunning: boolean }>(api.bot.status.path),
    refetchInterval: 5000,
  });
}

export function useBotControl() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (action: "start" | "stop") => {
      const path = action === "start" ? api.bot.start.path : api.bot.stop.path;
      const res = await fetch(path, { 
        method: "POST",
        credentials: "include"
      });
      if (!res.ok) throw new Error(`Failed to ${action} bot`);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [api.bot.status.path] });
    },
  });
}
