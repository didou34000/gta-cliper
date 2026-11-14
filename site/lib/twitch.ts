// Lives GTA en lecture seule, via l'API Twitch Helix (gratuite, 800 requêtes/min, aucun quota mensuel).
// Rien n'est écrit nulle part : ni R2, ni base, ni cache Vercel. Le résultat est gardé 60 s
// en mémoire du serveur, et n'est demandé que quand quelqu'un ouvre ou rafraîchit la page.
import { demoOn } from "./demo";

export type Stream = {
  login: string;
  name: string;
  title: string;
  game: string;
  lang: string;
  viewers: number;
  started_at: string;
  thumb: string;
  tags: string[];
};

export type LivesResult = {
  ok: boolean;
  configured: boolean;
  error?: string;
  streams: Stream[];
  truncated: boolean;     // il y a plus de lives que ce qu'on a chargé
  fetched_at: string;
  games: { id: string; name: string }[];
};

export const LIVE_GAMES = ["Grand Theft Auto VI", "Grand Theft Auto V"];
const PAGES = 10;          // 10 × 100 = les 1000 plus gros lives max par chargement
const TTL = 60_000;

const CLIENT_ID = process.env.TWITCH_CLIENT_ID || "7t3dj86daadls0hj8rru2y2nuxxx2z";
const SECRET = process.env.TWITCH_CLIENT_SECRET;

let token: { value: string; exp: number } | null = null;
let gameIds: { id: string; name: string }[] | null = null;
const cache = new Map<string, { at: number; data: LivesResult }>();

async function getToken(): Promise<string> {
  if (token && Date.now() < token.exp) return token.value;
  const r = await fetch("https://id.twitch.tv/oauth2/token", {
    method: "POST",
    body: new URLSearchParams({ client_id: CLIENT_ID, client_secret: SECRET!, grant_type: "client_credentials" }),
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`Twitch a refusé la connexion (${r.status}) : vérifie TWITCH_CLIENT_SECRET sur Vercel`);
  const j = await r.json();
  token = { value: j.access_token, exp: Date.now() + (j.expires_in - 300) * 1000 };
  return token.value;
}

async function helix<T>(path: string): Promise<T> {
  const r = await fetch(`https://api.twitch.tv/helix/${path}`, {
    headers: { "Client-Id": CLIENT_ID, Authorization: `Bearer ${await getToken()}` },
    cache: "no-store",
  });
  if (r.status === 401) token = null;
  if (!r.ok) throw new Error(`Twitch ${r.status} sur ${path.split("?")[0]}`);
  return r.json();
}

async function getGames() {
  if (gameIds) return gameIds;
  const q = LIVE_GAMES.map((n) => `name=${encodeURIComponent(n)}`).join("&");
  const j = await helix<{ data: { id: string; name: string }[] }>(`games?${q}`);
  gameIds = j.data.map((g) => ({ id: g.id, name: g.name }));
  return gameIds;
}

type HelixStream = { user_login: string; user_name: string; title: string; game_name: string; language: string; viewer_count: number; started_at: string; thumbnail_url: string; tags?: string[] };

/** Lives GTA VI + GTA V, triés par viewers. `lang` (code ISO, ex. « fr ») = filtre fait par Twitch. */
export async function loadLives(lang?: string): Promise<LivesResult> {
  const key = lang || "*";
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < TTL) return hit.data;
  if (demoOn()) return demoLives(lang);
  const empty = { streams: [], truncated: false, fetched_at: new Date().toISOString(), games: [] };
  if (!SECRET) return { ok: false, configured: false, ...empty };

  try {
    const games = await getGames();
    const base = games.map((g) => `game_id=${g.id}`).join("&") + (lang ? `&language=${encodeURIComponent(lang)}` : "") + "&first=100";
    const streams: Stream[] = [];
    let after: string | undefined;
    let pages = 0;
    do {
      const j = await helix<{ data: HelixStream[]; pagination?: { cursor?: string } }>(`streams?${base}${after ? `&after=${after}` : ""}`);
      for (const s of j.data) {
        streams.push({
          login: s.user_login, name: s.user_name, title: s.title, game: s.game_name, lang: s.language,
          viewers: s.viewer_count, started_at: s.started_at, tags: s.tags ?? [],
          thumb: s.thumbnail_url.replace("{width}", "440").replace("{height}", "248"),
        });
      }
      after = j.data.length ? j.pagination?.cursor : undefined;
      pages++;
    } while (after && pages < PAGES);
    // Les pages Twitch peuvent se chevaucher pendant que les chiffres bougent : on dédoublonne.
    const seen = new Set<string>();
    const uniq = streams.filter((s) => (seen.has(s.login) ? false : (seen.add(s.login), true)));
    uniq.sort((a, b) => b.viewers - a.viewers);
    const data: LivesResult = { ok: true, configured: true, streams: uniq, truncated: !!after, fetched_at: new Date().toISOString(), games };
    cache.set(key, { at: Date.now(), data });
    if (cache.size > 30) cache.delete(cache.keys().next().value!);
    return data;
  } catch (e) {
    return { ok: false, configured: true, error: (e as Error).message, ...empty };
  }
}

