// Consommation et quotas de chaque service, pour la page « Consommation ».
//
// Ce qui est MESURÉ :
//  - chaque passage du bot : opérations R2 (A/B), appels et coût Claude, clips, durée
//    (relevé écrit par le bot dans usage/AAAA-MM.json) ;
//  - les opérations R2 du site (compteur du site, usage/site-AAAA-MM-JJ.json) ;
//  - les minutes GitHub Actions du mois (API GitHub) ;
//  - si CF_API_TOKEN est défini : le total exact compté par Cloudflare (API Analytics).
// Ce qui est ESTIMÉ : la projection de fin de mois et l'usage Vercel (pas d'API gratuite).
import { getJsonKey, listAll, r2Configured } from "./r2";
import { gh } from "./github";

export type RunUsage = {
  at: string; kind: string; status: string; gh_run?: string;
  r2_a: number; r2_b: number; llm_calls: number; llm_in: number; llm_out: number; llm_usd: number;
  clips: number; seconds: number;
};

export type Usage = {
  month: string;              // AAAA-MM
  dayOfMonth: number;
  daysInMonth: number;
  runs: RunUsage[];
  bot: { a: number; b: number; usd: number; calls: number; clips: number; seconds: number };
  site: { a: number; b: number; pages: number; days: number };
  cloudflare: { a: number; b: number; storageBytes?: number } | null; // exact (si jeton)
  cloudflareError?: string;
  github: { minutes: number; runs: number } | null;
  perClip: { a: number; b: number; usd: number; minutes: number } | null;
  perRun: { a: number; b: number; usd: number; minutes: number } | null;
};

export const PLANS = {
  r2: { name: "Cloudflare R2 · gratuit", storageGB: 10, classA: 1_000_000, classB: 10_000_000 },
  vercel: { name: "Vercel · Hobby (gratuit)", invocations: 1_000_000, transferGB: 100, cpuHours: 4 },
  github: { name: "GitHub Actions · dépôt public", minutes: Infinity },
  claude: { name: "Claude API · paiement à l'usage", dailyCalls: 60 },
  buffer: { name: "Buffer · gratuit", channels: 3, queuePerChannel: 10 },
  twitch: { name: "Twitch API · gratuit", perMinute: 800 },
};

const sum = <T,>(xs: T[], f: (x: T) => number) => xs.reduce((n, x) => n + (f(x) || 0), 0);

