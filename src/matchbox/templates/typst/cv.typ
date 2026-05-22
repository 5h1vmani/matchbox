// Matchbox v0.3 — single CV template.
// ATS-parse-safe (section 13b of v0.3-design.md):
//  - single column
//  - standard headings ("Experience", "Skills", "Education")
//  - real selectable text only (no images for text)
//  - no tables or text boxes for layout
//  - nothing meaningful in header / footer
//  - standard bullet character (•)
//  - embeds a common font
//
// Invoked by `python -m matchbox.assemble`:
//   typst compile cv.typ out.pdf \
//     --input data=cv.json --input palette=slate --input font=source-serif

#let inputs = sys.inputs

#let palettes = (
  slate:   (page: rgb("#FFFFFF"), body: rgb("#1A1A1A"), heading: rgb("#1A2B3C"), accent: rgb("#3C6E9C")),
  ink:     (page: rgb("#FFFFFF"), body: rgb("#161616"), heading: rgb("#000000"), accent: rgb("#555555")),
  forest:  (page: rgb("#FFFFFF"), body: rgb("#1A1A1A"), heading: rgb("#1E3A2F"), accent: rgb("#2F6B4F")),
  claret:  (page: rgb("#FFFFFF"), body: rgb("#1A1A1A"), heading: rgb("#3A1E26"), accent: rgb("#8C3A4F")),
  bronze:  (page: rgb("#FDFDFB"), body: rgb("#1F1B16"), heading: rgb("#2E2417"), accent: rgb("#8A6A38")),
)

#let fonts = (
  "source-serif": "Source Serif Pro",
  "source-sans":  "Source Sans Pro",
  "inter":        "Inter",
  "atkinson-hyperlegible": "Atkinson Hyperlegible",
)

#let palette_name = inputs.at("palette", default: "slate")
#let font_name    = inputs.at("font",    default: "source-serif")
#let p = palettes.at(palette_name)
#let f = fonts.at(font_name, default: "Source Serif Pro")

#let data_path = inputs.at("data", default: "cv.json")
#let data = json(data_path)

#set document(title: data.profile.name, author: data.profile.name)
#set page(paper: "us-letter", margin: 0.7in, fill: p.page)
#set text(font: f, size: 10pt, fill: p.body)
#set par(leading: 0.55em, justify: false)

#let h2(t) = block(below: 0.4em)[
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
    #text(size: 9pt, fill: p.body)[#data.profile.contact.join(" · ")]
  ]
]

#v(0.6em)

#if "summary" in data and data.summary != "" [
  #text(size: 10pt, fill: p.body)[#data.summary]
  #v(0.4em)
]

// Experience
#if "experiences" in data and data.experiences.len() > 0 [
  #h2("Experience")
  #for exp in data.experiences [
    #grid(
      columns: (1fr, auto),
      gutter: 0pt,
      align(left)[#text(weight: "bold")[#exp.company] #h(0.3em) · #h(0.3em) #emph(exp.role)],
      align(right)[#text(size: 9pt, fill: p.body)[#exp.start_date — #exp.end_date#if exp.location != none [ · #exp.location]]],
    )
    #for b in exp.bullets [
      #block(below: 0.15em, above: 0.05em)[
        #grid(columns: (0.5em, 1fr), gutter: 0.4em,
          text(fill: p.accent)[•],
          text(size: 10pt, fill: p.body)[#b],
        )
      ]
    ]
    #v(0.3em)
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
    #text(weight: "bold")[#e.school] #h(0.3em) — #h(0.3em) #e.degree
    #if "end_date" in e and e.end_date != none [ #h(0.3em) (#e.end_date)]
    \
  ]
]