/** Nom normalisé pour relier un live aux clips du bot (« ZeratoR » = « zerator »). */
export const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

export const LANG_LABEL: Record<string, string> = {
  fr: "Français", en: "Anglais", es: "Espagnol", pt: "Portugais", de: "Allemand", it: "Italien",
  ru: "Russe", pl: "Polonais", tr: "Turc", ar: "Arabe", ja: "Japonais", ko: "Coréen", zh: "Chinois",
  nl: "Néerlandais", sv: "Suédois", uk: "Ukrainien", cs: "Tchèque", hu: "Hongrois", el: "Grec",
  ro: "Roumain", fi: "Finnois", da: "Danois", no: "Norvégien", th: "Thaï", vi: "Vietnamien",
  id: "Indonésien", hi: "Hindi", other: "Autre",
};

function demoLives(lang?: string): LivesResult {
  const mk = (login: string, name: string, game: string, l: string, viewers: number, title: string, minAgo: number): Stream => ({
    login, name, title, game, lang: l, viewers, started_at: new Date(Date.now() - minAgo * 60000).toISOString(), tags: [],
    thumb: `https://static-cdn.jtvnw.net/previews-ttv/live_user_${login}-440x248.jpg`,
  });
  const all = [
    mk("kaicenat", "KaiCenat", "Grand Theft Auto VI", "en", 182340, "GTA 6 FIRST DAY 24H STREAM", 190),
    mk("ibai", "Ibai", "Grand Theft Auto VI", "es", 96210, "GTA VI CON LOS CHICOS", 120),
    mk("squeezie", "Squeezie", "Grand Theft Auto VI", "fr", 64120, "ON DÉCOUVRE LEONIDA !!", 95),
    mk("zerator", "ZeratoR", "Grand Theft Auto VI", "fr", 31877, "GTA VI à 100% — jour 1", 240),
    mk("gaules", "Gaules", "Grand Theft Auto VI", "pt", 28450, "GTA 6 COM A TRIBO", 60),
    mk("gotaga", "Gotaga", "Grand Theft Auto V", "fr", 12030, "Dernier RP avant GTA 6", 45),
    mk("papaplatte", "Papaplatte", "Grand Theft Auto VI", "de", 9870, "gta 6 endlich", 30),
    mk("locklear", "Locklear", "Grand Theft Auto VI", "fr", 7420, "Vice City ce soir", 20),
    mk("xqc", "xQc", "Grand Theft Auto V", "en", 6500, "NOPIXEL BEFORE 6", 300),
    mk("doigby", "Doigby", "Grand Theft Auto V", "fr", 3100, "Flashback RP", 75),
  ];
  return {
    ok: true, configured: true, truncated: false, fetched_at: new Date().toISOString(),
    games: [{ id: "1", name: "Grand Theft Auto VI" }, { id: "32982", name: "Grand Theft Auto V" }],
    streams: lang ? all.filter((s) => s.lang === lang) : all,
  };
}
