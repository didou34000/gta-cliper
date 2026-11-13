import { PageHead, Panel, type Ctx } from "../ctx";
import { GAMES, REPO, STREAMERS } from "@/lib/launch";
import { bufferReady, publishEnabled } from "@/lib/buffer";
import { AUTO_OPTIONS, EVERY_OPTIONS, HOURS_OPTIONS, PUBLISH_OPTIONS, TOP_OPTIONS, VIEWS_OPTIONS } from "@/lib/schedule";
import { ago, fmtHours, fmtMin, hhmm } from "@/lib/format";

function ViewsSelect({ value }: { value: number }) {
  return (
    <select name="min_views" defaultValue={String(value)}>
      {VIEWS_OPTIONS.map((n) => <option key={n} value={n}>{n.toLocaleString("fr-FR")} vues</option>)}
    </select>
  );
}

function HoursSelect({ value }: { value: number }) {
  return (
    <select name="hours" defaultValue={String(value)}>
      {HOURS_OPTIONS.map((n) => <option key={n} value={n}>{fmtHours(n)}</option>)}
    </select>
  );
}

function GameSelect({ value }: { value?: string }) {
  const known = !value || GAMES.includes(value);
  return (
    <>
      <select name="jeu" defaultValue={known ? (value ?? GAMES[0]) : GAMES[0]}>
        {GAMES.map((g) => <option key={g} value={g}>{g === "tous" ? "Tous les jeux" : g}</option>)}
      </select>
      <input name="jeu_autre" placeholder="ou un autre jeu (nom exact sur Twitch)" maxLength={80} defaultValue={known ? "" : value} />
    </>
  );
}

