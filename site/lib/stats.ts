// Statistiques des posts publiés, lues dans Buffer (gratuit, même clé que la publication).
// Buffer remonte pour chaque post envoyé : vues, likes, commentaires, partages, taux
// d'engagement… Les chiffres sont rafraîchis par Buffer environ une fois par jour.
// Doc : https://developers.buffer.com/guides/post-metrics.html
// Sans BUFFER_API_KEY, rien n'est lu et le site affiche « pas connecté ».
import { CHANNELS, type Net } from "./buffer";

const API = "https://api.buffer.com";
const ORG = process.env.BUFFER_ORG_ID || "6ae8721deaf44e2b4ec5d7f2"; // « My organization »
// Les posts envoyés avant cette date sont les anciens posts du compte, pas ceux du bot.
export const BOT_START = "2026-11-11T00:00:00Z";

export type PostStats = {
  id: string;
  net: Net;
  text: string;
  at: string;                 // date d'envoi
  url?: string;               // lien du post sur TikTok / YouTube (si Buffer le donne)
  thumb?: string;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  engagement: number | null;  // en %
  avgWatch: number | null;    // secondes
  updatedAt?: string;
};

export type StatsResult =
  | { connected: false }
  | { connected: true; ok: false; error: string }
  | { connected: true; ok: true; posts: PostStats[]; scheduled: number; fetchedAt: string };

const NET_BY_CHANNEL = new Map(Object.entries(CHANNELS).filter(([, id]) => id).map(([n, id]) => [id, n as Net]));

async function gql(query: string) {
  const r = await fetch(API, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.BUFFER_API_KEY}` },
    body: JSON.stringify({ query }),
    // Buffer ne met ses chiffres à jour qu'une fois par jour : 30 min de cache suffisent
    // et ménagent la limite de l'API (quelques centaines d'appels par jour).
    next: { revalidate: 1800, tags: ["buffer-stats"] },
  });
  const j = await r.json().catch(() => null);
  if (!r.ok || !j || j.errors?.length) throw new Error(j?.errors?.[0]?.message || `HTTP ${r.status}`);
  return j.data;
}

// Deux versions de la requête : la complète (lien + miniature), et une minimale si Buffer
// refuse un champ (le schéma public n'est pas figé).
const FIELDS_FULL = "id text dueAt sentAt channelId metricsUpdatedAt metrics { type value } assets { source thumbnail }";
const FIELDS_MIN = "id text dueAt channelId metricsUpdatedAt metrics { type value }";

async function listPosts(status: "sent" | "scheduled", fields: string, maxPages: number) {
  const channels = JSON.stringify([...NET_BY_CHANNEL.keys()]);
  const nodes: any[] = [];
  let after: string | null = null;
  for (let page = 0; page < maxPages; page++) {
    const q = `query { posts(first: 100${after ? `, after: ${JSON.stringify(after)}` : ""}, input: { organizationId: ${JSON.stringify(ORG)}, filter: { status: [${status}], channelIds: ${channels} } }) { edges { node { ${fields} } } pageInfo { hasNextPage endCursor } } }`;
    const d = await gql(q);
    nodes.push(...(d?.posts?.edges ?? []).map((e: any) => e.node));
    if (!d?.posts?.pageInfo?.hasNextPage) break;
    after = d.posts.pageInfo.endCursor;
  }
  return nodes;
}

function toStats(n: any): PostStats | null {
  const net = NET_BY_CHANNEL.get(n.channelId);
  if (!net) return null;
  const m = new Map<string, number>((n.metrics ?? []).map((x: any) => [x.type, Number(x.value) || 0]));
  const asset = (n.assets ?? []).find((a: any) => a?.source) ?? {};
  const src: string | undefined = asset.source;
  return {
    id: n.id, net, text: n.text ?? "",
    at: n.sentAt ?? n.dueAt,
    url: src && /tiktok\.com|youtu/.test(src) ? src.split("?")[0] : undefined,
    thumb: asset.thumbnail,
    views: m.get("views") ?? m.get("impressions") ?? 0,
    likes: m.get("reactions") ?? m.get("likes") ?? 0,
    comments: m.get("comments") ?? 0,
    shares: m.get("shares") ?? 0,
    engagement: m.has("engagementRate") ? m.get("engagementRate")! : null,
    avgWatch: m.get("averageTimeWatched") || null,
    updatedAt: n.metricsUpdatedAt ?? undefined,
  };
}

export async function loadStats(): Promise<StatsResult> {
  if (!process.env.BUFFER_API_KEY) return { connected: false };
  try {
    let sent: any[];
    try { sent = await listPosts("sent", FIELDS_FULL, 5); }
    catch { sent = await listPosts("sent", FIELDS_MIN, 5); }
    const scheduled = await listPosts("scheduled", "id", 1).catch(() => []);
    const posts = sent.map(toStats).filter(Boolean) as PostStats[];
    posts.sort((a, b) => b.at.localeCompare(a.at));
    return { connected: true, ok: true, posts, scheduled: scheduled.length, fetchedAt: new Date().toISOString() };
  } catch (e) {
    return { connected: true, ok: false, error: String((e as Error).message ?? e).slice(0, 200) };
  }
}

export function totals(posts: PostStats[]) {
  const t = { posts: posts.length, views: 0, likes: 0, comments: 0, shares: 0, eng: null as number | null };
  let engSum = 0, engN = 0;
  for (const p of posts) {
    t.views += p.views; t.likes += p.likes; t.comments += p.comments; t.shares += p.shares;
    if (p.engagement != null && p.views > 0) { engSum += p.engagement; engN++; }
  }
  t.eng = engN ? engSum / engN : null;
  return t;
}
