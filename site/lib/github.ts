// Suivi des lancements sur GitHub Actions (gratuit, ne consomme rien sur Vercel Blob).
// Le jeton GH_DISPATCH_TOKEN (droit « Actions ») sert aussi à lire l'état des passages.
import { REPO } from "./launch";
import { demoOn, demoRun } from "./demo";

export type LiveStep = { name: string; status: string; conclusion: string | null };
export type LiveRun = {
  id: number;
  kind: "passage" | "youtube";
  event: string;
  status: "queued" | "in_progress" | "completed" | string;
  conclusion: string | null;
  created_at: string;
  updated_at: string;
  url: string;
  step?: string;          // étape GitHub en cours
  steps?: LiveStep[];
  mainStep?: LiveStep;    // l'étape qui fait vraiment le travail
};

const WORKFLOWS: { file: string; kind: LiveRun["kind"]; main: string }[] = [
  { file: "bot.yml", kind: "passage", main: "Passage du bot" },
  { file: "youtube.yml", kind: "youtube", main: "Clips depuis le lien YouTube" },
];

async function gh<T>(path: string): Promise<T | null> {
  const token = process.env.GH_DISPATCH_TOKEN;
  if (!token) return null;
  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}${path}`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "gta-clipper-site" },
      cache: "no-store",
    });
    return r.ok ? ((await r.json()) as T) : null;
  } catch {
    return null;
  }
}

type ApiRun = { id: number; event: string; status: string; conclusion: string | null; created_at: string; updated_at: string; html_url: string };

/** Le passage le plus récent (lancé à la main, depuis le site ou en cours), avec son étape. */
export async function latestRun(): Promise<LiveRun | null> {
  if (demoOn()) return demoRun();
  const lists = await Promise.all(WORKFLOWS.map((w) => gh<{ workflow_runs: ApiRun[] }>(`/actions/workflows/${w.file}/runs?per_page=4`)));
  const runs: (ApiRun & { w: (typeof WORKFLOWS)[number] })[] = [];
  lists.forEach((l, i) => {
    for (const r of l?.workflow_runs ?? []) {
      // Les contrôles programmés qui ne lancent rien ne comptent pas, sauf s'ils tournent encore.
      if (r.event === "schedule" && r.status === "completed" && r.conclusion !== "failure") continue;
      runs.push({ ...r, w: WORKFLOWS[i] });
    }
  });
  if (!runs.length) return null;
  runs.sort((a, b) => b.created_at.localeCompare(a.created_at));
  const r = runs.find((x) => x.status !== "completed") ?? runs[0];
  const run: LiveRun = {
    id: r.id, kind: r.w.kind, event: r.event, status: r.status, conclusion: r.conclusion,
    created_at: r.created_at, updated_at: r.updated_at, url: r.html_url,
  };
  // Détail des étapes : seulement pour un passage en cours ou fini il y a peu.
  if (r.status !== "completed" || Date.now() - +new Date(r.updated_at) < 15 * 60_000) {
    const jobs = await gh<{ jobs: { name: string; status: string; steps?: LiveStep[] }[] }>(`/actions/runs/${r.id}/jobs`);
    const steps = (jobs?.jobs ?? []).flatMap((j) => j.steps ?? []);
    run.steps = steps.map((s) => ({ name: s.name, status: s.status, conclusion: s.conclusion }));
    run.step = steps.find((s) => s.status === "in_progress")?.name;
    run.mainStep = run.steps.find((s) => s.name === r.w.main);
  }
  return run;
}
