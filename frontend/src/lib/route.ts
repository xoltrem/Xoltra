import { NextRequest, NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/lib/db";
import { users } from "@/lib/schema";
import { verifyIdToken } from "@/lib/firebaseAdmin";

// Backend helper: promote a user from 'free' -> 'pro' (call from payment webhook etc.)
export async function upgradeToPro(userId: string) {
  const [updated] = await db
    .update(users)
    .set({ tier: "pro" })
    .where(eq(users.id, userId))
    .returning();
  return updated;
}

// GET /api/user — client calls this after login with: Authorization: Bearer <idToken>
export async function GET(req: NextRequest) {
  // 1. Extract token from header
  const authHeader = req.headers.get("authorization");
  const idToken = authHeader?.startsWith("Bearer ") ? authHeader.split("Bearer ")[1] : null;

  if (!idToken) {
    return NextResponse.json({ error: "Missing Authorization header" }, { status: 401 });
  }

  // 2. Verify token via Firebase Admin SDK
  let decoded;
  try {
    decoded = await verifyIdToken(idToken);
  } catch {
    return NextResponse.json({ error: "Invalid or expired token" }, { status: 401 });
  }

  const uid = decoded.uid; // clean Firebase uid, used directly as PK (Rule 1 & 2)
  const email = decoded.email ?? "";

  // 3. Check if user exists in Neon; if not, insert as 'free'
  const existing = await db.query.users.findFirst({ where: eq(users.id, uid) });

  if (existing) {
    return NextResponse.json({ user: existing });
  }

  const [newUser] = await db
    .insert(users)
    .values({ id: uid, email, tier: "free" })
    .returning();

  return NextResponse.json({ user: newUser }, { status: 201 });
}
