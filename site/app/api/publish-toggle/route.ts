import { NextResponse } from "next/server";
import { publishQueue, setPublishEnabled } from "@/lib/buffer";

// Allume / coupe la publication auto (bouton dans Programmation).
export async function POST(req: Request) {
  const f = await req.formData();
  const on = f.get("enabled") === "on";
  await setPublishEnabled(on);
  if (on) await publishQueue().catch(() => {});
  return NextResponse.redirect(new URL("/?v=programmation", req.url), 303);
}
