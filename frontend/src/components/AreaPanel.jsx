import React, { useEffect, useState } from 'react';
import { api } from '../api.js';
import { categoryColor, shortCategory } from '../data/categories.js';
import Sparkline from './charts/Sparkline.jsx';
import Bars from './charts/Bars.jsx';
import { Tiles, Block, ymLabel, titleCase } from './StationCrimePanel.jsx';

// Summary for a clicked colonia or alcaldía. `area` = {kind, id, name}.
export default function AreaPanel({ area, filters, onClose, onStationClick }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setData(null); setError(null);
    const extra = area.kind === 'colonia' ? { colonia_id: area.id } : { alcaldia: area.name };
    // The area itself is the scope: strip any alcaldía filter so the peer ranking stays city-wide.
    api.area({ ...filters, alcaldia: null }, extra)
      .then(d => alive && setData(d))
      .catch(e => alive && setError(e.message));
    return () => { alive = false; };
  }, [area, filters]);

  return (
    <div className="panel" style={{ position: 'absolute', top: 12, right: 264, bottom: 12, width: 360, zIndex: 11, overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 16 }}>{area.name}</div>
          <div style={{ fontSize: 11, opacity: 0.7 }}>
            {area.kind === 'colonia' ? `Colonia · ${data?.area?.parent || area.alcaldia || ''}` : 'Alcaldía'}
            {data && <> · {data.window.from?.slice(0, 7)} → {data.window.to?.slice(0, 7)}</>}
          </div>
        </div>
        <button onClick={onClose} style={{ padding: '2px 8px' }}>×</button>
      </div>
      {error && <div style={{ color: '#f87171', fontSize: 12 }}>{error}</div>}
      {data && (
        <>
          <Tiles items={[
            { label: 'Carpetas', value: data.n_cases.toLocaleString(), sub: `#${data.rank_by_count ?? '—'} de ${data.n_peers}` },
            { label: 'Por km²', value: data.per_km2 != null ? data.per_km2.toLocaleString() : '—', sub: data.rank_by_density ? `#${data.rank_by_density} por densidad` : '' },
            { label: 'Por mes', value: data.per_month != null ? data.per_month.toLocaleString() : '—', sub: `${data.window.months} meses` },
            { label: 'Contra pasajeros', value: data.n_transport.toLocaleString(), sub: data.n_cases ? `${Math.round(data.n_transport / data.n_cases * 100)}%` : '' },
          ]} />
          <Block title="Carpetas por mes">
            <Sparkline series={data.monthly.map(m => ({ label: ymLabel(m.ym), y: m.n }))} width={330} />
          </Block>
          <Block title="Por categoría">
            <Bars items={data.top_categories.map(c => ({ label: shortCategory(c.categoria), value: c.n, color: categoryColor(c.categoria) }))} />
          </Block>
          <Block title="Delitos más frecuentes">
            <Bars items={data.top_delitos.map(d => ({ label: titleCase(d.delito), value: d.n }))} color="#64748b" maxLabel={44} />
          </Block>
          {data.metro_stations?.length > 0 && (
            <Block title="Estaciones del Metro en la zona">
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {data.metro_stations.map(s => (
                  <button key={s.station_key} onClick={() => onStationClick?.(s.station_key)} style={{ fontSize: 11, padding: '2px 8px', borderRadius: 12 }}>
                    {s.station_name} <span style={{ opacity: 0.6 }}>{s.lines.join('/')}</span>
                  </button>
                ))}
              </div>
            </Block>
          )}
        </>
      )}
    </div>
  );
}
