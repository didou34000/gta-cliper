import { NextResponse } from "next/server";
import { COOKIE, expectedToken } from "@/lib/auth";

export async function POST(req: Request) {
  const form = await req.formData();
  const pw = String(form.get("password") ?? "");
  const base = new URL(req.url);
  if (!process.env.SITE_PASSWORD || pw !== process.env.SITE_PASSWORD) {
    return NextResponse.redirect(new URL("/login?e=1", base), 303);
  }
  const res = NextResponse.redirect(new URL("/", base), 303);
  res.cookies.set(COOKIE, (await expectedToken())!, {
    httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: 60 * 60 * 24 * 60,
  });
  return res;
}
