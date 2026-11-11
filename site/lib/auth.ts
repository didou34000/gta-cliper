// Authentification minimale : un mot de passe partagé (SITE_PASSWORD), un cookie signé.
export const COOKIE = "gta_auth";

async function hmac(secret: string, msg: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(msg));
  return Array.from(new Uint8Array(sig)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function expectedToken(): Promise<string | null> {
  const pw = process.env.SITE_PASSWORD;
  if (!pw) return null;
  return hmac(pw, "gta-clipper-session-v1");
}

export async function isValid(token: string | undefined): Promise<boolean> {
  const exp = await expectedToken();
  return !!exp && !!token && token === exp;
}