export default async function ProgView({ ctx, launch, prog, yt }: { ctx: Ctx; launch?: string; prog?: string; yt?: string }) {
  const { schedule, state, lastRun, nextRun } = ctx;
  const pubOn = bufferReady() && (await publishEnabled());

  return (
    <>
      <PageHead title="Programmation" sub="Lance un passage tout de suite, ou laisse le bot tourner tout seul à intervalle régulier." />

      {launch && (
        <p className={`banner ${launch === "ok" ? "banner-ok" : ""}`}>
          {launch === "ok" && <>Passage lancé. Le bot démarre dans 1 à 2 minutes : suis-le dans <a href="/?v=bot">Bot en direct</a>. <a href={`https://github.com/${REPO}/actions`} target="_blank" rel="noreferrer">Voir sur GitHub</a></>}
          {launch === "notoken" && <>Bouton pas encore branché : il manque le jeton GitHub GH_DISPATCH_TOKEN sur Vercel.</>}
          {launch === "nostreamer" && <>Choisis au moins un streamer.</>}
          {launch.startsWith("error") && <>GitHub a refusé le lancement (code {launch.slice(5)}). Le jeton est peut-être expiré ou sans le droit « Actions ».</>}
        </p>
      )}
      {yt && (
        <p className={`banner ${yt === "ok" ? "banner-ok" : ""}`}>
          {yt === "ok" && <>Vidéo envoyée au bot. Il démarre dans 1 à 2 minutes ; compte 5 à 15 min pour 1 h de vidéo. Suis-le dans <a href="/?v=bot">Bot en direct</a>.</>}
          {yt === "badurl" && <>Ce lien n&apos;est pas une vidéo YouTube (format attendu : youtube.com/watch?v=… ou youtu.be/…).</>}
          {yt === "notoken" && <>Bouton pas encore branché : il manque le jeton GitHub GH_DISPATCH_TOKEN sur Vercel.</>}
          {yt.startsWith("error") && <>GitHub a refusé le lancement (code {yt.slice(5)}).</>}
        </p>
      )}
      {prog === "ok" && <p className="banner banner-ok">Réglage enregistré. Il est pris en compte au prochain contrôle (toutes les 20 min).</p>}

      <Panel title="Publication sur TikTok et YouTube">
        <form method="post" action="/api/publish-toggle" className="form-grid">
          <fieldset>
            <legend>Publication auto via Buffer</legend>
            <span className={pubOn ? "" : "muted"}>
              {!bufferReady() ? "Clé Buffer manquante sur Vercel : rien ne peut partir."
                : pubOn ? `🟢 Allumée : les clips « À poster » partent tout seuls, un toutes les ${fmtMin(schedule.publish_every_min)}.`
                : "⚪ Coupée : rien ne part, les clips validés attendent dans « À poster »."}
            </span>
          </fieldset>
          {bufferReady() && (
            <button type="submit" name="enabled" value={pubOn ? "off" : "on"} className={pubOn ? "btn ghost" : "btn-launch"}>
              {pubOn ? "Couper la publication" : "Allumer la publication"}
            </button>
          )}
        </form>
      </Panel>

      <Panel title="Clipper une vidéo YouTube">
        <form method="post" action="/api/youtube" className="form-grid">
          <fieldset className="wide">
            <legend>Lien de la vidéo</legend>
            <input name="url" type="url" required placeholder="https://www.youtube.com/watch?v=…" maxLength={300} />
            <span className="muted small">Le bot écoute toute la vidéo, repère les meilleurs moments (transcription + pics de volume) et en fait des clips 9:16 sous-titrés, comme Opus Clip.</span>
          </fieldset>
          <fieldset>
            <legend>Clips à sortir</legend>
            <input type="number" name="clips" min={1} max={8} defaultValue={3} />
          </fieldset>
          <fieldset>
            <legend>Jeu de la vidéo</legend>
            <GameSelect />
          </fieldset>
          <fieldset>
            <legend>Nom dans les titres</legend>
            <input name="streamer" placeholder="vide = nom de la chaîne" maxLength={40} />
          </fieldset>
          <button type="submit" className="btn-primary" disabled={state.key === "running"}>
            {state.key === "running" ? "Le bot est déjà occupé" : "Clipper"}
          </button>
        </form>
      </Panel>

      <Panel title="Lancer un passage maintenant">
        <form method="post" action="/api/launch" className="form-grid">
          <fieldset>
            <legend>Jeu</legend>
            <GameSelect />
          </fieldset>
          <fieldset>
            <legend>Streamers</legend>
            <select name="top" defaultValue="8">
              {TOP_OPTIONS.map((n) => <option key={n} value={n}>Les {n} plus gros streamers FR du jeu</option>)}
            </select>
          </fieldset>
          <fieldset>
            <legend>Clips max</legend>
            <input type="number" name="max_clips" min={1} max={10} defaultValue={3} />
          </fieldset>
          <fieldset>
            <legend>Vues minimum par clip</legend>
            <ViewsSelect value={200} />
          </fieldset>
          <fieldset>
            <legend>Clips créés dans les</legend>
            <HoursSelect value={48} />
          </fieldset>
          <button type="submit" className="btn-primary" disabled={state.key === "running"}>
            {state.key === "running" ? "Un passage est déjà en cours" : "Lancer"}
          </button>
          <details className="wide manual" open={launch === "nostreamer"}>
            <summary>ou choisir les streamers à la main</summary>
            <div className="checks">
              {STREAMERS.map((s) => (
                <label key={s.login}><input type="checkbox" name="streamer" value={s.login} /> {s.name}</label>
              ))}
            </div>
            <input name="streamers_autres" placeholder="autres logins Twitch, séparés par des virgules" maxLength={400} />
          </details>
        </form>
      </Panel>

      <Panel
        title="Passages automatiques"
        action={<span className={`tag ${schedule.enabled ? "tag-auto" : "tag-off"}`}>{schedule.enabled ? "active" : "arrêtée"}</span>}
      >
        <p className="muted small">
          {nextRun ? `Prochain passage vers ${hhmm(nextRun.toISOString())}` : "Aucun passage automatique"}
          {lastRun ? ` · dernier ${ago(lastRun)}` : ""}
        </p>
        <form method="post" action="/api/schedule" className="form-grid">
          <fieldset>
            <legend>Jeu</legend>
            <GameSelect value={schedule.game} />
          </fieldset>
          <fieldset>
            <legend>Streamers</legend>
            <select name="top" defaultValue={String(schedule.top)}>
              {TOP_OPTIONS.map((n) => <option key={n} value={n}>Les {n} plus gros FR</option>)}
            </select>
          </fieldset>
          <fieldset>
            <legend>Un passage toutes les</legend>
            <select name="every_min" defaultValue={String(schedule.every_min)}>
              {EVERY_OPTIONS.map((n) => <option key={n} value={n}>{fmtMin(n)}</option>)}
            </select>
          </fieldset>
          <fieldset>
            <legend>Clips max par passage</legend>
            <input type="number" name="max_clips" min={1} max={10} defaultValue={schedule.max_clips} />
          </fieldset>
          <fieldset>
            <legend>Vues minimum par clip</legend>
            <ViewsSelect value={schedule.min_views} />
          </fieldset>
          <fieldset>
            <legend>Clips créés dans les</legend>
            <HoursSelect value={schedule.hours} />
          </fieldset>
          <fieldset>
            <legend>Publier un clip toutes les</legend>
            <select name="publish_every_min" defaultValue={String(schedule.publish_every_min)}>
              {PUBLISH_OPTIONS.map((n) => <option key={n} value={n}>{fmtMin(n)}</option>)}
            </select>
            <span className="muted small">{pubOn
              ? "Chaque clip validé part tout seul via Buffer, espacé de ce délai (10 programmés max)."
              : bufferReady() ? "Utilisé quand la publication auto est allumée (en haut de la page)."
              : "Publication auto pas encore branchée (clé Buffer manquante)."}</span>
          </fieldset>
          <fieldset>
            <legend>Validation automatique</legend>
            <select name="auto_min" defaultValue={String(schedule.auto_min)}>
              {AUTO_OPTIONS.map((n) => <option key={n} value={n}>{n ? `Si potentiel ≥ ${n}/10` : "Non, je valide tout à la main"}</option>)}
            </select>
            <span className="muted small">Un clip noté au-dessus du seuil (et au titre sûr) passe tout seul « À poster ».</span>
          </fieldset>
          <fieldset>
            <legend>État</legend>
            <label className="toggle"><input type="checkbox" name="enabled" defaultChecked={schedule.enabled} /> Programmation active</label>
          </fieldset>
          <button type="submit" className="btn-primary">Enregistrer</button>
        </form>
      </Panel>
    </>
  );
}
