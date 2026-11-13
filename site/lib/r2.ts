// Stockage Cloudflare R2 (API compatible S3), utilisé par le site et par le bot.
// Quota gratuit par mois : 10 Go stockés, 1 million d'opérations de classe A (écriture,
// listage), 10 millions de classe B (lecture). Les suppressions sont gratuites.
//
// Règles pour rester économe :
//  - les fichiers qui changent (statut du bot, réglages, interrupteur de publication, relevés)
//    ont un nom fixe et sont lus directement (1 lecture B), jamais par listage ;
//  - seuls les clips et les décisions sont listés, avec un cache de 20 s par instance ;
//  - chaque opération est comptée (voir flushSiteOps) pour la page « Consommation ».
import { AwsClient } from "aws4fetch";

export type Obj = { pathname: string; url: string; size: number; uploadedAt: string };

const env = (k: string) => process.env[k] ?? "";
export const r2Configured = () =>
  !!(env("R2_ACCOUNT_ID") && env("R2_ACCESS_KEY_ID") && env("R2_SECRET_ACCESS_KEY") && env("R2_PUBLIC_URL"));
const bucket = () => env("R2_BUCKET") || "gta-clipper";
export const publicUrl = (key = "") => {
  const base = env("R2_PUBLIC_URL").replace(/\/+$/, "");
  return key ? `${base}/${key}` : base;
};
const endpoint = () => env("R2_ENDPOINT") || `https://${env("R2_ACCOUNT_ID")}.r2.cloudflarestorage.com`;
const encKey = (key: string) => key.split("/").map(encodeURIComponent).join("/");

let client: AwsClient | null = null;
function aws() {
  client ??= new AwsClient({
    accessKeyId: env("R2_ACCESS_KEY_ID"), secretAccessKey: env("R2_SECRET_ACCESS_KEY"),
    service: "s3", region: "auto", retries: 2,
  });
  return client;
}

// --- comptage des opérations du site --------------------------------------------------------
const ops = { a: 0, b: 0, pages: 0, since: Date.now() };
export const countOp = (cls: "A" | "B") => { if (cls === "A") ops.a++; else ops.b++; };
export const countPage = () => { ops.pages++; };

async function call(method: string, key: string, init: { query?: Record<string, string>; body?: BodyInit; headers?: Record<string, string> } = {}) {
  const qs = init.query ? "?" + new URLSearchParams(init.query).toString() : "";
  const url = `${endpoint()}/${bucket()}${key ? "/" + encKey(key) : ""}${qs}`;
  if (method !== "DELETE") countOp(method === "GET" && !init.query?.["list-type"] ? "B" : "A");
  return aws().fetch(url, { method, body: init.body, headers: init.headers, cache: "no-store" } as RequestInit);
}

const unxml = (s: string) =>
  s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, "&");
const tag = (xml: string, name: string) => {
  const m = xml.match(new RegExp(`<${name}>([\\s\\S]*?)</${name}>`));
  return m ? unxml(m[1]) : "";
};

// Cache court par instance : plusieurs composants de la même page ne relistent pas.
const listCache = new Map<string, { at: number; objs: Obj[] }>();

export async function listAll(prefix: string, maxAgeMs = 20_000): Promise<Obj[]> {
  const hit = listCache.get(prefix);
  if (hit && Date.now() - hit.at < maxAgeMs) return hit.objs;
  const out: Obj[] = [];
  let token = "";
  for (let i = 0; i < 50; i++) {
    const query: Record<string, string> = { "list-type": "2", prefix, "max-keys": "1000" };
    if (token) query["continuation-token"] = token;
    const r = await call("GET", "", { query });
    if (!r.ok) throw new Error(`R2 liste ${prefix} : HTTP ${r.status} ${(await r.text()).slice(0, 200)}`);
    const xml = await r.text();
    for (const m of xml.matchAll(/<Contents>([\s\S]*?)<\/Contents>/g)) {
      const key = tag(m[1], "Key");
      out.push({ pathname: key, url: publicUrl(key), size: Number(tag(m[1], "Size") || 0), uploadedAt: tag(m[1], "LastModified") });
    }
    token = tag(xml, "IsTruncated") === "true" ? tag(xml, "NextContinuationToken") : "";
    if (!token) break;
  }
  listCache.set(prefix, { at: Date.now(), objs: out });
  return out;
}

/** Lecture directe d'un fichier à nom fixe (pas de cache). null s'il n'existe pas. */
export async function getJsonKey<T>(key: string): Promise<T | null> {
  try {
    const r = await call("GET", key);
    if (r.status === 404) return null;
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

const suffixed = (path: string) => {
  const tag = Math.random().toString(16).slice(2, 12);
  const i = path.lastIndexOf(".");
  return i > path.lastIndexOf("/") ? `${path.slice(0, i)}-${tag}${path.slice(i)}` : `${path}-${tag}`;
};

/** Écrit un fichier. suffix=true : nom unique (jamais écrasé, cache long) ; false : nom fixe. */
export async function putObject(path: string, body: string, opts: { contentType?: string; suffix?: boolean } = {}) {
  const key = opts.suffix ? suffixed(path) : path;
  const r = await call("PUT", key, {
    body,
    headers: {
      "content-type": opts.contentType ?? "application/json",
      "cache-control": opts.suffix ? "public, max-age=31536000, immutable" : "no-cache",
    },
  });
  if (!r.ok) throw new Error(`R2 envoi ${path} : HTTP ${r.status} ${(await r.text()).slice(0, 200)}`);
  for (const p of listCache.keys()) if (key.startsWith(p)) listCache.delete(p);
  return { pathname: key, url: publicUrl(key) };
}

/** Supprime des fichiers (par URL publique ou par clé). Gratuit chez R2. */
export async function deleteObjects(urlsOrKeys: string[]) {
  const base = publicUrl() + "/";
  const keys = urlsOrKeys.map((u) => (u.startsWith(base) ? u.slice(base.length) : u));
  for (let i = 0; i < keys.length; i += 10) {
    await Promise.all(keys.slice(i, i + 10).map((k) => call("DELETE", k)));
  }
  listCache.clear();
}

// --- relevé des opérations du site ------------------------------------------------------------
// Toutes les 15 min au plus, chaque instance ajoute ses compteurs au relevé du jour
// (usage/site-AAAA-MM-JJ.json : 1 lecture + 1 écriture, elles-mêmes comptées).
let lastFlush = Date.now();
export async function flushSiteOps(force = false) {
  if (!r2Configured()) return;
  if (!force && Date.now() - lastFlush < 15 * 60_000) return;
  if (!ops.a && !ops.b && !ops.pages) return;
  lastFlush = Date.now();
  const day = new Date().toISOString().slice(0, 10);
  const key = `usage/site-${day}.json`;
  const take = { a: ops.a + 2, b: ops.b, pages: ops.pages };
  ops.a = 0; ops.b = 0; ops.pages = 0;
  try {
    const cur = (await getJsonKey<{ a: number; b: number; pages: number }>(key)) ?? { a: 0, b: 0, pages: 0 };
    await putObject(key, JSON.stringify({ a: cur.a + take.a, b: cur.b + take.b, pages: cur.pages + take.pages, at: new Date().toISOString() }));
  } catch {
    ops.a += take.a - 2; ops.b += take.b; ops.pages += take.pages; // on réessaiera plus tard
  }
}
