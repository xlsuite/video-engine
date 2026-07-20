#!/usr/bin/env python3
"""
DISCOVERY — run this AFTER transcribe.py.

It reads the `transcripts/` folder, turns the subtitles into clean, timecoded
quotes, and produces (into a `discovery/` subfolder):

    - Quote Index.html    a searchable, filterable, click-to-copy quote browser
    - Discovery Brief.md  themes, recurring people, strongest soundbites, angles

Two modes, chosen automatically:
    * SMART  - if an ANTHROPIC_API_KEY is set, Claude finds the themes, groups
               the quotes by meaning, and writes the brief (like a human pass).
    * OFFLINE- if no key, it still builds the full searchable index and groups
               quotes by keyword frequency. Free and private, but the theme
               grouping is word-based, not meaning-based.

Usage:
    python discover.py                  # analyze ./transcripts
    python discover.py "D:\\path"        # a different shoot folder
    python discover.py --offline        # force offline even if a key is set
    python discover.py --model claude-sonnet-4-6
"""

import os
import re
import sys
import json
import glob
import argparse
import datetime
from collections import Counter, defaultdict

# ---------------------------------------------------------------- SRT parsing

TC = re.compile(r"(\d\d):(\d\d):(\d\d)[,.](\d\d\d)\s*-->")

