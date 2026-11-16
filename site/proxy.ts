import { NextRequest, NextResponse } from "next/server";
import { COOKIE, isValid } from "@/lib/auth";

export async function proxy(req: NextRequest) {
  if (await isValid(req.cookies.get(COOKIE)?.value)) return NextResponse.next();
  if (req.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "Non connecté" }, { status: 401 });
  }
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = "";
  return NextResponse.redirect(url);
}

export const config = {
  // /flex et /board : pages démo publiques (données fictives, rien de secret).
  // /api/publish reste ouvert : GitHub l'appelle toutes les 20 min (il ne fait que remplir la file Buffer).
  matcher: ["/((?!flex|board|login|api/login|api/publish|api/twitch-token|_next/static|_next/image|favicon.ico).*)"],
};
