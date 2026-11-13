import { NextResponse } from "next/server";
import { AUTO_OPTIONS, EVERY_OPTIONS, HOURS_OPTIONS, PUBLISH_OPTIONS, TOP_OPTIONS, VIEWS_OPTIONS, loadSchedule, saveSchedule, type Schedule } from "@/lib/schedule";

const pick = (v: FormDataEntryValue | null, allowed: number[], dflt: number) => {
  const n = parseInt(String(v ?? ""), 10);
  return allowed.includes(n) ? n : dflt;
};

// Deux formulaires écrivent ici : « auto » (mode automatique) et « publish » (validation +
// rythme). Chacun ne change que ses propres réglages.
export async function POST(req: Request) {
  const f = await req.formData();
  const { schedule: cur } = await loadSchedule();
  const section = String(f.get("section") ?? "all");
  const next: Schedule = { ...cur };
  if (section !== "publish") {
    const other = String(f.get("jeu_autre") ?? "").trim();
    Object.assign(next, {
      enabled: f.get("enabled") === "on",
      every_min: pick(f.get("every_min"), EVERY_OPTIONS, cur.every_min),
      game: (other || String(f.get("jeu") ?? "")).slice(0, 80) || cur.game,
      top: pick(f.get("top"), TOP_OPTIONS, cur.top),
      max_clips: Math.min(10, Math.max(1, parseInt(String(f.get("max_clips") ?? cur.max_clips), 10) || cur.max_clips)),
      min_views: pick(f.get("min_views"), VIEWS_OPTIONS, cur.min_views),
      hours: pick(f.get("hours"), HOURS_OPTIONS, cur.hours),
    });
  }
  if (section !== "auto") {
    next.publish_every_min = pick(f.get("publish_every_min"), PUBLISH_OPTIONS, cur.publish_every_min);
    next.auto_min = pick(f.get("auto_min"), AUTO_OPTIONS, cur.auto_min);
  }
  delete next.at;
  await saveSchedule(next);
  return NextResponse.redirect(new URL("/?v=programmation&prog=ok", req.url), 303);
}
