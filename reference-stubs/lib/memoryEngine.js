import { db } from './db';

export async function getMemoryForUser(userId, query) {
  const rows = await db.memory.findRelevant(userId, query, { topK: 5 });
  return rows;
}
