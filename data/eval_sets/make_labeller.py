"""Build a self-contained HTML page for hand-labelling (or reviewing) an exported posting sample.

    python data/eval_sets/make_labeller.py data/eval_sets/extraction_v1.draft.jsonl

Writes labeller.html next to the input. Open it in a browser, label or review every posting,
then click "Download JSONL" and save the file as data/eval_sets/extraction_v1.jsonl. Progress
is kept in the browser's local storage under a key derived from the input file name, so
regenerating the page (for example after a taxonomy change) keeps existing work. "Load JSONL"
restores labels from a previously downloaded file.

The page never shows the extractor's output, so labels are not anchored on what the model
found. Review flags are computed from the posting text, the taxonomy aliases and the labels
selected so far (see FLAGS in the page script).
"""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "apps" / "api" / "app" / "seed" / "data" / "skills.json"

# Skills added after the draft labels were written. Postings that mention one of them get a
# review flag. Extend this when the taxonomy changes during labelling.
TAXONOMY_CHANGES = {
    "2026-11-21": [
        "test-automation",
        "manual-testing",
        "exploratory-testing",
        "regression-testing",
        "react-native",
        "tailwind-css",
        "pega",
        "pega-smart-dispute",
    ],
}

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Skill Labeller</title>
<style>
:root{--bg:#fafaf9;--fg:#1c1917;--muted:#6b645f;--card:#fff;--line:#e7e5e4;--acc:#2563eb;--on:#dbeafe;--warn:#b45309;--warnbg:#fef3c7;--ok:#15803d;--mark:#fde68a}
@media (prefers-color-scheme:dark){:root{--bg:#1c1917;--fg:#f5f5f4;--muted:#a8a29e;--card:#292524;--line:#44403c;--acc:#60a5fa;--on:#1e3a5f;--warn:#fbbf24;--warnbg:#422006;--ok:#4ade80;--mark:#854d0e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--bg);display:flex;gap:8px 12px;align-items:center;flex-wrap:wrap;padding:10px 16px;border-bottom:1px solid var(--line)}
input,select,button{font:inherit}
input[type=text],input[type=number],input[type=search],select{padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg)}
button{padding:6px 12px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer;min-height:34px}
button.primary{background:var(--acc);color:#fff;border-color:var(--acc)}
:focus-visible{outline:3px solid var(--acc);outline-offset:2px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
#strip{display:flex;flex-wrap:wrap;gap:3px;padding:8px 16px;border-bottom:1px solid var(--line)}
#strip button{min-height:0;width:14px;height:14px;padding:0;border-radius:3px}
#strip .rev{background:var(--ok);border-color:var(--ok)}#strip .exc{background:var(--muted)}#strip .flag{border:2px solid var(--warn)}
#strip .cur{outline:2px solid var(--fg);outline-offset:1px}
main{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:16px;padding:16px;align-items:start}
@media (max-width:860px){main{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}
#desc{white-space:pre-wrap;max-height:62vh;overflow:auto;padding-right:6px}
@media (max-width:860px){#desc{max-height:none}}
.side{position:sticky;top:70px}@media (max-width:860px){.side{position:static}}
.muted{color:var(--muted);font-size:13px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.chip{padding:3px 10px;border-radius:999px;border:1px solid var(--line);cursor:pointer;font-size:13px;background:var(--card);color:var(--fg);min-height:28px}
.chip.on{background:var(--on);border-color:var(--acc)}.chip.unknown{border-color:var(--warn);color:var(--warn)}
#list{max-height:40vh;overflow:auto;border-top:1px solid var(--line);margin-top:8px}
.cat{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:10px 0 2px}
.flags{background:var(--warnbg);color:var(--fg);border:1px solid var(--warn);border-radius:8px;padding:8px 12px;margin:10px 0;font-size:14px}
.flags ul{margin:4px 0 0;padding-left:18px}
mark{background:var(--mark);color:inherit;border-radius:2px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.status{font-weight:600}.status.ok{color:var(--ok)}
details{margin-top:12px}
</style></head><body>
<header>
  <strong>Skill labeller</strong>
  <span id="progress" class="muted" aria-live="polite"></span>
  <label class="muted">Initials <input id="who" type="text" size="6" autocomplete="off"></label>
  <button id="prev" title="Previous (←)">&larr; Prev</button>
  <label class="muted">Go to <input id="jump" type="number" min="1" style="width:5em" aria-label="Go to posting number"></label>
  <button id="next" title="Next (→)">Next &rarr;</button>
  <button id="nextTodo" title="Next not reviewed (n)">Next to review</button>
  <button id="nextFlag" title="Next flagged (f)">Next flagged</button>
  <button class="primary" id="download">Download JSONL</button>
  <label class="muted"><input type="file" id="load" accept=".jsonl,.json,application/jsonl" class="sr"><span role="button" tabindex="0" id="loadBtn" style="text-decoration:underline;cursor:pointer">Load JSONL</span></label>
</header>
<nav id="strip" aria-label="All postings"></nav>
<main>
  <section class="card">
    <div class="muted" id="pid"></div>
    <h2 id="title" style="margin:4px 0 8px"></h2>
    <div id="flags"></div>
    <div id="desc"></div>
  </section>
  <section class="card side">
    <div class="row">
      <span id="status" class="status"></span>
      <button class="primary" id="review" title="Mark reviewed and go to the next posting (r)">Mark reviewed &amp; next</button>
      <label class="muted"><input type="checkbox" id="exclude"> Not a usable job ad (exclude)</label>
    </div>
    <div class="muted" style="margin-top:10px">Selected skills (<span id="selCount">0</span>):</div>
    <div id="selected" class="chips" aria-live="polite"></div>
    <label class="row muted"><input type="checkbox" id="hl"> Highlight selected skills in the text</label>
    <div class="row" style="margin-top:8px">
      <input id="search" type="search" placeholder="Search skills or aliases (/ to focus, Enter adds first)" autocomplete="off" style="flex:1;min-width:12em" aria-label="Search skills">
      <select id="cat" aria-label="Filter by category"><option value="">All categories</option></select>
    </div>
    <div id="list"></div>
    <details><summary class="muted">Labelling rules</summary><ul class="muted">
      <li>Label only skills explicitly mentioned in the posting. A role name in the title is not a skill ("DevOps Engineer", "Data Analyst"); a technology named in the title is ("Frontend Developer (React)").</li>
      <li>Skip mentions that only describe the company ("we are a Snowflake partner").</li>
      <li>Most specific skill only; never add implied parents (PostgreSQL, not SQL; React Native, not React; Tailwind CSS, not CSS).</li>
      <li>Manual, exploratory and regression testing are not test automation. Selenium, Cypress and Playwright are test automation.</li>
      <li>Meaning matters: "react to", "go through", data-centre "networking" equipment, "Oracle ERP" are not the skills.</li>
      <li>Words cut off by "…" are not labelled. Full guide: data/eval_sets/README.md.</li>
    </ul></details>
  </section>
</main>
<script>
const POSTINGS = __POSTINGS__;
const SKILLS = __SKILLS__;
const CHANGES = __CHANGES__;
const KEY = "labeller:" + __NAME__;
const BY_SLUG = Object.fromEntries(SKILLS.map(s => [s.slug, s]));
const NEW_SKILLS = Object.entries(CHANGES).flatMap(([day, slugs]) => slugs.map(slug => ({slug, day})));
const $ = id => document.getElementById(id);
const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const aliasRe = a => new RegExp("(?<![a-z0-9])" + esc(a) + "(?![a-z0-9])", "i");
const RE = Object.fromEntries(SKILLS.map(s => [s.slug, s.aliases.map(aliasRe)]));

let state = {i: 0, who: "", labels: {}, excluded: {}, visited: {}};
try { state = Object.assign(state, JSON.parse(localStorage.getItem(KEY) || "{}")); } catch (e) {}
// Pages before 2026-11-21 had no explicit "reviewed" mark: moving past a posting was the review.
if (!state.reviewed) state.reviewed = Object.assign({}, state.visited || {});
state.i = Math.max(0, Math.min(POSTINGS.length - 1, state.i | 0));
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} };

const cur = () => POSTINGS[state.i];
const labelsOf = p => state.labels[p.id] || (p.skills || []);
function setLabels(p, list) { state.labels[p.id] = [...new Set(list)]; save(); }
function toggle(slug) {
  const c = labelsOf(cur()); const k = c.indexOf(slug);
  setLabels(cur(), k < 0 ? [...c, slug] : c.filter(s => s !== slug)); render();
}

function hits(slug, text) { return (RE[slug] || []).some(r => r.test(text)); }
function firstAlias(slug, text) {
  const s = BY_SLUG[slug]; if (!s) return null;
  for (let k = 0; k < s.aliases.length; k++) if (RE[slug][k].test(text)) return s.aliases[k];
  return null;
}
// Review flags: hints for the reviewer, never automatic label changes.
function flagsOf(p) {
  const out = []; const t = p.title || ""; const d = p.description || ""; const all = t + "\n" + d;
  const sel = labelsOf(p);
  for (const slug of sel) {
    const s = BY_SLUG[slug];
    if (!s) { out.push(`"${slug}" is no longer in the taxonomy. Pick its replacement.`); continue; }
    if (!hits(slug, all)) out.push(`${s.name} is selected but none of its aliases appear in the text. Keep only if the text clearly means it.`);
    else if (!hits(slug, d)) out.push(`${s.name} appears only in the title. Keep if it names a technology; remove if it is part of a role name.`);
  }
  for (const {slug, day} of NEW_SKILLS) {
    if (sel.includes(slug) || !BY_SLUG[slug]) continue;
    const a = firstAlias(slug, all);
    if (a) out.push(`New skill since ${day}: ${BY_SLUG[slug].name} ("${a}" in the text).`);
  }
  if (p.notes) out.push("Draft note: " + p.notes);
  return out;
}

function highlight(text, patterns) {
  const frag = document.createDocumentFragment();
  if (!patterns.length) { frag.append(text); return frag; }
  const re = new RegExp(patterns.map(p => "(?<![a-z0-9])(?:" + p + ")(?![a-z0-9])").join("|"), "gi");
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m[0] === "") { re.lastIndex++; continue; }
    frag.append(text.slice(last, m.index));
    const mk = document.createElement("mark"); mk.textContent = m[0]; frag.append(mk);
    last = m.index + m[0].length;
  }
  frag.append(text.slice(last));
  return frag;
}

function renderStrip() {
  const strip = $("strip"); strip.innerHTML = "";
  POSTINGS.forEach((p, i) => {
    const b = document.createElement("button");
    const st = state.excluded[p.id] ? "exc" : state.reviewed[p.id] ? "rev" : "";
    const fl = flagsOf(p).length && !state.reviewed[p.id] ? " flag" : "";
    b.className = st + fl + (i === state.i ? " cur" : "");
    b.title = `${i + 1}: ${p.title}` + (st === "rev" ? " (reviewed)" : st === "exc" ? " (excluded)" : "");
    b.setAttribute("aria-label", b.title);
    b.onclick = () => goTo(i); strip.appendChild(b);
  });
}

function render() {
  const p = cur(); const sel = labelsOf(p);
  const reviewed = POSTINGS.filter(x => state.reviewed[x.id]).length;
  const excluded = POSTINGS.filter(x => state.excluded[x.id]).length;
  $("progress").textContent = `Posting ${state.i + 1} / ${POSTINGS.length} · reviewed ${reviewed} · excluded ${excluded}`;
  $("pid").textContent = p.id + (p.draft_by ? ` · draft by ${p.draft_by}` : "");
  $("who").value = state.who; $("jump").value = state.i + 1;
  $("exclude").checked = !!state.excluded[p.id];
  $("status").textContent = state.reviewed[p.id] ? "✓ Reviewed" : "Not reviewed";
  $("status").className = "status" + (state.reviewed[p.id] ? " ok" : "");

  const q = $("search").value.trim().toLowerCase();
  const pats = [];
  if ($("hl").checked) sel.forEach(slug => (BY_SLUG[slug]?.aliases || []).forEach(a => pats.push(esc(a))));
  if (q.length >= 2) pats.push(esc(q));
  $("title").replaceChildren(highlight(p.title, pats));
  $("desc").replaceChildren(highlight(p.description, pats));

  const fl = flagsOf(p); const box = $("flags"); box.innerHTML = "";
  if (fl.length) {
    const div = document.createElement("div"); div.className = "flags"; div.setAttribute("role", "note");
    div.append("Check before marking reviewed:");
    const ul = document.createElement("ul"); fl.forEach(f => { const li = document.createElement("li"); li.textContent = f; ul.appendChild(li); });
    div.appendChild(ul); box.appendChild(div);
  }

  const selBox = $("selected"); selBox.innerHTML = ""; $("selCount").textContent = sel.length;
  sel.slice().sort().forEach(slug => {
    const s = BY_SLUG[slug]; const b = document.createElement("button");
    b.className = "chip on" + (s ? "" : " unknown"); b.setAttribute("aria-pressed", "true");
    b.textContent = (s ? s.name : slug + " (not in taxonomy)") + " ×";
    b.setAttribute("aria-label", "Remove " + (s ? s.name : slug)); b.onclick = () => toggle(slug); selBox.appendChild(b);
  });

  const cat = $("cat").value; const list = $("list"); list.innerHTML = "";
  const matches = SKILLS.filter(s => (!cat || s.category === cat) &&
    (!q || s.name.toLowerCase().includes(q) || s.slug.includes(q) || s.aliases.some(a => a.includes(q))));
  list.dataset.first = matches.length ? matches[0].slug : "";
  let lastCat = null;
  matches.forEach(s => {
    if (s.category !== lastCat) { const h = document.createElement("div"); h.className = "cat"; h.textContent = s.category; list.appendChild(h); lastCat = s.category; }
    const on = sel.includes(s.slug); const b = document.createElement("button");
    b.className = "chip" + (on ? " on" : ""); b.setAttribute("aria-pressed", String(on));
    const via = q && !s.name.toLowerCase().includes(q) ? s.aliases.find(a => a.includes(q)) : null;
    b.textContent = s.name + (via ? ` · "${via}"` : "");
    b.title = (s.parent ? `Child of ${BY_SLUG[s.parent]?.name || s.parent}. ` : "") + "Aliases: " + s.aliases.join(", ");
    b.onclick = () => toggle(s.slug); list.appendChild(b);
  });
  if (!matches.length) list.textContent = "No skill matches. Skills outside the taxonomy are not labelled.";
  renderStrip();
}

function goTo(i) {
  state.visited[cur().id] = true;
  state.i = Math.max(0, Math.min(POSTINGS.length - 1, i));
  $("search").value = ""; save(); render(); window.scrollTo(0, 0);
}
function findFrom(pred) {
  for (let k = 1; k <= POSTINGS.length; k++) { const i = (state.i + k) % POSTINGS.length; if (pred(POSTINGS[i])) return i; }
  return -1;
}
const todo = p => !state.reviewed[p.id] && !state.excluded[p.id];
function nextTodo() { const i = findFrom(todo); i < 0 ? alert("Every posting is reviewed or excluded.") : goTo(i); }
function nextFlag() { const i = findFrom(p => todo(p) && flagsOf(p).length); i < 0 ? alert("No flagged posting left to review.") : goTo(i); }
function markReviewed() {
  const p = cur(); if (!state.labels[p.id]) state.labels[p.id] = (p.skills || []).slice();
  state.reviewed[p.id] = true; save();
  const i = findFrom(todo); i < 0 ? render() : goTo(i);
}

$("prev").onclick = () => goTo(state.i - 1); $("next").onclick = () => goTo(state.i + 1);
$("nextTodo").onclick = nextTodo; $("nextFlag").onclick = nextFlag; $("review").onclick = markReviewed;
$("jump").onchange = e => { const n = parseInt(e.target.value, 10); if (n >= 1 && n <= POSTINGS.length) goTo(n - 1); };
$("search").oninput = render; $("cat").onchange = render; $("hl").onchange = render;
$("search").onkeydown = e => {
  if (e.key === "Enter" && $("list").dataset.first) { toggle($("list").dataset.first); $("search").select(); }
  if (e.key === "Escape") { $("search").value = ""; render(); }
};
$("who").oninput = e => { state.who = e.target.value.trim(); save(); };
$("exclude").onchange = e => { state.excluded[cur().id] = e.target.checked; save(); render(); };
[...new Set(SKILLS.map(s => s.category))].sort().forEach(c => { const o = document.createElement("option"); o.value = o.textContent = c; $("cat").appendChild(o); });

$("download").onclick = () => {
  if (!state.who) { alert("Enter your initials first."); $("who").focus(); return; }
  const kept = POSTINGS.filter(p => !state.excluded[p.id]);
  const unreviewed = kept.filter(p => !state.reviewed[p.id]).length;
  const excluded = POSTINGS.length - kept.length;
  const msg = `${kept.length} postings will be exported (${excluded} excluded).` +
    (unreviewed ? `\n${unreviewed} are NOT reviewed yet; they are exported with "not reviewed" in labelled_by.` : "") + "\nDownload?";
  if (!confirm(msg)) return;
  const today = new Date().toISOString().slice(0, 10);
  const seen = new Set();
  const lines = [];
  for (const p of kept) {
    if (seen.has(p.id)) continue; seen.add(p.id);
    const by = state.reviewed[p.id]
      ? (p.draft_by ? `${p.draft_by} (draft), reviewed by ${state.who}` : state.who)
      : (p.draft_by ? `${p.draft_by} (draft), not reviewed` : `${state.who} (not reviewed)`);
    lines.push(JSON.stringify({id: p.id, title: p.title, description: p.description,
      skills: [...new Set(labelsOf(p))].sort(), labelled_by: by, labelled_at: today}));
  }
  const blob = new Blob([lines.join("\n") + "\n"], {type: "application/jsonl"});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "extraction_v1.jsonl"; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};

$("loadBtn").onclick = () => $("load").click();
$("loadBtn").onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("load").click(); } };
$("load").onchange = async e => {
  const file = e.target.files[0]; if (!file) return;
  const ids = new Set(POSTINGS.map(p => p.id)); let rows = [];
  try { rows = (await file.text()).split(/\r?\n/).filter(l => l.trim()).map(l => JSON.parse(l)); }
  catch (err) { alert("Not a valid JSONL file: " + err.message); return; }
  const usable = rows.filter(r => ids.has(r.id) && Array.isArray(r.skills));
  const changed = usable.filter(r => state.labels[r.id] && JSON.stringify([...state.labels[r.id]].sort()) !== JSON.stringify([...r.skills].sort())).length;
  if (!confirm(`${usable.length} of ${rows.length} rows match postings on this page; ${changed} differ from labels saved in this browser and will be replaced. Load?`)) return;
  for (const r of usable) {
    state.labels[r.id] = [...new Set(r.skills)];
    if (/reviewed by/.test(r.labelled_by || "") || (r.labelled_by && !/draft|not reviewed/.test(r.labelled_by))) state.reviewed[r.id] = true;
  }
  save(); render(); e.target.value = "";
};

document.addEventListener("keydown", e => {
  if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) return;
  if (e.key === "ArrowRight") goTo(state.i + 1); else if (e.key === "ArrowLeft") goTo(state.i - 1);
  else if (e.key === "n") nextTodo(); else if (e.key === "f") nextFlag(); else if (e.key === "r") markReviewed();
  else if (e.key === "/") { e.preventDefault(); $("search").focus(); }
});
render();
</script></body></html>
"""


def build(src: Path) -> tuple[str, list[str]]:
    postings = [
        json.loads(line)
        for line in src.read_text(encoding="utf-8").splitlines()
        if line
    ]
    dupes = [i for i, n in Counter(p["id"] for p in postings).items() if n > 1]
    if dupes:
        raise SystemExit(f"Duplicate posting ids in {src.name}: {dupes}")
    raw_skills = json.loads(SKILLS.read_text(encoding="utf-8"))["skills"]
    skills = [
        {
            "slug": s["slug"],
            "name": s["name"],
            "category": s["category"],
            "parent": s.get("parent"),
            "aliases": [
                (a if isinstance(a, str) else a["alias"]).lower() for a in s["aliases"]
            ],
        }
        for s in raw_skills
    ]
    skills.sort(key=lambda s: (s["category"], s["name"].lower()))
    known = {s["slug"] for s in skills}
    warnings = [
        f"{p['id']}: label '{slug}' is not in the taxonomy"
        for p in postings
        for slug in p.get("skills", [])
        if slug not in known
    ]
    html = (
        PAGE.replace("__POSTINGS__", json.dumps(postings).replace("</", "<\\/"))
        .replace("__SKILLS__", json.dumps(skills))
        .replace("__CHANGES__", json.dumps(TAXONOMY_CHANGES))
        .replace("__NAME__", json.dumps(src.stem))
    )
    return html, warnings


def main() -> None:
    src = Path(sys.argv[1])
    html, warnings = build(src)
    out = src.with_name("labeller.html")
    out.write_text(html, encoding="utf-8")
    for w in warnings:
        print("warning:", w)
    print(f"Wrote {out} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
