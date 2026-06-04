/* Icon atom. The design prototype used the Lucide CDN global (window.lucide);
   in the bundle we use lucide-react behind the SAME `<Icon name=... />` API, so
   every call site is unchanged. Names are the design's kebab-case; a few Lucide
   renames are aliased, and any miss falls back to a plain circle (never crashes). */
import { Circle, icons, type LucideProps } from "lucide-react";
import type { ComponentType, CSSProperties } from "react";

type Registry = Record<string, ComponentType<LucideProps>>;
const REGISTRY = icons as unknown as Registry;

// Icons Lucide renamed to the "circle-*" scheme since the prototype was authored.
const ALIASES: Record<string, string> = {
  "alert-circle": "CircleAlert",
  "x-circle": "CircleX",
  "check-circle": "CircleCheck",
  "chart-line": "ChartLine",
};

function toPascal(name: string): string {
  return name.replace(/(^|-)([a-z0-9])/g, (_m, _sep, c: string) => c.toUpperCase());
}

export interface IconProps {
  name: string;
  size?: number;
  strokeWidth?: number;
  className?: string;
  style?: CSSProperties;
}

export function Icon({ name, size = 18, strokeWidth = 2, className, style }: IconProps) {
  const Cmp = REGISTRY[ALIASES[name] ?? toPascal(name)] ?? REGISTRY[toPascal(name)] ?? Circle;
  return (
    <span className={className} style={{ display: "inline-flex", lineHeight: 0, ...style }}>
      <Cmp size={size} strokeWidth={strokeWidth} />
    </span>
  );
}
