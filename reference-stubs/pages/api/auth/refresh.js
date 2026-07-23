import { verifyRefresh, issueTokens } from '../../../lib/tokens';

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end();
  const { refresh } = req.body || {};
  try {
    const payload = verifyRefresh(refresh);
    const { access } = issueTokens(payload.sub);
    res.status(200).json({ access });
  } catch {
    res.status(401).json({ error: 'invalid_refresh' });
  }
}
