'use strict';
require('dotenv').config();
const express = require('express');
const cors    = require('cors');
const auth    = require('./auth');

const app = express();

app.set('trust proxy', 1); // needed for req.ip behind reverse proxy

app.use(cors({ origin: process.env.FRONTEND_URL || 'http://localhost:5173', credentials: true }));
app.use(express.json({ limit: '10kb' }));

app.use('/api/auth', auth);

app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({ error: 'Internal server error.' });
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`Auth server on :${PORT}`));
