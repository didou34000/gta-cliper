"""Client minimal pour Cloudflare R2 (API compatible S3), bibliothèque standard uniquement.

Utilisé par le bot et par le petit script de planification (qui tourne avant
l'installation des dépendances). Signature AWS SigV4, région « auto ».
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

VARS = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_PUBLIC_URL")
NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


class R2Error(RuntimeError):
    pass


def configured() -> bool:
    return all(os.environ.get(k) for k in VARS)


def bucket() -> str:
    return os.environ.get("R2_BUCKET") or "gta-clipper"


def public_url(key: str = "") -> str:
    base = os.environ["R2_PUBLIC_URL"].rstrip("/")
    return f"{base}/{key}" if key else base


def _endpoint() -> tuple[str, str]:
    """(schéma, hôte). R2_ENDPOINT ne sert qu'aux tests (serveur S3 local)."""
    ep = os.environ.get("R2_ENDPOINT")
    if ep:
        u = urllib.parse.urlparse(ep)
        return u.scheme, u.netloc
    return "https", f"{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def request(method: str, key: str = "", query: dict | None = None, body: bytes = b"",
            headers: dict | None = None, timeout: int = 300) -> bytes:
    scheme, host = _endpoint()
    path = "/" + bucket() + ("/" + urllib.parse.quote(key, safe="/-_.~") if key else "")
    q = sorted((query or {}).items())
    qs = "&".join(f"{urllib.parse.quote(str(k), safe='-_.~')}={urllib.parse.quote(str(v), safe='-_.~')}"
                  for k, v in q)
    now = datetime.now(timezone.utc)
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    h = {"host": host, "x-amz-date": amz_date, "x-amz-content-sha256": payload_hash,
         **{k.lower(): str(v) for k, v in (headers or {}).items()}}
    signed = ";".join(sorted(h))
    canonical = "\n".join([method, path, qs,
                           "".join(f"{k}:{h[k].strip()}\n" for k in sorted(h)),
                           signed, payload_hash])
    scope = f"{day}/auto/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                         hashlib.sha256(canonical.encode()).hexdigest()])
    k = _sign(("AWS4" + os.environ["R2_SECRET_ACCESS_KEY"]).encode(), day)
    for part in ("auto", "s3", "aws4_request"):
        k = _sign(k, part)
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    h["authorization"] = (f"AWS4-HMAC-SHA256 Credential={os.environ['R2_ACCESS_KEY_ID']}/{scope}, "
                          f"SignedHeaders={signed}, Signature={sig}")
    url = f"{scheme}://{host}{path}" + (f"?{qs}" if qs else "")
    last = ""
    # Classes de facturation R2 : A = écriture/listage, B = lecture, DELETE = gratuit.
    op_class = ("" if method == "DELETE" else
                "B" if method in ("GET", "HEAD") and "list-type" not in (query or {}) else "A")
    for attempt in range(4):
        try:
            from . import usage
            if op_class:
                usage.r2(op_class)  # chaque tentative compte chez Cloudflare
        except ImportError:
            pass
        req = urllib.request.Request(url, data=body if method in ("PUT", "POST") else None,
                                     method=method, headers={k: v for k, v in h.items() if k != "host"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404 and method == "DELETE":
                return b""
            if e.code == 404 and method == "GET":
                raise FileNotFoundError(key) from e
            last = f"HTTP {e.code} : {e.read()[:300].decode(errors='replace')}"
            if e.code < 500 and e.code != 429:
                break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = str(e)
        time.sleep(2 ** attempt)
    raise R2Error(f"R2 {method} {key or '(liste)'} : {last}")


def put(key: str, data: bytes, content_type: str, cache_control: str = "no-cache") -> None:
    request("PUT", key, body=data, headers={"content-type": content_type,
                                            "cache-control": cache_control})


def get(key: str) -> bytes | None:
    """Lecture directe (classe B, pas de cache). None si le fichier n'existe pas."""
    try:
        return request("GET", key, timeout=30)
    except FileNotFoundError:
        return None


def list_objects(prefix: str) -> list[dict]:
    """Renvoie [{pathname, url, size, uploadedAt}] (même forme que l'ancien Vercel Blob)."""
    out, token = [], None
    for _ in range(50):
        q = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            q["continuation-token"] = token
        root = ET.fromstring(request("GET", query=q, timeout=30))
        for c in root.iter(f"{NS}Contents"):
            key = c.findtext(f"{NS}Key")
            out.append({"pathname": key, "url": public_url(key),
                        "size": int(c.findtext(f"{NS}Size") or 0),
                        "uploadedAt": c.findtext(f"{NS}LastModified")})
        token = root.findtext(f"{NS}NextContinuationToken")
        if root.findtext(f"{NS}IsTruncated") != "true" or not token:
            break
    return out


def delete(keys: list[str]) -> None:
    """Suppression une par une : DeleteObject est gratuit chez Cloudflare R2."""
    for k in keys:
        request("DELETE", k, timeout=30)
