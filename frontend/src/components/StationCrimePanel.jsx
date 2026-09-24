import React, { useEffect, useState } from 'react';
import { api } from '../api.js';
import { categoryColor, shortCategory, MODE_LABELS } from '../data/categories.js';
import Sparkline from './charts/Sparkline.jsx';
import Bars from './charts/Bars.jsx';
import HourDowGrid from './charts/HourDowGrid.jsx';

const LINE_COLORS = {
  L1: '#f04e98', L2: '#005eb8', L3: '#af9800', L4: '#6bbbae', L5: '#fdd500', L6: '#da291c',
  L7: '#e87722', L8: '#009a44', L9: '#512f2e', LA: '#981d97', LB: '#b1b3b3', L12: '#b0a32a',
};

export default function StationCrimePanel({ stationKey, filters, onClose }) {
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setReport(null); setError(null);
    api.stationReport(stationKey, filters, { radius: filters.radius, include_profiles: true })
      .then(r => alive && setReport(r))
      .catch(e => alive && setError(e.message));
    return () => { alive = false; };
  }, [stationKey, filters]);

  const t = report?.totals;
  return (
    <div className="panel" style={{ position: 'absolute', top: 12, right: 264, bottom: 12, width: 360, zIndex: 11, overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 16 }}>{report?.station?.station_name || (error ? 'Error' : 'Cargando…')}</div>
          {report && (
            <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
              {report.station.lines.map(l => (
                <span key={l} style={{ background: LINE_COLORS[l] || '#555', color: '#fff', fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 8 }}>{l}</span>
              ))}
              <span style={{ fontSize: 11, opacity: 0.7, marginLeft: 4 }}>radio {report.radius_m} m · {report.window.from?.slice(0, 7)} → {report.window.to?.slice(0, 7)}</span>
            </div>
          )}
        </div>
        <button onClick={onClose} style={{ padding: '2px 8px' }}>×</button>
      </div>
      {error && <div style={{ color: '#f87171', fontSize: 12 }}>{error}</div>}
      {report && (
        <>
          <Tiles items={[
            { label: 'Carpetas', value: t.n_cases.toLocaleString(), sub: `#${t.rank_by_count ?? '—'} de ${t.n_stations}` },
            { label: 'Por millón de entradas', value: t.rate_per_million != null ? t.rate_per_million.toLocaleString() : '—', sub: t.rank_by_rate ? `#${t.rank_by_rate} por tasa` : 'sin afluencia' },
            { label: 'Entradas diarias', value: t.avg_daily_entries != null ? t.avg_daily_entries.toLocaleString() : '—', sub: 'promedio' },
            { label: 'Contra pasajeros', value: t.n_transport.toLocaleString(), sub: t.transport_share != null ? `${Math.round(t.transport_share * 100)}% del total` : '' },
          ]} />

          <Block title="Carpetas por mes (y entradas al Metro, azul)">
            <Sparkline
              series={report.monthly.map(m => ({ label: ymLabel(m.ym), y: m.n }))}
              secondary={report.monthly.map(m => ({ label: ymLabel(m.ym), y: m.entries || 0 }))}
              width={330}
            />
          </Block>

          <Block title="Por categoría">
            <Bars items={report.by_category.slice(0, 8).map(c => ({ label: shortCategory(c.categoria), value: c.n, color: categoryColor(c.categoria) }))} />
          </Block>

          {report.by_mode?.length > 0 && (
            <Block title="Delitos contra pasajeros por modo">
              <Bars items={report.by_mode.map(m => ({ label: MODE_LABELS[m.mode] || m.mode, value: m.n }))} color="#ff6600" />
            </Block>
          )}

          <Block title="Delitos más frecuentes">
            <Bars items={report.top_delitos.slice(0, 8).map(d => ({ label: titleCase(d.delito), value: d.n }))} color="#64748b" maxLabel={44} />
          </Block>

          {report.profiles && (
            <Block title={`Hora y día del hecho (${Math.round((report.profiles.hora_ok_share || 0) * 100)}% con hora válida)`}>
              <HourDowGrid grid={report.profiles.hour_dow} cell={11} />
            </Block>
          )}
        </>
      )}
    </div>
  );
}

export function Tiles({ items }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, margin: '8px 0 10px' }}>
      {items.map((it, i) => (
        <div key={i} style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 6, padding: '6px 8px' }}>
          <div style={{ fontSize: 10, opacity: 0.7 }}>{it.label}</div>
          <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 1.2 }}>{it.value}</div>
          {it.sub && <div style={{ fontSize: 10, opacity: 0.6 }}>{it.sub}</div>}
        </div>
      ))}
    </div>
  );
}

export function Block({ title, children }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 4 }}>{title}</div>
      {children}
    </div>
  );
}

export function ymLabel(ym) { const y = Math.floor(ym / 100), m = ym % 100; return `${String(m).padStart(2, '0')}/${String(y).slice(2)}`; }
export function titleCase(s) { return (s || '').toLowerCase().replace(/(^|\s)\S/g, c => c.toUpperCase()); }
