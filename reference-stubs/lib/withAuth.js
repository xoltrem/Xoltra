import { verifyAccess } from './tokens';
import { checkRate, flagIfAbusive, isUnderReview } from './rateLimit';

export function withAuth(handler) {
  return async (req, res) => {
    const authHeader = req.headers.authorization || '';
    const token = authHeader.startsWith('Bearer ') ? authHeader.slice(7) : null;
    if (!token) return res.status(401).json({ error: 'unauthorized' });

    let payload;
    try {
      payload = verifyAccess(token);
    } catch {
      return res.status(401).json({ error: 'invalid_token' });
    }

    const userId = payload.sub;

    if (await isUnderReview(userId)) {
      // Under manual review, not banned — still gets a clear, honest response.
      return res.status(423).json({ error: 'account_under_review' });
    }

    const ok = await checkRate(userId);
    if (!ok) {
      await flagIfAbusive(userId);
      return res.status(429).json({ error: 'rate_limited' });
    }

    req.userId = userId;
    return handler(req, res);
  };
}
