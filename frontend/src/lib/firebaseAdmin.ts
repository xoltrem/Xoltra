import "server-only";
import { initializeApp, getApps, cert, App } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";

// Singleton pattern — Next.js hot-reloads/serverless can re-run this module
const adminApp: App = getApps().length
  ? getApps()[0]
  : initializeApp({
      credential: cert({
        projectId: process.env.FIREBASE_PROJECT_ID,
        clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
        // .env stores \n as literal chars — convert back to real newlines
        privateKey: process.env.FIREBASE_PRIVATE_KEY?.replace(/\\n/g, "\n"),
      }),
    });

export const adminAuth = getAuth(adminApp);

// Verifies the ID token sent from the client; throws if invalid/expired
export async function verifyIdToken(idToken: string) {
  return adminAuth.verifyIdToken(idToken);
}
