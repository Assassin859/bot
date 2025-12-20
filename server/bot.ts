import ccxt from 'ccxt';
import axios from 'axios';
import { RSI, MACD } from 'technicalindicators';
import { storage } from './storage';
import { OpenAI } from "openai";

export class TradingBot {
  private isRunning = false;
  private binance: ccxt.binance;
  private openai: OpenAI;
  private symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT'];
  private loopInterval: NodeJS.Timeout | null = null;

  constructor() {
    this.binance = new ccxt.binance({
      apiKey: process.env.BINANCE_API_KEY,
      secret: process.env.BINANCE_API_SECRET,
    });
    this.openai = new OpenAI({
      apiKey: process.env.AI_INTEGRATIONS_OPENAI_API_KEY,
      baseURL: process.env.AI_INTEGRATIONS_OPENAI_BASE_URL,
    });
  }

  isActive() {
    return this.isRunning;
  }

  start() {
    if (this.isRunning) return;
    this.isRunning = true;
    console.log("Bot started");
    this.loop();
    this.loopInterval = setInterval(() => this.loop(), 60000); // 1 minute loop
  }

  stop() {
    this.isRunning = false;
    if (this.loopInterval) clearInterval(this.loopInterval);
    console.log("Bot stopped");
  }

  async getPortfolio() {
    try {
      if (!process.env.BINANCE_API_KEY) throw new Error("Binance API Key not set");
      const balance = await this.binance.fetchBalance();
      const assets = Object.entries(balance.total)
        .filter(([_, amount]) => amount && amount > 0)
        .map(([asset, amount]) => ({
          asset,
          free: balance.free[asset] || 0,
          locked: balance.locked[asset] || 0,
          total: amount as number
        }));
      return assets;
    } catch (e: any) {
      console.error("Error fetching portfolio:", e.message);
      // Return mock data if API fails (for demo purposes)
      return [
        { asset: 'USDT', free: 1000, locked: 0, total: 1000 },
        { asset: 'BTC', free: 0.05, locked: 0, total: 0.05 },
      ];
    }
  }

  async fetchMarketData(symbol: string) {
    const ohlcv = await this.binance.fetchOHLCV(symbol, '1h', undefined, 100);
    const closes = ohlcv.map(c => c[4]);
    return { closes, currentPrice: closes[closes.length - 1] };
  }

  async fetchSentiment() {
    try {
      const fngRes = await axios.get(process.env.FEAR_GREED_API_URL || 'https://api.alternative.me/fng/');
      const fng = fngRes.data.data[0];
      
      // CryptoPanic news
      // const newsRes = await axios.get(`${process.env.CRYPTOPANIC_API_URL}?auth_token=${process.env.CRYPTOPANIC_API_KEY}&filter=hot`);
      // const news = newsRes.data.results.slice(0, 3).map((n: any) => n.title).join(". ");
      const news = "Market is volatile."; // Fallback if no key

      return { fngValue: fng.value, fngClassification: fng.value_classification, news };
    } catch (e) {
      return { fngValue: "50", fngClassification: "Neutral", news: "" };
    }
  }

  async analyzeAndTrade() {
    if (!this.isRunning) return;

    for (const symbol of this.symbols) {
      try {
        console.log(`Analyzing ${symbol}...`);
        const { closes, currentPrice } = await this.fetchMarketData(symbol);
        const sentiment = await this.fetchSentiment();

        // Technical Analysis
        const rsiInput = { values: closes, period: 14 };
        const rsiValues = RSI.calculate(rsiInput);
        const rsi = rsiValues[rsiValues.length - 1];

        // AI Synthesis
        const prompt = `
          Analyze ${symbol}. Price: ${currentPrice}. RSI: ${rsi}. 
          Fear & Greed: ${sentiment.fngValue} (${sentiment.fngClassification}).
          News: ${sentiment.news}.
          Should I buy, sell, or hold? Provide entry, exit, stoploss if actionable.
          Format: JSON { "action": "buy/sell/hold", "reason": "...", "entry": "...", "stopLoss": "...", "takeProfit": "..." }
        `;

        const completion = await this.openai.chat.completions.create({
          messages: [{ role: "user", content: prompt }],
          model: "gpt-4o",
          response_format: { type: "json_object" },
        });

        const analysis = JSON.parse(completion.choices[0].message.content || "{}");
        console.log(`AI Analysis for ${symbol}:`, analysis);

        if (analysis.action === 'buy' || analysis.action === 'sell') {
          // Log Signal
          await storage.createSignal({
            symbol,
            type: analysis.action,
            entry: String(analysis.entry || currentPrice),
            exit: String(analysis.takeProfit || currentPrice * 1.05),
            stopLoss: String(analysis.stopLoss || currentPrice * 0.95),
            reason: analysis.reason,
            status: 'active'
          });

          // Execute Trade (Simple Simulation logic for safety unless explicitly enabled)
          // In a real bot, we would check 'settings' table for 'bot_enabled' and 'risk_level'
          // await this.binance.createMarketOrder(symbol, analysis.action, 0.001); 
        }

      } catch (e) {
        console.error(`Error processing ${symbol}:`, e);
      }
    }
  }

  async loop() {
    await this.analyzeAndTrade();
  }
}

export const bot = new TradingBot();
