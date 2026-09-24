import React, { useEffect, useMemo, useState } from 'react';
import CollapsiblePanel from './CollapsiblePanel.jsx';
import { api } from '../api.js';
import { categoryColor, shortCategory, LOW_IMPACT, NON_CRIMINAL, MODE_LABELS, DOW_LABELS } from '../data/categories.js';

// Left-hand filter panel. Emits one `filters` object (see api.filterQuery)
// through setFilters; MapApp debounces the refetch.
export default function FilterPanel({ filters, setFilters, coverage, collapseSignal }) {
  const [catalog, setCatalog] = useState(null);
  const [showAllCats, setShowAllCats] = useState(false);

  useEffect(() => {
    api.categoriesList().then(setCatalog).catch(() => setCatalog({ categories: [], modes: [] }));
  }, []);

  const minMonth = coverage?.cases?.from?.slice(0, 7) || '2019-01';
  const maxMonth = coverage?.cases?.to?.slice(0, 7) || '2024-11';
  const set = (patch) => setFilters(f => ({ ...f, ...patch }));

  const highImpactCats = useMemo(
    () => (catalog?.categories || []).map(c => c.categoria).filter(c => c !== LOW_IMPACT && c !== NON_CRIMINAL),
    [catalog],
  );
  const isHighImpact = filters.categories.length > 0 && highImpactCats.length > 0 &&
    filters.categories.length === highImpactCats.length && highImpactCats.every(c => filters.categories.includes(c));

  const toggleCat = (c) => {
    const next = new Set(filters.categories);
    next.has(c) ? next.delete(c) : next.add(c);
    set({ categories: [...next] });
  };
  const toggleMode = (m) => {
    const next = new Set(filters.modes);
    next.has(m) ? next.delete(m) : next.add(m);
    set({ modes: [...next] });
  };
  const toggleDow = (d) => {
    const next = new Set(filters.dows);
    next.has(d) ? next.delete(d) : next.add(d);
    set({ dows: [...next].sort() });
  };
  const [h0, h1] = filters.hours ? filters.hours.split('-').map(Number) : [null, null];

  const cats = catalog?.categories || [];
  const visibleCats = showAllCats ? cats : cats.slice(0, 8);

  return (
    <CollapsiblePanel title="Filtros" position={{ top: 12, left: 12 }} width={300} collapseSignal={collapseSignal}>
      <Section title="Periodo (fecha del hecho)">
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <input type="month" min={minMonth} max={maxMonth} value={filters.from?.slice(0, 7) || ''}
            onChange={e => set({ from: e.target.value ? `${e.target.value}-01` : null })} style={{ flex: 1, fontSize: 12, padding: 4 }} />
          <span style={{ opacity: 0.6 }}>→</span>
          <input type="month" min={minMonth} max={maxMonth} value={filters.to?.slice(0, 7) || ''}
            onChange={e => set({ to: e.target.value ? endOfMonth(e.target.value) : null })} style={{ flex: 1, fontSize: 12, padding: 4 }} />
        </div>
        <div style={{ display: 'flex', gap: 4, marginTop: 6, flexWrap: 'wrap' }}>
          <Chip on={false} onClick={() => set({ from: `${maxMonth.slice(0, 4)}-01-01`, to: endOfMonth(maxMonth) })}>Último año</Chip>
          <Chip on={false} onClick={() => set(lastMonths(maxMonth, 12))}>Últimos 12 meses</Chip>
          <Chip on={false} onClick={() => set({ from: null, to: null })}>Todo ({minMonth.slice(0, 4)}–{maxMonth.slice(0, 4)})</Chip>
        </div>
      </Section>

      <Section title="Categoría de delito">
        <div style={{ display: 'flex', gap: 4, marginBottom: 6, flexWrap: 'wrap' }}>
          <Chip on={filters.categories.length === 0} onClick={() => set({ categories: [] })}>Todas</Chip>
          <Chip on={isHighImpact} onClick={() => set({ categories: isHighImpact ? [] : highImpactCats })}>Solo alto impacto</Chip>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 190, overflowY: 'auto' }}>
          {visibleCats.map(c => (
            <label key={c.categoria} title={c.categoria} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 12 }}>
              <input type="checkbox" checked={filters.categories.includes(c.categoria)} onChange={() => toggleCat(c.categoria)} />
              <span style={{ width: 10, height: 10, borderRadius: 2, background: categoryColor(c.categoria), flexShrink: 0 }} />
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{shortCategory(c.categoria)}</span>
              <span style={{ opacity: 0.5, fontSize: 10 }}>{fmtK(c.n)}</span>
            </label>
          ))}
          {cats.length > 8 && (
            <button onClick={() => setShowAllCats(s => !s)} style={{ fontSize: 11, padding: '2px 6px', alignSelf: 'flex-start' }}>
              {showAllCats ? 'Menos' : `Ver las ${cats.length}`}
            </button>
          )}
        </div>
      </Section>

      <Section title="Transporte público">
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 12 }}>
          <input type="checkbox" checked={filters.transportOnly} onChange={() => set({ transportOnly: !filters.transportOnly, modes: filters.transportOnly ? [] : filters.modes })} />
          Solo delitos contra pasajeros
        </label>
        {filters.transportOnly && (
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
            {(catalog?.modes || []).map(m => (
              <Chip key={m.mode} on={filters.modes.includes(m.mode)} onClick={() => toggleMode(m.mode)} title={`${m.n.toLocaleString()} carpetas`}>
                {MODE_LABELS[m.mode] || m.mode}
              </Chip>
            ))}
          </div>
        )}
      </Section>

      <Section title="Hora y día">
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <input type="checkbox" checked={!!filters.hours} onChange={e => set({ hours: e.target.checked ? '22-5' : null })} /> Horas
          </label>
          {filters.hours && (
            <>
              <input type="number" min={0} max={23} value={h0} onChange={e => set({ hours: `${clampH(e.target.value)}-${h1}` })} style={{ width: 48, padding: 3 }} />
              <span style={{ opacity: 0.6 }}>a</span>
              <input type="number" min={0} max={23} value={h1} onChange={e => set({ hours: `${h0}-${clampH(e.target.value)}` })} style={{ width: 48, padding: 3 }} />
              <span style={{ opacity: 0.6, fontSize: 10 }}>(incl., cruza medianoche)</span>
            </>
          )}
        </div>
        <div style={{ display: 'flex', gap: 3, marginTop: 6 }}>
          {DOW_LABELS.map((d, i) => (
            <Chip key={d} on={filters.dows.includes(i + 1)} onClick={() => toggleDow(i + 1)}>{d}</Chip>
          ))}
        </div>
      </Section>

      <Section title="Estaciones del Metro">
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12, flexWrap: 'wrap' }}>
          <span style={{ opacity: 0.75 }}>Medida:</span>
          <Chip on={filters.normalize === 'count'} onClick={() => set({ normalize: 'count' })}>Conteo</Chip>
          <Chip on={filters.normalize === 'rate'} onClick={() => set({ normalize: 'rate' })} title="Carpetas por millón de entradas al Metro en los mismos meses">Por millón de usuarios</Chip>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12, marginTop: 6 }}>
          <span style={{ opacity: 0.75 }}>Radio:</span>
          <Chip on={filters.radius === 300} onClick={() => set({ radius: 300 })}>300 m</Chip>
          <Chip on={filters.radius === 500} onClick={() => set({ radius: 500 })}>500 m</Chip>
        </div>
      </Section>
    </CollapsiblePanel>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 12 }}>{title}</div>
      {children}
    </div>
  );
}

export function Chip({ on, onClick, children, title }) {
  return (
    <button onClick={onClick} title={title} style={{
      padding: '2px 8px', fontSize: 11, borderRadius: 12,
      background: on ? '#1f6feb' : '#161b22', color: on ? '#fff' : '#cbd5e1',
      border: `1px solid ${on ? '#1f6feb' : '#30363d'}`,
    }}>{children}</button>
  );
}

function fmtK(n) { return n >= 1000 ? `${Math.round(n / 1000)}k` : String(n); }
function clampH(v) { const n = Math.max(0, Math.min(23, parseInt(v || '0', 10) || 0)); return n; }
function endOfMonth(ym) {
  const [y, m] = ym.split('-').map(Number);
  const d = new Date(Date.UTC(y, m, 0));
  return d.toISOString().slice(0, 10);
}
export function lastMonths(maxMonth, n) {
  const [y, m] = maxMonth.split('-').map(Number);
  const start = new Date(Date.UTC(y, m - n, 1));
  return { from: start.toISOString().slice(0, 10), to: endOfMonth(maxMonth) };
}
