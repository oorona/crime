import React from 'react';
import { useT } from '../../i18n.js';

// Inline-SVG line chart for a monthly series. `series` is [{label, y}]; an
// optional `secondary` series (same length) is drawn faint on its own scale
// (used for ridership behind the crime count).
export default function Sparkline({ series, secondary, width = 300, height = 70, color = '#f97316', color2 = '#3b82f6', formatY = v => v }) {
  const t = useT();
  if (!series?.length) return <div style={{ fontSize: 11, opacity: 0.6 }}>{t('nodata')}</div>;
  const pad = { l: 4, r: 4, t: 6, b: 14 };
  const w = width - pad.l - pad.r, h = height - pad.t - pad.b;
  const ys = series.map(p => p.y ?? 0);
  const max = Math.max(1, ...ys), min = 0;
  const xOf = i => pad.l + (series.length === 1 ? w / 2 : (i / (series.length - 1)) * w);
  const yOf = v => pad.t + h - ((v - min) / (max - min || 1)) * h;
  const path = series.map((p, i) => `${i ? 'L' : 'M'}${xOf(i).toFixed(1)},${yOf(p.y ?? 0).toFixed(1)}`).join(' ');
  let path2 = null;
  if (secondary?.length === series.length) {
    const ys2 = secondary.map(p => p.y ?? 0);
    const max2 = Math.max(1, ...ys2);
    const y2Of = v => pad.t + h - (v / max2) * h;
    path2 = secondary.map((p, i) => `${i ? 'L' : 'M'}${xOf(i).toFixed(1)},${y2Of(p.y ?? 0).toFixed(1)}`).join(' ');
  }
  const last = series[series.length - 1];
  const peak = ys.indexOf(max);
  return (
    <svg width={width} height={height} style={{ display: 'block', overflow: 'visible' }}>
      {path2 && <path d={path2} fill="none" stroke={color2} strokeWidth={1.2} strokeOpacity={0.45} />}
      <path d={path} fill="none" stroke={color} strokeWidth={1.8} />
      <circle cx={xOf(peak)} cy={yOf(max)} r={2.5} fill={color} />
      <text x={xOf(peak)} y={yOf(max) - 4} fontSize={9} fill="#e6edf3" textAnchor="middle">{formatY(max)}</text>
      <text x={pad.l} y={height - 2} fontSize={9} fill="#8b949e">{series[0].label}</text>
      <text x={width - pad.r} y={height - 2} fontSize={9} fill="#8b949e" textAnchor="end">{last.label}</text>
    </svg>
  );
}
