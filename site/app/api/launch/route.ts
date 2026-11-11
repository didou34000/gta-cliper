import { NextResponse } from "next/server";
import { REPO, WORKFLOW } from "@/lib/launch";

// Lance un passage du bot sur GitHub Actions avec le jeu et les streamers choisis.
// Le jeton GH_DISPATCH_TOKEN (Vercel) n'a que le droit « Actions » sur le dépôt.
export async function POST(req: Request) {
  const f = await req.formData();
  const back = (q: string) => NextResponse.redirect(new URL(`/?launch=${q}`, req.url), 303);

  const token = process.env.GH_DISPATCH_TOKEN;
  if (!token) return back("notoken");

  const other = String(f.get("jeu_autre") ?? "").trim();
  const jeu = (other || String(f.get("jeu") ?? "")).trim().slice(0, 80) || "Grand Theft Auto VI";

  const logins = [
    ...f.getAll("streamer").map(String),
    ...String(f.get("streamers_autres") ?? "").split(/[\s,;]+/),
  ]
    .map((l) => l.trim().toLowerCase().replace(/^@/, ""))
    .filter((l) => /^[a-z0-9_]{3,25}$/.test(l));
  const uniq = [...new Set(logins)].slice(0, 20);
  // Par défaut : les N plus gros streamers FR du jeu. Si des streamers sont cochés, on prend ceux-là.
  const top = uniq.length ? 0 : Math.min(20, Math.max(1, parseInt(String(f.get("top") ?? "8"), 10) || 8));

  const n = Math.min(10, Math.max(1, parseInt(String(f.get("max_clips") ?? "3"), 10) || 3));

  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "gta-clipper-site",
    },
    body: JSON.stringify({ ref: "main", inputs: { jeu, top_streamers: String(top), streamers: uniq.join(","), max_clips: String(n) } }),
    cache: "no-store",
  });
  if (!r.ok) {
    console.error("dispatch", r.status, await r.text());
    return back(`error${r.status}`);
  }
  return back("ok");
}
