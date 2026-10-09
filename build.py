#!/usr/bin/env python3
"""Static site generator for the Catalina King portfolio.

    python3 build.py              build into ./site (unfilled slots shown as placeholders)
    python3 build.py --production omit unfilled image slots and empty text fields
    python3 build.py --serve      build, then serve ./site on http://localhost:8000

Content lives in content/*.json, images in assets/images/<project-slug>/.
"""
import argparse
import datetime
import html
import http.server
import json
import re
import shutil
import socketserver
import sys
from functools import partial
from pathlib import Path
from urllib.parse import quote

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
STATIC = ROOT / "static"
IMAGES = ROOT / "assets" / "images"
OUT = ROOT / "site"
CACHE = ROOT / ".cache" / "images"

SRCSET_WIDTHS = (640, 1280, 1920)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

SECTIONS = [
    ("concept", "Concept", ("concept",)),
    ("process", "Process", ("process",)),
    ("plans", "Plans", ("plan", "diagram", "site")),
    ("elevations", "Elevations & Sections", ("elevation", "section")),
    ("renderings", "Renderings & Perspectives", ("rendering", "perspective")),
    ("models", "Models", ("model",)),
    ("final", "Final Presentation", ("final",)),
]

SIZES = {
    "full": "(min-width: 1700px) 1600px, 100vw",
    "wide": "(min-width: 1000px) 83vw, 100vw",
    "left": "(min-width: 800px) 50vw, 100vw",
    "right": "(min-width: 800px) 50vw, 100vw",
    "offset-l": "(min-width: 800px) 66vw, 100vw",
    "offset-r": "(min-width: 800px) 66vw, 100vw",
    "narrow": "(min-width: 800px) 50vw, 100vw",
    "third": "(min-width: 800px) 33vw, 100vw",
    "tall": "(min-width: 800px) 50vw, 100vw",
    "card": "(min-width: 800px) 60vw, 100vw",
}

e = html.escape


def esc(value):
    return e(str(value), quote=True)


