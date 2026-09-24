import React from 'react';
import { SEQ_RAMP } from '../data/categories.js';

// Bottom-left legend for the active crime layers.
export default function Legend({ layers, stationMetric, stationMax, coloniaMetric, heatRes }) {
  const rows = [];
  if (layers.heat) rows.push(
    <LegendRow key="heat" title={`Densidad de carpetas (hex ${heatRes} m)`}>
      <Gradient colors={['rgba(33,102,172,0)', '#4575b4', '#fee090', '#f46d43', '#a50026']} />
      <Ends a="menos" b="más" />
    </LegendRow>
  );
  if (layers.stations) rows.push(
    <LegendRow key="st" title={stationMetric === 'rate' ? 'Estaciones: carpetas por millón de entradas' : 'Estaciones: carpetas en el radio'}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {[0.15, 0.45, 0.8, 1].map((k, i) => (
          <span key={i} style={{
            width: 6 + 16 * k, height: 6 + 16 * k, borderRadius: '50%',
            background: SEQ_RAMP[Math.min(4, Math.round(k * 4))], border: '1px solid #fff',
          }} />
        ))}
        <span style={{ fontSize: 10, opacity: 0.8, marginLeft: 4 }}>máx {stationMax != null ? fmt(stationMax) : '—'}</span>
      </div>
    </LegendRow>
  );
  if (layers.colonias) rows.push(
    <LegendRow key="col" title={coloniaMetric === 'per_km2' ? 'Colonias: carpetas por km²' : 'Colonias: carpetas'}>
      <Gradient colors={SEQ_RAMP} />
      <Ends a="quintil 1" b="quintil 5" />
    </LegendRow>
  );
  if (layers.points) rows.push(
    <LegendRow key="pts" title="Puntos: carpetas individuales (zoom ≥ 15), color por categoría" />
  );
  if (!rows.length) return null;
  return (
    <div className="panel" style={{ position: 'absolute', left: 12, bottom: 28, zIndex: 9, width: 250, padding: '8px 10px', fontSize: 11 }}>
      {rows}
    </div>
  );
}

function LegendRow({ title, children }) {
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ opacity: 0.85, marginBottom: 3 }}>{title}</div>
      {children}
    </div>
  );
}
function Gradient({ colors }) {
  return <div style={{ height: 8, borderRadius: 3, background: `linear-gradient(to right, ${colors.join(',')})` }} />;
}
function Ends({ a, b }) {
  return <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, opacity: 0.7 }}><span>{a}</span><span>{b}</span></div>;
}
function fmt(v) { return v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(Math.round(v * 10) / 10); }
