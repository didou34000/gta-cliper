"""Interface web locale de validation humaine : regarder, corriger le titre, accepter ou rejeter."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, send_from_directory, url_for


def create_app(cfg: dict) -> Flask:
    app = Flask(__name__)
    paths = {k: Path(cfg["paths"][k]) for k in ("review", "approved", "rejected")}
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)

    def items(folder: Path) -> list[dict]:
        out = []
        for d in sorted(folder.iterdir(), reverse=True):
            mf = d / "meta.json"
            if mf.exists():
                m = json.loads(mf.read_text(encoding="utf-8"))
                m["_id"] = d.name
                out.append(m)
        return out

    @app.get("/")
    def index():
        tab = request.args.get("tab", "review")
        if tab not in paths:
            tab = "review"
        counts = {k: sum(1 for d in p.iterdir() if (d / "meta.json").exists())
                  for k, p in paths.items()}
        return render_template("review.html", items=items(paths[tab]), tab=tab, counts=counts)

    @app.get("/media/<tab>/<item>/<name>")
    def media_file(tab, item, name):
        if tab not in paths or name not in ("clip.mp4", "thumb.jpg"):
            abort(404)
        return send_from_directory(paths[tab].resolve() / item, name)

    @app.post("/decide/<item>")
    def decide(item):
        src = paths["review"] / item
        if not (src / "meta.json").exists():
            abort(404)
        m = json.loads((src / "meta.json").read_text(encoding="utf-8"))
        m["title"] = request.form.get("title", m["title"]).strip()
        m["description"] = request.form.get("description", m["description"]).strip()
        m["hashtags"] = [t if t.startswith("#") else f"#{t}"
                         for t in request.form.get("hashtags", "").split() if t]
        action = request.form.get("action")
        m["status"] = "approved" if action == "approve" else "rejected"
        m["decided_at"] = datetime.now(timezone.utc).isoformat()
        (src / "meta.json").write_text(json.dumps(m, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
        if action == "approve":
            # Texte prêt à copier-coller dans TikTok / Shorts / Reels
            (src / "post.txt").write_text(
                f"{m['title']}\n\n{m['description']}\n\n{' '.join(m['hashtags'])}\n",
                encoding="utf-8")
        dest = paths["approved" if action == "approve" else "rejected"] / item
        shutil.move(str(src), str(dest))
        return redirect(url_for("index"))

    return app
