import { NextResponse } from "next/server";
import { REPO } from "@/lib/launch";

// Lien YouTube -> clips : lance le workflow « youtube.yml » sur GitHub Actions.
const YT = /^https?:\/\/(www\.|m\.)?(youtube\.com\/(watch\?|shorts\/|live\/)|youtu\.be\/)[\w\-?=&%.\/]+$/i;

export async function POST(req: Request) {
  const f = await req.formData();
  const back = (q: string) => NextResponse.redirect(new URL(`/?v=programmation&yt=${q}`, req.url), 303);

  const token = process.env.GH_DISPATCH_TOKEN;
  if (!token) return back("notoken");

  const url = String(f.get("url") ?? "").trim().slice(0, 300);
  if (!YT.test(url)) return back("badurl");
  const other = String(f.get("jeu_autre") ?? "").trim();
  const jeu = (other || String(f.get("jeu") ?? "")).trim().slice(0, 80) || "Grand Theft Auto VI";
  const clips = String(Math.min(8, Math.max(1, parseInt(String(f.get("clips") ?? "3"), 10) || 3)));
  const streamer = String(f.get("streamer") ?? "").replace(/[^\p{L}\p{N} _.'-]/gu, "").trim().slice(0, 40);

  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/youtube.yml/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "gta-clipper-site",
    },
    body: JSON.stringify({ ref: "main", inputs: { url, clips, jeu, streamer } }),
    cache: "no-store",
  });
  if (!r.ok) {
    console.error("dispatch youtube", r.status, await r.text());
    return back(`error${r.status}`);
  }
  return back("ok");
}
