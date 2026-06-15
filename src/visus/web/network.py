"""Network traffic capture for visus-web pages.

Two complementary layers feed a single, scrubbed request list:

1. **JS hook** — patches ``fetch``, ``XMLHttpRequest``, ``navigator.sendBeacon``
   and dynamically-inserted ``<script>``/``<img>`` ``src`` (JSONP / pixel pings)
   so same-origin response bodies and request bodies are recorded in
   ``window.__vcm_capture``. Installed before any interaction.
2. **CDP performance log** — when ``use_cdp`` is on and the page is driven by a
   Chromium engine launched with performance logging (visus-web enables this by
   default), :meth:`NetworkCapture.get_requests` drains Chrome's performance log
   and correlates ``Network.requestWillBeSent`` / ``responseReceived`` /
   ``loadingFinished`` events. This catches everything the browser does at the
   network layer — JSONP ``<script>``, ``sendBeacon``, images, fonts and
   top-level document navigations — that the fetch/XHR patch alone cannot see.

The two layers are merged and de-duplicated on ``(method, url)``; the JS hook's
readable response body wins, CDP fills in status, resource type and request
headers (auth/cookies), which are then scrubbed at read time.

The JS expressions are written as zero-argument arrow functions because the
visus-web :meth:`Page.evaluate` contract wraps the expression as
``(<expression>)(arg)`` before executing it in the page.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

_SECRET_HEADERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "proxy-authorization",
    "x-api-key",
    "x-auth-token",
    "x-session-id",
}
_SECRET_HEADER_RE = re.compile(r"^x-.*-(token|key|auth|session|secret)$", re.IGNORECASE)


def scrub_headers(h: dict) -> dict:  # type: ignore[type-arg]
    """Return a copy of *h* with secret headers redacted to ``"REDACTED"``."""
    out: dict[str, Any] = {}
    for k, v in h.items():
        if str(k).lower() in _SECRET_HEADERS or _SECRET_HEADER_RE.match(str(k)):
            out[k] = "REDACTED"
        else:
            out[k] = v
    return out


# Zero-arg arrow function: visus-web Page.evaluate wraps as ``(<expr>)(arg)``,
# so this installs the hook once and returns True. Beyond fetch/XHR it also
# intercepts sendBeacon and dynamically-set <script>/<img> src (JSONP / pings),
# which never go through fetch/XHR; cross-origin response bodies for those are
# opaque to JS, so only the request side is recorded (the CDP layer fills in the
# rest). Each entry carries a ``resourceType`` so callers can filter by kind.
_HOOK_JS = r"""() => {
  if (window.__vcm_installed) return true;
  window.__vcm_installed = true;
  window.__vcm_capture = [];
  const push = (e) => { try { window.__vcm_capture.push(e); } catch (_) {} };
  const _f = window.fetch;
  if (_f) window.fetch = async (...a) => {
    const res = await _f(...a);
    try {
      const clone = res.clone();
      push({url: res.url, method: (a[1]&&a[1].method)||'GET', status: res.status,
            reqBody: (a[1]&&a[1].body)||null, respBody: await clone.text(),
            headers: Object.fromEntries(res.headers.entries()), resourceType: 'fetch'});
    } catch (_) {}
    return res;
  };
  const _open = XMLHttpRequest.prototype.open;
  const _send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m, u){
    this.__vcm = {m, u}; return _open.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function(b){
    this.addEventListener('load', () => push({url: (this.__vcm&&this.__vcm.u)||this.responseURL,
      method: (this.__vcm&&this.__vcm.m)||'GET', status: this.status, reqBody: b||null,
      respBody: this.responseText, headers: {}, resourceType: 'xhr'}));
    return _send.apply(this, arguments);
  };
  if (navigator.sendBeacon) {
    const _bk = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = function(url, data){
      try { push({url: ''+url, method: 'POST', status: 0, reqBody: null,
                  respBody: null, headers: {}, resourceType: 'ping'}); } catch (_) {}
      return _bk(url, data);
    };
  }
  const _ce = document.createElement.bind(document);
  document.createElement = function(tag){
    const el = _ce(tag);
    try {
      const t = (''+tag).toLowerCase();
      if (t === 'script' || t === 'img') {
        const proto = (t === 'script') ? HTMLScriptElement.prototype : HTMLImageElement.prototype;
        const desc = Object.getOwnPropertyDescriptor(proto, 'src');
        if (desc && desc.set) {
          Object.defineProperty(el, 'src', {
            configurable: true, enumerable: true,
            get(){ return desc.get.call(this); },
            set(v){
              try { push({url: ''+v, method: 'GET', status: 0, reqBody: null,
                          respBody: null, headers: {},
                          resourceType: (t === 'script') ? 'script' : 'image'}); } catch (_) {}
              return desc.set.call(this, v);
            }
          });
        }
      }
    } catch (_) {}
    return el;
  };
  return true;
}"""

_READ_JS = "() => JSON.stringify(window.__vcm_capture || [])"

# Resource kinds whose bodies are worth fetching via Network.getResponseBody.
_TEXTY_HINTS = ("json", "javascript", "xml", "html", "text", "x-www-form-urlencoded", "csv")
_TEXTY_TYPES = {"XHR", "Fetch", "Script", "Document", "EventSource"}


def _is_texty(mime: str | None, rtype: str | None) -> bool:
    """Whether a response body is likely text worth retrieving (vs. image/font/media)."""
    m = (mime or "").lower()
    if any(h in m for h in _TEXTY_HINTS):
        return True
    return (rtype or "") in _TEXTY_TYPES


def _normalize(e: dict[str, Any], source: str) -> dict[str, Any]:
    """Coerce a raw hook/CDP entry into the uniform output shape."""
    rt = e.get("resourceType")
    if rt is None:
        rt = e.get("kind")
    return {
        "url": e.get("url", ""),
        "method": str(e.get("method") or "GET").upper(),
        "status": e.get("status") or 0,
        "reqBody": e.get("reqBody"),
        "respBody": e.get("respBody"),
        "headers": dict(e.get("headers") or {}),
        "resourceType": rt,
        "source": source,
    }


class NetworkCapture:
    """Capture network traffic on a visus-web :class:`Page` (JS hook + CDP).

    Usage::

        cap = NetworkCapture(page)
        cap.start()            # install hook BEFORE interactions
        page.goto(...)         # drive the site
        reqs = cap.get_requests(filter_type=["xhr", "fetch"])
        cap.export_enriched("capture.json")
    """

    def __init__(self, page: Any, use_cdp: bool = True) -> None:
        self.page = page
        self.use_cdp = use_cdp
        self._started = False
        self._cdp_active = False
        # CDP events are folded incrementally into one correlated record per hop
        # (keyed ``requestId:hop`` so each redirect leg is its own entry), rather
        # than retaining the raw performance log — this bounds memory to the
        # number of requests and keeps each drain O(new events).
        self._cdp_records: dict[str, dict[str, Any]] = {}
        self._cdp_order: list[str] = []
        self._cdp_hop: dict[str, int] = {}
        self._cdp_bodies: dict[str, str | None] = {}

    def _driver(self) -> Any:
        """Best-effort reach into the underlying Selenium driver, or ``None``."""
        delegate = getattr(self.page, "_delegate", None)
        if delegate is None:
            return None
        return getattr(delegate, "_driver", None)

    def _enable_cdp(self) -> None:
        """Enable the CDP Network domain when the driver supports it.

        Falls back silently (leaving only the JS hook) on any failure or when
        ``execute_cdp_cmd`` is unavailable (non-Chromium engine or a stub page).
        """
        driver = self._driver()
        execute_cdp = getattr(driver, "execute_cdp_cmd", None)
        if not callable(execute_cdp):
            return
        try:
            execute_cdp("Network.enable", {})
            self._cdp_active = True
        except Exception:
            self._cdp_active = False

    def start(self) -> None:
        """Install the JS hook (and the CDP path when enabled) before interactions."""
        # Install JS hook BEFORE interactions (works for CDP and fallback alike).
        self.page.evaluate(_HOOK_JS)
        self._cdp_records = {}
        self._cdp_order = []
        self._cdp_hop = {}
        self._cdp_bodies = {}
        if self.use_cdp:
            self._enable_cdp()
        self._started = True

    def stop(self) -> None:
        if self._cdp_active:
            driver = self._driver()
            execute_cdp = getattr(driver, "execute_cdp_cmd", None)
            if callable(execute_cdp):
                try:
                    execute_cdp("Network.disable", {})
                except Exception:
                    pass
        self._cdp_active = False
        self._started = False

    # ------------------------------------------------------------------
    # CDP performance-log draining
    # ------------------------------------------------------------------

    def _record(self, key: str) -> dict[str, Any]:
        """Get or create the correlated record for *key* (``requestId:hop``)."""
        rec = self._cdp_records.get(key)
        if rec is None:
            rec = {
                "url": "", "method": "GET", "reqBody": None, "status": 0,
                "req_headers": {}, "resp_headers": {}, "resourceType": None,
                "mime": "", "finished": False, "redirect": False,
            }
            self._cdp_records[key] = rec
            self._cdp_order.append(key)
        return rec

    def _drain_cdp(self) -> None:
        """Fold new ``Network.*`` events off Chrome's performance log into records.

        ``get_log('performance')`` returns *and clears* the entries logged since
        the last call, so correlation is incremental: each event is merged into
        its ``requestId:hop`` record and the raw log is discarded. HTTP redirects
        arrive as a second ``requestWillBeSent`` for the same id carrying the 30x
        ``redirectResponse`` — that leg is finalized as its own entry before the
        new hop begins. Silently no-ops when the driver lacks ``get_log`` (non
        Chromium / not launched with performance logging) or reading it fails.
        """
        driver = self._driver()
        get_log = getattr(driver, "get_log", None)
        if not callable(get_log):
            return
        try:
            logs = get_log("performance")
        except Exception:
            return
        for entry in logs or []:
            try:
                msg = json.loads(entry["message"])["message"]
                method = msg.get("method", "")
                params = msg.get("params") or {}
            except (KeyError, TypeError, ValueError):
                continue
            if not isinstance(method, str) or not method.startswith("Network."):
                continue
            rid = params.get("requestId")
            if not rid:
                continue
            if method == "Network.requestWillBeSent":
                redirect = params.get("redirectResponse")
                if redirect is not None and rid in self._cdp_hop:
                    prev = self._cdp_records.get(f"{rid}:{self._cdp_hop[rid]}")
                    if prev is not None:  # finalize the redirected leg with its 30x
                        prev["status"] = redirect.get("status") or prev["status"]
                        prev["resp_headers"].update(redirect.get("headers") or {})
                        if redirect.get("mimeType"):
                            prev["mime"] = redirect.get("mimeType")
                        prev["finished"] = True
                        prev["redirect"] = True  # 30x leg: no retrievable body
                    self._cdp_hop[rid] += 1
                else:
                    self._cdp_hop.setdefault(rid, 0)
                rec = self._record(f"{rid}:{self._cdp_hop[rid]}")
                req = params.get("request") or {}
                rec["url"] = req.get("url") or rec["url"]
                rec["method"] = str(req.get("method") or rec["method"]).upper()
                if req.get("postData") is not None:
                    rec["reqBody"] = req.get("postData")
                rec["req_headers"].update(req.get("headers") or {})
                if params.get("type"):
                    rec["resourceType"] = params.get("type")
            elif method == "Network.responseReceived":
                self._cdp_hop.setdefault(rid, 0)
                rec = self._record(f"{rid}:{self._cdp_hop[rid]}")
                resp = params.get("response") or {}
                rec["status"] = resp.get("status") or rec["status"]
                rec["resp_headers"].update(resp.get("headers") or {})
                if resp.get("mimeType"):
                    rec["mime"] = resp.get("mimeType")
                if params.get("type"):
                    rec["resourceType"] = params.get("type")
            elif method == "Network.loadingFinished":
                if rid in self._cdp_hop:
                    done = self._cdp_records.get(f"{rid}:{self._cdp_hop[rid]}")
                    if done is not None:
                        done["finished"] = True

    def _fetch_body(
        self, rid: str, mime: str | None, rtype: str | None, finished: bool
    ) -> str | None:
        """Best-effort ``Network.getResponseBody`` for one request, cached per id.

        Skips binary resources (images/fonts/media) and bodies that aren't ready
        yet; tolerates eviction (the body may be gone after a navigation).
        """
        if rid in self._cdp_bodies:
            return self._cdp_bodies[rid]
        if not _is_texty(mime, rtype):
            self._cdp_bodies[rid] = None
            return None
        if not finished:
            return None  # may become available on a later drain — don't cache yet
        driver = self._driver()
        execute_cdp = getattr(driver, "execute_cdp_cmd", None)
        if not callable(execute_cdp):
            self._cdp_bodies[rid] = None
            return None
        try:
            res = execute_cdp("Network.getResponseBody", {"requestId": rid})
        except Exception:
            self._cdp_bodies[rid] = None  # evicted / not retrievable — don't retry
            return None
        raw = res.get("body") if isinstance(res, dict) else None
        body: str | None = raw if isinstance(raw, str) else None
        if body is not None and res.get("base64Encoded"):
            try:  # strict decode: binary bodies are dropped, not turned to mojibake
                body = base64.b64decode(body).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                body = None
        self._cdp_bodies[rid] = body
        return body

    def _build_cdp_entries(self) -> list[dict[str, Any]]:
        """Materialize the correlated CDP records into normalized entries.

        Records are already folded by :meth:`_drain_cdp`; this only fetches
        bodies (skipping 30x redirect legs, which have none) and shapes output.
        """
        entries: list[dict[str, Any]] = []
        for key in self._cdp_order:
            rec = self._cdp_records[key]
            if not rec["url"]:
                continue
            if rec["redirect"]:
                body = None  # redirect leg carries no retrievable body
            else:
                rid = key.rsplit(":", 1)[0]
                body = self._fetch_body(rid, rec["mime"], rec["resourceType"], rec["finished"])
            entries.append(
                {
                    "url": rec["url"],
                    "method": rec["method"],
                    "status": rec["status"],
                    "reqBody": rec["reqBody"],
                    "respBody": body,
                    "headers": {**rec["req_headers"], **rec["resp_headers"]},
                    "resourceType": rec["resourceType"],
                    "source": "cdp",
                }
            )
        return entries

    def get_requests(self, filter_type: list[str] | None = None) -> list[dict[str, Any]]:
        """Read captured requests, merging the JS hook buffer with CDP events.

        Entries are de-duplicated on ``(method, url)``; the JS hook's readable
        response body is preferred, while CDP supplies status, resource type and
        request headers. Headers are scrubbed on every returned entry.

        ``filter_type`` (e.g. ``["xhr", "fetch"]``) keeps entries whose resource
        type matches; entries with no known type (legacy hook entries) always
        pass through.
        """
        raw = self.page.evaluate(_READ_JS)
        hook_entries = json.loads(raw) if raw else []

        # Merge hook + CDP into one ordered map keyed by (method, url, reqBody).
        # The body discriminator keeps genuinely distinct requests to the same
        # endpoint (e.g. two POSTs with different payloads) from collapsing,
        # while a hook entry and its CDP twin (same request) still coalesce —
        # the hook's readable body is kept and CDP fills status/type/headers.
        merged: dict[tuple[str, str, str | None], dict[str, Any]] = {}
        order: list[tuple[str, str, str | None]] = []

        def _merge(e: dict[str, Any]) -> None:
            body = e.get("reqBody")
            key = (e["method"], e["url"], body if body is None else str(body))
            tgt = merged.get(key)
            if tgt is None:
                merged[key] = e
                order.append(key)
                return
            if not tgt.get("status"):
                tgt["status"] = e.get("status") or tgt.get("status")
            if not tgt.get("respBody"):
                tgt["respBody"] = e.get("respBody")
            if tgt.get("resourceType") is None:
                tgt["resourceType"] = e.get("resourceType")
            tgt["headers"] = {**(e.get("headers") or {}), **(tgt.get("headers") or {})}

        for he in hook_entries:
            _merge(_normalize(he, "hook"))
        if self.use_cdp and self._cdp_active:
            self._drain_cdp()
            for ce in self._build_cdp_entries():
                _merge(ce)

        entries = [merged[k] for k in order]
        for e in entries:
            e["headers"] = scrub_headers(e.get("headers") or {})

        if filter_type:
            want = {t.lower() for t in filter_type}
            entries = [
                e
                for e in entries
                if e["resourceType"] is None or str(e["resourceType"]).lower() in want
            ]
        return entries

    def export_enriched(self, path: str) -> None:
        """Write the Appendix-B-shaped JSON: ``{target_url, entries}`` (scrubbed)."""
        entries = self.get_requests()
        doc = {"target_url": getattr(self.page, "url", ""), "entries": entries}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
