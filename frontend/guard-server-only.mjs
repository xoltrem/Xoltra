#!/usr/bin/env node
/**
 * Fails CI if any file importing db.ts / firebase-admin.ts is marked "use client"
 * or lives outside server-only boundaries. Run via: node scripts/guard-server-only.mjs
 */
import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";

const ROOT = join(process.cwd(), "src");
const GUARDED = ["db.ts", "firebase-admin.ts"];
let failed = false;

function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      walk(full);
    } else if (/\.(ts|tsx)$/.test(entry)) {
      const content = readFileSync(full, "utf8");
      const isClient = content.trimStart().startsWith('"use client"');
      const importsGuarded = GUARDED.some((g) => content.includes(g.replace(".ts", "")));
      if (isClient && importsGuarded) {
        console.error(`BLOCKED: ${full} is "use client" but imports a server-only module.`);
        failed = true;
      }
    }
  }
}

walk(ROOT);
if (failed) process.exit(1);
console.log("guard-server-only: OK");
