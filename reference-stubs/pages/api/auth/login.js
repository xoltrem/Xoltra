import bcrypt from 'bcryptjs';
import { db } from '../../../lib/db';
import { issueTokens } from '../../../lib/tokens';

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end();
  const { email, password } = req.body || {};
  if (!email || !password) return res.status(400).json({ error: 'missing_fields' });

  const user = await db.users?.findByEmail?.(email);
  if (!user || !(await bcrypt.compare(password, user.passwordHash))) {
    return res.status(401).json({ error: 'invalid_credentials' });
  }

  const tokens = issueTokens(user.id);
  res.status(200).json(tokens);
}