class Build:
    def __init__(self, production):
        self.production = production
        self.site = json.loads((CONTENT / "site.json").read_text(encoding="utf-8"))
        self.projects = json.loads((CONTENT / "projects.json").read_text(encoding="utf-8"))
        project_order = {slug: rank for rank, slug in enumerate(self.site.get("project_priority", []))}
        self.projects.sort(key=lambda project: project_order.get(project["slug"], len(project_order)))
        self.by_slug = {p["slug"]: p for p in self.projects}
        self.year = datetime.date.today().year
        self._image_cache = {}

    # ---------- images ----------
    def image(self, folder, file):
        """Return image info; 'exists' is False when the file has not been added yet."""
        key = (folder, file)
        if key in self._image_cache:
            return self._image_cache[key]
        src = IMAGES / folder / file
        info = {"exists": src.is_file() and src.suffix.lower() in IMAGE_EXTS, "folder": folder, "file": file}
        if info["exists"]:
            dest_dir = OUT / "assets" / "images" / folder
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest_dir / file)
            info["full"] = f"assets/images/{quote(folder)}/{quote(file)}"
            info["w"] = info["h"] = None
            info["srcset"] = []
            if Image:
                with Image.open(src) as im:
                    im = ImageOps.exif_transpose(im)
                    info["w"], info["h"] = im.size
                    for width in SRCSET_WIDTHS:
                        if width >= im.width:
                            continue
                        name = f"{src.stem}-{width}.webp"
                        cached = CACHE / folder / name
                        if not cached.exists() or cached.stat().st_mtime < src.stat().st_mtime:
                            cached.parent.mkdir(parents=True, exist_ok=True)
                            im.resize((width, round(im.height * width / im.width)), Image.LANCZOS).save(
                                cached, "WEBP", quality=88, method=4
                            )
                        shutil.copy2(cached, dest_dir / name)
                        info["srcset"].append((f"assets/images/{quote(folder)}/{quote(name)}", width))
        self._image_cache[key] = info
        return info

    @staticmethod
    def ratio_value(ratio):
        a, b = ratio.split("/")
        return float(a) / float(b)

    def ratio_of(self, info, fallback):
        if info["exists"] and info["w"]:
            return info["w"] / info["h"]
        return self.ratio_value(fallback)

    def img_tag(self, info, alt, root, sizes, eager=False):
        attrs = [f'src="{root}{info["full"]}"', f'alt="{esc(alt)}"']
        if info["srcset"]:
            parts = [f"{root}{u} {w}w" for u, w in info["srcset"]]
            parts.append(f"{root}{info['full']} {info['w']}w")
            attrs.append(f'srcset="{", ".join(parts)}"')
            attrs.append(f'sizes="{sizes}"')
        if info["w"]:
            attrs.append(f'width="{info["w"]}" height="{info["h"]}"')
        attrs.append('fetchpriority="high"' if eager else 'loading="lazy"')
        attrs.append('decoding="async"')
        return f"<img {' '.join(attrs)}>"

    def placeholder(self, folder, file, alt, ratio):
        return (
            f'<div class="ph" style="aspect-ratio:{esc(ratio)}" role="img" aria-label="{esc(alt)}">'
            f'<span class="ph__text">Image to come<small>assets/images/{esc(folder)}/{esc(file)}</small></span></div>'
        )

    def figure(self, folder, item, root, layout, eager=False):
        info = self.image(folder, item["file"])
        if not info["exists"] and self.production:
            return ""
        ratio = self.ratio_of(info, item.get("ratio", "4/3"))
        # Let the artwork decide: portrait pieces never stretch to a landscape layout.
        if ratio < 0.9 and layout in ("full", "wide", "narrow", "offset-l", "offset-r"):
            layout = "tall"
        classes = f"fig fig--{layout}"
        classes += " fig--lift" if item.get("lift") else ""
        classes += " fig--framed" if item.get("frame") else ""
        caption = item.get("caption", "")
        if info["exists"]:
            media = self.img_tag(info, item["alt"], root, SIZES.get(layout, SIZES["wide"]), eager)
            media = (
                f'<a class="fig__link" href="{root}{info["full"]}" data-lightbox '
                f'data-caption="{esc(caption or item["alt"])}" aria-label="View larger: {esc(item["alt"])}">{media}</a>'
            )
        else:
            media = self.placeholder(folder, item["file"], item["alt"], item.get("ratio", "4/3"))
        cap = f"<figcaption>{esc(caption)}</figcaption>" if caption else ""
        reveal = "" if eager else " data-reveal"
        # Cap display size relative to the file so low-resolution scans are never blown up.
        nat = f' style="--nat:{info["w"]}px;--r:{info["w"] / info["h"]:.4f}"' if info["exists"] and info["w"] else ""
        return f'<figure class="{classes}"{reveal}{nat}>{media}{cap}</figure>'

    @staticmethod
    def resolve_pairs(items):
        """Turn unpaired left/right layouts into single offset layouts."""
        resolved = []
        i = 0
        while i < len(items):
            layout = items[i].get("layout", "wide")
            nxt = items[i + 1].get("layout") if i + 1 < len(items) else None
            if layout == "left" and nxt == "right":
                resolved += [(items[i], "left"), (items[i + 1], "right")]
                i += 2
                continue
            if layout == "left":
                layout = "offset-l"
            elif layout == "right":
                layout = "offset-r"
            resolved.append((items[i], layout))
            i += 1
        return resolved

    def figures(self, folder, items, root):
        out = [self.figure(folder, item, root, layout) for item, layout in self.resolve_pairs(items)]
        return "".join(f for f in out if f)

    @staticmethod
    def title_html(text):
        return esc(text)

    # ---------- page shell ----------
    def shell(self, *, title, description, body, depth, active="", og_image=None, path="", jsonld=None, nav=None):
        root = "../" * depth
        s = self.site
        full_title = title if title == s["name"] else f"{title} — {s['name']}"
        base = s.get("site_url", "").rstrip("/")
        canonical = f'<link rel="canonical" href="{esc(base + "/" + path)}">' if base else ""
        og = [("og:type", "website"), ("og:title", full_title), ("og:description", description), ("og:site_name", s["name"])]
        if og_image and base:
            og.append(("og:image", f"{base}/{og_image}"))
        og_tags = "".join(f'<meta property="{k}" content="{esc(v)}">' for k, v in og)
        ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
        main_attrs = ""
        if nav:
            main_attrs = f' data-prev="{root}projects/{esc(nav[0])}/" data-next="{root}projects/{esc(nav[1])}/"'

        def nav_link(name, href, key):
            cur = ' aria-current="page"' if active == key else ""
            return f'<a href="{root}{href}"{cur}>{name}</a>'

        c = s["contact"]
        footer_links = []
        if c.get("email"):
            footer_links.append(f'<a href="mailto:{esc(c["email"])}">Email</a>')
        if c.get("linkedin"):
            footer_links.append(f'<a href="{esc(c["linkedin"])}" rel="noopener" target="_blank">LinkedIn</a>')
        if c.get("instagram"):
            footer_links.append(f'<a href="{esc(c["instagram"])}" rel="noopener" target="_blank">Instagram</a>')
        footer_nav = "".join(f"<li>{l}</li>" for l in footer_links)

        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="theme-color" content="#fdfdfb">
{canonical}{og_tags}
<link rel="preload" href="{root}static/fonts/libre-caslon-display.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{root}static/css/styles.css">
<script>document.documentElement.classList.add("js")</script>
{ld}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<div class="progress" aria-hidden="true"><span></span></div>
<header class="site-header">
  <div class="site-header__inner">
    <a class="wordmark" href="{root}index.html" aria-label="{esc(s["name"])} — home">{esc(s["name"])}</a>
    <nav aria-label="Primary">{nav_link("Work", "work/", "work")}{nav_link("About", "about/", "about")}{nav_link("Contact", "contact/", "contact")}</nav>
  </div>
