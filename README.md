# Catalina King — portfolio site

A dependency-free static site (Python 3 + Pillow to build, plain HTML/CSS/JS to run).

```bash
python3 build.py --serve        # build into ./site and open http://localhost:8000
python3 build.py --production   # final build: hides empty image slots and "to be added" text
```

Upload the contents of `site/` to any static host (Netlify, GitHub Pages, Cloudflare Pages…).
Set `site_url` in `content/site.json` first so canonical links, social previews and `sitemap.xml` are generated.

## Updating content

| What | Where |
| --- | --- |
| Name, tagline, email, résumé, LinkedIn, About details | `content/site.json` |
| Projects (text, process steps, image list) | `content/projects.json` |
| Images | `assets/images/<project-slug>/` |
| Look and feel | `static/css/styles.css` |

### Add a project

Copy an entry in `content/projects.json` and give it a new `slug`. Each image has:

- `file` — name inside `assets/images/<slug>/` (missing files show a labelled placeholder)
- `kind` — `hero`, `concept`, `process`, `plan`, `elevation`, `section`, `rendering`, `perspective`, `final`; this picks the page section
- `layout` — `full`, `wide`, `left` + `right` (a pair), `offset-l`, `offset-r`, `narrow`; portrait art is automatically kept narrow
- `stage` — for `process` images, one of the project's `process` labels
- `frame` — `true` adds the charcoal frame to artwork that has none
- `caption`, `alt`, `lift` (stagger a pair), `ratio` (placeholder shape only)

### Importing high-resolution images

`assets/highQualitlyImages/` holds the originals (PDFs, HEIC, JPG). The Hero Lair, Philips Field Station and Olivier's Chocolate images were exported from it at up to 3200px
into `assets/images/<slug>/`. Art & Architecture North, Quiet Harbor and Casa de Luz y Tierra still use screenshot crops; add originals the same way.
`site/` is large (about 130 MB) because the lightbox serves the full-size file; resized WebP versions are cached in `.cache/`.

### Replace the images with originals

The current images were cropped from low-resolution screenshots of the PDF pages (kept in `source/`).
Export each piece at full resolution from the PDF/originals and save it over the file with the same name
(or change `file` in the JSON). The build creates responsive WebP sizes automatically; the lightbox shows the original.

### To fill in

`email`, `resume` (a PDF path/URL), `about.bio`, degree, expected graduation, interests and software skills are empty on purpose;
nothing was invented. They show as dashed placeholders until filled and disappear in `--production` builds.
