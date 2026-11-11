// Petits fichiers JSON à nom fixe dans Vercel Blob (réglages, interrupteurs).
// Pourquoi : l'offre gratuite de Blob ne donne que 2 000 « opérations avancées » par mois,
// et chaque list() ou put() en coûte une. Lire un fichier par son adresse publique est une
// « opération simple » (10 000 par mois, et gratuite quand le CDN a la réponse en cache).
import { put } from "@vercel/blob";

/** Adresse publique d'un fichier à nom fixe (même règle que @vercel/blob). */
export function blobUrl(pathname: string) {
  const store = (process.env.BLOB_READ_WRITE_TOKEN ?? "").split("_")[3] ?? "";
  return `https://${store}.public.blob.vercel-storage.com/${pathname}`;
}

/** Lit un fichier à nom fixe. undefined = absent (404), null = illisible. */
export async function readFixed<T>(pathname: string, fresh = false): Promise<T | undefined | null> {
  try {
    const url = fresh ? `${blobUrl(pathname)}?t=${Date.now()}` : blobUrl(pathname);
    const r = await fetch(url, { cache: "no-store" });
    if (r.status === 404) return undefined;
    return r.ok ? ((await r.json()) as T) : null;
  } catch {
    return null;
  }
}

export async function writeFixed(pathname: string, data: unknown) {
  await put(pathname, JSON.stringify(data), {
    access: "public", contentType: "application/json",
    addRandomSuffix: false, allowOverwrite: true, cacheControlMaxAge: 60,
  });
}