</header>
<main id="main"{main_attrs}>
{body}
</main>
<footer class="site-footer">
  <div class="wrap site-footer__inner">
    <p><strong>{esc(s["name"])}</strong><br>{esc(s["role"])}</p>
    <ul class="inline-list">{footer_nav}</ul>
    <p class="small">&copy; {self.year} {esc(s["name"])}</p>
  </div>
</footer>
<script src="{root}static/js/main.js" defer></script>
</body>
</html>
"""

    # ---------- shared components ----------
    def project_card(self, p, root):
        folder = p["slug"]
        hero = next((i for i in p["images"] if i["kind"] == "hero"), None)
        if p.get("card_image"):
            hero = next((i for i in p["images"] if i["file"] == p["card_image"]), hero)
        media = '<div class="ph" style="aspect-ratio:4/3"></div>'
        if hero:
            info = self.image(folder, hero["file"])
            framed = " card__media--framed" if hero.get("frame") else ""
            if info["exists"]:
                ratio = self.ratio_of(info, "4/3")
                media = (
                    f'<div class="card__media{framed}" style="aspect-ratio:{ratio:.4f}">'
                    f'{self.img_tag(info, "", root, SIZES["card"])}</div>'
                )
            else:
                media = f'<div class="card__media">{self.placeholder(folder, hero["file"], hero["alt"], p.get("card_ratio", "4/3"))}</div>'
        meta = " · ".join(x for x in (p["course"].split(" — ")[0], p["year"]) if x)
        hover = " · ".join(x for x in (p["instructor"], p["location"]) if x)
        return f"""<a class="card" href="{root}projects/{esc(p["slug"])}/" data-reveal>
  <div class="card__frame">{media}<span class="card__hover" aria-hidden="true">{esc(hover)}</span></div>
  <div class="card__meta">
    <h3 class="card__title">{self.title_html(p["title"])}</h3>
    <p class="card__cat">{esc(p["category"])}</p>
    <p class="card__small">{esc(meta)}</p>
  </div>
