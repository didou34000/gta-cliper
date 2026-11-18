// Publication automatique via Buffer (gratuit : 10 posts programmés max par réseau).
// Les clips « À poster » (validés) partent dans l'ordre de validation, espacés de
// publish_every_min (réglage du site). Buffer publie ensuite tout seul à l'heure dite.
//  - BUFFER_API_KEY (Vercel, obligatoire) : https://publish.buffer.com/settings/api
//  - BUFFER_TIKTOK_CHANNEL_ID / BUFFER_YOUTUBE_CHANNEL_ID / BUFFER_INSTAGRAM_CHANNEL_ID (facultatifs) :
//    comptes Buffer visés ; un réseau sans identifiant est ignoré
// Sans clé, rien ne part : les clips attendent dans « À poster » comme avant.
import { loadClips, saveDecision, type Clip, type Networks, type NetworkState } from "./data";
import { loadSchedule, nextAllowed, parisClock } from "./schedule";
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
    // Miniature avec le titre incrustée au tout début de la vidéo : on la désigne comme
    // couverture (TikTok et Instagram seulement ; YouTube choisit lui-même).
    assets: [{ video: { url: c.video_url, ...(c.cover && net !== "youtube" ? { metadata: { thumbnailOffset: 30 } } : {}) } }],
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
  const r = await sendOnce(net, c, due);
  // Si Buffer refuse la couverture choisie, on renvoie sans (le post compte plus que la miniature).
  if (r.state === "error" && c.cover && net !== "youtube") return sendOnce(net, { ...c, cover: false }, due);
  return r;
}

async function sendOnce(net: Net, c: Clip, due: Date): Promise<NetworkState> {
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

const DELETE = `mutation DeletePost($input: DeletePostInput!) {
  deletePost(input: $input) {
    ... on DeletePostSuccess { id }
    ... on VoidMutationError { message }
  }
}`;

/** Retire un post programmé de Buffer (avant sa sortie). */
async function unschedule(id: string): Promise<boolean> {
  try {
    const r = await fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.BUFFER_API_KEY}` },
      body: JSON.stringify({ query: DELETE, variables: { input: { id } } }),
      cache: "no-store",
    });
    const j = await r.json().catch(() => null);
    return !!j?.data?.deletePost?.id;
  } catch {
    return false;
  }
}

// Garde-fou : le compte est GTA 6. Un clip validé qui ne parle pas de GTA (titre, description,
// hashtags) n'est jamais envoyé : il reste dans « À poster » pour une décision à la main.
const GTA_RE = /\bgta\b|gta ?(6|vi)\b|grand theft auto/i;
// Programmation sur GTA VI : on ne publie que des clips GTA VI (pas le stock GTA V).
const GTA6_RE = /grand theft auto vi\b|gta\s*(6|vi)\b/i;
const matchesGame = (c: Clip, game?: string) => !game || !/\bvi$/i.test(game.trim()) || GTA6_RE.test([(c as unknown as { game?: string }).game ?? "", c.title, ...(c.hashtags ?? [])].join(" "));
export const isGtaClip = (c: Clip) => GTA_RE.test([c.title, c.description, ...(c.hashtags ?? [])].join(" "));

// Posts déjà programmés dans Buffer sur nos comptes, y compris ceux qui ne viennent pas du
// clipper (vidéos niches, carrousels…) : on s'écarte d'eux aussi.
const ORG = process.env.BUFFER_ORG_ID || "6ae8721deaf44e2b4ec5d7f2";
const POSTS_QUERY = `query Posts($input: PostsInput!) {
  posts(first: 100, input: $input) { edges { node { dueAt sentAt text } } }
}`;
// Textes des posts lus au dernier appel : sert à ne jamais envoyer deux fois le même clip
// (deux appels simultanés de la file, ou un état du site en retard sur Buffer).
let lastTexts: string[] = [];
const inBufferAlready = (c: Clip) => {
  const keys = [c.title, c.description].map((x) => (x ?? "").trim().toLowerCase().slice(0, 60)).filter((x) => x.length >= 20);
  return keys.some((k) => lastTexts.some((t) => t.includes(k)));
};
export async function bufferDues(): Promise<number[] | null> {
  try {
    const r = await fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.BUFFER_API_KEY}` },
      body: JSON.stringify({ query: POSTS_QUERY, variables: { input: {
        organizationId: ORG, filter: {
          channelIds: NETS.map((n) => CHANNELS[n]),
          // programmés ET déjà publiés récemment : l'écart compte depuis le dernier post sorti
          status: ["scheduled", "sending", "sent"],
          dueAt: { start: new Date(Date.now() - 24 * 3600_000).toISOString() },
        } } } }),
      cache: "no-store",
    });
    const j = await r.json().catch(() => null);
    if (!j?.data?.posts) { console.error("Buffer posts:", j?.errors?.[0]?.message ?? r.status); return null; }
    const edges = (j.data?.posts?.edges ?? []) as { node: { dueAt?: string; sentAt?: string; text?: string } }[];
    lastTexts = edges.map((e) => (e.node?.text ?? "").toLowerCase());
    return edges.map((e) => +new Date(e.node?.sentAt ?? e.node?.dueAt ?? 0)).filter((t: number) => t > 0);
  } catch {
    return null;
  }
}


