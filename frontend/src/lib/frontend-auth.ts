"use client";
import { initializeApp, getApps, getApp } from "firebase/app";
import { getAuth, onAuthStateChanged } from "firebase/auth";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

const app = getApps().length ? getApp() : initializeApp(firebaseConfig);
export const auth = getAuth(app);

// Call this after login (or on app load) to sync the user into Neon
export async function syncUserWithBackend() {
  const currentUser = auth.currentUser;
  if (!currentUser) return null;

  // Get fresh Firebase ID token
  const idToken = await currentUser.getIdToken();

  // Send it to the secured Vercel API route
  const res = await fetch("/api/user", {
    method: "GET",
    headers: { Authorization: `Bearer ${idToken}` },
  });

  if (!res.ok) throw new Error("Failed to sync user");
  return res.json(); // { user: { id, email, tier, createdAt } }
}

// Example: run sync automatically once auth state resolves
onAuthStateChanged(auth, (user) => {
  if (user) syncUserWithBackend().catch(console.error);
});