async function cloudflareTotals(month: string): Promise<{ a: number; b: number; storageBytes?: number }> {
  const token = process.env.CF_API_TOKEN, account = process.env.R2_ACCOUNT_ID;
  if (!token || !account) throw new Error("pas de jeton");
  const start = `${month}-01T00:00:00Z`;
  const query = `query($a: String!, $s: Time!, $e: Time!, $b: String!) { viewer { accounts(filter: {accountTag: $a}) {
    ops: r2OperationsAdaptiveGroups(limit: 100, filter: {datetime_geq: $s, datetime_leq: $e, bucketName: $b}) { sum { requests } dimensions { actionType } }
    st: r2StorageAdaptiveGroups(limit: 1, filter: {datetime_geq: $s, datetime_leq: $e, bucketName: $b}, orderBy: [datetime_DESC]) { max { payloadSize } }
  } } }`;
  const r = await fetch("https://api.cloudflare.com/client/v4/graphql", {
    method: "POST", cache: "no-store",
    headers: { Authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify({ query, variables: { a: account, s: start, e: new Date().toISOString(), b: process.env.R2_BUCKET || "gta-clipper" } }),
  });
  const j = await r.json();
  if (j.errors?.length) throw new Error(j.errors[0].message);
  const acc = j.data?.viewer?.accounts?.[0];
  // Liste officielle des opérations de classe A (le reste est en classe B, sauf les suppressions).
  const A = new Set(["ListBuckets", "PutBucket", "ListObjects", "PutObject", "CopyObject", "CompleteMultipartUpload",
    "CreateMultipartUpload", "ListMultipartUploads", "UploadPart", "UploadPartCopy", "ListParts", "PutBucketEncryption",
    "PutBucketCors", "PutBucketLifecycleConfiguration", "LifecycleStorageTierTransition", "DeleteObjects"]);
  const FREE = new Set(["DeleteObject", "DeleteBucket", "AbortMultipartUpload"]);
  let a = 0, b = 0;
  for (const g of acc?.ops ?? []) {
    const t = g.dimensions.actionType as string, n = g.sum.requests as number;
    if (FREE.has(t)) continue;
    if (A.has(t)) a += n; else b += n;
  }
  return { a, b, storageBytes: acc?.st?.[0]?.max?.payloadSize };
}

async function githubMinutes(month: string): Promise<{ minutes: number; runs: number } | null> {
  type R = { workflow_runs: { run_started_at?: string; created_at: string; updated_at: string; status: string }[]; total_count: number };
  let minutes = 0, runs = 0;
  for (let page = 1; page <= 5; page++) {
    const d = await gh<R>(`/actions/runs?per_page=100&page=${page}&created=%3E%3D${month}-01`);
    if (!d) return page === 1 ? null : { minutes: Math.round(minutes), runs };
    for (const r of d.workflow_runs) {
      if (r.status !== "completed") continue;
      runs++;
      // GitHub facture à la minute entamée, par job ; on arrondit le passage entier.
      minutes += Math.ceil((+new Date(r.updated_at) - +new Date(r.run_started_at ?? r.created_at)) / 60000);
    }
    if (d.workflow_runs.length < 100) break;
  }
  return { minutes: Math.round(minutes), runs };
}

export async function loadUsage(): Promise<Usage> {
  const now = new Date();
  const month = now.toISOString().slice(0, 7);
  const daysInMonth = new Date(now.getUTCFullYear(), now.getUTCMonth() + 1, 0).getDate();
  const empty = { a: 0, b: 0, pages: 0, days: 0 };

  const [book, siteDays, cf, ghm] = await Promise.all([
    r2Configured() ? getJsonKey<{ runs: RunUsage[] }>(`usage/${month}.json`) : null,
    r2Configured()
      ? listAll(`usage/site-${month}`, 60_000).then((objs) =>
          Promise.all(objs.map((o) => getJsonKey<{ a: number; b: number; pages: number }>(o.pathname))))
      : Promise.resolve([]),
    cloudflareTotals(month).then((v) => ({ v, e: undefined as string | undefined }), (e: Error) => ({ v: null, e: e.message })),
    githubMinutes(month),
  ]);

  const runs = (book?.runs ?? []).filter((r) => r.at?.startsWith(month));
  const site = { ...empty };
  for (const d of siteDays) {
    if (!d) continue;
    site.a += d.a || 0; site.b += d.b || 0; site.pages += d.pages || 0; site.days += 1;
  }
  const bot = {
    a: sum(runs, (r) => r.r2_a), b: sum(runs, (r) => r.r2_b), usd: sum(runs, (r) => r.llm_usd),
    calls: sum(runs, (r) => r.llm_calls), clips: sum(runs, (r) => r.clips), seconds: sum(runs, (r) => r.seconds),
  };
  const withClips = runs.filter((r) => r.clips > 0);
  const nc = sum(withClips, (r) => r.clips);
  const perClip = nc ? {
    a: sum(withClips, (r) => r.r2_a) / nc, b: sum(withClips, (r) => r.r2_b) / nc,
    usd: sum(withClips, (r) => r.llm_usd) / nc, minutes: sum(withClips, (r) => r.seconds) / 60 / nc,
  } : null;
  const perRun = runs.length ? {
    a: bot.a / runs.length, b: bot.b / runs.length, usd: bot.usd / runs.length, minutes: bot.seconds / 60 / runs.length,
  } : null;

  return {
    month, dayOfMonth: now.getUTCDate(), daysInMonth, runs: runs.slice(-50).reverse(), bot, site,
    cloudflare: cf.v, cloudflareError: process.env.CF_API_TOKEN ? cf.e : undefined,
    github: ghm, perClip, perRun,
  };
}
