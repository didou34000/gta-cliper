// Programmation des passages, réglée depuis le site et lue par GitHub toutes les 20 min
// (gta_clipper/schedule.py).
//  schedule/current.json     : le réglage en cours (nom fixe, écrasé à chaque enregistrement)
//  schedule/config-<ms>.json : ancien format, lu seulement si current.json n'existe pas encore
//  schedule/last-run.json    : heure du dernier passage programmé (écrit par le bot)
// Lu en cache (1 h, vidé à chaque enregistrement) pour économiser le quota Blob.
import { list } from "@vercel/blob";
import { revalidateTag, unstable_cache } from "next/cache";
import { readFixed, writeFixed } from "./blobfile";

export type Schedule = {
  enabled: boolean;
  every_min: number;          // un passage toutes les N minutes (20 min minimum)
  game: string;               // nom exact Twitch, ou « tous »
  top: number;                // N plus gros streamers FR du jeu
  max_clips: number;          // clips max par passage
  min_views: number;          // vues minimum d'un clip Twitch
  hours: number;              // fenêtre : clips des N dernières heures
  publish_every_min: number;  // rythme de publication voulu (utilisé par la file « À poster »)
  auto_min: number;           // validation auto si potentiel ≥ N/10 (0 = toujours à la main)
  at?: string;
};

export const DEFAULT_SCHEDULE: Schedule = {
  enabled: false, every_min: 30, game: "Grand Theft Auto VI", top: 8, max_clips: 3, min_views: 200, hours: 48, publish_every_min: 120, auto_min: 7,
};

export const EVERY_OPTIONS = [20, 30, 60, 120, 180, 360];
export const PUBLISH_OPTIONS = [10, 30, 60, 120, 180, 240, 360, 720];
export const TOP_OPTIONS = [3, 5, 8, 10, 15];
export const VIEWS_OPTIONS = [20, 50, 100, 200, 500, 1000, 5000];
export const AUTO_OPTIONS = [0, 6, 7, 8, 9];
export const HOURS_OPTIONS = [6, 12, 24, 48, 72, 100, 168, 200, 336, 720];

async function readConfig(): Promise<Schedule> {
  const cur = await readFixed<Partial<Schedule>>("schedule/current.json", true);
  if (cur) return { ...DEFAULT_SCHEDULE, ...cur };
  if (cur === null) return DEFAULT_SCHEDULE;
  // Ancien format : une liste, une seule fois (le bot recopie ensuite sous le nom fixe).
  const { blobs } = await list({ prefix: "schedule/config-", limit: 1000 });
  const last = blobs.sort((a, b) => +new Date(a.uploadedAt) - +new Date(b.uploadedAt)).pop();
  if (!last) return DEFAULT_SCHEDULE;
  const r = await fetch(last.url, { cache: "no-store" });
  const cfg = r.ok ? { ...DEFAULT_SCHEDULE, ...(await r.json()) } : DEFAULT_SCHEDULE;
  await writeFixed("schedule/current.json", cfg).catch(() => {});
  return cfg;
}

const cachedConfig = unstable_cache(readConfig, ["schedule-config"], { revalidate: 3600, tags: ["schedule"] });

export async function loadSchedule(): Promise<{ schedule: Schedule; lastRun: string | null }> {
  if (!process.env.BLOB_READ_WRITE_TOKEN) return { schedule: DEFAULT_SCHEDULE, lastRun: null };
  try {
    const [schedule, last] = await Promise.all([
      cachedConfig(),
      readFixed<{ at?: string }>("schedule/last-run.json"),
    ]);
    return { schedule, lastRun: last?.at ? new Date(last.at).toISOString() : null };
  } catch {
    return { schedule: DEFAULT_SCHEDULE, lastRun: null };
  }
}

export async function saveSchedule(s: Schedule) {
  await writeFixed("schedule/current.json", { ...s, at: new Date().toISOString() });
  revalidateTag("schedule", { expire: 0 });
}