</a>"""

    def process_flow(self):
        steps = "".join(f"<li>{esc(s)}</li>" for s in self.site["process_flow"])
        return f'<ol class="flow" data-flow aria-label="Design process">{steps}</ol>'

    def optional(self, value, label):
        """Empty text fields show a placeholder in dev builds and disappear in production."""
        if value:
            return esc(value)
        return "" if self.production else f'<span class="todo">{esc(label)}</span>'

    # ---------- pages ----------
    def home(self):
        s = self.site
        hero_cfg = {**s["home_hero"], "kind": "hero", "layout": "full"}
        hero_fig = self.figure(s.get("home_hero_folder", "home"), hero_cfg, "", "full", eager=True)
        featured = [self.by_slug[x] for x in s["featured"] if x in self.by_slug]
        cards = "".join(self.project_card(p, "") for p in featured)
        caps = "".join(
            f'<li data-reveal><a class="practice__link" href="projects/{esc(c["project"])}/">'
            f'<span class="practice__number" aria-hidden="true">{i:02d}</span>'
            f'<span class="practice__copy"><span class="practice__discipline">{esc(c["title"])}</span>'
            f'<span class="practice__text">{esc(c["text"])}</span></span>'
            f'<span class="practice__project">{esc(self.by_slug[c["project"]]["title"])}</span>'
            '<span class="practice__arrow" aria-hidden="true">&rarr;</span></a></li>'
            for i, c in enumerate(s["capabilities"], 1)
        )
        process_links = "".join(
            f'<li><a href="projects/{esc(slug)}/">{esc(self.by_slug[slug]["title"])}</a></li>' for slug in s["process_projects"]
        )
        body = f"""<section class="wrap intro">
  <p class="eyebrow">{esc(s["role"])}</p>
  <h1 class="title">{esc(s["name"])}</h1>
  <p class="lead">{esc(s["tagline"])}</p>
  <a class="button" href="work/">View work</a>
</section>
<div class="wrap">{hero_fig}</div>
<section class="wrap section practice" aria-labelledby="shows">
  <div class="practice__intro">
    <p class="eyebrow practice__eyebrow">{esc(s["practice"]["eyebrow"])}</p>
    <h2 id="shows" class="h2 practice__heading">{esc(s["practice"]["title"])}</h2>
    <p class="practice__lead">{esc(s["practice"]["intro"])}</p>
  </div>
  <ol class="practice__list">{caps}</ol>
</section>
<section class="wrap section" aria-labelledby="selected">
  <div class="section__head"><h2 id="selected" class="h2">Selected work</h2><a class="more" href="work/">All work &rarr;</a></div>
  <div class="work-grid">{cards}</div>
</section>
<section class="band" aria-labelledby="process">
  <div class="wrap band__inner">
    <h2 id="process" class="title title--md">Process is part of the work</h2>
    {self.process_flow()}
    <p class="lead">{esc(s["process_flow_text"])}</p>
    <ul class="inline-list">{process_links}</ul>
  </div>
</section>
<section class="wrap section cta" aria-labelledby="cta">
  <h2 id="cta" class="title title--md">Let&rsquo;s talk about design.</h2>
  <a class="button" href="contact/">Contact</a>
</section>"""
        return self.shell(
            title=s["name"], description=s["description"], body=body, depth=0,
            og_image=self.og_image(), path="", jsonld=self.person_jsonld(),
        )

    def og_image(self):
        info = self.image(self.site.get("home_hero_folder", "home"), self.site["home_hero"]["file"])
        if info["exists"]:
            return info["srcset"][-1][0] if info["srcset"] else info["full"]
        return None

    def person_jsonld(self):
        s = self.site
        c = s["contact"]
        data = {"@context": "https://schema.org", "@type": "Person", "name": s["name"], "description": s["description"],
                "affiliation": {"@type": "CollegeOrUniversity", "name": "University of Idaho"}}
        if s.get("site_url"):
            data["url"] = s["site_url"]
        same = [c[k] for k in ("linkedin", "instagram") if c.get(k)]
        if same:
            data["sameAs"] = same
        return data

    def work(self):
        cards = "".join(self.project_card(p, "../") for p in self.projects)
        body = f"""<section class="wrap page-head">
  <p class="eyebrow">Selected works in 2nd year design</p>
  <h1 class="title">Work</h1>
  <p class="lead">Architectural graphics, hand rendering, residential design, conceptual architecture, research through design and urban renewal.</p>
