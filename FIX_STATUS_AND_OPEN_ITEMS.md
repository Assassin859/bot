# Fix Status and Open Items

_Date: 2026-06-19_

This file consolidates the issue notes, fix summaries, and review reports in the repo into one status list. It separates what is already fixed from what still needs work or verification.

## Verified fixes done

### Startup, API, and resilience
- Removed hardcoded secrets from `.replit`.
- Tightened CORS behavior in the server bootstrap.
- Added startup retry behavior for `EADDRINUSE` so the server can recover by moving to the next port.
- Improved port conflict messaging and Windows process detection.
- Increased API timeout handling from 15s to 30s in the futures metrics and microstructure analyzers.
- Increased retry attempts from 2 to 3 and expanded exponential backoff.
- Improved invalid order book handling so missing or bad order book data degrades gracefully.
- Improved Binance API key error detection and messaging for codes `-2015`, `-1022`, and `-1021`.
- Improved general error-handler Binance authentication detection.

### Trading logic and PnL
- Fixed futures prediction route contract alignment between server, shared routes, and client hooks.
- Corrected take-profit and stop-loss logic so the stop-loss cap uses actual position margin instead of total account margin.
- Persisted TP/SL corrections back to SQLite so repaired values survive restarts.
- Changed `closePosition()` so persistence happens before in-memory state is finalized.
- Normalized Binance / CCXT price and numeric fields in the futures adapter.
- Made external Binance position auto-close use `reduceOnly`.
- Added WebSocket reconnect cleanup so intentional disconnects do not trigger stale reconnects.
- Added mark-price based PnL handling so the bot better matches Binance futures PnL.
- Added `fetchMarkPrice()` support and improved fallback order for PnL calculation.

### Analysis, prediction, and automation
- Added candlestick validation and integrated it into data fetch and storage paths.
- Added confidence calibration checks before opening positions.
- Added NLP-based sentiment processing with multi-source support and fallback behavior.
- Added live-trade signal extraction and signal tracking hooks.
- Added partial profit taking and related exit checks.
- Added market regime detection and regime-based confidence / sizing adjustments.
- Added better futures prediction and dashboard integration.
- Added structured logging in several key paths.

### Validation already recorded in repo notes
- `npm run build` passes from `D:\bot_2_backup_2\Crypto-AlgoBot`.
- The reported `npm run check` failure appears to come from `node_modules/drizzle-orm/.../insert.d.ts` and is not tied to a local source edit.

## Still needed or not fully verified

### Open code issues still called out in the reports
- The fallback order-size precision logic in `server/automation/engine.ts` still uses a hardcoded `0.001` step size when market metadata is unavailable.
- Broader precision and step-size handling should be reviewed for non-BTC / non-ETH symbols.
- Additional persistence and reconciliation paths in the automation layer should be checked for any remaining memory / SQLite divergence.
- The close/open lifecycle in trading automation should be reviewed for failure paths where a partial DB or exchange failure can look successful in logs.
- Balance validation still appears to be a live issue in the log analysis path, especially where insufficient margin attempts continue after validation warnings.
- Binance timestamp / recvWindow drift (`-1021`) still needs a targeted clock-sync or request-window review.

### Open operational and environment items
- The sentiment analysis improvement depends on the `sentiment` npm package being installed.
- The updated startup flow should be revalidated using the actual dev command used by the project.
- The bot should be tested against real Binance connectivity to confirm the timeout and authentication fixes behave as expected in practice.

### Issues that were documented but should be rechecked after the fixes
- Margin insufficient errors (`-2019`) should be rechecked after account balance and sizing validation are corrected.
- Port conflict handling should be revalidated with a live server start on Windows.
- Order book and trade fetch timeouts should be rechecked to confirm the longer timeout and retry policy are sufficient.
- Position size adjustment warnings that mention a hardcoded step size should be rechecked after the precision fallback is replaced.

## Notes from the review reports

- The code review still flags large-file maintainability work in `server/automation/engine.ts`, `server/analysis/predictor.ts`, and `server/routes.ts`.
- The progress report says the audit is not complete yet and explicitly lists remaining edge cases.
- Some log-based issues were already resolved in code, but the repo still needs fresh runtime validation to confirm they are gone in practice.

## Suggested next actions

1. Replace the hardcoded precision fallback in `server/automation/engine.ts` with symbol-driven metadata only.
2. Review balance validation and margin checks so failed checks stop order submission earlier.
3. Revalidate the actual startup and Binance connectivity path with the project's current dev command.
4. Install the `sentiment` package if it has not already been installed in the current environment.
5. Confirm the `-1021` timestamp issue is gone by checking live API calls after a clock and recvWindow review.

## Source notes used for this file

- `ERROR_FIXES_SUMMARY.md`
- `ERROR_LOG_ANALYSIS.md`
- `ERROR_LOG_ANALYSIS_LATEST.md`
- `PNL_FIX_SUMMARY.md`
- `IMPLEMENTATION_NOTES.md`
- `PROGRESS_REPORT.md`
- `PROJECT_REVIEW_REPORT.md`
