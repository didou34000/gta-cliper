// Programmation des passages, réglée depuis le site et lue par GitHub toutes les 10 min
// (gta_clipper/schedule.py).
//  schedule/config-<ms>.json : chaque réglage enregistré (jamais écrasé, le plus récent gagne)
//  schedule/last-run.json    : heure du dernier passage programmé (écrit par le bot)
import { list, put } from "@vercel/blob";

export type Schedule = {
  enabled: boolean;
  every_min: number;          // un passage toutes les N minutes (10 min minimum)
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

export const EVERY_OPTIONS = [10, 15, 20, 30, 60, 120, 180, 360];
export const PUBLISH_OPTIONS = [10, 30, 60, 120, 180, 240, 360, 720];
export const TOP_OPTIONS = [3, 5, 8, 10, 15];
export const VIEWS_OPTIONS = [20, 50, 100, 200, 500, 1000, 5000];
export const AUTO_OPTIONS = [0, 6, 7, 8, 9];
export const HOURS_OPTIONS = [6, 12, 24, 48, 72, 100, 168, 200, 336, 720];

export async function loadSchedule(): Promise<{ schedule: Schedule; lastRun: string | null }> {
  if (!process.env.BLOB_READ_WRITE_TOKEN) return { schedule: DEFAULT_SCHEDULE, lastRun: null };
  try {
    const { blobs } = await list({ prefix: "schedule/", limit: 1000 });
    const cfgs = blobs.filter((b) => b.pathname.startsWith("schedule/config-"))
      .sort((a, b) => +new Date(a.uploadedAt) - +new Date(b.uploadedAt));
    const last = blobs.find((b) => b.pathname === "schedule/last-run.json");
    let schedule = DEFAULT_SCHEDULE;
    if (cfgs.length) {
      const r = await fetch(cfgs[cfgs.length - 1].url, { next: { revalidate: 86400 } });
      if (r.ok) schedule = { ...DEFAULT_SCHEDULE, ...(await r.json()) };
    }
    return { schedule, lastRun: last ? new Date(last.uploadedAt).toISOString() : null };
  } catch {
    return { schedule: DEFAULT_SCHEDULE, lastRun: null };
  }
}

export async function saveSchedule(s: Schedule) {
  await put(`schedule/config-${Date.now()}.json`, JSON.stringify({ ...s, at: new Date().toISOString() }), {
    access: "public", contentType: "application/json", addRandomSuffix: true,
  });
}
