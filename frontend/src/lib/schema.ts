import { pgTable, pgEnum, text, timestamp } from "drizzle-orm/pg-core";

// Rule 3: clean Postgres enum for tiers
export const userTierEnum = pgEnum("user_tier", ["free", "pro", "enterprise"]);

// Rule 2: Firebase uid (raw string, no prefixing/composite keys) used directly as PK
export const users = pgTable("users", {
  id: text("id").primaryKey(), // = Firebase Auth uid, unmodified
  email: text("email").notNull().unique(),
  tier: userTierEnum("tier").notNull().default("free"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
});

export type User = typeof users.$inferSelect;
export type NewUser = typeof users.$inferInsert;
