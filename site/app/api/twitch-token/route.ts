import { NextResponse } from "next/server";
import { createHmac, timingSafeEqual } from "node:crypto";
import { getToken } from "@/lib/twitch";

// Jeton Twitch « application » (lecture des données publiques uniquement) prêté au bot GitHub
// quand sa propre clé Twitch est refusée. Le bot prouve qu'il est le bot en signant l'heure
// avec la clé R2 que lui et le site connaissent déjà (rien de secret ne circule).
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const key = process.env.R2_SECRET_ACCESS_KEY;
  const ts = req.headers.get("x-ts") ?? "";
  const sig = req.headers.get("x-sig") ?? "";
  const age = Math.abs(Date.now() / 1000 - Number(ts));
  if (!key || !ts || !(age < 300)) return NextResponse.json({ error: "refusé" }, { status: 403 });
  const want = createHmac("sha256", key).update(`twitch-token:${ts}`).digest("hex");
  if (sig.length !== want.length || !timingSafeEqual(Buffer.from(sig), Buffer.from(want))) {
    return NextResponse.json({ error: "refusé" }, { status: 403 });
  }
  try {
    return NextResponse.json({ access_token: await getToken(), expires_in: 3000 });
  } catch (e) {
    return NextResponse.json({ error: String(e).slice(0, 200) }, { status: 502 });
  }
}
