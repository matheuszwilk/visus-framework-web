(function () {
  "use strict";
  if (window.__visus) return;

  function normWs(s) {
    return (s || "").replace(/ /g, " ").replace(/\s+/g, " ").trim();
  }
  function normText(el) {
    return normWs(el.textContent || "");
  }

  var NAME_FROM_CONTENT = new Set([
    "button", "link", "heading", "menuitem", "menuitemcheckbox", "menuitemradio",
    "option", "tab", "treeitem", "cell", "columnheader", "rowheader", "gridcell",
    "checkbox", "radio", "switch", "row", "tooltip", "listitem",
  ]);

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
    if (NAME_FROM_CONTENT.has(computeRole(el))) {
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
    if (!(el instanceof Element)) return false;
    var style = getComputedStyle(el);
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
          out.push.apply(out, base.querySelectorAll(step.value));
        }
      } else if (step.kind === "xpath") {
        for (r = 0; r < roots.length; r++) {
          var ctx = (roots[r] === document) ? document : roots[r];
          var res = document.evaluate(step.value, ctx, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
          for (j = 0; j < res.snapshotLength; j++) out.push(res.snapshotItem(j));
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
  };
})();