</section>
<section class="wrap" aria-label="Projects"><div class="work-grid">{cards}</div></section>
<div class="band"><div class="wrap band__inner">{self.process_flow()}</div></div>"""
        return self.shell(
            title="Work",
            description="Selected projects by Catalina King: architectural graphics, hand rendering, residential design, conceptual architecture, research through design and urban renewal.",
            body=body, depth=1, active="work", path="work/", og_image=self.og_image(),
        )

    def project(self, idx):
        p = self.projects[idx]
        root = "../../"
        folder = p["slug"]
        titles = {k: t for k, t, _ in SECTIONS}
        titles.update(p.get("section_titles", {}))
        notes = p.get("section_notes", {})

        hero = next((i for i in p["images"] if i["kind"] == "hero"), None)
        hero_fig = self.figure(folder, hero, root, hero.get("layout", "full"), eager=True) if hero else ""

        eyebrow = p.get("eyebrow") or p["category"]

        steps = "".join(
            f'<li data-reveal><span class="step__n" aria-hidden="true">{n:02d}</span><h3>{esc(st["label"])}</h3><p>{esc(st["note"])}</p></li>'
            for n, st in enumerate(p["process"], 1)
        )
        stage_order = [st["label"] for st in p["process"]]

        sections_html = []
        for key, _, kinds in SECTIONS:
            items = [i for i in p["images"] if i["kind"] in kinds]
            heading = esc(titles[key])
            note = f'<p class="section-note">{esc(notes[key])}</p>' if key in notes else ""
            if key == "concept":
                paras = "".join(f"<p>{esc(t)}</p>" for t in p.get("concept", []))
                program = "".join(f"<li>{esc(f)}</li>" for f in p.get("facts", []))
                q = p.get("quote")
                quote = (f'<blockquote class="quote"><p>{esc(q["text"])}</p><footer>{esc(q["source"])}, {esc(self.site["name"])}</footer></blockquote>'
                         if q else "")
                figs = self.figures(folder, items, root)
                sections_html.append(f"""<section class="wrap section" id="concept" aria-labelledby="h-concept">
  <div class="concept">
    <div class="concept__title"><p class="eyebrow">Concept</p><h2 id="h-concept" class="h2">{esc(p.get("concept_title", "Concept"))}</h2></div>
    <div class="concept__body prose">{paras}{quote}{f'<ul class="chips" aria-label="Includes">{program}</ul>' if program else ""}</div>
  </div>
  {f'<div class="grid">{figs}</div>' if figs else ""}
