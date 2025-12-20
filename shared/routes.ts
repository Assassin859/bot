import { z } from 'zod';
import { insertSignalSchema, insertTradeSchema, insertSettingSchema, signals, trades, settings } from './schema';

export const errorSchemas = {
  validation: z.object({
    message: z.string(),
    field: z.string().optional(),
  }),
  notFound: z.object({
    message: z.string(),
  }),
  internal: z.object({
    message: z.string(),
  }),
};

export const api = {
  signals: {
    list: {
      method: 'GET' as const,
      path: '/api/signals',
      responses: {
        200: z.array(z.custom<typeof signals.$inferSelect>()),
      },
    },
  },
  trades: {
    list: {
      method: 'GET' as const,
      path: '/api/trades',
      responses: {
        200: z.array(z.custom<typeof trades.$inferSelect>()),
      },
    },
  },
  portfolio: {
    get: {
      method: 'GET' as const,
      path: '/api/portfolio',
      responses: {
        200: z.array(z.object({
          asset: z.string(),
          free: z.number(),
          locked: z.number(),
          total: z.number(),
        })),
        500: errorSchemas.internal,
      },
    },
  },
  settings: {
    list: {
      method: 'GET' as const,
      path: '/api/settings',
      responses: {
        200: z.array(z.custom<typeof settings.$inferSelect>()),
      },
    },
    update: {
      method: 'POST' as const,
      path: '/api/settings',
      input: insertSettingSchema,
      responses: {
        200: z.custom<typeof settings.$inferSelect>(),
        400: errorSchemas.validation,
      },
    },
  },
  bot: {
    start: {
      method: 'POST' as const,
      path: '/api/bot/start',
      responses: {
        200: z.object({ status: z.string() }),
      },
    },
    stop: {
      method: 'POST' as const,
      path: '/api/bot/stop',
      responses: {
        200: z.object({ status: z.string() }),
      },
    },
    status: {
      method: 'GET' as const,
      path: '/api/bot/status',
      responses: {
        200: z.object({ isRunning: z.boolean() }),
      },
    },
  },
};

export function buildUrl(path: string, params?: Record<string, string | number>): string {
  let url = path;
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (url.includes(`:${key}`)) {
        url = url.replace(`:${key}`, String(value));
      }
    });
  }
  return url;
}
