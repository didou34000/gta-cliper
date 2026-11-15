import { NextResponse } from "next/server";
import { AUTO_OPTIONS, EVERY_OPTIONS, HOURS_OPTIONS, HOUR_OPTIONS, NET_OPTIONS, PUBLISH_OPTIONS, PUB_MAX_OPTIONS, TOP_OPTIONS, VIEWS_OPTIONS, loadSchedule, saveSchedule, type Schedule } from "@/lib/schedule";

const pick = (v: FormDataEntryValue | null, allowed: number[], dflt: number) => {
  const n = parseInt(String(v ?? ""), 10);
  return allowed.includes(n) ? n : dflt;
};

const days = (f: FormData, name: string) => {
  const d = [...new Set(f.getAll(name).map((v) => parseInt(String(v), 10)).filter((n) => n >= 0 && n <= 6))].sort();
  return d.length ? d : [0, 1, 2, 3, 4, 5, 6];
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
      days: days(f, "days"),
      run_from: pick(f.get("run_from"), HOUR_OPTIONS, cur.run_from),
      run_to: pick(f.get("run_to"), HOUR_OPTIONS, cur.run_to),
      peak_from: pick(f.get("peak_from"), HOUR_OPTIONS, cur.peak_from),
      peak_to: pick(f.get("peak_to"), HOUR_OPTIONS, cur.peak_to),
      peak_every_min: pick(f.get("peak_every_min"), [0, ...EVERY_OPTIONS], cur.peak_every_min),
    });
  }
  if (section !== "auto") {
    next.publish_every_min = pick(f.get("publish_every_min"), PUBLISH_OPTIONS, cur.publish_every_min);
    next.auto_min = pick(f.get("auto_min"), AUTO_OPTIONS, cur.auto_min);
    next.pub_days = days(f, "pub_days");
    next.pub_from = pick(f.get("pub_from"), HOUR_OPTIONS, cur.pub_from);
    next.pub_to = pick(f.get("pub_to"), HOUR_OPTIONS, cur.pub_to);
    next.pub_max_day = pick(f.get("pub_max_day"), PUB_MAX_OPTIONS, cur.pub_max_day);
    const nets = f.getAll("nets").map(String).filter((n) => NET_OPTIONS.some((o) => o.id === n));
    next.nets = nets.length ? nets : cur.nets;
  }
  delete next.at;
  await saveSchedule(next);
  return NextResponse.redirect(new URL("/?v=programmation&prog=ok", req.url), 303);
}
