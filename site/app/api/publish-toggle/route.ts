import { NextResponse } from "next/server";
import { publishQueue, setPublishEnabled } from "@/lib/buffer";
import { setWorkflow } from "@/lib/github";

// Allume / coupe la publication auto (bouton dans Programmation).
export async function POST(req: Request) {
  const f = await req.formData();
  const on = f.get("enabled") === "on";
  await setPublishEnabled(on);
  await setWorkflow("publish.yml", on); // pas de passage toutes les 20 min si c'est coupé
  if (on) await publishQueue().catch(() => {});
  return NextResponse.redirect(new URL("/?v=programmation", req.url), 303);
}
