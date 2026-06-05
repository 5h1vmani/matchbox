/* Matchbox — command palette (⌘K). Jump to any surface or fire a quick action
   from anywhere. Ported from designs/v1.2/Palette.jsx; keyboard-first by design
   (focus-on-open, arrow/enter/escape), so it satisfies the a11y pass too. */
import { useEffect, useMemo, useRef, useState } from "react";
import { cx } from "../lib/derive";
import { Icon } from "./icon";

export interface Command {
  id: string;
  label: string;
  group: string;
  icon: string;
  hint?: string;
  kbd?: string;
  run: () => void;
}

export function CommandPalette({ commands, onClose }: { commands: Command[]; onClose: () => void }) {
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const filtered = useMemo(
    () =>
      commands.filter(
        (c) =>
          !q.trim() ||
          (c.label + " " + (c.hint || "") + " " + c.group).toLowerCase().includes(q.toLowerCase()),
      ),
    [commands, q],
  );

  useEffect(() => {
    setActive(0);
  }, [q]);

  const run = (c: Command) => {
    c.run();
    onClose();
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (filtered[active]) run(filtered[active]);
    } else if (e.key === "Escape") {
      onClose();
    }
  };

  // Group, preserving first-seen order.
  const groups: { name: string; items: Command[] }[] = [];
  for (const c of filtered) {
    let g = groups.find((x) => x.name === c.group);
    if (!g) {
      g = { name: c.group, items: [] };
      groups.push(g);
    }
    g.items.push(c);
  }
  let idx = 0;

  return (
    <div
      className="palette-scrim"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette" onMouseDown={(e) => e.stopPropagation()}>
        <div className="palette__input">
          <Icon name="search" size={18} style={{ color: "var(--muted-foreground)" }} />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onKey}
            placeholder="Search screens and actions…"
            aria-label="Search screens and actions"
          />
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
                  <div
                    key={c.id}
                    className={cx("palette__item", my === active && "on")}
                    onMouseEnter={() => setActive(my)}
                    onClick={() => run(c)}
                  >
                    <span className="pic">
                      <Icon name={c.icon} size={16} />
                    </span>
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
