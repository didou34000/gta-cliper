// Active / désactive un workflow GitHub Actions depuis le site, pour qu'aucun contrôle
// automatique ne tourne tant que l'utilisateur n'a rien allumé.
//  bot-cron.yml : passages programmés (suit Programmation > État)
//  publish.yml  : remplissage de la file Buffer (suit l'interrupteur de publication)
// Jeton GH_DISPATCH_TOKEN (Vercel), droit « Actions » en écriture sur le dépôt.
import { REPO } from "./launch";

export async function setWorkflow(file: "bot-cron.yml" | "publish.yml", on: boolean): Promise<boolean> {
  const token = process.env.GH_DISPATCH_TOKEN;
  if (!token) return false;
  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${file}/${on ? "enable" : "disable"}`, {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "gta-clipper-site",
      },
      cache: "no-store",
    });
    if (!r.ok) console.error("workflow", file, on, r.status, await r.text());
    return r.ok;
  } catch (e) {
    console.error("workflow", file, on, e);
    return false;
  }
}
