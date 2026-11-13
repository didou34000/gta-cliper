import { PageHead, Panel, type Ctx } from "../ctx";
import { GAMES, REPO, STREAMERS } from "@/lib/launch";
import { bufferReady, publishEnabled } from "@/lib/buffer";
import { AUTO_OPTIONS, EVERY_OPTIONS, HOURS_OPTIONS, PUBLISH_OPTIONS, TOP_OPTIONS, VIEWS_OPTIONS } from "@/lib/schedule";
import { ago, fmtMin, hhmm } from "@/lib/format";

const VIEWS_HINT: Record<number, string> = { 200: " (conseillé)" };
const hoursLabel = (h: number) => (h < 24 ? `${h} dernières heures` : h === 24 ? "dernières 24 h" : h % 24 === 0 ? `${h / 24} derniers jours` : `${h} dernières heures`);

function Views({ value }: { value: number }) {
  return (
    <select name="min_views" defaultValue={String(value)} aria-label="Vues minimum">
      {VIEWS_OPTIONS.map((n) => <option key={n} value={n}>{n.toLocaleString("fr-FR")}{VIEWS_HINT[n] ?? ""}</option>)}
    </select>
  );
}
function Hours({ value }: { value: number }) {
  return (
    <select name="hours" defaultValue={String(value)} aria-label="Période">
      {HOURS_OPTIONS.map((n) => <option key={n} value={n}>{hoursLabel(n)}</option>)}
    </select>
  );
}
function Top({ value }: { value: number }) {
  return (
    <select name="top" defaultValue={String(value)} aria-label="Nombre de streamers">
      {TOP_OPTIONS.map((n) => <option key={n} value={n}>{n}</option>)}
    </select>
  );
}
function Count({ name, value, max }: { name: string; value: number; max: number }) {
  return (
    <select name={name} defaultValue={String(value)} aria-label="Nombre de clips">
      {Array.from({ length: max }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}</option>)}
    </select>
  );
}
function Game({ value }: { value?: string }) {
  const known = !value || GAMES.includes(value);
  return (
    <select name="jeu" defaultValue={known ? (value ?? GAMES[0]) : GAMES[0]} aria-label="Jeu">
      {GAMES.map((g) => <option key={g} value={g}>{g === "tous" ? "n'importe quel jeu" : g}</option>)}
    </select>
  );
}
function OtherGame({ value }: { value?: string }) {
  const known = !value || GAMES.includes(value);
  return (
    <p className="sentence">Autre jeu (nom exact sur Twitch) : <input name="jeu_autre" placeholder="ex. Minecraft" maxLength={80} defaultValue={known ? "" : value} aria-label="Autre jeu" /></p>
  );
}

