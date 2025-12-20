import type { Express } from "express";
import type { Server } from "http";
import { storage } from "./storage";
import { api } from "@shared/routes";
import { z } from "zod";
import { bot } from "./bot";

export async function registerRoutes(
  httpServer: Server,
  app: Express
): Promise<Server> {
  
  app.get(api.signals.list.path, async (_req, res) => {
    const signals = await storage.getSignals();
    res.json(signals);
  });

  app.get(api.trades.list.path, async (_req, res) => {
    const trades = await storage.getTrades();
    res.json(trades);
  });

  app.get(api.portfolio.get.path, async (_req, res) => {
    try {
      const portfolio = await bot.getPortfolio();
      res.json(portfolio);
    } catch (e: any) {
      res.status(500).json({ message: e.message });
    }
  });

  app.get(api.settings.list.path, async (_req, res) => {
    const settings = await storage.getSettings();
    res.json(settings);
  });

  app.post(api.settings.update.path, async (req, res) => {
    try {
      const input = api.settings.update.input.parse(req.body);
      const setting = await storage.updateSetting(input.key, input.value);
      res.json(setting);
    } catch (err) {
      if (err instanceof z.ZodError) {
        return res.status(400).json({ message: err.errors[0].message });
      }
      res.status(500).json({ message: "Internal server error" });
    }
  });

  app.post(api.bot.start.path, async (_req, res) => {
    bot.start();
    res.json({ status: "started" });
  });

  app.post(api.bot.stop.path, async (_req, res) => {
    bot.stop();
    res.json({ status: "stopped" });
  });

  app.get(api.bot.status.path, async (_req, res) => {
    res.json({ isRunning: bot.isActive() });
  });

  return httpServer;
}
