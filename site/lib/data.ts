// Lecture/écriture des données dans Cloudflare R2 (lib/r2.ts).
//  clips/<id>/meta-*.json, clip-*.mp4, thumb-*.jpg : écrits une fois par le bot
//  decisions/<id>/<ms>-*.json : chaque action faite sur le site (jamais écrasé)
//  status/live.json         : statut du bot (un seul fichier réécrit, lu sans listage)
import { BudgetError, deleteObjects, getJsonKey, listAll, publicUrl, putObject, r2Configured, type Obj } from "./r2";
import { DEMO_BEAT, DEMO_CLIPS, demoOn } from "./demo";

export type Status = "pending" | "approved" | "rejected" | "posted";

export type Clip = {
  id: string;
  streamer: string;
  title: string;
  alt_titles: string[];
  description: string;
  hashtags: string[];
  confidence: string;
  kind?: "twitch_clip" | "vod_chat_spike" | string;
  views?: number;
  chat_zscore?: number;
  duration: number;
  transcript: string;
  source_url?: string;
  created_at: string;
  video_url?: string;
  thumb_url?: string;
  status: Status;
  post_url?: string;
  decided_at?: string;
  run?: RunInfo;              // passage qui a produit le clip
  rank?: number;              // place dans le classement de ce passage
  potential?: number | null;  // note de potentiel /10 (présélection Claude Haiku)
  potential_reason?: string;
  networks?: Networks;        // publication par réseau (lib/buffer.ts)
};

export type NetworkState = { state: "scheduled" | "posted" | "draft" | "error"; due?: string; id?: string; url?: string; error?: string; at: string };
export type Networks = Partial<Record<"tiktok" | "youtube" | "instagram", NetworkState>>;

export type RunInfo = {
  id: string;
  at: string;
  trigger: string;            // « manuel » ou « programmé »
  game: string;
  top: number;
  max_clips?: number | null;
  min_views?: number;
  hours?: number;
  source?: string;            // lien de la vidéo, pour un passage « lien YouTube »
};

export type Heartbeat = {
  ts: string;
  status: "running" | "idle" | "error" | string;
  step?: string;
  node?: string;
  message?: string;
  stats?: Record<string, number>;
  logs?: string[];
  streamer?: string;
  streamers?: Record<string, StreamerState>;
  events?: BotEvent[];
};

export type StreamerState = {
  etat: string; clips_vus: number; retenus: number; deja_faits: number;
  produits: number; erreurs: number; pics_chat: number; action: string; ts: string;
};

export type BotEvent = { ts: string; streamer: string; node: string; text: string; level: string };

export type Decision = {
  status: Status;
  title?: string;
  description?: string;
  hashtags?: string[];
  post_url?: string;
  networks?: Networks;
  at: string;
};

const hasStore = r2Configured;

// Fichiers à nom unique (jamais réécrits) : lus par l'URL publique, gardés en cache 24 h par
// Vercel (donc presque aucune lecture R2). Si l'accès public répond mal, lecture signée.
async function getJson<T>(url: string, immutable = true): Promise<T | null> {
  try {
    const r = await fetch(url, immutable ? { next: { revalidate: 86400 } } : { cache: "no-store" });
    if (r.ok) return (await r.json()) as T;
  } catch {}
  const base = publicUrl() + "/";
  return url.startsWith(base) ? getJsonKey<T>(url.slice(base.length)) : null;
}

export async function loadHeartbeat(): Promise<{ last: Heartbeat | null; history: Heartbeat[] }> {
  if (demoOn()) return { last: DEMO_BEAT, history: [DEMO_BEAT] };
  if (!hasStore()) return { last: null, history: [] };
  const last = await getJsonKey<Heartbeat>("status/live.json");
  return { last, history: last ? [last] : [] };
}

export async function loadClips(): Promise<Clip[]> {
  return (await loadClipsAndSize()).clips;
}

