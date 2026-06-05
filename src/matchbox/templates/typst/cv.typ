// Matchbox — single CV template (presentation layer).
// ATS-parse-safe: single column, standard headings ("Experience", "Skills",
// "Education"), real selectable text only, no tables/text-boxes for layout,
// nothing meaningful in header/footer, standard bullet (•), embedded fonts.
//
// FONTS are bundled in shared/fonts and reached via `typst --font-path`.
// The previous template named fonts that were never installed (Source Serif
// Pro, Inter, Source Sans), so every render silently fell back to a Typst
// default. The keys below stay stable for the web route's FONTS allow-list,
// but every value now points at a font that actually resolves:
//   - "Atkinson Hyperlegible", "IBM Plex Sans"  -> bundled (shared/fonts)
//   - "Charter"                                 -> system serif
//
// Invoked by `python -m matchbox.assemble`:
//   typst compile cv.typ out.pdf --font-path <repo>/shared/fonts \
//     --input data=cv.json --input palette=slate \
//     --input font=atkinson-hyperlegible --input page=a4

#let inputs = sys.inputs

#let palettes = (
  slate:   (page: rgb("#FFFFFF"), body: rgb("#1A1A1A"), heading: rgb("#1A2B3C"), accent: rgb("#3C6E9C")),
  ink:     (page: rgb("#FFFFFF"), body: rgb("#161616"), heading: rgb("#000000"), accent: rgb("#555555")),
  forest:  (page: rgb("#FFFFFF"), body: rgb("#1A1A1A"), heading: rgb("#1E3A2F"), accent: rgb("#2F6B4F")),
  claret:  (page: rgb("#FFFFFF"), body: rgb("#1A1A1A"), heading: rgb("#3A1E26"), accent: rgb("#8C3A4F")),
  bronze:  (page: rgb("#FDFDFB"), body: rgb("#1F1B16"), heading: rgb("#2E2417"), accent: rgb("#8A6A38")),
)

#let fonts = (
  "atkinson-hyperlegible": "Atkinson Hyperlegible",  // bundled; default for FDE / SA bases
  "source-sans":           "IBM Plex Sans",          // bundled
  "inter":                 "IBM Plex Sans",          // bundled (closest match)
  "source-serif":          "Charter",                // system serif
)

#let papers = (
  "a4":        "a4",         // default — India / UK / most of the world
  "letter":    "us-letter",
  "us-letter": "us-letter",
)

#let palette_name = inputs.at("palette", default: "slate")
#let font_name    = inputs.at("font",    default: "atkinson-hyperlegible")
#let page_name    = inputs.at("page",    default: "a4")
#let p     = palettes.at(palette_name)
#let f     = fonts.at(font_name, default: "Atkinson Hyperlegible")
#let paper = papers.at(page_name, default: "a4")

#let data_path = inputs.at("data", default: "cv.json")
#let data = json(data_path)

#set document(title: data.profile.name, author: data.profile.name)
#set page(paper: paper, margin: 0.7in, fill: p.page)
#set text(font: f, size: 10pt, fill: p.body)
#set par(leading: 0.62em, justify: false)

#let h2(t) = block(below: 0.45em)[
  #text(size: 11pt, weight: "bold", fill: p.heading)[#upper(t)]
  #v(-0.25em)
  #line(length: 100%, stroke: 0.5pt + p.accent)
]

// Header
#align(left)[
  #text(size: 18pt, weight: "bold", fill: p.heading)[#data.profile.name]
  #if "headline" in data.profile [
    \
    #text(size: 10pt, fill: p.body)[#data.profile.headline]
  ]
  #if "contact" in data.profile [
    \
    #text(size: 9pt, fill: p.body)[#data.profile.contact.join("  ·  ")]
  ]
]

#v(0.6em)

// Summary
#if "summary" in data and data.summary != "" [
  #text(size: 10pt, fill: p.body)[#data.summary]
  #v(0.4em)
]

// Core Competencies — a recruiter-skim + ATS keyword row. Rendered only when
// the assembler supplies a "competencies" list; absent today, ready for bases.
#if "competencies" in data and data.competencies.len() > 0 [
  #h2("Core Competencies")
  #text(size: 10pt, fill: p.body)[#data.competencies.join("   ·   ")]
  #v(0.4em)
]

// Experience. A role flagged "earlier": true renders as a single compressed
// line (for older / supporting roles), so recent relevant roles keep the room.
#if "experiences" in data and data.experiences.len() > 0 [
  #h2("Experience")
  #for exp in data.experiences [
    #if exp.at("earlier", default: false) [
      #block(below: 0.28em)[
        #text(size: 9.5pt, fill: p.body)[#text(weight: "bold")[#exp.company] #h(0.3em)·#h(0.3em) #emph(exp.role) #h(0.3em)·#h(0.3em) #exp.start_date – #exp.end_date#if exp.location != none [, #exp.location]]
      ]
    ] else [
      #grid(
        columns: (1fr, auto),
        gutter: 0pt,
        align(left)[#text(weight: "bold")[#exp.company] #h(0.3em) · #h(0.3em) #emph(exp.role)],
        align(right)[#text(size: 9pt, fill: p.body)[#exp.start_date – #exp.end_date#if exp.location != none [ · #exp.location]]],
      )
      #v(0.18em)
      #for b in exp.bullets [
        #block(below: 0.18em, above: 0.05em)[
          #grid(columns: (0.5em, 1fr), gutter: 0.4em,
            text(fill: p.accent)[•],
            text(size: 10pt, fill: p.body)[#b],
          )
        ]
      ]
      #v(0.35em)
    ]
  ]
]

// Projects
#if "projects" in data and data.projects.len() > 0 [
  #h2("Projects")
  #for proj in data.projects [
    #text(weight: "bold")[#proj.name]
    #if "url" in proj and proj.url != none [ #h(0.3em) #text(size: 9pt, fill: p.accent)[#proj.url]]
    \
    #text(size: 10pt, fill: p.body)[#proj.text]
    #v(0.3em)
  ]
]

// Skills
#if "skills" in data and data.skills.len() > 0 [
  #h2("Skills")
  #for cat in data.skills [
    #text(weight: "bold")[#cat.category]: #text(size: 10pt, fill: p.body)[#cat.items.join(", ")]
    \
  ]
]

// Education
#if "education" in data and data.education.len() > 0 [
  #h2("Education")
  #for e in data.education [
    #text(weight: "bold")[#e.school] #h(0.3em) · #h(0.3em) #e.degree
    #if "end_date" in e and e.end_date != none [ #h(0.3em) (#e.end_date)]
    \
  ]
]
