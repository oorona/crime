import React from 'react';
import { DOW_LABELS } from '../../data/categories.js';

// 7 × 24 heat grid: rows = weekday (Mon first), cols = hour of day.
export default function HourDowGrid({ grid, cell = 11, gap = 1 }) {
  if (!grid?.length) return <div style={{ fontSize: 11, opacity: 0.6 }}>Sin datos</div>;
  const max = Math.max(1, ...grid.flat());
  const labelW = 26;
  const width = labelW + 24 * (cell + gap), height = 12 + 7 * (cell + gap);
  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      {[0, 6, 12, 18, 23].map(h => (
        <text key={h} x={labelW + h * (cell + gap) + cell / 2} y={9} fontSize={8} fill="#8b949e" textAnchor="middle">{h}</text>
      ))}
      {grid.map((row, d) => (
        <g key={d} transform={`translate(0, ${12 + d * (cell + gap)})`}>
          <text x={0} y={cell - 2} fontSize={8} fill="#8b949e">{DOW_LABELS[d]}</text>
          {row.map((v, h) => (
            <rect key={h} x={labelW + h * (cell + gap)} y={0} width={cell} height={cell} rx={1.5}
              fill="#f97316" fillOpacity={0.08 + 0.92 * (v / max)}>
              <title>{`${DOW_LABELS[d]} ${h}:00 — ${v}`}</title>
            </rect>
          ))}
        </g>
      ))}
    </svg>
  );
}
