import { NextResponse } from "next/server";
import { AUTO_OPTIONS, EVERY_OPTIONS, HOURS_OPTIONS, PUBLISH_OPTIONS, TOP_OPTIONS, VIEWS_OPTIONS, saveSchedule } from "@/lib/schedule";

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
    min_views: pick(f.get("min_views"), VIEWS_OPTIONS, 200),
    hours: pick(f.get("hours"), HOURS_OPTIONS, 48),
    publish_every_min: pick(f.get("publish_every_min"), PUBLISH_OPTIONS, 120),
    auto_min: pick(f.get("auto_min"), AUTO_OPTIONS, 7),
  });
  return NextResponse.redirect(new URL("/?prog=ok", req.url), 303);
}