</section>""")
                continue
            if key == "process":
                groups = {}
                for it in items:
                    groups.setdefault(it.get("stage", ""), []).append(it)
                ordered = sorted(groups, key=lambda g: stage_order.index(g) if g in stage_order else 99)
                inner = ""
                for g in ordered:
                    figs = self.figures(folder, groups[g], root)
                    if figs:
                        sub = f'<h3 class="stage-title">{esc(g)}</h3>' if g else ""
                        inner += f'{sub}<div class="grid">{figs}</div>'
                if inner:
                    sections_html.append(f'<section class="wrap section" id="process" aria-labelledby="h-process"><div class="section__head"><h2 id="h-process" class="h2">{heading}</h2></div>{note}{inner}</section>')
                continue
            figs = self.figures(folder, items, root)
            if figs:
                sections_html.append(f'<section class="wrap section" id="{key}" aria-labelledby="h-{key}"><div class="section__head"><h2 id="h-{key}" class="h2">{heading}</h2></div>{note}<div class="grid">{figs}</div></section>')

        subnav_items = [(m.group(1), m.group(2)) for h in sections_html
                        for m in [re.search(r'id="([a-z]+)" aria-labelledby="h-[a-z]+">.*?<h2[^>]*>(.*?)</h2>', h, re.S)] if m]
        subnav = ("<nav class=\"subnav\" aria-label=\"On this page\"><div class=\"subnav__inner\">"
                  + "".join(f'<a href="#{k}">{"Concept" if k == "concept" else t}</a>' for k, t in subnav_items) + "</div></nav>") if len(subnav_items) > 2 else ""
        n = len(self.projects)
        prv, nxt = self.projects[(idx - 1) % n], self.projects[(idx + 1) % n]
        priority_projects = [
            self.by_slug[slug]
            for slug in self.site.get("project_priority", [])
            if slug in self.by_slug
        ]
        if len(priority_projects) > 1:
            current_priority = next(
                (i for i, project in enumerate(priority_projects) if project["slug"] == p["slug"]),
                None,
            )
            recommendation = (
                priority_projects[(current_priority + 1) % len(priority_projects)]
                if current_priority is not None
                else priority_projects[idx % len(priority_projects)]
            )
        else:
            recommendation = nxt
        next_block = f"""<section class="next" aria-label="Featured project">
  <div class="wrap">
    <a class="next__link" href="{root}projects/{esc(recommendation["slug"])}/">
      <span class="eyebrow">Featured project</span>
      <span class="title title--md">{self.title_html(recommendation["title"])}</span>
      <span class="next__cat">{esc(recommendation["category"])} &rarr;</span>
    </a>
  </div>
</section>"""

        body = f"""<article>
<header class="wrap project-head">
  <p class="eyebrow"><a href="{root}work/">Work</a> / {esc(eyebrow)}</p>
  <h1 class="title">{self.title_html(p["title"])}</h1>
  <p class="subtitle">{esc(p["subtitle"])}</p>
  <p class="pitch">{esc(p.get("pitch") or " ".join(p["description"]))}</p>
</header>
<div class="wrap">{hero_fig}</div>
{subnav}
<section class="wrap section" aria-labelledby="h-path">
  <div class="section__head"><h2 id="h-path" class="h2">Path through the project</h2></div>
  <ol class="steps">{steps}</ol>
</section>
{"".join(sections_html)}
</article>
{next_block}"""
        hero_info = self.image(folder, hero["file"]) if hero else None
        og = None
        if hero_info and hero_info["exists"]:
            og = hero_info["srcset"][-1][0] if hero_info["srcset"] else hero_info["full"]
        return self.shell(
            title=p["title"], description=p["summary"], body=body, depth=2, active="work",
            path=f"projects/{p['slug']}/", og_image=og, nav=(prv["slug"], nxt["slug"]),
        )

    def about(self):
        s = self.site["about"]
        c = self.site["contact"]
        bio = (f'<div class="prose"><p>{esc(s["bio"])}</p></div>' if s["bio"]
               else ("" if self.production else '<div class="prose"><p class="todo todo--block">Short biography to be added.</p></div>'))
        rows = ""
        for d in s["details"]:
            val = self.optional(d["value"], "To be added")
            if val:
                rows += f'<div><dt>{esc(d["label"])}</dt><dd>{val}</dd></div>'
        resume = (f'<a class="button button--ghost" href="{esc(c["resume"])}">Resume (PDF)</a>' if c.get("resume")
                  else ("" if self.production else '<span class="todo">Resume link to be added</span>'))
        linkedin = (f'<a class="button button--ghost" href="{esc(c["linkedin"])}" rel="noopener" target="_blank">LinkedIn</a>'
                    if c.get("linkedin") else "")
        body = f"""<section class="wrap page-head">
  <p class="eyebrow">About</p>
  <h1 class="title">{esc(self.site["name"])}</h1>
  <p class="lead">{esc(s["intro"])}</p>
</section>
<section class="wrap about">
  <dl class="facts facts--meta">{rows}</dl>
  <div class="about__main">{bio}<p class="prose-note">{esc(s["portfolio_note"])}</p><div class="actions">{resume}{linkedin}<a class="button" href="../contact/">Contact</a></div></div>
