import { pgTable, text, serial, integer, boolean, timestamp, jsonb, numeric } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

export const signals = pgTable("signals", {
  id: serial("id").primaryKey(),
  symbol: text("symbol").notNull(),
  type: text("type").notNull(), // 'buy' or 'sell'
  entry: text("entry").notNull(),
  exit: text("exit").notNull(),
  stopLoss: text("stop_loss").notNull(),
  reason: text("reason"),
  timestamp: timestamp("timestamp").defaultNow(),
  status: text("status").default("active"), // active, executed, expired
});

export const trades = pgTable("trades", {
  id: serial("id").primaryKey(),
  symbol: text("symbol").notNull(),
  side: text("side").notNull(), // 'buy' or 'sell'
  amount: text("amount").notNull(),
  price: text("price").notNull(),
  status: text("status").default("open"), // open, closed
  pnl: text("pnl"),
  timestamp: timestamp("timestamp").defaultNow(),
  binanceId: text("binance_id"),
});

export const settings = pgTable("settings", {
  id: serial("id").primaryKey(),
  key: text("key").unique().notNull(),
  value: text("value").notNull(),
});

export const insertSignalSchema = createInsertSchema(signals).omit({ id: true, timestamp: true });
export const insertTradeSchema = createInsertSchema(trades).omit({ id: true, timestamp: true });
export const insertSettingSchema = createInsertSchema(settings).omit({ id: true });

export type Signal = typeof signals.$inferSelect;
export type InsertSignal = z.infer<typeof insertSignalSchema>;
export type Trade = typeof trades.$inferSelect;
export type InsertTrade = z.infer<typeof insertTradeSchema>;
export type Setting = typeof settings.$inferSelect;
export type InsertSetting = z.infer<typeof insertSettingSchema>;

export type PortfolioBalance = {
  asset: string;
  free: number;
  locked: number;
  total: number;
};
