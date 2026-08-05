import "server-only";
import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";

import { serverEnv } from "./env";
import * as schema from "./schema";

void serverEnv;

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});

export const db = drizzle(pool, { schema });