/** Premier créneau autorisé (jours/heures de publication) à au moins `gap` de tout post prévu. */
function freeSlot(from: number, busy: number[], gap: number, days: number[], start: number, end: number): Date {
  let t = nextAllowed(new Date(from), days, start, end);
  for (let i = 0; i < 60; i++) {
    const clash = busy.filter((d) => Math.abs(d - +t) < gap);
    if (!clash.length) return t;
    t = nextAllowed(new Date(Math.max(...clash) + gap), days, start, end);
  }
  return t;
}

/** Bouton « Publier » : programme CE clip sur Buffer au premier créneau libre (1 h 30 d'écart),
 *  même si la publication auto est coupée. */
export async function publishOne(id: string): Promise<{ ok: boolean; message: string; due?: string }> {
  if (!bufferReady()) return { ok: false, message: "BUFFER_API_KEY manquante" };
  const [clips, { schedule }, external] = await Promise.all([loadClips(), loadSchedule(), bufferDues()]);
  const c = clips.find((x) => x.id === id);
  if (!c || !c.video_url) return { ok: false, message: "Clip ou vidéo introuvable" };
  if (!external) return { ok: false, message: "Impossible de lire les posts déjà prévus dans Buffer : rien n'a été programmé, réessaie dans une minute" };
  const busy = [...new Set([...external, ...clips.flatMap(dues)])];
  // Même écart que la publication auto (réglage « un post toutes les N min » ; 30 min = 2 posts/h max).
  const gap = Math.max(10, schedule.publish_every_min || 90) * 60_000;
  const due = freeSlot(Date.now() + FIRST_DELAY_MS, busy, gap, schedule.pub_days, schedule.pub_from, schedule.pub_to);
  const nets = NETS.filter((n) => !schedule.nets?.length || schedule.nets.includes(n));
  const networks: Networks = { ...(c.networks ?? {}) };
  for (const net of nets) {
    if (networks[net]?.state === "scheduled" || networks[net]?.state === "posted") continue;
    networks[net] = await send(net, c, due);
  }
  const anyOk = Object.values(networks).some((n) => n?.state === "scheduled" || n?.state === "posted");
  await saveDecision(c.id, {
    status: anyOk ? "posted" : "approved",
    title: c.title, description: c.description, hashtags: c.hashtags, post_url: c.post_url, networks,
  });
  return anyOk ? { ok: true, message: `Programmé le ${due.toISOString()}`, due: due.toISOString() }
    : { ok: false, message: Object.values(networks).find((n) => n?.error)?.error ?? "Échec Buffer" };
}

// Règle du 16/11 : un clip qui ne dépasse pas 6/10 ne part jamais tout seul (il reste dans
// « À poster » ; le bouton « Publier » reste possible, c'est alors un choix fait à la main).
export const MIN_SCORE = 7;
// Seuil réel : auto_min de la Programmation (7 par défaut), jamais sous 1.
const minScore = (auto?: number) => Math.max(1, auto || MIN_SCORE);

const dues = (c: Clip) =>
  Object.values(c.networks ?? {}).filter((n) => n?.state === "scheduled" && n.due).map((n) => +new Date(n!.due!));

// Règle du 16/11 (soir) : le bot garde UN clip programmé d'avance (le prochain post). Si un
// passage sort un clip mieux noté que celui-là et qu'il n'est pas encore parti, le nouveau
// prend sa place au même horaire ; l'ancien repasse dans « À poster » (il repartira plus tard
// s'il reste le meilleur). Les clips programmés à la main (bouton « Publier ») ne sont jamais
// remplacés.
const AUTO_AHEAD = 1;
const SWAP_MIN_LEAD_MS = 10 * 60_000; // on ne touche plus à un post qui part dans moins de 10 min

