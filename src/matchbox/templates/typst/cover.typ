// Matchbox v0.3 — cover-letter template.
// Sibling to cv.typ. Reads cover.txt (plain text) and renders a single
// page. ATS-parse-safe in the same way as the CV template.
//
// Invoked by `python -m matchbox.assemble --cover`:
//   typst compile cover.typ out.pdf \
//     --input data=cover.txt --input meta=cover_meta.json \
//     --input palette=slate --input font=source-serif

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

#let body_path = inputs.at("data", default: "cover.txt")
#let meta_path = inputs.at("meta", default: "cover_meta.json")
#let body = read(body_path)
#let meta = json(meta_path)

#set document(title: meta.candidate_name + " — Cover Letter", author: meta.candidate_name)
#set page(paper: "us-letter", margin: 0.8in, fill: p.page)
#set text(font: f, size: 11pt, fill: p.body)
#set par(leading: 0.7em, justify: false, first-line-indent: 0pt)

// Sender block
#align(left)[
  #text(size: 12pt, weight: "bold", fill: p.heading)[#meta.candidate_name]
  #if "contact" in meta and meta.contact.len() > 0 [
    \
    #text(size: 9pt, fill: p.body)[#meta.contact.join(" · ")]
  ]
]

#v(0.8em)

// Date
#if "date" in meta [
  #align(left)[#text(size: 10pt, fill: p.body)[#meta.date]]
  #v(0.4em)
]

// Recipient
#if "recipient" in meta [
  #align(left)[
    #for line in meta.recipient [#text(size: 10pt, fill: p.body)[#line]\
    ]
  ]
  #v(0.4em)
]

// Salutation
#if "salutation" in meta [
  #text(size: 11pt, fill: p.body)[#meta.salutation]
  #v(0.4em)
]

// Body — preserves paragraph breaks (double newlines)
#for para in body.split("\n\n") [
  #if para.trim() != "" [
    #text(size: 11pt, fill: p.body)[#para.trim()]
    #v(0.4em)
  ]
]

// Closing
#if "closing" in meta [
  #v(0.4em)
  #text(size: 11pt, fill: p.body)[#meta.closing]
  \
  #text(size: 11pt, weight: "bold", fill: p.heading)[#meta.candidate_name]
]
