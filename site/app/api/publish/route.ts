import { NextResponse } from "next/server";
import { publishQueue } from "@/lib/buffer";
import { flushSiteOps } from "@/lib/r2";

// Remplit la file Buffer avec les clips validés. Appelé après chaque validation sur le site
// et toutes les 20 min par GitHub (.github/workflows/publish.yml).
export const dynamic = "force-dynamic";

export async function POST() {
  const r = await publishQueue();
  await flushSiteOps().catch(() => {});
  return NextResponse.json(r, { status: r.ok ? 200 : 503 });
}
