import { NextResponse } from "next/server";
import { EVERY_OPTIONS, PUBLISH_OPTIONS, TOP_OPTIONS, saveSchedule } from "@/lib/schedule";

const pick = (v: FormDataEntryValue | null, allowed: number[], dflt: number) => {
  const n = parseInt(String(v ?? ""), 10);
  return allowed.includes(n) ? n : dflt;
};

export async function POST(req: Request) {
  const f = await req.formData();
  const other = String(f.get("jeu_autre") ?? "").trim();
  await saveSchedule({
    enabled: f.get("enabled") === "on",
    every_min: pick(f.get("every_min"), EVERY_OPTIONS, 30),
    game: (other || String(f.get("jeu") ?? "")).slice(0, 80) || "Grand Theft Auto VI",
    top: pick(f.get("top"), TOP_OPTIONS, 8),
    max_clips: Math.min(10, Math.max(1, parseInt(String(f.get("max_clips") ?? "3"), 10) || 3)),
    publish_every_min: pick(f.get("publish_every_min"), PUBLISH_OPTIONS, 120),
  });
  return NextResponse.redirect(new URL("/?prog=ok", req.url), 303);
}
