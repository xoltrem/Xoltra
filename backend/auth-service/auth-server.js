'use strict';
require('dotenv').config();
const express = require('express');
const cors    = require('cors');
const auth    = require('./auth');

const app = express();
app.set('trust proxy', 1);
// FIX: was single-origin (Vite dashboard only, :5173) — blocked the main
// Next.js app (:3000) from ever reaching this service. Allow both.
const ALLOWED_ORIGINS = (process.env.FRONTEND_URLS || 'http://localhost:3000,http://localhost:5173')
  .split(',').map(o => o.trim());
app.use(cors({ origin: ALLOWED_ORIGINS, credentials: true }));
app.use(express.json({ limit: '10kb' }));
app.use('/api/auth', auth);
app.use((err, req, res, next) => res.status(500).json({ error: 'Internal server error.' }));

// local dev
if (process.env.NODE_ENV !== 'production' || process.env.LOCAL_DEV) {
  app.listen(process.env.PORT || 5000, () => console.log(`Auth server on :${process.env.PORT || 5000}`));
}

module.exports = app; // Vercel expects this
