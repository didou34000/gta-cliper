import { PageHead, Panel, type Ctx } from "../ctx";
import type { Clip } from "@/lib/data";
import { LANG_LABEL, norm, type LivesResult, type Stream } from "@/lib/twitch";
import { compact, hhmm } from "@/lib/format";

const JEUX: { key: string; label: string; game?: string }[] = [
  { key: "tous", label: "Tous les GTA" },
  { key: "vi", label: "GTA VI", game: "Grand Theft Auto VI" },
  { key: "v", label: "GTA V", game: "Grand Theft Auto V" },
];

function uptime(iso: string) {
  const m = Math.max(0, Math.round((Date.now() - +new Date(iso)) / 60000));
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}`;
}

const langName = (l: string) => LANG_LABEL[l] ?? l.toUpperCase();

export default function LivesView({ ctx, lives, jeu, lang, q }: { ctx: Ctx; lives: LivesResult; jeu?: string; lang?: string; q?: string }) {
  const j = JEUX.find((x) => x.key === jeu) ?? JEUX[0];
  const query = (q ?? "").trim().toLowerCase();

  // Clips déjà faits par le bot, par streamer.
  const byStreamer = new Map<string, Clip[]>();
  for (const c of ctx.clips) {
    if (!c.streamer || c.status === "rejected") continue;
    const k = norm(c.streamer);
    byStreamer.set(k, [...(byStreamer.get(k) ?? []), c]);
  }
  for (const list of byStreamer.values()) list.sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at));
  const clipsOf = (s: Stream) => byStreamer.get(norm(s.login)) ?? byStreamer.get(norm(s.name)) ?? [];

  const inGame = lives.streams.filter((s) => !j.game || s.game === j.game);
  const shown = inGame.filter((s) => !query || s.name.toLowerCase().includes(query) || s.login.includes(query) || s.title.toLowerCase().includes(query));
  const viewers = inGame.reduce((n, s) => n + s.viewers, 0);
  const vi = lives.streams.filter((s) => s.game === "Grand Theft Auto VI");

  // Langues présentes (sur l'ensemble chargé quand aucun filtre langue n'est actif).
  const langs = new Map<string, { n: number; v: number }>();
  for (const s of inGame) {
    const x = langs.get(s.lang) ?? { n: 0, v: 0 };
    langs.set(s.lang, { n: x.n + 1, v: x.v + s.viewers });
  }
  const langList = [...langs.entries()].sort((a, b) => b[1].v - a[1].v);
  if (lang && !langs.has(lang)) langList.unshift([lang, { n: 0, v: 0 }]);

  const href = (p: { jeu?: string; lang?: string | null; q?: string | null }) => {
    const u = new URLSearchParams({ v: "lives" });
    const jj = p.jeu ?? j.key; if (jj !== "tous") u.set("jeu", jj);
    const ll = p.lang === null ? undefined : p.lang ?? lang; if (ll) u.set("lang", ll);
    const qq = p.q === null ? undefined : p.q ?? q; if (qq) u.set("q", qq);
    return `/?${u}`;
  };

  return (
    <>
      <PageHead
        title="Lives GTA"
        sub={<>Tous les lives GTA du monde en ce moment, d&apos;après Twitch · mis à jour à {hhmm(lives.fetched_at)} · lecture seule, rien n&apos;est clippé ni stocké</>}
      >
        <a href={href({})} className="btn-primary">↻ Rafraîchir</a>
      </PageHead>

      {!lives.configured && (
        <Panel title="Twitch pas encore branché sur le site">
          <p>Il manque une seule variable sur Vercel : <code>TWITCH_CLIENT_SECRET</code> (la même que dans les secrets GitHub du bot).</p>
          <p className="muted small">Vercel → projet gta-clipper → Settings → Environment Variables → ajouter <code>TWITCH_CLIENT_SECRET</code> (Production), puis redéployer.</p>
        </Panel>
      )}
      {lives.configured && !lives.ok && <p className="banner">Twitch a répondu une erreur : {lives.error}. Réessaie dans une minute.</p>}

      {lives.ok && (
        <>
          <div className="kpis">
            <div className="kpi kpi-pink"><span className="kpi-label">Lives {j.key === "tous" ? "GTA" : j.label}{lang ? ` en ${langName(lang).toLowerCase()}` : ""}</span>
              <span className="kpi-value">{inGame.length.toLocaleString("fr-FR")}{lives.truncated ? "+" : ""}</span>
              <span className="kpi-hint">{lives.truncated ? "les 1000 plus gros affichés" : "tous les lives en cours"}</span></div>
            <div className="kpi"><span className="kpi-label">Viewers au total</span><span className="kpi-value">{compact(viewers)}</span>
              <span className="kpi-hint">sur ces lives</span></div>
            <div className="kpi kpi-violet"><span className="kpi-label">Sur GTA VI</span><span className="kpi-value">{vi.length}</span>
              <span className="kpi-hint">{vi.length ? `${compact(vi.reduce((n, s) => n + s.viewers, 0))} viewers` : "sortie le 19 nov. (NZ le 18 à midi, heure de Paris)"}</span></div>
            <div className="kpi"><span className="kpi-label">Déjà clippés par le bot</span>
              <span className="kpi-value">{inGame.filter((s) => clipsOf(s).length).length}</span>
              <span className="kpi-hint">streamers en live avec au moins un clip</span></div>
          </div>

          <div className="lv-filters">
            <div className="lv-tabs" role="tablist" aria-label="Jeu">
              {JEUX.map((x) => (
                <a key={x.key} href={href({ jeu: x.key })} className={x.key === j.key ? "on" : ""} aria-current={x.key === j.key ? "page" : undefined}>{x.label}</a>
              ))}
            </div>
            <form method="get" action="/" className="lv-search">
              <input type="hidden" name="v" value="lives" />
              {j.key !== "tous" && <input type="hidden" name="jeu" value={j.key} />}
              {lang && <input type="hidden" name="lang" value={lang} />}
              <input name="q" defaultValue={q} placeholder="Chercher un streamer ou un titre" aria-label="Chercher" />
            </form>
          </div>

          <div className="lv-langs" aria-label="Langue">
            <a href={href({ lang: null })} className={!lang ? "on" : ""}>Toutes les langues</a>
            {langList.map(([l, x]) => (
              <a key={l} href={href({ lang: l })} className={l === lang ? "on" : ""}>
                {langName(l)} {!lang && <small>{x.n} · {compact(x.v)}</small>}
              </a>
            ))}
          </div>

          {!shown.length ? (
            <Panel><p className="muted">Aucun live ne correspond{query ? ` à « ${q} »` : ""}.</p></Panel>
          ) : (
            <div className="lv-grid">
              {shown.map((s, i) => {
                const clips = clipsOf(s);
                return (
                  <article key={s.login} className="lv-card">
                    <a href={`https://www.twitch.tv/${s.login}`} target="_blank" rel="noreferrer" className="lv-thumb"
                      style={{ backgroundImage: `url(${s.thumb})` }} aria-label={`Ouvrir le live de ${s.name} sur Twitch`}>
                      <span className="lv-live">LIVE</span>
                      <span className="lv-rank">#{i + 1}</span>
                      <span className="lv-viewers">● {s.viewers.toLocaleString("fr-FR")}</span>
                      <span className="lv-up">{uptime(s.started_at)}</span>
                    </a>
                    <div className="lv-body">
                      <p className="lv-name">
                        <a href={`https://www.twitch.tv/${s.login}`} target="_blank" rel="noreferrer">{s.name}</a>
                        <span className="lv-lang" title={langName(s.lang)}>{s.lang.toUpperCase()}</span>
                        <span className={`lv-game ${s.game === "Grand Theft Auto VI" ? "vi" : ""}`}>{s.game === "Grand Theft Auto VI" ? "GTA VI" : "GTA V"}</span>
                      </p>
                      <p className="lv-title" title={s.title}>{s.title}</p>
                      {clips.length > 0 ? (
                        <div className="lv-clips">
                          <span className="lv-clips-n">✂ {clips.length} clip{clips.length > 1 ? "s" : ""} du bot</span>
                          {clips.slice(0, 3).map((c) => (
                            <a key={c.id} href={c.video_url ?? c.source_url ?? "#"} target="_blank" rel="noreferrer" title={c.title}
                              className={`lv-clip st-${c.status}`}>{c.title}</a>
                          ))}
                          {clips.length > 3 && <a href="/?v=valider" className="lv-more">+ {clips.length - 3} autres</a>}
                        </div>
                      ) : <p className="lv-noclip">Pas encore de clip du bot</p>}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </>
      )}
    </>
  );
}
