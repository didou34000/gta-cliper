import { NextResponse } from "next/server";
import { deleteClip, saveDecision, type Status } from "@/lib/data";
import { publishOne, publishQueue } from "@/lib/buffer";

const ALLOWED: Status[] = ["pending", "approved", "rejected", "posted"];

export async function POST(req: Request) {
  const f = await req.formData();
  const id = String(f.get("id") ?? "");
  const raw = String(f.get("status") ?? "");
  const publishNow = raw === "publish"; // bouton « Publier » : validé + programmé tout de suite
  const status = (publishNow ? "approved" : raw) as Status;
  if (!id || !ALLOWED.includes(status)) {
    return NextResponse.json({ error: "Requête invalide" }, { status: 400 });
  }
  const hashtags = String(f.get("hashtags") ?? "")
    .split(/\s+/).filter(Boolean).map((t) => (t.startsWith("#") ? t : `#${t}`));
  if (status === "rejected") {
    await deleteClip(id);
  } else await saveDecision(id, {
    status,
    title: String(f.get("title") ?? "").trim() || undefined,
    description: String(f.get("description") ?? "").trim() || undefined,
    hashtags: hashtags.length ? hashtags : undefined,
    post_url: String(f.get("post_url") ?? "").trim() || undefined,
  });
  // Un clip validé part tout de suite dans la file Buffer (si la clé est configurée).
  let note = "";
  if (publishNow) {
    const r = await publishOne(id).catch((e) => ({ ok: false, message: String(e) }));
    note = r.ok ? "" : r.message;
  } else if (status === "approved") await publishQueue().catch(() => {});
  const back = String(f.get("back") ?? "/");
  const url = new URL(back.startsWith("/") ? back : "/", req.url);
  if (note) url.searchParams.set("erreur", note.slice(0, 200));
  return NextResponse.redirect(url, 303);
}
