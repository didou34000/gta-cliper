import { Meter, PageHead, Panel, type Ctx } from "../ctx";
import { CHANNELS } from "@/lib/buffer";
import { euros, mb } from "@/lib/format";

const GB = 1024 * 1024 * 1024;
// Ordres de grandeur mesurés (Claude Haiku 5.5) : titres ~0,2 centime par clip, présélection ~0,1 centime par passage.
const CENTS_PER_CLIP = 0.2;
const CENTS_PER_RUN = 0.1;

type Row = { name: string; ok: boolean | null; detail: string; fix?: React.ReactNode };

export default function SettingsView({ ctx }: { ctx: Ctx }) {
  const { last, clips, bytes, stats } = ctx;
  const botOk = last ? (last.status === "error" ? false : true) : null;
  const rows: Row[] = [
    { name: "Stockage des clips (Vercel Blob)", ok: ctx.configured, detail: ctx.configured ? "branché" : "BLOB_READ_WRITE_TOKEN manquant sur Vercel" },
    {
      name: "Buffer (publication + stats)",
      ok: !stats.connected ? false : stats.ok,
      detail: !stats.connected ? "clé BUFFER_API_KEY manquante sur Vercel" : stats.ok ? `branché · ${stats.posts.length} posts lus` : `erreur : ${stats.error}`,
      fix: !stats.connected ? <a href="https://publish.buffer.com/settings/api" target="_blank" rel="noreferrer">Créer la clé</a> : undefined,
    },
    { name: "TikTok @gta6francenews", ok: !!CHANNELS.tiktok, detail: "via Buffer (stats : vues, likes, commentaires, partages, engagement)" },
    { name: "YouTube « GTA 6 FRANCE »", ok: !!CHANNELS.youtube, detail: "via Buffer (stats remontées par Buffer)" },
    { name: "Instagram", ok: CHANNELS.instagram ? true : null, detail: CHANNELS.instagram ? "via Buffer" : "pas branché · 1 place gratuite restante dans Buffer" },
    {
      name: "Bouton « Lancer » (GitHub)", ok: !!process.env.GH_DISPATCH_TOKEN,
      detail: process.env.GH_DISPATCH_TOKEN ? "branché" : "jeton GH_DISPATCH_TOKEN manquant sur Vercel",
    },
    {
      name: "Twitch + Claude (secrets GitHub)", ok: botOk,
      detail: botOk === null ? "pas encore vérifié : aucun passage" : botOk ? "OK au dernier passage du bot" : "le dernier passage a échoué, voir Bot en direct",
    },
  ];

  const runs = new Set(clips.map((c) => c.run?.id).filter(Boolean)).size;
  const cost = clips.length * CENTS_PER_CLIP + runs * CENTS_PER_RUN;
  const scheduled = stats.connected && stats.ok ? stats.scheduled : null;

  return (
    <>
      <PageHead title="Connexions & coûts" sub="Ce qui est branché, ce qui manque, et ce que ça coûte." />

      <Panel title="Connexions">
        <ul className="conn">
          {rows.map((r) => (
            <li key={r.name} className={`conn-${r.ok === null ? "na" : r.ok ? "ok" : "ko"}`}>
              <span className="conn-dot" aria-hidden="true" />
              <span className="conn-name">{r.name}</span>
              <span className="conn-detail">{r.detail}{r.fix ? <> · {r.fix}</> : null}</span>
            </li>
          ))}
        </ul>
      </Panel>

      <div className="grid-2">
        <Panel title="Quotas gratuits">
          <div className="meters">
            <Meter label={<>Stockage Vercel · {mb(bytes)} sur 1 Go</>} value={bytes} max={GB} />
            <p className="muted small">Le bot fait le ménage tout seul à 800 Mo (publiés d&apos;abord, puis les plus anciens) jusqu&apos;à redescendre à 400 Mo.</p>
            {scheduled != null
              ? <Meter label={<>File Buffer · {scheduled} posts programmés sur 10</>} value={scheduled} max={10} tone="violet" />
              : <p className="muted small">File Buffer : visible une fois la clé Buffer ajoutée (10 posts programmés max en gratuit).</p>}
          </div>
        </Panel>

        <Panel title="Coût Claude (estimation)">
          <p className="big-num">{euros(cost)}</p>
          <p className="muted small">
            Pour les {clips.length} clips encore stockés et {runs} passage{runs > 1 ? "s" : ""} : ~{CENTS_PER_CLIP.toLocaleString("fr-FR")} centime par clip (titres, Haiku 5.5)
            + ~{CENTS_PER_RUN.toLocaleString("fr-FR")} centime par passage (note de potentiel). C&apos;est une estimation basse : les clips rejetés ou nettoyés ne sont plus comptés.
            Le vrai montant est sur <a href="https://console.anthropic.com/settings/usage" target="_blank" rel="noreferrer">console.anthropic.com</a>.
          </p>
          <p className="muted small">Twitch, GitHub Actions, Vercel et Buffer : gratuits dans les limites actuelles.</p>
        </Panel>
      </div>

      <Panel title="Garde-fous du bot">
        <ul className="facts facts-cols">
          <li><span>Appels Claude par jour</span><b>60 max</b></li>
          <li><span>Clips par passage</span><b>10 max</b></li>
          <li><span>Clips par jour</span><b>40 max</b></li>
          <li><span>Arrêt après échecs d&apos;affilée</span><b>5</b></li>
          <li><span>Arrêt d&apos;urgence</span><b>fichier STOP</b></li>
          <li><span>Réglés dans</span><b>config.yaml</b></li>
        </ul>
      </Panel>
    </>
  );
}
