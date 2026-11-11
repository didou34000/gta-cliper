import { NextResponse } from "next/server";
import { saveDecision, type Status } from "@/lib/data";

const ALLOWED: Status[] = ["pending", "approved", "rejected", "posted"];

export async function POST(req: Request) {
  const f = await req.formData();
  const id = String(f.get("id") ?? "");
  const status = String(f.get("status") ?? "") as Status;
  if (!id || !ALLOWED.includes(status)) {
    return NextResponse.json({ error: "Requête invalide" }, { status: 400 });
  }
  const hashtags = String(f.get("hashtags") ?? "")
    .split(/\s+/).filter(Boolean).map((t) => (t.startsWith("#") ? t : `#${t}`));
  await saveDecision(id, {
    status,
    title: String(f.get("title") ?? "").trim() || undefined,
    description: String(f.get("description") ?? "").trim() || undefined,
    hashtags: hashtags.length ? hashtags : undefined,
    post_url: String(f.get("post_url") ?? "").trim() || undefined,
  });
  const back = String(f.get("back") ?? "/");
  return NextResponse.redirect(new URL(back.startsWith("/") ? back : "/", req.url), 303);
}