export default async function ProgView({ ctx, launch, prog, yt }: { ctx: Ctx; launch?: string; prog?: string; yt?: string }) {
  const { schedule, state, lastRun, nextRun } = ctx;
  const pubOn = bufferReady() && (await publishEnabled());
  const busy = state.key === "running";
  const err = launch ?? yt;

  return (
    <>
      <PageHead title="Lancer le bot" sub="Choisis ce que le bot doit clipper. Tu suis ensuite chaque étape en direct, en haut de l'écran." />

      {err && err !== "ok" && (
        <p className="banner">
          {err === "badurl" && <>Ce lien n&apos;est pas une vidéo YouTube (format attendu : youtube.com/watch?v=… ou youtu.be/…).</>}
          {err === "notoken" && <>Bouton pas encore branché : il manque le jeton GitHub GH_DISPATCH_TOKEN sur Vercel.</>}
          {err === "nostreamer" && <>Choisis au moins un streamer.</>}
          {err.startsWith("error") && <>GitHub a refusé le lancement (code {err.slice(5)}). Le jeton est peut-être expiré ou sans le droit « Actions ». <a href={`https://github.com/${REPO}/actions`} target="_blank" rel="noreferrer">Voir GitHub</a></>}
        </p>
      )}
      {prog === "ok" && <p className="banner banner-ok">Réglage enregistré.</p>}

      <div className="launch-grid">
        <Panel title={<><span className="step-n">A</span> Une vidéo YouTube</>} className="launch">
          <form method="post" action="/api/youtube" className="stack">
            <p className="muted">Colle le lien d&apos;une vidéo longue : le bot l&apos;écoute en entier et garde les meilleurs moments (20 à 60 s), comme Opus Clip.</p>
            <input name="url" type="url" required placeholder="https://www.youtube.com/watch?v=…" maxLength={300} className="big-input" aria-label="Lien YouTube" />
            <p className="sentence">Sortir <Count name="clips" value={3} max={8} /> clips de cette vidéo.</p>
            <details className="opts">
              <summary>Options</summary>
              <p className="sentence">Jeu de la vidéo : <Game /></p>
              <OtherGame />
              <p className="sentence">Nom dans les titres : <input name="streamer" placeholder="nom de la chaîne" maxLength={40} aria-label="Nom dans les titres" /></p>
            </details>
            <button type="submit" className="btn-primary" disabled={busy}>{busy ? "Le bot est occupé, attends la fin" : "Clipper la vidéo"}</button>
            <p className="muted small">Compte 5 à 15 min pour 1 h de vidéo. YouTube bloque parfois les serveurs : le suivi te le dira.</p>
          </form>
        </Panel>

        <Panel title={<><span className="step-n">B</span> Les clips Twitch du moment</>} className="launch">
          <form method="post" action="/api/launch" className="stack">
            <p className="sentence">
              Regarder les clips des <Top value={8} /> plus gros streamers FR sur <Game />,
              créés ces <Hours value={48} />, vus au moins <Views value={200} /> fois,
              et monter les <Count name="max_clips" value={3} max={10} /> meilleurs.
            </p>
            <details className="opts" open={launch === "nostreamer"}>
              <summary>Autre jeu, ou choisir les streamers moi-même</summary>
              <OtherGame />
              <div className="checks">
                {STREAMERS.map((s) => (
                  <label key={s.login}><input type="checkbox" name="streamer" value={s.login} /> {s.name}</label>
                ))}
              </div>
              <input name="streamers_autres" placeholder="autres logins Twitch, séparés par des virgules" maxLength={400} />
            </details>
            <button type="submit" className="btn-primary" disabled={busy}>{busy ? "Un passage est déjà en cours" : "Lancer la recherche"}</button>
            <details className="opts">
              <summary>Comment le bot choisit</summary>
              <ol className="how">
                <li>Il prend les clips les plus vus de chaque streamer sur la période.</li>
                <li>Il écarte les clips de moins de 20 s, les doublons et ceux déjà faits.</li>
                <li>Claude note chaque clip sur 10 en regardant l&apos;image et le titre.</li>
                <li>Il monte les meilleurs (2 par streamer maximum), avec sous-titres et titre.</li>
              </ol>
            </details>
          </form>
        </Panel>
      </div>

      <Panel
        title={<><span className="step-n">C</span> Mode automatique</>}
        action={<span className={`tag ${schedule.enabled ? "tag-auto" : "tag-off"}`}>{schedule.enabled ? "allumé" : "éteint"}</span>}
      >
        <form method="post" action="/api/schedule" className="stack">
          <input type="hidden" name="section" value="auto" />
          <p className="muted small">
            {schedule.enabled ? (nextRun ? `Prochain passage vers ${hhmm(nextRun.toISOString())}.` : "") : "Le bot ne tourne que quand tu le lances."}
            {lastRun ? ` Dernier passage automatique ${ago(lastRun)}.` : ""}
          </p>
          <p className="sentence">
            Toutes les <select name="every_min" defaultValue={String(schedule.every_min)} aria-label="Fréquence">
              {EVERY_OPTIONS.map((n) => <option key={n} value={n}>{fmtMin(n)}</option>)}
            </select>, regarder les clips des <Top value={schedule.top} /> plus gros streamers FR sur <Game value={schedule.game} />,
            créés ces <Hours value={schedule.hours} />, vus au moins <Views value={schedule.min_views} /> fois,
            et monter les <Count name="max_clips" value={schedule.max_clips} max={10} /> meilleurs.
          </p>
          <details className="opts"><summary>Autre jeu</summary><OtherGame value={schedule.game} /></details>
          <div className="row">
            <label className="switch"><input type="checkbox" name="enabled" defaultChecked={schedule.enabled} /> <span>Allumer le mode automatique</span></label>
            <button type="submit" className="btn-primary">Enregistrer</button>
          </div>
        </form>
      </Panel>

      <Panel
        title={<><span className="step-n">D</span> Validation et publication</>}
        action={<span className={`tag ${pubOn ? "tag-auto" : "tag-off"}`}>{pubOn ? "publication allumée" : "publication coupée"}</span>}
      >
        <form method="post" action="/api/schedule" className="stack">
          <input type="hidden" name="section" value="publish" />
          <p className="sentence">
            Valider tout seul un clip noté <select name="auto_min" defaultValue={String(schedule.auto_min)} aria-label="Validation automatique">
              {AUTO_OPTIONS.map((n) => <option key={n} value={n}>{n ? `${n}/10 ou plus` : "jamais (je valide tout)"}</option>)}
            </select>, puis publier un clip validé toutes les <select name="publish_every_min" defaultValue={String(schedule.publish_every_min)} aria-label="Rythme de publication">
              {PUBLISH_OPTIONS.map((n) => <option key={n} value={n}>{fmtMin(n)}</option>)}
            </select>.
          </p>
          <p className="muted small">Un clip dont le titre est marqué « peu sûr » reste toujours en validation manuelle.</p>
          <div className="row"><button type="submit" className="btn-ghost">Enregistrer</button></div>
        </form>
        <form method="post" action="/api/publish-toggle" className="row pub-row">
          <span className={pubOn ? "" : "muted"}>
            {!bufferReady() ? "Clé Buffer manquante sur Vercel : rien ne peut partir."
              : pubOn ? "🟢 Les clips « À poster » partent tout seuls sur TikTok et YouTube."
              : "⚪ Rien ne part : les clips validés attendent dans « À poster »."}
          </span>
          {bufferReady() && (
            <button type="submit" name="enabled" value={pubOn ? "off" : "on"} className={pubOn ? "btn-ghost" : "btn-primary"}>
              {pubOn ? "Couper la publication" : "Allumer la publication"}
            </button>
          )}
        </form>
      </Panel>
    </>
  );
}
