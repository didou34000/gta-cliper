import { Meter, PageHead, Panel, type Ctx } from "../ctx";
import { CHANNELS } from "@/lib/buffer";
import { mb } from "@/lib/format";
import { PLANS, type Usage } from "@/lib/usage";

const GB = 1024 ** 3;
const nf = (n: number, d = 0) => n.toLocaleString("fr-FR", { maximumFractionDigits: d, minimumFractionDigits: 0 });
const usd = (n: number) => (n < 0.01 && n > 0 ? `${nf(n * 100, 3)} ¢` : `${nf(n, 2)} $`);
const dt = (iso: string) => new Date(iso).toLocaleString("fr-FR", { timeZone: "Europe/Paris", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

type Row = { name: string; ok: boolean | null; detail: string; fix?: React.ReactNode };

function Src({ kind }: { kind: "mesuré" | "estimé" | "exact Cloudflare" }) {
  return <span className={`src src-${kind === "estimé" ? "est" : "mes"}`}>{kind}</span>;
}

export default function SettingsView({ ctx, usage }: { ctx: Ctx; usage: Usage }) {
  const { last, bytes, stats, schedule } = ctx;
  const u = usage;
  const botOk = last ? last.status !== "error" : null;

  // --- R2 : mesuré (bot + site), ou exact si Cloudflare répond -------------------------------
  const counted = { a: u.bot.a + u.site.a, b: u.bot.b + u.site.b };
  const r2 = u.cloudflare ?? counted;
  const r2Src = u.cloudflare ? "exact Cloudflare" : "mesuré";
  const frac = u.dayOfMonth / u.daysInMonth;
  // Projection fin de mois : rythme actuel du site + passages programmés au rythme réglé.
  const autoRunsLeft = schedule.enabled ? Math.round(((u.daysInMonth - u.dayOfMonth) * 24 * 60) / schedule.every_min) : 0;
  const projA = Math.round(r2.a / Math.max(frac, 1 / u.daysInMonth) + (u.perRun ? autoRunsLeft * u.perRun.a : 0));
  const projB = Math.round(r2.b / Math.max(frac, 1 / u.daysInMonth) + (u.perRun ? autoRunsLeft * u.perRun.b : 0));
  const projUsd = u.bot.usd / Math.max(frac, 1 / u.daysInMonth) + (u.perRun ? autoRunsLeft * u.perRun.usd : 0);
  const storage = u.cloudflare?.storageBytes ?? bytes;
  const scheduled = stats.connected && stats.ok ? stats.scheduled : null;

  const rows: Row[] = [
    { name: "Stockage Cloudflare R2", ok: ctx.configured, detail: ctx.configured ? "branché" : "clés R2_… manquantes sur Vercel (et sur GitHub pour le bot)" },
    {
      name: "Buffer (publication + stats)", ok: !stats.connected ? false : stats.ok,
      detail: !stats.connected ? "clé BUFFER_API_KEY manquante sur Vercel" : stats.ok ? `branché · ${stats.posts.length} posts lus` : `erreur : ${stats.error}`,
      fix: !stats.connected ? <a href="https://publish.buffer.com/settings/api" target="_blank" rel="noreferrer">Créer la clé</a> : undefined,
    },
    { name: "TikTok @gta6francenews", ok: !!CHANNELS.tiktok, detail: "via Buffer" },
    { name: "YouTube « GTA 6 FRANCE »", ok: !!CHANNELS.youtube, detail: "via Buffer" },
    { name: "Instagram", ok: CHANNELS.instagram ? true : null, detail: CHANNELS.instagram ? "via Buffer" : "pas branché · 1 place gratuite restante dans Buffer" },
    { name: "Bouton « Lancer » + suivi (GitHub)", ok: !!process.env.GH_DISPATCH_TOKEN, detail: process.env.GH_DISPATCH_TOKEN ? "branché" : "jeton GH_DISPATCH_TOKEN manquant sur Vercel" },
    { name: "Twitch + Claude (secrets GitHub)", ok: botOk, detail: botOk === null ? "pas encore vérifié : aucun passage" : botOk ? "OK au dernier passage du bot" : "le dernier passage a échoué, voir Suivi du bot" },
    {
      name: "Compteur exact Cloudflare (facultatif)", ok: u.cloudflare ? true : process.env.CF_API_TOKEN ? false : null,
      detail: u.cloudflare ? "branché : les chiffres R2 viennent de Cloudflare" : process.env.CF_API_TOKEN ? `erreur : ${u.cloudflareError}` : "jeton CF_API_TOKEN (Account Analytics : Read) absent : chiffres comptés par le bot et le site",
    },
  ];

  return (
    <>
      <PageHead title="Consommation & quotas" sub={`Mois en cours (${u.month}), jour ${u.dayOfMonth} sur ${u.daysInMonth}. Chaque chiffre dit s'il est mesuré ou estimé.`} />

      <Panel title="Par clip et par passage" sub="Moyennes mesurées sur les passages de ce mois">
        {u.perClip || u.perRun ? (
          <ul className="facts facts-cols">
            {u.perClip && <>
              <li><span>Coût Claude par clip</span><b>{usd(u.perClip.usd)}</b></li>
              <li><span>Opérations R2 par clip</span><b>{nf(u.perClip.a, 1)} A · {nf(u.perClip.b, 1)} B</b></li>
              <li><span>Temps de calcul par clip</span><b>{nf(u.perClip.minutes, 1)} min</b></li>
            </>}
            {u.perRun && <>
              <li><span>Coût Claude par passage</span><b>{usd(u.perRun.usd)}</b></li>
              <li><span>Opérations R2 par passage</span><b>{nf(u.perRun.a, 1)} A · {nf(u.perRun.b, 1)} B</b></li>
              <li><span>Durée moyenne d&apos;un passage</span><b>{nf(u.perRun.minutes, 1)} min</b></li>
            </>}
          </ul>
        ) : <p className="muted">Aucun passage mesuré ce mois-ci : les moyennes apparaîtront après le premier passage sur R2.</p>}
      </Panel>

      <div className="grid-2">
        <Panel title="Cloudflare R2 (stockage)" sub={PLANS.r2.name}>
          <div className="meters">
            <Meter label={<>Opérations A (envois, listages) · {nf(r2.a)} sur 1 million <Src kind={r2Src} /></>} value={r2.a} max={PLANS.r2.classA} />
            <Meter label={<>Opérations B (lectures) · {nf(r2.b)} sur 10 millions <Src kind={r2Src} /></>} value={r2.b} max={PLANS.r2.classB} tone="violet" />
            <Meter label={<>Stockage · {mb(storage)} sur 10 Go <Src kind={u.cloudflare?.storageBytes ? "exact Cloudflare" : "mesuré"} /></>} value={storage} max={PLANS.r2.storageGB * GB} />
          </div>
          <ul className="facts">
            <li><span>Dont bot ({u.runs.length} passage{u.runs.length > 1 ? "s" : ""})</span><b>{nf(u.bot.a)} A · {nf(u.bot.b)} B</b></li>
            <li><span>Dont site ({nf(u.site.pages)} ouverture{u.site.pages > 1 ? "s" : ""} de page)</span><b>{nf(u.site.a)} A · {nf(u.site.b)} B</b></li>
            <li><span>Fin de mois à ce rythme <Src kind="estimé" /></span><b>{nf(projA)} A ({nf((projA / PLANS.r2.classA) * 100, 2)} %) · {nf(projB)} B</b></li>
            <li><span>Suppressions</span><b>gratuites</b></li>
          </ul>
          <p className="muted small">Le compteur du site est envoyé toutes les 15 min : les dernières minutes peuvent manquer.</p>
        </Panel>

        <Panel title="Claude (titres, notes, moments)" sub={PLANS.claude.name}>
          <p className="big-num">{usd(u.bot.usd)}</p>
          <p className="muted small">Ce mois-ci <Src kind="mesuré" /> : {nf(u.bot.calls)} appel{u.bot.calls > 1 ? "s" : ""}, calculé avec les jetons réellement utilisés au tarif public (Haiku 5.5 : 0,10 $ / 0,50 $ par million de jetons).</p>
          <ul className="facts">
            <li><span>Fin de mois à ce rythme <Src kind="estimé" /></span><b>{usd(projUsd)}</b></li>
            <li><span>Garde-fou</span><b>{PLANS.claude.dailyCalls} appels par jour max</b></li>
            <li><span>Montant facturé réel</span><b><a href="https://console.anthropic.com/settings/usage" target="_blank" rel="noreferrer">console Anthropic</a></b></li>
          </ul>
        </Panel>

        <Panel title="GitHub Actions (le bot tourne ici)" sub={PLANS.github.name}>
          {u.github ? <>
            <p className="big-num">{nf(u.github.minutes)} min</p>
            <p className="muted small">{nf(u.github.runs)} exécution{u.github.runs > 1 ? "s" : ""} ce mois-ci <Src kind="mesuré" />, contrôles de programmation compris. Dépôt public : minutes illimitées et gratuites sur les machines standard.</p>
          </> : <p className="muted">Illisible : jeton GH_DISPATCH_TOKEN manquant sur Vercel.</p>}
        </Panel>

        <Panel title="Vercel (le site)" sub={PLANS.vercel.name}>
          <ul className="facts">
            <li><span>Ouvertures de page ce mois-ci <Src kind="mesuré" /></span><b>{nf(u.site.pages)}</b></li>
            <li><span>Appels de fonctions</span><b>1 million / mois inclus</b></li>
            <li><span>Données transférées</span><b>100 Go / mois inclus</b></li>
            <li><span>Temps de calcul actif</span><b>4 h / mois inclus</b></li>
          </ul>
          <p className="muted small">Les vidéos sont servies par Cloudflare, pas par Vercel. Vercel ne donne pas ces compteurs par API gratuite : chiffres exacts dans le tableau de bord Vercel, onglet Usage. À ce volume, on reste très loin des limites <Src kind="estimé" />.</p>
        </Panel>

        <Panel title="Buffer (publication)" sub={PLANS.buffer.name}>
          <div className="meters">
            {scheduled != null
              ? <Meter label={<>File d&apos;attente · {scheduled} posts programmés sur {PLANS.buffer.queuePerChannel} par réseau <Src kind="mesuré" /></>} value={scheduled} max={PLANS.buffer.queuePerChannel} tone="violet" />
              : <p className="muted small">File Buffer visible une fois la clé Buffer ajoutée.</p>}
          </div>
          <ul className="facts">
            <li><span>Réseaux branchés</span><b>{[CHANNELS.tiktok, CHANNELS.youtube, CHANNELS.instagram].filter(Boolean).length} sur {PLANS.buffer.channels}</b></li>
          </ul>
        </Panel>

        <Panel title="Twitch et YouTube" sub="Gratuits">
          <ul className="facts">
            <li><span>API Twitch</span><b>800 requêtes / minute, pas de quota mensuel</b></li>
            <li><span>YouTube (téléchargement)</span><b>pas de quota, mais blocages anti-robot possibles</b></li>
            <li><span>Transcription Whisper</span><b>sur GitHub, gratuite</b></li>
          </ul>
        </Panel>
      </div>

      <Panel title="Derniers passages" sub="Relevé exact écrit par le bot à la fin de chaque passage">
        {u.runs.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Quand</th><th>Type</th><th className="num">Clips</th><th className="num">Durée</th><th className="num">R2 A</th><th className="num">R2 B</th><th className="num">Appels Claude</th><th className="num">Coût Claude</th></tr></thead>
              <tbody>
                {u.runs.map((r, i) => (
                  <tr key={i}>
                    <td data-l="Quand">{dt(r.at)}{r.status === "error" ? " · échec" : ""}</td>
                    <td data-l="Type">{r.kind === "youtube" ? "lien YouTube" : "Twitch"}</td>
                    <td data-l="Clips" className="num">{r.clips}</td>
                    <td data-l="Durée" className="num">{nf(r.seconds / 60, 1)} min</td>
                    <td data-l="R2 A" className="num">{r.r2_a}</td>
                    <td data-l="R2 B" className="num">{r.r2_b}</td>
                    <td data-l="Claude" className="num">{r.llm_calls}</td>
                    <td data-l="Coût" className="num">{usd(r.llm_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="muted">Pas encore de passage enregistré ce mois-ci.</p>}
      </Panel>

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

      <Panel title="Garde-fous du bot">
        <ul className="facts facts-cols">
          <li><span>Appels Claude par jour</span><b>60 max</b></li>
          <li><span>Clips par passage</span><b>10 max</b></li>
          <li><span>Clips par jour</span><b>40 max</b></li>
          <li><span>Envois vers le stockage par jour</span><b>600 max</b></li>
          <li><span>Arrêt après échecs d&apos;affilée</span><b>5</b></li>
          <li><span>Statut du bot envoyé</span><b>toutes les 30 s max</b></li>
        </ul>
      </Panel>
    </>
  );
}
