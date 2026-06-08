(function () {
  "use strict";
  if (window.__visus) return;

  function normWs(s) {
    return (s || "").replace(/ /g, " ").replace(/\s+/g, " ").trim();
  }
  function normText(el) {
    return normWs(el.textContent || "");
  }

  // Plain object used as a set for IE11 compatibility (Set array-constructor is broken in Trident).
  var NAME_FROM_CONTENT = {
    "button": true, "link": true, "heading": true, "menuitem": true,
    "menuitemcheckbox": true, "menuitemradio": true, "option": true, "tab": true,
    "treeitem": true, "cell": true, "columnheader": true, "rowheader": true,
    "gridcell": true, "checkbox": true, "radio": true, "switch": true,
    "row": true, "tooltip": true, "listitem": true,
  };

  function implicitRole(el) {
    var tag = el.tagName.toLowerCase();
    var type = (el.getAttribute && (el.getAttribute("type") || "text").toLowerCase()) || "text";
    switch (tag) {
      case "a": case "area": return el.hasAttribute("href") ? "link" : null;
      case "button": return "button";
      case "h1": case "h2": case "h3": case "h4": case "h5": case "h6": return "heading";
      case "nav": return "navigation";
      case "main": return "main";
      case "aside": return "complementary";
      case "article": return "article";
      case "ul": case "ol": return "list";
      case "li": return "listitem";
      case "table": return "table";
      case "tr": return "row";
      case "td": return "cell";
      case "th": return "columnheader";
      case "img": return el.getAttribute("alt") === "" ? "presentation" : "img";
      case "select": return (el.multiple || (el.size && el.size > 1)) ? "listbox" : "combobox";
      case "option": return "option";
      case "textarea": return "textbox";
      case "progress": return "progressbar";
      case "fieldset": return "group";
      case "dialog": return "dialog";
      case "summary": return "button";
      case "form": return "form";
      case "input": {
        var m = {
          search: "searchbox", email: "textbox", tel: "textbox", text: "textbox",
          url: "textbox", number: "spinbutton", range: "slider", checkbox: "checkbox",
          radio: "radio", button: "button", submit: "button", reset: "button", image: "button",
        };
        if (type in m) return m[type];
        if (type === "hidden" || type === "password") return null;
        return "textbox";
      }
      default: return null;
    }
  }
  function computeRole(el) {
    var explicit = el.getAttribute && el.getAttribute("role");
    if (explicit) {
      var r = explicit.trim().split(/\s+/)[0];
      if (r) return r;
    }
    return implicitRole(el);
  }

  function isLabelable(el) {
    return ["INPUT", "SELECT", "TEXTAREA", "BUTTON", "METER", "OUTPUT", "PROGRESS"].indexOf(el.tagName) >= 0;
  }
  function accessibleName(el) {
    var lb = el.getAttribute("aria-labelledby");
    if (lb) {
      var txt = lb.split(/\s+/).map(function (id) {
        var e = document.getElementById(id);
        return e ? normText(e) : "";
      }).join(" ");
      txt = normWs(txt);
      if (txt) return txt;
    }
    var al = el.getAttribute("aria-label");
    if (al && al.trim()) return normWs(al);
    if (isLabelable(el)) {
      var lbl = "";
      if (el.id) {
        var f = document.querySelector('label[for="' + (window.CSS && CSS.escape ? CSS.escape(el.id) : el.id) + '"]');
        if (f) lbl = normText(f);
      }
      if (!lbl && el.closest) {
        var wrap = el.closest("label");
        if (wrap) lbl = normText(wrap);
      }
      if (lbl) return lbl;
      var ph = el.getAttribute("placeholder");
      if (ph) return normWs(ph);
    }
    if (el.tagName === "IMG" || (el.tagName === "INPUT" && (el.getAttribute("type") || "") === "image")) {
      var alt = el.getAttribute("alt");
      if (alt) return normWs(alt);
    }
    if (NAME_FROM_CONTENT[computeRole(el)]) {
      var t = normText(el);
      if (t) return t;
    }
    if (el.tagName === "INPUT") {
      var ty = (el.getAttribute("type") || "").toLowerCase();
      if (ty === "button" || ty === "submit" || ty === "reset") return normWs(el.value || "");
    }
    var title = el.getAttribute("title");
    if (title) return normWs(title);
    return "";
  }

  function isVisible(el) {
    // Cross-realm safe: elements collected from an iframe's contentDocument belong
    // to that iframe's realm, so `el instanceof Element` (top realm) is false for
    // them. Duck-type on nodeType and use the element's own view for getComputedStyle.
    if (!el || el.nodeType !== 1) return false;
    var view = (el.ownerDocument && el.ownerDocument.defaultView) || window;
    var style = view.getComputedStyle(el);
    if (style.visibility === "hidden" || style.display === "none") return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function isDisabled(el) {
    var dis = ["BUTTON", "INPUT", "SELECT", "TEXTAREA", "OPTION", "OPTGROUP", "FIELDSET"];
    if (dis.indexOf(el.tagName) >= 0 && el.disabled) return true;
    if (el.closest && el.closest("fieldset[disabled]")) return true;
    var n = el;
    while (n) {
      if (n.getAttribute && n.getAttribute("aria-disabled") === "true") return true;
      n = n.parentElement;
    }
    return false;
  }
  function isReadonly(el) {
    if (["INPUT", "TEXTAREA", "SELECT"].indexOf(el.tagName) >= 0 && el.readOnly) return true;
    if (el.getAttribute && el.getAttribute("aria-readonly") === "true") return true;
    return false;
  }
  function isEditableTag(el) {
    if (el.isContentEditable) return true;
    return ["INPUT", "TEXTAREA"].indexOf(el.tagName) >= 0;
  }
  function elementState(el, state) {
    var vis = isVisible(el);
    switch (state) {
      case "visible": return { matches: vis, received: vis ? "visible" : "hidden" };
      case "hidden": return { matches: !vis, received: vis ? "visible" : "hidden" };
      case "enabled": return { matches: !isDisabled(el), received: isDisabled(el) ? "disabled" : "enabled" };
      case "disabled": return { matches: isDisabled(el), received: isDisabled(el) ? "disabled" : "enabled" };
      case "editable": return { matches: !isDisabled(el) && !isReadonly(el) && isEditableTag(el), received: "" };
      case "checked": {
        var c = (typeof el.checked === "boolean") ? el.checked : el.getAttribute("aria-checked") === "true";
        return { matches: c, received: c ? "checked" : "unchecked" };
      }
      default: return { matches: false, received: "unknown-state:" + state };
    }
  }

  function matchText(el, value, exact) {
    var t = normText(el);
    var v = normWs(value);
    return exact ? t === v : t.toLowerCase().indexOf(v.toLowerCase()) >= 0;
  }
  function matchName(el, name, exact) {
    var an = accessibleName(el);
    var v = normWs(name);
    return exact ? an === v : an.toLowerCase().indexOf(v.toLowerCase()) >= 0;
  }

  function attrText(el, attr) { return normWs(el.getAttribute(attr) || ""); }
  function matchAttr(el, attr, value, exact) {
    var a = attrText(el, attr), v = normWs(value);
    return exact ? a === v : a.toLowerCase().indexOf(v.toLowerCase()) >= 0;
  }
  function labelText(el) {
    var lb = el.getAttribute("aria-labelledby");
    if (lb) {
      var t = normWs(lb.split(/\s+/).map(function (id) {
        var e = document.getElementById(id); return e ? normText(e) : "";
      }).join(" "));
      if (t) return t;
    }
    var al = el.getAttribute("aria-label");
    if (al && al.trim()) return normWs(al);
    if (el.id) {
      var f = document.querySelector('label[for="' + (window.CSS && CSS.escape ? CSS.escape(el.id) : el.id) + '"]');
      if (f) return normText(f);
    }
    if (el.closest) { var w = el.closest("label"); if (w) return normText(w); }
    return "";
  }
  function matchLabel(el, value, exact) {
    if (!isLabelable(el)) return false;
    var l = labelText(el), v = normWs(value);
    return exact ? l === v : l.toLowerCase().indexOf(v.toLowerCase()) >= 0;
  }

  function dedupe(els) {
    var seen = [], out = [];
    for (var i = 0; i < els.length; i++) {
      if (seen.indexOf(els[i]) < 0) { seen.push(els[i]); out.push(els[i]); }
    }
    return out;
  }
  function innermost(els) {
    return els.filter(function (e) {
      for (var i = 0; i < els.length; i++) {
        if (els[i] !== e && e.contains(els[i])) return false;
      }
      return true;
    });
  }

  // Recursive shadow-aware querySelectorAll: collects matches in `base` and in
  // every open shadow root reachable from it (feature-detected `shadowRoot`).
  function deepQuerySelectorAll(base, selector, acc) {
    var i, matches;
    try {
      matches = base.querySelectorAll(selector);
      for (i = 0; i < matches.length; i++) acc.push(matches[i]);
    } catch (qErr) { /* malformed selector against this root */ }
    var hosts = base.querySelectorAll("*");
    for (i = 0; i < hosts.length; i++) {
      var sr = hosts[i].shadowRoot;
      if (sr) deepQuerySelectorAll(sr, selector, acc);
    }
    return acc;
  }

  function queryAll(stepsJson) {
    var steps = (typeof stepsJson === "string") ? JSON.parse(stepsJson) : stepsJson;
    var current = null; // null => root is document
    for (var i = 0; i < steps.length; i++) {
      var step = steps[i];
      var roots = (current === null) ? [document] : current;
      var out = [];
      var r, base, all, j, e;
      if (step.kind === "css") {
        for (r = 0; r < roots.length; r++) {
          base = roots[r];
          if (step.deep) {
            deepQuerySelectorAll(base, step.value, out);
          } else {
            out.push.apply(out, base.querySelectorAll(step.value));
          }
        }
      } else if (step.kind === "xpath") {
        // IE / Trident (Edge IE-mode) has no document.evaluate/XPathResult: skip XPath
        // resolution there (leave `out` empty for this step) instead of throwing.
        if (typeof document.evaluate === "function" && typeof XPathResult !== "undefined") {
          for (r = 0; r < roots.length; r++) {
            var ctx = (roots[r] === document) ? document : roots[r];
            var res = document.evaluate(step.value, ctx, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
            for (j = 0; j < res.snapshotLength; j++) out.push(res.snapshotItem(j));
          }
        }
      } else if (step.kind === "role") {
        for (r = 0; r < roots.length; r++) {
          base = roots[r];
          all = base.querySelectorAll("*");
          for (j = 0; j < all.length; j++) {
            e = all[j];
            if (computeRole(e) === step.role && (step.name == null || matchName(e, step.name, step.exact))) out.push(e);
          }
        }
      } else if (step.kind === "text") {
        for (r = 0; r < roots.length; r++) {
          base = roots[r];
          all = base.querySelectorAll("*");
          for (j = 0; j < all.length; j++) {
            e = all[j];
            if (matchText(e, step.value, step.exact)) out.push(e);
          }
        }
        out = innermost(out);
      } else if (step.kind === "filter_has_text") {
        for (r = 0; r < roots.length; r++) {
          if (roots[r] !== document && matchText(roots[r], step.value, false)) out.push(roots[r]);
        }
      } else if (step.kind === "label") {
        for (r = 0; r < roots.length; r++) {
          base = roots[r]; all = base.querySelectorAll("*");
          for (j = 0; j < all.length; j++) { e = all[j]; if (matchLabel(e, step.value, step.exact)) out.push(e); }
        }
      } else if (step.kind === "placeholder") {
        for (r = 0; r < roots.length; r++) {
          base = roots[r]; all = base.querySelectorAll("[placeholder]");
          for (j = 0; j < all.length; j++) { e = all[j]; if (matchAttr(e, "placeholder", step.value, step.exact)) out.push(e); }
        }
      } else if (step.kind === "alt") {
        for (r = 0; r < roots.length; r++) {
          base = roots[r]; all = base.querySelectorAll("[alt]");
          for (j = 0; j < all.length; j++) { e = all[j]; if (matchAttr(e, "alt", step.value, step.exact)) out.push(e); }
        }
      } else if (step.kind === "title") {
        for (r = 0; r < roots.length; r++) {
          base = roots[r]; all = base.querySelectorAll("[title]");
          for (j = 0; j < all.length; j++) { e = all[j]; if (matchAttr(e, "title", step.value, step.exact)) out.push(e); }
        }
      } else if (step.kind === "testid") {
        var attr = step.attr || "data-testid";
        for (r = 0; r < roots.length; r++) {
          base = roots[r]; all = base.querySelectorAll("[" + attr + "]");
          for (j = 0; j < all.length; j++) { e = all[j]; if (attrText(e, attr) === normWs(step.value)) out.push(e); }
        }
      } else if (step.kind === "nth") {
        var arr = roots.filter(function (x) { return x !== document; });
        var idx = step.index < 0 ? arr.length + step.index : step.index;
        out = (idx >= 0 && idx < arr.length) ? [arr[idx]] : [];
      } else if (step.kind === "smart") {
        // Pasted-element locator: try candidate selectors in order, preferring the
        // first that matches a single element, else the first that matches any.
        // Malformed / non-matching candidates are skipped (fault-tolerant).
        var sFirst = null;
        for (var sc = 0; sc < step.candidates.length; sc++) {
          var cand = step.candidates[sc];
          var sFound = [];
          // A deep step/candidate must pierce shadow roots even on the smart fallback,
          // otherwise shadow-DOM fields bestLocator marked deep cannot be re-resolved.
          var sDeep = step.deep || cand.deep;
          for (r = 0; r < roots.length; r++) {
            base = roots[r];
            try {
              if (cand.css != null) {
                if (sDeep) {
                  deepQuerySelectorAll(base, cand.css, sFound);
                } else {
                  sFound.push.apply(sFound, base.querySelectorAll(cand.css));
                }
              } else if (cand.xpath != null && typeof document.evaluate === "function" && typeof XPathResult !== "undefined") {
                var sCtx = (base === document) ? document : base;
                var sRes = document.evaluate(cand.xpath, sCtx, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                for (j = 0; j < sRes.snapshotLength; j++) sFound.push(sRes.snapshotItem(j));
              }
            } catch (sErr) { /* skip a malformed or non-matching candidate */ }
          }
          sFound = dedupe(sFound);
          if (sFound.length === 1) { out = sFound; sFirst = null; break; }
          if (sFound.length > 0 && sFirst === null) sFirst = sFound;
        }
        if (out.length === 0 && sFirst !== null) out = sFirst;
      }
      current = dedupe(out);
    }
    return current === null ? [] : current;
  }

  function clickablePoint(el) {
    var r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }
  function hitTarget(el, x, y) {
    var top = document.elementFromPoint(x, y);
    if (!top) return false;
    return el === top || el.contains(top) || top.contains(el);
  }
  function checkStable(el, cb) {
    // resolves cb(true/false) after comparing the rect across 2 animation frames
    var r1 = el.getBoundingClientRect();
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        var r2 = el.getBoundingClientRect();
        cb(r1.x === r2.x && r1.y === r2.y && r1.width === r2.width && r1.height === r2.height);
      });
    });
  }

  function snapshot() {
    var roles = ["button", "link", "textbox", "searchbox", "checkbox", "radio", "combobox",
                 "heading", "tab", "menuitem", "option", "switch", "slider", "spinbutton"];
    var out = [], all = document.querySelectorAll("*");
    for (var i = 0; i < all.length; i++) {
      var e = all[i], r = computeRole(e);
      if (roles.indexOf(r) >= 0 && isVisible(e)) out.push({ role: r, name: accessibleName(e) });
    }
    return out;
  }

  function highlight(el) {
    unhighlight();
    if (!el || !el.getBoundingClientRect) return null;
    var r = el.getBoundingClientRect();
    var box = document.createElement("div");
    box.setAttribute("data-visus-highlight", "1");
    box.style.cssText =
      "position:fixed;z-index:2147483647;pointer-events:none;box-sizing:border-box;" +
      "border:3px solid #cc785c;box-shadow:0 0 0 2px rgba(204,120,92,.35);" +
      "left:" + r.left + "px;top:" + r.top + "px;width:" + r.width + "px;height:" + r.height + "px;";
    var cx = document.createElement("div");
    cx.setAttribute("data-visus-highlight", "1");
    cx.style.cssText =
      "position:fixed;z-index:2147483647;pointer-events:none;width:10px;height:10px;" +
      "border:2px solid #cc785c;border-radius:50%;" +
      "left:" + (r.left + r.width / 2 - 5) + "px;top:" + (r.top + r.height / 2 - 5) + "px;";
    document.documentElement.appendChild(box);
    document.documentElement.appendChild(cx);
    return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) };
  }
  function unhighlight() {
    var n = document.querySelectorAll("[data-visus-highlight]");
    for (var i = 0; i < n.length; i++) n[i].parentNode.removeChild(n[i]);
  }

  // ------------------------------------------------------------------
  // Field enumeration (window.__visus.listFields)
  // ------------------------------------------------------------------

  // Roles considered interactive "fields" for enumeration.
  var FIELD_ROLES = {
    "button": true, "link": true, "textbox": true, "searchbox": true,
    "combobox": true, "listbox": true, "checkbox": true, "radio": true,
    "switch": true, "slider": true, "spinbutton": true, "menuitem": true,
    "menuitemcheckbox": true, "menuitemradio": true, "option": true, "tab": true,
    "treeitem": true,
  };
  // ARIA values of aria-haspopup that indicate a custom dropdown trigger.
  var HASPOPUP_DROPDOWN = {
    "listbox": true, "menu": true, "tree": true, "grid": true, "dialog": true, "true": true,
  };

  function cssEscape(s) {
    if (window.CSS && CSS.escape) return CSS.escape(s);
    // Minimal fallback: escape characters that are unsafe in a CSS identifier.
    return String(s).replace(/([^\w-])/g, "\\$1");
  }
  function cssAttrValue(s) {
    return String(s).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  }

  // Map a native control / computed role to a coarse field `kind`.
  function fieldKind(el, role) {
    var tag = el.tagName.toLowerCase();
    var type = (el.getAttribute && (el.getAttribute("type") || "").toLowerCase()) || "";
    if (tag === "textarea") return "textarea";
    if (tag === "select") return "select";
    if (tag === "a" && el.hasAttribute("href")) return "link";
    if (tag === "button") return "button";
    if (tag === "input") {
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      if (type === "button" || type === "submit" || type === "reset" || type === "image") {
        return "button";
      }
      return "input";
    }
    // role-driven classification for custom widgets / contenteditable
    if (role === "button") return "button";
    if (role === "link") return "link";
    if (role === "checkbox" || role === "switch" || role === "menuitemcheckbox") return "checkbox";
    if (role === "radio" || role === "menuitemradio") return "radio";
    if (role === "combobox" || role === "listbox") return "dropdown";
    if (role === "textbox" || role === "searchbox") {
      return el.isContentEditable ? "editable" : "input";
    }
    if (el.isContentEditable) return "editable";
    return "other";
  }

  // True if `el` qualifies as an enumerable field (native control or interactive role).
  function isFieldCandidate(el) {
    var tag = el.tagName.toLowerCase();
    var type = (el.getAttribute && (el.getAttribute("type") || "").toLowerCase()) || "";
    if (tag === "input" && type !== "hidden") return true;
    if (tag === "textarea" || tag === "select" || tag === "button") return true;
    if (tag === "a" && el.hasAttribute("href")) return true;
    if (el.isContentEditable) return true;
    if (el.getAttribute && el.getAttribute("contenteditable") != null
        && el.getAttribute("contenteditable") !== "false") return true;
    var role = computeRole(el);
    if (role && FIELD_ROLES[role]) return true;
    var hp = el.getAttribute && el.getAttribute("aria-haspopup");
    if (hp && HASPOPUP_DROPDOWN[hp.toLowerCase()]) return true;
    return false;
  }

  // Build a ready-to-use locator step list (and a human string) for `el`, mirroring
  // the _htmlsel.py ranking: id -> testid -> name -> aria-label -> role+name ->
  // minimal CSS -> smart. `deep` marks shadow-DOM css steps so the resolver pierces.
  var TEST_HOOKS = ["data-testid", "data-test", "data-test-id", "data-qa", "data-cy"];
  function bestLocator(el, deep) {
    var tag = el.tagName.toLowerCase();
    var k, v, css = null, kind = null;
    var id = el.getAttribute && el.getAttribute("id");
    if (id) { css = "#" + cssEscape(id); kind = "css"; }
    if (css === null) {
      for (k = 0; k < TEST_HOOKS.length; k++) {
        v = el.getAttribute && el.getAttribute(TEST_HOOKS[k]);
        if (v) { css = "[" + TEST_HOOKS[k] + '="' + cssAttrValue(v) + '"]'; kind = "testid"; break; }
      }
    }
    if (css === null) {
      v = el.getAttribute && el.getAttribute("name");
      if (v) { css = tag + '[name="' + cssAttrValue(v) + '"]'; kind = "name"; }
    }
    if (css === null) {
      v = el.getAttribute && el.getAttribute("aria-label");
      if (v && v.trim()) { css = '[aria-label="' + cssAttrValue(v) + '"]'; kind = "label"; }
    }
    if (css === null) {
      // role + accessible-name (expressed as a role step the engine understands)
      var role = computeRole(el);
      var nm = accessibleName(el);
      if (role && nm) {
        return {
          steps: [{ kind: "role", role: role, name: nm, exact: true }],
          locator: "role=" + role + "[name=\"" + nm + "\"]",
          locator_kind: "role",
        };
      }
    }
    if (css === null) {
      // minimal CSS: tag + classes (escaped), else a smart candidate list
      var classes = (el.getAttribute && el.getAttribute("class") || "").split(/\s+/);
      var sel = tag, c;
      for (c = 0; c < classes.length; c++) {
        if (classes[c]) sel += "." + cssEscape(classes[c]);
      }
      if (sel !== tag) { css = sel; kind = "css"; }
    }
    if (css === null) {
      // smart fallback: a couple of identifying attributes, else bare tag
      var cands = [], attrs = ["type", "role", "placeholder", "href"], a, av;
      var base = tag;
      for (a = 0; a < attrs.length; a++) {
        av = el.getAttribute && el.getAttribute(attrs[a]);
        if (av) base += "[" + attrs[a] + '="' + cssAttrValue(av) + '"]';
      }
      cands.push({ css: base });
      return {
        steps: [{ kind: "smart", tag: tag, candidates: cands, deep: deep }],
        locator: base,
        locator_kind: "smart",
      };
    }
    var step = { kind: "css", value: css };
    if (deep) step.deep = true;
    return { steps: [step], locator: css, locator_kind: kind };
  }

  // A resolvable CSS selector path for `el` within its OWN root (document, open
  // shadow root, or iframe document). Prefers an #id anchor; else an
  // :nth-of-type path up to the nearest ancestor id / root.
  function cssPath(el) {
    if (!el || el.nodeType !== 1) return "";
    var id = el.getAttribute && el.getAttribute("id");
    if (id) return "#" + cssEscape(id);
    var parts = [], node = el, seg, pid, parent, s, sib, sameTag, idx;
    while (node && node.nodeType === 1) {
      seg = node.tagName.toLowerCase();
      pid = node.getAttribute && node.getAttribute("id");
      if (pid && node !== el) { parts.unshift("#" + cssEscape(pid)); break; }
      parent = node.parentNode;
      if (parent && parent.children && parent.children.length) {
        sameTag = 0; idx = 0;
        for (s = 0; s < parent.children.length; s++) {
          sib = parent.children[s];
          if (sib.tagName === node.tagName) {
            sameTag++;
            if (sib === node) idx = sameTag;
          }
        }
        if (sameTag > 1) seg += ":nth-of-type(" + idx + ")";
      }
      parts.unshift(seg);
      node = node.parentNode;
      if (!node || node.nodeType !== 1) break;
    }
    return parts.join(" > ");
  }

  // An XPath for `el` within its OWN root. Prefers //*[@id="..."]; else an
  // absolute positional path.
  function xPath(el) {
    if (!el || el.nodeType !== 1) return "";
    var id = el.getAttribute && el.getAttribute("id");
    if (id) return '//*[@id="' + id + '"]';
    var parts = [], node = el, tag, parent, idx, count, s, sib;
    while (node && node.nodeType === 1) {
      tag = node.tagName.toLowerCase();
      parent = node.parentNode;
      idx = 1;
      if (parent && parent.children && parent.children.length) {
        count = 0;
        for (s = 0; s < parent.children.length; s++) {
          sib = parent.children[s];
          if (sib.tagName === node.tagName) {
            count++;
            if (sib === node) { idx = count; break; }
          }
        }
      }
      parts.unshift(tag + "[" + idx + "]");
      node = parent;
      if (!node || node.nodeType !== 1) break;
    }
    return "/" + parts.join("/");
  }

  // Depth-first collection of field descriptors across the main document, open
  // shadow roots, and same-origin iframes. `frameChain` is the CSS selector chain
  // of iframes traversed to reach `root`; `inShadow` marks shadow-DOM context.
  function collectFields(root, frameChain, inShadow, includeHidden, kinds, acc) {
    var all;
    try {
      all = root.querySelectorAll("*");
    } catch (qErr) { return; }
    var i, el, sr, kind, role, visible, disabled;
    for (i = 0; i < all.length; i++) {
      el = all[i];
      if (isFieldCandidate(el)) {
        role = computeRole(el);
        kind = fieldKind(el, role);
        // custom dropdown trigger overrides a generic role classification
        var hp = el.getAttribute && el.getAttribute("aria-haspopup");
        if (hp && HASPOPUP_DROPDOWN[hp.toLowerCase()]) kind = "dropdown";
        if (!kinds || kinds.indexOf(kind) >= 0) {
          visible = isVisible(el);
          disabled = isDisabled(el);
          if (includeHidden || (visible && !disabled)) {
            var loc = bestLocator(el, inShadow);
            var rect = el.getBoundingClientRect();
            var type = el.getAttribute && el.getAttribute("type");
            var checked = (typeof el.checked === "boolean") ? el.checked
              : (el.getAttribute && el.getAttribute("aria-checked") === "true" ? true : null);
            acc.push({
              el: el,
              descriptor: {
                index: -1,
                kind: kind,
                tag: el.tagName.toLowerCase(),
                type: type || null,
                role: role || null,
                name: accessibleName(el),
                label: labelText(el) || null,
                placeholder: (el.getAttribute && el.getAttribute("placeholder")) || null,
                value: (typeof el.value === "string") ? el.value : null,
                checked: checked,
                disabled: disabled,
                visible: visible,
                frame: frameChain.slice(),
                shadow: inShadow,
                locator: loc.locator,
                locator_kind: loc.locator_kind,
                css: cssPath(el),
                xpath: xPath(el),
                deep: !!inShadow,
                steps: loc.steps,
                rect: { x: rect.left, y: rect.top, w: rect.width, h: rect.height },
                frameChain: frameChain.slice(),
                inShadow: inShadow,
              },
            });
          }
        }
      }
      // recurse into an open shadow root (feature-detected)
      sr = el.shadowRoot;
      if (sr) collectFields(sr, frameChain, true, includeHidden, kinds, acc);
      // recurse into same-origin iframes
      if (el.tagName === "IFRAME") {
        var doc = null;
        try { doc = el.contentDocument; } catch (xErr) { doc = null; }
        if (doc) {
          collectFields(doc, frameChain.concat([iframeSelector(el)]), inShadow,
            includeHidden, kinds, acc);
        }
      }
    }
  }

  // A CSS selector that identifies an iframe within its parent document, for the
  // Python-side frame switcher (resolver.py keys off this chain).
  function iframeSelector(el) {
    var id = el.getAttribute("id");
    if (id) return "#" + cssEscape(id);
    var name = el.getAttribute("name");
    if (name) return 'iframe[name="' + cssAttrValue(name) + '"]';
    var src = el.getAttribute("src");
    if (src) return 'iframe[src="' + cssAttrValue(src) + '"]';
    return "iframe";
  }

  function listFields(opts) {
    opts = opts || {};
    var kinds = opts.kinds || null;
    var includeHidden = !!opts.includeHidden;
    var acc = [];
    collectFields(document, [], false, includeHidden, kinds, acc);
    // dedup by element (most specific kind already chosen per element), assign indices
    var seen = [], out = [], i, item;
    for (i = 0; i < acc.length; i++) {
      item = acc[i];
      if (seen.indexOf(item.el) < 0) {
        seen.push(item.el);
        item.descriptor.index = out.length;
        out.push(item.descriptor);
      }
    }
    return out;
  }

  // ------------------------------------------------------------------
  // Numbered field highlight (window.__visus.highlightFields / clearHighlights)
  // ------------------------------------------------------------------

  var KIND_COLORS = {
    "input": "#2563eb", "textarea": "#2563eb", "editable": "#2563eb",
    "button": "#16a34a", "link": "#9333ea",
    "checkbox": "#ea580c", "radio": "#ea580c",
    "select": "#0d9488", "dropdown": "#0d9488",
  };
  function kindColor(kind) {
    return KIND_COLORS[kind] || "#6b7280";
  }

  var _fieldOverlay = { nodes: [], items: null, onScroll: null, raf: 0, scrollX: 0, scrollY: 0 };

  // Absolute (document-relative) rect for a field, adding same-origin iframe offsets.
  // The viewport rect in `item.rect` is FROZEN at capture time; the boxes are
  // position:absolute (document coordinates), so the document offset must be baked
  // ONCE using the scroll position present when listFields ran. Re-adding the LIVE
  // window.pageXOffset/pageYOffset on every reposition would drift every box by the
  // scroll delta on scroll. We therefore use the captured scroll offset constant.
  function absoluteRect(item) {
    var x = item.rect.x, y = item.rect.y;
    var chain = item.frameChain || [];
    var doc = document, j;
    for (j = 0; j < chain.length; j++) {
      var fr = doc.querySelector(chain[j]);
      if (!fr) break;
      var fb = fr.getBoundingClientRect();
      x += fb.left;
      y += fb.top;
      try { doc = fr.contentDocument || doc; } catch (e) { /* cross-origin */ }
    }
    return {
      left: x + _fieldOverlay.scrollX,
      top: y + _fieldOverlay.scrollY,
      w: item.rect.w,
      h: item.rect.h,
    };
  }

  function renderFieldOverlay() {
    clearOverlayNodes();
    var items = _fieldOverlay.items;
    if (!items || !items.length) return;
    var body = document.body || document.documentElement;
    var i;
    for (i = 0; i < items.length; i++) {
      var it = items[i];
      if (!it.rect || (it.rect.w <= 0 && it.rect.h <= 0)) continue;
      var ar = absoluteRect(it);
      var color = kindColor(it.kind);
      var box = document.createElement("div");
      box.setAttribute("data-visus-field", "1");
      box.style.cssText =
        "position:absolute;z-index:2147483646;pointer-events:none;box-sizing:border-box;" +
        "border:2px solid " + color + ";border-radius:2px;" +
        "left:" + ar.left + "px;top:" + ar.top + "px;" +
        "width:" + ar.w + "px;height:" + ar.h + "px;";
      var badge = document.createElement("div");
      badge.setAttribute("data-visus-field", "1");
      badge.appendChild(document.createTextNode(String(it.index)));
      badge.style.cssText =
        "position:absolute;z-index:2147483647;pointer-events:none;" +
        "font:bold 11px/14px sans-serif;color:#fff;background:" + color + ";" +
        "padding:0 4px;border-radius:2px;min-width:14px;text-align:center;" +
        "left:" + ar.left + "px;top:" + Math.max(0, ar.top - 14) + "px;";
      body.appendChild(box);
      body.appendChild(badge);
      _fieldOverlay.nodes.push(box);
      _fieldOverlay.nodes.push(badge);
    }
  }

  function clearOverlayNodes() {
    var n = document.querySelectorAll("[data-visus-field]");
    for (var i = 0; i < n.length; i++) {
      if (n[i].parentNode) n[i].parentNode.removeChild(n[i]);
    }
    _fieldOverlay.nodes = [];
  }

  function scheduleReposition() {
    if (_fieldOverlay.raf) return;
    _fieldOverlay.raf = requestAnimationFrame(function () {
      _fieldOverlay.raf = 0;
      renderFieldOverlay();
    });
  }

  function highlightFields(list) {
    clearHighlights();
    if (!list || !list.length) return;
    _fieldOverlay.items = list;
    // Bake the document offset present at capture time so absolute boxes stay pinned
    // to the document on scroll (re-adding the live offset on reposition would drift).
    _fieldOverlay.scrollX = window.pageXOffset || 0;
    _fieldOverlay.scrollY = window.pageYOffset || 0;
    renderFieldOverlay();
    _fieldOverlay.onScroll = function () { scheduleReposition(); };
    window.addEventListener("scroll", _fieldOverlay.onScroll, true);
    window.addEventListener("resize", _fieldOverlay.onScroll, true);
  }

  function clearHighlights() {
    if (_fieldOverlay.onScroll) {
      window.removeEventListener("scroll", _fieldOverlay.onScroll, true);
      window.removeEventListener("resize", _fieldOverlay.onScroll, true);
      _fieldOverlay.onScroll = null;
    }
    if (_fieldOverlay.raf) {
      cancelAnimationFrame(_fieldOverlay.raf);
      _fieldOverlay.raf = 0;
    }
    clearOverlayNodes();
    _fieldOverlay.items = null;
  }

  window.__visus = {
    queryAll: queryAll,
    elementState: elementState,
    role: computeRole,
    accessibleName: accessibleName,
    normText: normText,
    attrText: attrText,
    clickablePoint: clickablePoint,
    hitTarget: hitTarget,
    checkStable: checkStable,
    snapshot: snapshot,
    highlight: highlight,
    unhighlight: unhighlight,
    listFields: listFields,
    highlightFields: highlightFields,
    clearHighlights: clearHighlights,
  };
})();