</section>"""
        return self.shell(
            title="About", description=f'About {self.site["name"]}, interior architecture and design student at the University of Idaho.',
            body=body, depth=1, active="about", path="about/", jsonld=self.person_jsonld(),
        )

    def contact(self):
        c = self.site["contact"]
        s = self.site
        rows = []

        def row(label, value_html):
            if value_html:
                rows.append(f"<div><dt>{label}</dt><dd>{value_html}</dd></div>")

        row("Email", f'<a href="mailto:{esc(c["email"])}">{esc(c["email"])}</a>' if c.get("email")
            else ("" if self.production else '<span class="todo">Email to be added</span>'))
        row("LinkedIn", f'<a href="{esc(c["linkedin"])}" rel="noopener" target="_blank">linkedin.com/in/catalina-king</a>' if c.get("linkedin") else "")
        row("Resume", f'<a href="{esc(c["resume"])}">Download PDF</a>' if c.get("resume")
            else ("" if self.production else '<span class="todo">Resume download to be added</span>'))
        row("Instagram", f'<a href="{esc(c["instagram"])}" rel="noopener" target="_blank">@catalina.king05</a>' if c.get("instagram") else "")
        body = f"""<section class="wrap page-head contact">
  <p class="eyebrow">Contact</p>
  <h1 class="title">{esc(s["name"])}</h1>
  <p class="lead">{esc(s["role"])}</p>
  <dl class="contact__list">{"".join(rows)}</dl>
</section>"""
        return self.shell(title="Contact", description=f'Contact {s["name"]} — interior architecture and design.',
                          body=body, depth=1, active="contact", path="contact/")

    def not_found(self):
        body = """<section class="wrap page-head">
  <p class="eyebrow">404</p>
  <h1 class="title">Page not found</h1>
  <p class="lead"><a href="/">Return to the portfolio</a></p>
</section>"""
        page = self.shell(title="Page not found", description="Page not found.", body=body, depth=0)
        return (page.replace('href="static/', 'href="/static/').replace('src="static/', 'src="/static/')
                .replace('href="index.html"', 'href="/"').replace('href="work/"', 'href="/work/"')
                .replace('href="about/"', 'href="/about/"').replace('href="contact/"', 'href="/contact/"'))

    # ---------- output ----------
    def write(self, rel, content):
        path = OUT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def run(self):
        if OUT.exists():
            shutil.rmtree(OUT)
        OUT.mkdir()
        shutil.copytree(STATIC, OUT / "static")
        self.write("index.html", self.home())
        self.write("work/index.html", self.work())
        self.write("about/index.html", self.about())
        self.write("contact/index.html", self.contact())
        for i, p in enumerate(self.projects):
            self.write(f"projects/{p['slug']}/index.html", self.project(i))
        self.write("404.html", self.not_found())
        base = self.site.get("site_url", "").rstrip("/")
        robots = "User-agent: *\nAllow: /\n"
        if base:
            urls = ["", "work/", "about/", "contact/"] + [f"projects/{p['slug']}/" for p in self.projects]
            sm = "".join(f"<url><loc>{esc(base + '/' + u)}</loc></url>" for u in urls)
            self.write("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>\n')
            robots += f"Sitemap: {base}/sitemap.xml\n"
        self.write("robots.txt", robots)
        found = sum(1 for v in self._image_cache.values() if v["exists"])
        print(f"Built {len(self.projects)} projects into {OUT} ({found} images found, {len(self._image_cache) - found} slots empty)")
        if Image is None:
            print("Note: Pillow is not installed, so responsive image sizes were not generated (pip install pillow).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--production", action="store_true", help="omit empty image slots and empty text fields")
    ap.add_argument("--serve", nargs="?", const=8000, type=int, metavar="PORT", help="serve ./site after building")
    args = ap.parse_args()
    Build(args.production).run()
    if args.serve:
        handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT))
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", args.serve), handler) as httpd:
            print(f"Serving on http://localhost:{args.serve}  (Ctrl+C to stop)")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                sys.exit(0)


if __name__ == "__main__":
    main()
