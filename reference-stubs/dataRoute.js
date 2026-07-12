'use strict';
const express = require('express');
const rateLimit = require('express-rate-limit');
const { z } = require('zod');
const router = express.Router();

const limiter = rateLimit({ windowMs: 60_000, max: 30 });

const recordSchema = z.object({
  userId: z.string().uuid(),
  version: z.number().int().nonnegative(),
});

// GET /api/record/golden — returns server-authoritative record
router.get('/record/golden', limiter, requireAuth, async (req, res) => {
  const parsed = recordSchema.safeParse({ userId: req.user.id, version: 0 });
  if (!parsed.success) return res.status(400).json({ error: 'invalid_request' });

  const record = await db.getRecord(req.user.id);
  if (!record) return res.status(404).json({ error: 'not_found' });

  res.json({ record, issuedAt: Date.now() });
});

function requireAuth(req, res, next) {
  if (!req.user) return res.status(401).json({ error: 'unauthorized' });
  next();
}

module.exports = router;
