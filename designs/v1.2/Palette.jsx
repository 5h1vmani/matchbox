/* Matchbox — command palette (⌘K). Jump to any surface or fire a quick action
   from anywhere. The keyboard spine that makes the app feel like a daily driver. */
const { useState: usePalState, useEffect: usePalFx, useRef: usePalRef } = React;

function CommandPalette({ commands, onClose }) {
  const [q, setQ] = usePalState("");
  const [active, setActive] = usePalState(0);
  const inputRef = usePalRef(null);

  usePalFx(() => { if (inputRef.current) inputRef.current.focus(); }, []);

  const filtered = commands.filter((c) =>
    !q.trim() || (c.label + " " + (c.hint || "") + " " + c.group).toLowerCase().includes(q.toLowerCase())
  );

  usePalFx(() => { setActive(0); }, [q]);

  const run = (c) => { c.run(); onClose(); };

  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, filtered.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); if (filtered[active]) run(filtered[active]); }
    else if (e.key === "Escape") { onClose(); }
  };

  // group, preserving order
  const groups = [];
  filtered.forEach((c) => {
    let g = groups.find((x) => x.name === c.group);
    if (!g) { g = { name: c.group, items: [] }; groups.push(g); }
    g.items.push(c);
  });
  let idx = 0;

  return (
    <div className="palette-scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="palette" onMouseDown={(e) => e.stopPropagation()}>
        <div className="palette__input">
          <Icon name="search" size={18} style={{ color: "var(--muted-foreground)" }} />
          <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey}
            placeholder="Search screens and actions…" />
          <span className="esc">esc</span>
        </div>
        <div className="palette__body">
          {filtered.length === 0 && <div className="palette__empty">Nothing matches “{q}”.</div>}
          {groups.map((g) => (
            <div key={g.name}>
              <div className="palette__sec">{g.name}</div>
              {g.items.map((c) => {
                const my = idx++;
                return (
                  <div key={c.id} className={window.cx("palette__item", my === active && "on")}
                    onMouseEnter={() => setActive(my)} onClick={() => run(c)}>
                    <span className="pic"><Icon name={c.icon} size={16} /></span>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div className="pt">{c.label}</div>
                      {c.hint && <div className="ps">{c.hint}</div>}
                    </div>
                    {c.kbd && <span className="pk">{c.kbd}</span>}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

window.CommandPalette = CommandPalette;
