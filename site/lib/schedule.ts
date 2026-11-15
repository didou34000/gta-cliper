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
  // Horaires (heure de Paris). Une plage « de 22 h à 3 h » passe minuit. 0 → 24 = toute la journée.
  days: number[];             // jours où le bot tourne (0 = dimanche … 6 = samedi)
  run_from: number;           // passages seulement entre run_from h …
  run_to: number;             // … et run_to h
  peak_from: number;          // heures de pointe : passages plus fréquents
  peak_to: number;
  peak_every_min: number;     // fréquence pendant les heures de pointe (0 = pas d'heures de pointe)
  pub_days: number[];         // jours où l'on publie
  pub_from: number;           // publications seulement entre pub_from h …
  pub_to: number;             // … et pub_to h
  pub_max_day: number;        // posts max par jour et par réseau (0 = pas de limite)
  nets: string[];             // réseaux visés : tiktok, youtube
  at?: string;
};

export const DEFAULT_SCHEDULE: Schedule = {
  enabled: false, every_min: 30, game: "Grand Theft Auto VI", top: 8, max_clips: 3, min_views: 200, hours: 48, publish_every_min: 120, auto_min: 7,
  days: [0, 1, 2, 3, 4, 5, 6], run_from: 0, run_to: 24, peak_from: 18, peak_to: 24, peak_every_min: 0,
  pub_days: [0, 1, 2, 3, 4, 5, 6], pub_from: 8, pub_to: 24, pub_max_day: 0, nets: ["tiktok", "youtube"],
};

export const EVERY_OPTIONS = [20, 30, 45, 60, 90, 120, 180, 240, 360];
export const PUBLISH_OPTIONS = [10, 20, 30, 45, 60, 90, 120, 180, 240, 360, 720];
export const TOP_OPTIONS = [3, 5, 8, 10, 15, 20];
export const HOUR_OPTIONS = Array.from({ length: 25 }, (_, i) => i); // 0 … 24
export const PUB_MAX_OPTIONS = [0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20];
export const DAY_NAMES = ["dim", "lun", "mar", "mer", "jeu", "ven", "sam"];
export const DAY_ORDER = [1, 2, 3, 4, 5, 6, 0];
export const NET_OPTIONS = [{ id: "tiktok", label: "TikTok" }, { id: "youtube", label: "YouTube Shorts" }];

const TZ = "Europe/Paris";
export const GTA6_RELEASE = new Date("2026-11-18T10:30:00Z");
/** Jour (0 = dim) et heure décimale à Paris pour une date. */
export function parisClock(d: Date): { day: number; hour: number; date: string } {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ, weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(d).map((x) => [x.type, x.value]));
  const day = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(p.weekday);
  return { day, hour: +p.hour + +p.minute / 60, date: `${p.year}-${p.month}-${p.day}` };
}
/** L'heure h est-elle dans la plage [from, to) ? Gère les plages qui passent minuit. */
export function inWindow(h: number, from: number, to: number): boolean {
  if (from === to || (from === 0 && to === 24)) return true;
  return from < to ? h >= from && h < to : h >= from || h < to;
}
/** Jour « de rattachement » d'une plage de nuit : à 1 h du matin dans une plage 22 h → 3 h, c'est encore la veille. */
function windowDay(c: { day: number; hour: number }, from: number, to: number) {
  return from > to && c.hour < to ? (c.day + 6) % 7 : c.day;
}
export function allowedAt(d: Date, days: number[], from: number, to: number): boolean {
  const c = parisClock(d);
  return inWindow(c.hour, from, to) && (days?.length ? days : [0, 1, 2, 3, 4, 5, 6]).includes(windowDay(c, from, to));
}
/** Premier instant ≥ d autorisé (pas de 5 min, au plus 8 jours plus loin). */
export function nextAllowed(d: Date, days: number[], from: number, to: number): Date {
  let t = new Date(Math.ceil(+d / 60000) * 60000);
  for (let i = 0; i < 8 * 24 * 12 && !allowedAt(t, days, from, to); i++) t = new Date(+t + 5 * 60000);
  return t;
}
/** Fréquence en vigueur à cet instant (heures de pointe ou normale), en minutes. */
export function everyAt(s: Schedule, d: Date): number {
  return s.peak_every_min && inWindow(parisClock(d).hour, s.peak_from, s.peak_to) ? s.peak_every_min : s.every_min;
}
/** Prochain passage prévu (null si mode auto éteint). */
export function nextRunAt(s: Schedule, lastRun: string | null): Date | null {
  if (!s.enabled) return null;
  let now = new Date();
  // Même barrière que le bot (gta_clipper/schedule.py) : rien avant la sortie de GTA VI.
  if (/theft auto vi|gta ?(6|vi)\b/i.test(s.game) && +now < +GTA6_RELEASE) now = GTA6_RELEASE;
  const base = lastRun ? new Date(Math.max(+now, +new Date(lastRun) + everyAt(s, now) * 60000)) : now;
  return nextAllowed(base, s.days, s.run_from, s.run_to);
}
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