def tc_to_sec(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

def sec_to_tc(sec):
    sec = int(sec)
    return f"{sec//3600:02d}:{(sec%3600)//60:02d}:{sec%60:02d}"

def parse_srt(path):
    """Return list of (start_sec, text)."""
    out = []
    cur_start, cur_text = None, []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                m = TC.search(line)
                if m:
                    if cur_start is not None and cur_text:
                        out.append((cur_start, " ".join(cur_text).strip()))
                    cur_start = tc_to_sec(*m.groups())
                    cur_text = []
                elif line.strip() and not line.strip().isdigit():
                    cur_text.append(line.strip())
        if cur_start is not None and cur_text:
            out.append((cur_start, " ".join(cur_text).strip()))
    except Exception as e:
        print(f"  ! couldn't read {path}: {e}")
    return out

# ------------------------------------------------------- quote assembly

SENT_END = (".", "?", "!")

def assemble_quotes(segments):
    """Merge tiny subtitle lines into quote-sized units, keeping the start tc."""
    quotes = []
    buf, buf_start = [], None
    def words(s):
        return len(s.split())
    for start, text in segments:
        if not text:
            continue
        if buf_start is None:
            buf_start = start
        buf.append(text)
        joined = " ".join(buf)
        if (joined.rstrip().endswith(SENT_END) and words(joined) >= 8) or words(joined) >= 45:
            quotes.append((buf_start, joined.strip()))
            buf, buf_start = [], None
    if buf:
        quotes.append((buf_start, " ".join(buf).strip()))
    return [(s, t) for (s, t) in quotes if len(t.split()) >= 4]

def collect(transcripts_dir):
    quotes = []
    qid = 0
    srts = sorted(glob.glob(os.path.join(transcripts_dir, "**", "*.srt"), recursive=True))
    for srt in srts:
        rel = os.path.relpath(srt, transcripts_dir)
        clip = os.path.splitext(os.path.basename(srt))[0]
        folder = os.path.dirname(rel).replace("\\", "/")
        segs = parse_srt(srt)
        for start, text in assemble_quotes(segs):
            qid += 1
            quotes.append({
                "id": f"L{qid:04d}", "clip": clip, "folder": folder,
                "tc": sec_to_tc(start), "sec": start, "text": text,
                "theme": None, "who": "", "notable": False,
            })
    return quotes

# ------------------------------------------------------- offline analysis

STOP = set("""a an the and or but so of to in on at for with from by as is are was were be been
being it its this that these those i you he she we they them his her our your their me my mine ok okay
yeah yes no not just like really very much more most some any all out up down here there what when where
who how why which there's it's i'm you're we're they're don't didn't can't gonna wanna kind got get gets
about into over than then them they're im dont thats theres youre were well right gonna get like know think
mean stuff things thing one two three he's she's we've i've you've say said says going go went come came
have has had having that's because good want wanted wants nice will would could should doing does did done
actually little big guys guy fucking fuck shit gotta really pretty things thing yeah well right knows mean
means likes liked kinda okay sure maybe basically literally honestly exactly anyway something someone
everything anything nothing people person lot bit bunch first second last next even still many every your
yours you'll we'll that'll day today year years week weeks time times make makes made take takes took
going look looks looking see saw seen give gave tell told talk talked put thank thanks hello uh um very
also back now then i'll we're they'd i'd he'd let lets gonna stuff dude man guys yeah cool great love
fun thing things bro guys nope yep huh wow hey oh ah other others another whatever whoever
none isn't aren't wasn't won't they've doesn't couldn't wouldn't shouldn't""".split())

def offline_analyze(quotes, top_n_themes=8):
    freq = Counter()
    for q in quotes:
        for w in re.findall(r"[a-zA-Z']{4,}", q["text"].lower()):
            if w not in STOP:
                freq[w] += 1
    keywords = [w for w, _ in freq.most_common(top_n_themes) if w != "other"]
    names = {k.capitalize() for k in keywords}
    themes = [{"name": k.capitalize(), "desc": f"Quotes mentioning '{k}'."} for k in keywords]
    for q in quotes:
        low = q["text"].lower()
        q["theme"] = next((k.capitalize() for k in keywords if k in low), "Other")
        q["notable"] = len(q["text"].split()) >= 12
    if "Other" not in names and any(q["theme"] == "Other" for q in quotes):
        themes.append({"name": "Other", "desc": "Everything else."})
    brief = offline_brief(quotes, themes, freq)
    return themes, brief

def offline_brief(quotes, themes, freq):
    lines = ["# Discovery Brief (offline / keyword mode)\n",
             f"_Generated {datetime.date.today()} - {len(quotes)} quotes across "
             f"{len({q['clip'] for q in quotes})} clips._\n",
             "> No API key was set, so themes below are grouped by keyword frequency, "
             "not meaning. Set `ANTHROPIC_API_KEY` for a real thematic pass.\n",
             "## Top keywords\n",
             ", ".join(f"{w} ({c})" for w, c in freq.most_common(20)) + "\n",
             "## Quotes by keyword theme\n"]
    by = defaultdict(list)
    for q in quotes:
        by[q["theme"]].append(q)
    for t in themes:
        qs = sorted(by.get(t["name"], []), key=lambda x: -len(x["text"]))[:6]
        if not qs:
            continue
        lines.append(f"### {t['name']}  ({len(by[t['name']])} quotes)\n")
        for q in qs:
            lines.append(f"- \"{q['text']}\"  \n  `{q['clip']} @ {q['tc']}`")
        lines.append("")
    return "\n".join(lines)

# ------------------------------------------------------- smart (Claude) analysis

def _json_from(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.strip())
    a, b = text.find("{"), text.rfind("}")
    if a != -1 and b != -1:
        text = text[a:b + 1]
    return json.loads(text)

def smart_analyze(quotes, model):
    import anthropic
    client = anthropic.Anthropic()

    def call(prompt, max_tokens=8000):
        r = client.messages.create(model=model, max_tokens=max_tokens,
                                   messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")

    # 1) Derive a theme taxonomy from all the text
    all_text = "\n".join(q["text"] for q in quotes)
    if len(all_text) > 120000:
        all_text = all_text[:120000]
    tax_prompt = (
        "You are a documentary story producer reviewing raw transcript material from a "
        "field shoot (interviews, vlog, ambient conversation). Read the quotes below and "
        "identify the 5-9 strongest recurring THEMES that could structure a story.\n\n"
        'Return ONLY JSON: {"themes":[{"name":"short label","desc":"one sentence"}]}\n\n'
        "TRANSCRIPT:\n" + all_text
    )
    themes = _json_from(call(tax_prompt, 2000))["themes"]
    theme_names = [t["name"] for t in themes]

    # 2) Tag every quote against that taxonomy, in batches
    BATCH = 100
    for i in range(0, len(quotes), BATCH):
        batch = quotes[i:i + BATCH]
        numbered = "\n".join(f'{q["id"]} [{q["tc"]}] ({q["clip"]}): {q["text"]}' for q in batch)
        tag_prompt = (
            "Themes:\n" + "\n".join(f"- {n}" for n in theme_names) + "\n\n"
            "For each numbered line, assign the single best theme (use exactly one of the "
            'theme labels above, or "Other"), guess the speaker or context in 1-4 words if '
            'inferable (else ""), and mark notable=true if it is a strong, quotable soundbite.\n'
            'Return ONLY JSON: {"tags":{"L0001":{"theme":"...","who":"...","notable":true}}}\n\n'
            "LINES:\n" + numbered
        )
        try:
            tags = _json_from(call(tag_prompt, 8000)).get("tags", {})
        except Exception as e:
            print(f"  ! tagging batch {i//BATCH+1} failed ({e}); leaving untagged")
            tags = {}
        by_id = {q["id"]: q for q in batch}
        for qid, info in tags.items():
            if qid in by_id:
                by_id[qid]["theme"] = info.get("theme") or "Other"
                by_id[qid]["who"] = (info.get("who") or "").strip()
                by_id[qid]["notable"] = bool(info.get("notable"))
        print(f"  tagged {min(i+BATCH, len(quotes))}/{len(quotes)} quotes")
    for q in quotes:
        if not q["theme"]:
            q["theme"] = "Other"

    # 3) Write the brief from the tagged data
    by = defaultdict(list)
    for q in quotes:
        if q["notable"]:
            by[q["theme"]].append(q)
    digest = {}
    for t in theme_names + ["Other"]:
        digest[t] = [f'"{q["text"]}" - {q["who"] or "?"} ({q["clip"]} @ {q["tc"]})'
                     for q in by.get(t, [])[:14]]
    brief_prompt = (
        "You are a documentary story producer. Using the themes and their strongest quotes "
        "below, write a tight DISCOVERY BRIEF in Markdown for the director. Include, in this order:\n"
        "1. A 2-3 sentence overview of what this footage is.\n"
        "2. ## Themes - each theme as a ### heading with a 1-2 sentence take and its 2-3 best "
        "quotes (keep the `clip @ tc` tag on each quote).\n"
        "3. ## Recurring people / brands - who shows up and what they represent.\n"
        "4. ## Candidate narrative angles - 2-4 distinct ways to cut a story from this, each one line.\n"
        "5. ## Strongest single soundbites - the 5 lines you would build a trailer around (with `clip @ tc`).\n"
        "Be concrete and decisive. Do not invent quotes; only use what is given.\n\n"
        "THEMES:\n" + json.dumps(themes, indent=1) + "\n\n"
        "QUOTES BY THEME:\n" + json.dumps(digest, indent=1)
    )
    brief = call(brief_prompt, 6000)
    header = (f"_Generated {datetime.date.today()} with {model} - {len(quotes)} quotes across "
              f"{len({q['clip'] for q in quotes})} clips._\n\n")
    if not brief.lstrip().startswith("#"):
        brief = "# Discovery Brief\n\n" + brief
    brief = re.sub(r"(# .*\n)", r"\1\n" + header, brief, count=1)
    return themes, brief

# ------------------------------------------------------- HTML index

PALETTE = ["#7bbf6a", "#caa14a", "#c97b5a", "#b85c7a", "#5a9cc9",
           "#6ac9b8", "#9a7bcf", "#8a9298", "#d08a5a", "#5ab87a"]

def build_index(quotes, themes, out_path):
    theme_color = {}
    for i, t in enumerate(themes):
        theme_color[t["name"]] = PALETTE[i % len(PALETTE)]
    theme_color.setdefault("Other", "#8a9298")
    qs = sorted(quotes, key=lambda q: (not q["notable"], q["clip"], q["sec"]))
    data = [[q["text"], q["who"], q["theme"], q["clip"], q["tc"]] for q in qs]
    payload = {"themes": theme_color, "quotes": data}
    htmldoc = INDEX_TEMPLATE.replace("/*DATA*/", json.dumps(payload))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(htmldoc)

INDEX_TEMPLATE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Quote Index</title>
<style>
:root{--bg:#0f1110;--card:#1a1d1b;--line:#2c302d;--txt:#e8eae8;--muted:#9aa39c;--accent:#7bbf6a;--accent2:#3a7d44}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
header{padding:22px 26px 14px;border-bottom:1px solid var(--line);position:sticky;top:0;background:#0f1110;z-index:5}
h1{margin:0 0 2px;font-size:20px}.sub{color:var(--muted);font-size:13px}
.controls{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;align-items:center}
input[type=search]{flex:1;min-width:220px;background:var(--card);border:1px solid var(--line);color:var(--txt);padding:9px 12px;border-radius:9px;font-size:14px;outline:none}
input[type=search]:focus{border-color:var(--accent2)}.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{background:var(--card);border:1px solid var(--line);color:var(--muted);padding:6px 11px;border-radius:20px;font-size:12.5px;cursor:pointer;user-select:none}
.chip:hover{border-color:var(--accent2);color:var(--txt)}.chip.on{background:var(--accent2);border-color:var(--accent);color:#fff}
.count{color:var(--muted);font-size:12.5px;margin-left:auto}main{padding:18px 26px 80px;max-width:1100px;margin:0 auto}
.q{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:0 0 11px;cursor:pointer}
.q:hover{border-color:var(--accent2)}.q .text{font-size:15.5px;margin:0 0 9px}
.meta{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12.5px;color:var(--muted)}
.tag{border:1px solid var(--line);border-radius:6px;padding:2px 8px}.who{color:var(--txt);font-weight:600}
.tc{font-family:ui-monospace,Menlo,monospace;color:var(--accent);background:#0f1110;border:1px solid var(--line);border-radius:6px;padding:2px 8px}
.src{font-family:ui-monospace,monospace;color:var(--muted);font-size:11.5px}.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--accent2);color:#fff;padding:9px 18px;border-radius:24px;font-size:13px;opacity:0;pointer-events:none;transition:.2s}
.toast.show{opacity:1}.empty{color:var(--muted);text-align:center;padding:50px 0}
footer{color:var(--muted);font-size:12px;padding:0 26px 30px;max-width:1100px;margin:0 auto}
</style></head><body>
<header><h1>Quote Index</h1><div class="sub">Click any card to copy its source + timecode. Filter by theme, or search.</div>
<div class="controls"><input id="search" type="search" placeholder="Search quotes, speakers, themes...">
<div class="chips" id="chips"></div><span class="count" id="count"></span></div></header>
<main id="list"></main>
<footer>Auto-generated from the shoot's transcripts. Timecodes are the in-point of the line in its clip;
in long interviews treat them as "scrub to roughly here." The matching <code>.srt</code> has every line.</footer>
<div class="toast" id="toast"></div>
<script>
const D=/*DATA*/;const THEMES=D.themes,Q=D.quotes;
let activeTheme=null,term="";
const list=document.getElementById('list'),chipsEl=document.getElementById('chips'),countEl=document.getElementById('count'),toast=document.getElementById('toast');
Object.keys(THEMES).forEach(t=>{const c=document.createElement('span');c.className='chip';c.textContent=t;
c.onclick=()=>{activeTheme=activeTheme===t?null:t;[...chipsEl.children].forEach(x=>x.classList.toggle('on',x.textContent===activeTheme));render();};chipsEl.appendChild(c);});
document.getElementById('search').addEventListener('input',e=>{term=e.target.value.toLowerCase();render();});
function esc(s){return (s||'').replace(/[&<>]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[m]));}
function render(){list.innerHTML='';
const rows=Q.filter(q=>{if(activeTheme&&q[2]!==activeTheme)return false;
if(term){return (q[0]+' '+q[1]+' '+q[2]).toLowerCase().includes(term);}return true;});
countEl.textContent=rows.length+' / '+Q.length+' quotes';
if(!rows.length){list.innerHTML='<div class="empty">No quotes match.</div>';return;}
rows.forEach(q=>{const[text,who,theme,file,tc]=q;const card=document.createElement('div');card.className='q';
card.innerHTML='<p class="text">“'+esc(text)+'”</p><div class="meta">'+
'<span class="dot" style="background:'+(THEMES[theme]||'#8a9298')+'"></span>'+
(who?'<span class="who">'+esc(who)+'</span>':'')+
'<span class="tag">'+esc(theme)+'</span><span class="tc">'+esc(tc)+'</span><span class="src">'+esc(file)+'</span></div>';
card.onclick=()=>{navigator.clipboard.writeText(file+'  @  '+tc+'  -  "'+text+'"');showToast('Copied source + timecode');};
list.appendChild(card);});}
let tT;function showToast(m){toast.textContent=m;toast.classList.add('show');clearTimeout(tT);tT=setTimeout(()=>toast.classList.remove('show'),1400);}
render();
</script></body></html>"""

# ------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--offline", action="store_true", help="Force offline mode.")
    ap.add_argument("--model", default=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"))
    args = ap.parse_args()

    root = os.path.abspath(args.root.strip().strip('"').rstrip("\\/"))
    tdir = os.path.join(root, "transcripts")
    if not os.path.isdir(tdir):
        print(f"No 'transcripts' folder in {root}. Run transcribe.py first.")
        sys.exit(1)

    print("Reading transcripts...")
    quotes = collect(tdir)
    if not quotes:
        print("No quotes found in the subtitles. Nothing to do.")
        return
    print(f"Found {len(quotes)} quotes across {len({q['clip'] for q in quotes})} clips.")

    have_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    smart = have_key and not args.offline
    if smart:
        print(f"SMART mode (Claude / {args.model}). Analyzing themes...")
        try:
            themes, brief = smart_analyze(quotes, args.model)
        except Exception as e:
            print(f"  ! smart analysis failed ({e}). Falling back to offline.")
            themes, brief = offline_analyze(quotes)
    else:
        why = "no ANTHROPIC_API_KEY set" if not have_key else "--offline"
        print(f"OFFLINE mode ({why}). Grouping by keyword...")
        themes, brief = offline_analyze(quotes)

    out = os.path.join(root, "discovery")
    os.makedirs(out, exist_ok=True)
    idx = os.path.join(out, "Quote Index.html")
    brf = os.path.join(out, "Discovery Brief.md")
    build_index(quotes, themes, idx)
    with open(brf, "w", encoding="utf-8") as f:
        f.write(brief)

    print("=" * 64)
    print("Done.")
    print(f"  {idx}")
    print(f"  {brf}")
    print("=" * 64)

if __name__ == "__main__":
    main()
