// Publication automatique via Buffer (gratuit : 10 posts programmés max par réseau).
// Les clips « À poster » (validés) partent dans l'ordre de validation, espacés de
// publish_every_min (réglage du site). Buffer publie ensuite tout seul à l'heure dite.
//  - BUFFER_API_KEY (Vercel, obligatoire) : https://publish.buffer.com/settings/api
//  - BUFFER_TIKTOK_CHANNEL_ID / BUFFER_YOUTUBE_CHANNEL_ID / BUFFER_INSTAGRAM_CHANNEL_ID (facultatifs) :
//    comptes Buffer visés ; un réseau sans identifiant est ignoré
// Sans clé, rien ne part : les clips attendent dans « À poster » comme avant.
import { loadClips, saveDecision, type Clip, type Networks, type NetworkState } from "./data";
import { loadSchedule } from "./schedule";
import { getJsonKey, putObject, r2Configured } from "./r2";

const API = "https://api.buffer.com";
const MAX_SCHEDULED = 10;         // limite du plan gratuit Buffer, par réseau
const FIRST_DELAY_MS = 3 * 60_000; // premier post au plus tôt dans 3 min
const RETRY_AFTER_MS = 60 * 60_000; // après une erreur, on réessaie au bout d'1 h

export type Net = "tiktok" | "youtube" | "instagram";
export const CHANNELS: Record<Net, string> = {
  tiktok: process.env.BUFFER_TIKTOK_CHANNEL_ID || "6af4a00862b70b94b0f80baa", // @gta6francenews
  youtube: process.env.BUFFER_YOUTUBE_CHANNEL_ID || "6af49c4762b70b94b0f7bdd3", // GTA 6 FRANCE
  instagram: process.env.BUFFER_INSTAGRAM_CHANNEL_ID || "",
};
const NETS = (Object.keys(CHANNELS) as Net[]).filter((n) => CHANNELS[n]);

export const bufferReady = () => !!process.env.BUFFER_API_KEY;

// Interrupteur « Publication auto » réglé sur le site : publish/state.json (nom fixe, lu directement).
// Éteint par défaut : même avec la clé Buffer, rien ne part tant qu'il n'est pas allumé.
export async function publishEnabled(): Promise<boolean> {
  if (!r2Configured()) return false;
  return !!(await getJsonKey<{ enabled?: boolean }>("publish/state.json"))?.enabled;
}

export async function setPublishEnabled(enabled: boolean) {
  await putObject("publish/state.json", JSON.stringify({ enabled, at: new Date().toISOString() }));
}

const MUTATION = `mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id dueAt } }
    ... on MutationError { message }
  }
}`;

function caption(c: Clip) {
  return [c.title, c.description, c.hashtags.join(" ")].filter(Boolean).join("\n\n").slice(0, 2200);
}

function inputFor(net: Net, c: Clip, due: Date) {
  const base = {
    channelId: CHANNELS[net],
    schedulingType: "automatic",
    mode: "customScheduled",
    dueAt: due.toISOString(),
    assets: [{ video: { url: c.video_url } }],
  };
  if (net === "tiktok") return { ...base, text: caption(c), metadata: { tiktok: { title: c.title.slice(0, 90) } } };
  if (net === "instagram") return { ...base, text: caption(c), metadata: { instagram: { type: "reel", shouldShareToFeed: true } } };
  const ytTitle = c.title.includes("#Shorts") ? c.title : `${c.title} #Shorts`;
  return {
    ...base,
    text: [c.description, c.hashtags.join(" ")].filter(Boolean).join("\n\n").slice(0, 4900),
    metadata: { youtube: { title: ytTitle.slice(0, 100), categoryId: "20", privacy: "public", madeForKids: false } },
  };
}

async function send(net: Net, c: Clip, due: Date): Promise<NetworkState> {
  const at = new Date().toISOString();
  try {
    const r = await fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.BUFFER_API_KEY}` },
      body: JSON.stringify({ query: MUTATION, variables: { input: inputFor(net, c, due) } }),
      cache: "no-store",
    });
    const j = await r.json().catch(() => null);
    const res = j?.data?.createPost;
    if (res?.post?.id) return { state: "scheduled", id: res.post.id, due: res.post.dueAt ?? due.toISOString(), at };
    const msg = res?.message || j?.errors?.[0]?.message || `HTTP ${r.status}`;
    return { state: "error", error: String(msg).slice(0, 300), at };
  } catch (e) {
    return { state: "error", error: String(e).slice(0, 300), at };
  }
}

const dues = (c: Clip) =>
  Object.values(c.networks ?? {}).filter((n) => n?.state === "scheduled" && n.due).map((n) => +new Date(n!.due!));

/** Envoie à Buffer les clips validés, tant qu'il reste de la place dans la file Buffer. */
export async function publishQueue(): Promise<{ ok: boolean; sent: number; message: string }> {
  if (!bufferReady()) return { ok: false, sent: 0, message: "BUFFER_API_KEY manquante : publication auto désactivée" };
  if (!(await publishEnabled())) return { ok: false, sent: 0, message: "Publication auto coupée sur le site" };
  const [clips, { schedule }] = await Promise.all([loadClips(), loadSchedule()]);
  const now = Date.now();
  const every = Math.max(10, schedule.publish_every_min || 120) * 60_000;

  const allDues = clips.flatMap(dues);
  let inFlight = clips.filter((c) => dues(c).some((d) => d > now)).length;
  let last = allDues.length ? Math.max(...allDues) : 0;

  const todo = clips
    .filter((c) => c.status === "approved" && c.video_url)
    .filter((c) => !Object.values(c.networks ?? {}).some((n) => n?.state === "error" && now - +new Date(n.at) < RETRY_AFTER_MS))
    .sort((a, b) => (a.decided_at ?? "").localeCompare(b.decided_at ?? ""));

  let sent = 0;
  for (const c of todo) {
    if (inFlight >= MAX_SCHEDULED) break;
    const due = new Date(Math.max(now + FIRST_DELAY_MS, last + every));
    const networks: Networks = { ...(c.networks ?? {}) };
    for (const net of NETS) {
      if (networks[net]?.state === "scheduled" || networks[net]?.state === "posted") continue;
      networks[net] = await send(net, c, due);
    }
    const anyOk = Object.values(networks).some((n) => n?.state === "scheduled" || n?.state === "posted");
    await saveDecision(c.id, {
      status: anyOk ? "posted" : "approved",
      title: c.title, description: c.description, hashtags: c.hashtags, post_url: c.post_url, networks,
    });
    if (anyOk) { sent++; inFlight++; last = +due; }
  }
  return { ok: true, sent, message: sent ? `${sent} clip(s) programmé(s) sur Buffer` : "Rien à envoyer" };
}
