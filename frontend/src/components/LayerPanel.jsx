import React from 'react';
import { agencyMeta } from '../data/agencies.js';
import CollapsiblePanel from './CollapsiblePanel.jsx';
import { useT } from '../i18n.js';

const CRIME_LAYERS = ['heat', 'stations', 'colonias', 'alcaldias', 'points'];

export default function LayerPanel({
  agencies, activeBasemap, setActiveBasemap,
  visibleAgencies, setVisibleAgencies,
  crimeLayers, setCrimeLayers,
  collapseSignal,
}) {
  const t = useT();
  const togAgency = (id) => {
    const next = new Set(visibleAgencies);
    next.has(id) ? next.delete(id) : next.add(id);
    setVisibleAgencies(next);
  };
  const togLayer = (id) => setCrimeLayers(L => ({ ...L, [id]: !L[id] }));
  const sortedAgencies = [...agencies].sort((a, b) =>
    (agencyMeta(a.agency_id).displayOrder || 99) - (agencyMeta(b.agency_id).displayOrder || 99));

  return (
    <CollapsiblePanel title={t('l.title')} position={{ top: 12, right: 12 }} width={240} collapseSignal={collapseSignal} defaultCollapsed>
      <div style={{ fontWeight: 600, marginBottom: 8 }}>{t('l.crime')}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 12 }}>
        {CRIME_LAYERS.map(id => (
          <label key={id} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
            <input type="checkbox" checked={!!crimeLayers[id]} onChange={() => togLayer(id)} />
            <span style={{ fontSize: 13 }}>{t(`l.${id}`)}</span>
          </label>
        ))}
      </div>

      <div style={{ fontWeight: 600, marginBottom: 8 }}>{t('l.basemap')}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 12 }}>
        {[{ id: 'osm', label: 'OpenStreetMap' }, { id: 'esri-sat', label: t('l.sat') }].map(b => (
          <label key={b.id} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
            <input type="radio" name="basemap" checked={activeBasemap === b.id} onChange={() => setActiveBasemap(b.id)} />
            <span style={{ fontSize: 13 }}>{b.label}</span>
          </label>
        ))}
      </div>

      <div style={{ fontWeight: 600, marginBottom: 8 }}>{t('l.network')}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {sortedAgencies.map(a => {
          const meta = agencyMeta(a.agency_id);
          return (
            <label key={a.agency_id} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', opacity: meta.dimmed ? 0.7 : 1 }}>
              <input type="checkbox" checked={visibleAgencies.has(a.agency_id)} onChange={() => togAgency(a.agency_id)} />
              <span style={{ display: 'inline-block', width: 12, height: 12, borderRadius: 2, background: meta.color }} />
              <span style={{ fontSize: 13 }}>{meta.label}</span>
              <span style={{ marginLeft: 'auto', fontSize: 11, opacity: 0.6 }}>{a.n_stops}</span>
            </label>
          );
        })}
      </div>
    </CollapsiblePanel>
  );
}
