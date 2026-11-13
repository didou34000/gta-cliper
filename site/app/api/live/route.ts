import { NextResponse } from "next/server";
import { loadHeartbeat, type Heartbeat } from "@/lib/data";
import { latestRun, type LiveRun } from "@/lib/github";
import { demoOn, DEMO_BEAT } from "@/lib/demo";
import { flushSiteOps } from "@/lib/r2";

export const dynamic = "force-dynamic";

export type Live = { run: LiveRun | null; beat: Heartbeat | null; now: string };

// Le statut du bot (status/live.json sur R2, 1 lecture de classe B) n'est relu qu'au plus
// toutes les 12 s, et seulement quand un passage tourne ou vient de finir.
let cache: { at: number; beat: Heartbeat | null } = { at: 0, beat: null };

async function freshBeat(): Promise<Heartbeat | null> {
  if (Date.now() - cache.at < 12_000) return cache.beat;
  const { last } = await loadHeartbeat().catch(() => ({ last: null }));
  cache = { at: Date.now(), beat: last ? { ...last, logs: undefined, events: last.events?.slice(-12) } : null };
  return cache.beat;
}

export async function GET() {
  if (demoOn()) return NextResponse.json({ run: await latestRun(), beat: DEMO_BEAT, now: new Date().toISOString() } satisfies Live);
  const run = await latestRun();
  flushSiteOps().catch(() => {});
  const busy = !!run && (run.status !== "completed" || Date.now() - +new Date(run.updated_at) < 5 * 60_000);
  return NextResponse.json({ run, beat: busy ? await freshBeat() : cache.beat, now: new Date().toISOString() } satisfies Live);
}
