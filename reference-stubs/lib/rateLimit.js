import { kv } from '@vercel/kv';

const WINDOW_S = 60;
const LIMIT = 60;         // requests/min/user
const FLAG_THRESHOLD = 5; // consecutive over-limit windows -> flag for review

export async function checkRate(userId) {
  const key = `rl:${userId}:${Math.floor(Date.now() / 1000 / WINDOW_S)}`;
  const count = await kv.incr(key);
  if (count === 1) await kv.expire(key, WINDOW_S);
  return count <= LIMIT;
}

// Soft flag: marks account for manual review. Never auto-bans, never deletes
// user data, never touches the client. A human/dashboard decides next steps.
export async function flagIfAbusive(userId) {
  const flagKey = `flagcount:${userId}`;
  const n = await kv.incr(flagKey);
  await kv.expire(flagKey, 3600);
  if (n >= FLAG_THRESHOLD) {
    await kv.set(`review_queue:${userId}`, { userId, flaggedAt: Date.now(), reason: 'rate_abuse' });
  }
}

export async function isUnderReview(userId) {
  return !!(await kv.get(`review_queue:${userId}`));
}
