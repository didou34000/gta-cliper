// Programmation des passages, réglée depuis le site et lue par GitHub toutes les 20 min
// (gta_clipper/schedule.py).
//  schedule/config.json   : le réglage en cours (nom fixe, lu directement : 1 lecture, pas de listage)
//  schedule/last-run.json : heure du dernier passage programmé (écrit par GitHub)
import { getJsonKey, putObject, r2Configured } from "./r2";

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

export async function loadSchedule(): Promise<{ schedule: Schedule; lastRun: string | null }> {
  if (!r2Configured()) return { schedule: DEFAULT_SCHEDULE, lastRun: null };
  const [cfg, last] = await Promise.all([
    getJsonKey<Partial<Schedule>>("schedule/config.json"),
    getJsonKey<{ at?: string }>("schedule/last-run.json"),
  ]);
  return { schedule: { ...DEFAULT_SCHEDULE, ...(cfg ?? {}) }, lastRun: last?.at ?? null };
}

export async function saveSchedule(s: Schedule) {
  await putObject("schedule/config.json", JSON.stringify({ ...s, at: new Date().toISOString() }));
}
