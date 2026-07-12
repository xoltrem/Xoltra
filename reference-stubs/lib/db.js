// Replace with real Postgres/Prisma client. Stubbed for structure only.
export const db = {
  memory: {
    async findRelevant(userId, query, opts) { return []; },
  },
  skills: {
    async get(userId) { return { xp: 0 }; },
    async save(userId, data) { return data; },
  },
};
