import { db } from "./db";
import {
  signals, trades, settings,
  type InsertSignal, type InsertTrade, type InsertSetting,
  type Signal, type Trade, type Setting
} from "@shared/schema";
import { eq, desc } from "drizzle-orm";

export interface IStorage {
  getSignals(): Promise<Signal[]>;
  createSignal(signal: InsertSignal): Promise<Signal>;
  getTrades(): Promise<Trade[]>;
  createTrade(trade: InsertTrade): Promise<Trade>;
  getSettings(): Promise<Setting[]>;
  updateSetting(key: string, value: string): Promise<Setting>;
  getSetting(key: string): Promise<Setting | undefined>;
}

export class DatabaseStorage implements IStorage {
  async getSignals(): Promise<Signal[]> {
    return await db.select().from(signals).orderBy(desc(signals.timestamp));
  }

  async createSignal(signal: InsertSignal): Promise<Signal> {
    const [newSignal] = await db.insert(signals).values(signal).returning();
    return newSignal;
  }

  async getTrades(): Promise<Trade[]> {
    return await db.select().from(trades).orderBy(desc(trades.timestamp));
  }

  async createTrade(trade: InsertTrade): Promise<Trade> {
    const [newTrade] = await db.insert(trades).values(trade).returning();
    return newTrade;
  }

  async getSettings(): Promise<Setting[]> {
    return await db.select().from(settings);
  }

  async updateSetting(key: string, value: string): Promise<Setting> {
    const [updated] = await db.insert(settings)
      .values({ key, value })
      .onConflictDoUpdate({ target: settings.key, set: { value } })
      .returning();
    return updated;
  }

  async getSetting(key: string): Promise<Setting | undefined> {
    const [setting] = await db.select().from(settings).where(eq(settings.key, key));
    return setting;
  }
}

export const storage = new DatabaseStorage();
