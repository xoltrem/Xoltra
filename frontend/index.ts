import "server-only";
import { drizzle } from "drizzle-orm/vercel-postgres";
import { sql } from "@vercel/postgres";
import { serverEnv } from "./env";
import * as schema from "./schema";

void serverEnv; // throws at import time if env is misconfigured

export const db = drizzle(sql, { schema });