/** Clips + place occupée par les vidéos/miniatures dans R2 (en octets), avec les mêmes appels list. */
export async function loadClipsAndSize(): Promise<{ clips: Clip[]; bytes: number }> {
  if (demoOn()) return { clips: DEMO_CLIPS, bytes: 210e6 };
  if (!hasStore()) return { clips: [], bytes: 0 };
  let clipBlobs: Obj[], decisionBlobs: Obj[];
  try {
    [clipBlobs, decisionBlobs] = await Promise.all([listAll("clips/"), listAll("decisions/")]);
  } catch (e) {
    if (e instanceof BudgetError) return { clips: [], bytes: 0 }; // plafond atteint : le bandeau l'explique
    throw e;
  }
  const bytes = clipBlobs.reduce((n, b) => n + (b.size ?? 0), 0);

  const byId = new Map<string, { meta?: string; video?: string; thumb?: string }>();
  for (const b of clipBlobs) {
    const [, id, file] = b.pathname.split("/");
    if (!id || !file) continue;
    const e = byId.get(id) ?? {};
    if (file.startsWith("meta")) e.meta = b.url;
    else if (file.startsWith("clip")) e.video = b.url;
    else if (file.startsWith("thumb")) e.thumb = b.url;
    byId.set(id, e);
  }

  const latest = new Map<string, string>();
  for (const b of decisionBlobs) {
    const [, id] = b.pathname.split("/");
    const prev = latest.get(id);
    if (!prev || b.pathname > prev) latest.set(id, b.pathname);
  }
  const decisionUrl = new Map(decisionBlobs.map((b) => [b.pathname, b.url]));

  const clips = await Promise.all(
    [...byId.entries()].filter(([, e]) => e.meta).map(async ([id, e]) => {
      const meta = await getJson<Partial<Clip>>(e.meta!);
      if (!meta) return null;
      const dPath = latest.get(id);
      const d = dPath ? await getJson<Decision>(decisionUrl.get(dPath)!) : null;
      const defaults = { streamer: "?", title: "", duration: 0, created_at: "", alt_titles: [] as string[], hashtags: [] as string[], description: "", confidence: "medium", transcript: "" };
      const clip: Clip = {
        ...defaults, ...(meta as Partial<Clip>), id, video_url: e.video, thumb_url: e.thumb, status: "pending",
      };
      if (d) {
        clip.status = d.status;
        clip.title = d.title ?? clip.title;
        clip.description = d.description ?? clip.description;
        clip.hashtags = d.hashtags ?? clip.hashtags;
        clip.post_url = d.post_url;
        clip.decided_at = d.at;
        clip.networks = d.networks;
      }
      return clip;
    })
  );
  return { clips: (clips.filter(Boolean) as Clip[]).sort((a, b) => b.created_at.localeCompare(a.created_at)), bytes };
}

/** Supprime définitivement un clip (vidéo, miniature, méta, décisions).
 *  Un repère seen/<id>.json est gardé pour que le bot ne le refasse jamais. */
export async function deleteClip(id: string) {
  if (!/^[\w.-]+$/.test(id)) throw new Error("id invalide");
  await putObject(`seen/${id}.json`, "{}");
  // Pas de listage : on reprend la liste déjà en cache (clips/ et decisions/ entiers).
  const [c, d] = await Promise.all([listAll("clips/"), listAll("decisions/")]);
  const urls = [...c, ...d].filter((b) => b.pathname.startsWith(`clips/${id}/`) || b.pathname.startsWith(`decisions/${id}/`)).map((b) => b.url);
  if (urls.length) await deleteObjects(urls);
}

export async function saveDecision(id: string, d: Omit<Decision, "at">) {
  if (!/^[\w.-]+$/.test(id)) throw new Error("id invalide");
  const at = new Date().toISOString();
  await putObject(`decisions/${id}/${Date.now()}.json`, JSON.stringify({ ...d, at }), { suffix: true });
}