/** Envoie à Buffer les clips validés : le meilleur d'abord, un seul d'avance, remplacé si mieux. */
export async function publishQueue(): Promise<{ ok: boolean; sent: number; message: string }> {
  if (!bufferReady()) return { ok: false, sent: 0, message: "BUFFER_API_KEY manquante : publication auto désactivée" };
  if (!(await publishEnabled())) return { ok: false, sent: 0, message: "Publication auto coupée sur le site" };
  const [clips, { schedule }, external] = await Promise.all([loadClips(), loadSchedule(), bufferDues()]);
  if (!external) return { ok: false, sent: 0, message: "Lecture des posts Buffer impossible : rien envoyé (réessai au prochain tour)" };
  const now = Date.now();
  const every = Math.max(10, schedule.publish_every_min || 120) * 60_000;
  const nets = NETS.filter((n) => !schedule.nets?.length || schedule.nets.includes(n));

  const todo = clips
    .filter((c) => !inBufferAlready(c))
    .filter((c) => c.status === "approved" && c.video_url && isGtaClip(c) && matchesGame(c, schedule.game) && (c.potential ?? 0) >= minScore(schedule.auto_min))
    .filter((c) => !Object.values(c.networks ?? {}).some((n) => n?.state === "error" && now - +new Date(n.at) < RETRY_AFTER_MS))
    // Le meilleur clip d'abord (note de clic), à égalité le plus récent (plus frais).
    .sort((a, b) => (b.potential ?? 0) - (a.potential ?? 0) || (b.decided_at ?? "").localeCompare(a.decided_at ?? ""));

  const schedTo = async (c: Clip, due: Date) => {
    const networks: Networks = { ...(c.networks ?? {}) };
    for (const net of nets) {
      if (networks[net]?.state === "scheduled" || networks[net]?.state === "posted") continue;
      const r = await send(net, c, due);
      networks[net] = r.state === "scheduled" ? { ...r, auto: true } : r;
    }
    const anyOk = Object.values(networks).some((n) => n?.state === "scheduled" || n?.state === "posted");
    await saveDecision(c.id, {
      status: anyOk ? "posted" : "approved",
      title: c.title, description: c.description, hashtags: c.hashtags, post_url: c.post_url, networks,
    });
    return anyOk;
  };

  // Clips du bot programmés et pas encore partis.
  // Buffer fait foi : un horaire noté sur le site mais absent de Buffer (post supprimé ou
  // envoyé plus tôt à la main) ne bloque plus la file.
  const live = (d: number) => d > now && external.some((e) => Math.abs(e - d) < 120_000);
  const ahead = clips
    .filter((c) => c.status === "posted" && dues(c).some(live))
    .filter((c) => Object.values(c.networks ?? {}).every((n) => !n || n.state !== "scheduled" || n.auto));
  let sent = 0, swapped = 0;

  // 1) Remplacement : un clip validé mieux noté prend la place d'un clip auto pas encore parti.
  for (const old of [...ahead].sort((a, b) => (a.potential ?? 0) - (b.potential ?? 0))) {
    const best = todo[0];
    if (!best || (best.potential ?? 0) <= (old.potential ?? 0)) break;
    const due = Math.min(...dues(old).filter((d) => d > now));
    if (due - now < SWAP_MIN_LEAD_MS) continue;
    const ids = Object.values(old.networks ?? {}).filter((n) => n?.state === "scheduled" && n.id).map((n) => n!.id!);
    const ok = (await Promise.all(ids.map(unschedule))).every(Boolean);
    const left: Networks = {};
    for (const [k, n] of Object.entries(old.networks ?? {}) as [keyof Networks, NetworkState][]) {
      if (n.state !== "scheduled" || !ok) left[k] = n; // si Buffer a refusé, on garde la trace
    }
    if (!ok) { console.error("Remplacement annulé : Buffer n'a pas retiré", old.id); continue; }
    await saveDecision(old.id, {
      status: "approved", title: old.title, description: old.description, hashtags: old.hashtags,
      post_url: old.post_url, networks: left,
    });
    todo.shift();
    if (await schedTo(best, new Date(due))) { sent++; swapped++; }
    ahead.splice(ahead.indexOf(old), 1, best);
  }

  // 2) Toujours un clip d'avance : s'il n'y en a pas, on programme le meilleur au prochain créneau.
  const allDues = [...new Set(external)];
  const perDay = new Map<string, number>(); // posts déjà prévus par jour (heure de Paris)
  for (const c of clips) {
    const d = dues(c);
    if (d.length) { const k = parisClock(new Date(Math.min(...d))).date; perDay.set(k, (perDay.get(k) ?? 0) + 1); }
  }
  const slot = (from: number): Date => {
    let t = nextAllowed(new Date(from), schedule.pub_days, schedule.pub_from, schedule.pub_to);
    for (let i = 0; i < 14 && schedule.pub_max_day > 0 && (perDay.get(parisClock(t).date) ?? 0) >= schedule.pub_max_day; i++) {
      const c = parisClock(t);
      t = nextAllowed(new Date(+t + (24 - c.hour) * 3600_000 + 60_000), schedule.pub_days, schedule.pub_from, schedule.pub_to);
    }
    return t;
  };
  let inFlight = ahead.length;
  const inBuffer = clips.filter((c) => dues(c).some(live)).length;
  for (const c of todo) {
    if (inFlight >= AUTO_AHEAD || inBuffer + sent >= MAX_SCHEDULED) break;
    // Premier créneau libre à au moins `every` de TOUT post (passé ou à venir, vidéos niches
    // comprises) : un post prévu ce soir ne bloque plus les clips de l'après-midi.
    const due = freeSlot(+slot(now + FIRST_DELAY_MS), allDues, every, schedule.pub_days, schedule.pub_from, schedule.pub_to);
    if (+due - now > 7 * 24 * 3600_000) break; // rien d'autorisé dans les 7 jours : on attend
    if (await schedTo(c, due)) {
      sent++; inFlight++; allDues.push(+due);
      const k = parisClock(due).date; perDay.set(k, (perDay.get(k) ?? 0) + 1);
    }
  }
  const msg = sent ? `${sent} clip(s) programmé(s) sur Buffer${swapped ? ` (dont ${swapped} en remplacement d'un clip moins bien noté)` : ""}` : "Rien à envoyer";
  return { ok: true, sent, message: msg };
}
