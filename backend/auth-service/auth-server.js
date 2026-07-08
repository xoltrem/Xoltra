'use strict';
require('dotenv').config();
const express = require('express');
const cors    = require('cors');
const auth    = require('./auth');

const app = express();
app.set('trust proxy', 1);
app.use(cors({ origin: process.env.FRONTEND_URL || 'http://localhost:5173', credentials: true }));
app.use(express.json({ limit: '10kb' }));
app.use('/api/auth', auth);
app.use((err, req, res, next) => res.status(500).json({ error: 'Internal server error.' }));

// local dev
if (process.env.NODE_ENV !== 'production' || process.env.LOCAL_DEV) {
  app.listen(process.env.PORT || 5000, () => console.log(`Auth server on :${process.env.PORT || 5000}`));
}

module.exports = app; // Vercel expects this
