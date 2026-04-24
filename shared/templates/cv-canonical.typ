// cv-canonical.typ — Canonical CV template.
// Parameters injected at render time by matchbox/tailor/render.py.
// Geo footer controlled by `geo` parameter: "uk" | "india" | "relocate".
// Placeholder — full Typst source written in Phase 3.

#let geo = sys.inputs.at("geo", default: "india")
#let content = json(sys.inputs.at("content_path", default: ""))

// Template body to be implemented in Phase 3.1.
// Shiva reviews and edits cv-canonical-draft.md → converts to Typst here.
