import React from 'react';
import { useT } from '../../i18n.js';

// Horizontal bars. `items` is [{label, value, color?}]; widths relative to max.
export default function Bars({ items, max, color = '#3b82f6', formatValue = v => v.toLocaleString(), maxLabel = 34 }) {
  const t = useT();
  if (!items?.length) return <div style={{ fontSize: 11, opacity: 0.6 }}>{t('nodata')}</div>;
  const m = max ?? Math.max(1, ...items.map(i => i.value));
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {items.map((it, i) => {
        const label = it.label.length > maxLabel ? it.label.slice(0, maxLabel - 1) + '…' : it.label;
        return (
          <div key={i} title={it.label} style={{ display: 'grid', gridTemplateColumns: '1fr 56px', gap: 6, alignItems: 'center', fontSize: 11 }}>
            <div style={{ position: 'relative', height: 16, background: '#161b22', borderRadius: 3, overflow: 'hidden' }}>
              <div style={{ position: 'absolute', inset: 0, width: `${Math.max(2, (it.value / m) * 100)}%`, background: it.color || color, opacity: 0.55 }} />
              <span style={{ position: 'absolute', left: 6, top: 1, whiteSpace: 'nowrap', color: '#e6edf3' }}>{label}</span>
            </div>
            <span style={{ textAlign: 'right', opacity: 0.85, fontVariantNumeric: 'tabular-nums' }}>{formatValue(it.value)}</span>
          </div>
        );
      })}
    </div>
  );
}
