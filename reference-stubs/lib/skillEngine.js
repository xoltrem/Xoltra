import { db } from './db';

export async function computeSkillState(userId, input) {
  const profile = await db.skills.get(userId);
  // proprietary calculation stays server-side, never exposed to client
  const updated = applyProgress(profile, input);
  await db.skills.save(userId, updated);
  return updated;
}

function applyProgress(profile, input) {
  return { ...profile, xp: (profile?.xp || 0) + (input?.delta || 0) };
}
