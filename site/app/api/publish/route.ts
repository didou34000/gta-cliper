import { NextResponse } from "next/server";
import { publishQueue } from "@/lib/buffer";

// Remplit la file Buffer avec les clips validés. Appelé toutes les 20 min par GitHub
// (.github/workflows/publish.yml, sans ?force : ne fait rien avant l'heure utile) et par le bot
// après une validation automatique (?force=1).
export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const force = new URL(req.url).searchParams.get("force") === "1";
  const r = await publishQueue({ force });
  return NextResponse.json(r, { status: r.ok ? 200 : 503 });
}
