import "server-only";
import { z } from "zod";

const serverEnvSchema = z.object({
  POSTGRES_URL: z.string().url(),
  FIREBASE_PROJECT_ID: z.string().min(1),
  FIREBASE_CLIENT_EMAIL: z.string().email(),
  FIREBASE_PRIVATE_KEY: z.string().min(1),
});

const clientEnvSchema = z.object({
  NEXT_PUBLIC_FIREBASE_API_KEY: z.string().min(1),
  NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: z.string().min(1),
  NEXT_PUBLIC_FIREBASE_PROJECT_ID: z.string().min(1),
  NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET: z.string().min(1),
  NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID: z.string().min(1),
  NEXT_PUBLIC_FIREBASE_APP_ID: z.string().min(1),
});

const parsedServer = serverEnvSchema.safeParse(process.env);
if (!parsedServer.success) {
  console.error(parsedServer.error.flatten().fieldErrors);
  throw new Error("Missing/invalid SERVER env vars. Check Vercel project settings.");
}

const parsedClient = clientEnvSchema.safeParse(process.env);
if (!parsedClient.success) {
  console.error(parsedClient.error.flatten().fieldErrors);
  throw new Error("Missing/invalid NEXT_PUBLIC env vars.");
}

export const serverEnv = parsedServer.data;
export const clientEnv = parsedClient.data;
