// Display config per agency. `color` is the fallback when routes.route_color
// is missing. `dimmed` flags agencies we de-emphasize (commuter rail, charters)
// because the user explicitly asked for the 6 main modes.
export const AGENCIES = {
  METRO:       { label: 'Metro',       color: '#FF6600', stopRadius: 5, displayOrder: 1 },
  MB:          { label: 'Metrobús',    color: '#9E1F63', stopRadius: 4, displayOrder: 2 },
  RTP:         { label: 'RTP',         color: '#003DA5', stopRadius: 3, displayOrder: 3, dimmed: true },
  TROLE:       { label: 'Trolebús',    color: '#009B3A', stopRadius: 4, displayOrder: 4 },
  CBB:         { label: 'Cablebús',    color: '#4EC3E0', stopRadius: 5, displayOrder: 5 },
  TL:          { label: 'Tren Ligero', color: '#9D2235', stopRadius: 5, displayOrder: 6 },
  SEMOVI:      { label: 'SEMOVI',      color: '#1F5AF0', stopRadius: 4, displayOrder: 7, dimmed: true },
  CC:          { label: 'Corredores',  color: '#888888', stopRadius: 3, displayOrder: 8, dimmed: true },
  SUB:         { label: 'Suburbano',   color: '#aa3333', stopRadius: 4, displayOrder: 9, dimmed: true },
  INTERURBANO: { label: 'Insurgente',  color: '#83332E', stopRadius: 4, displayOrder: 10, dimmed: true },
  PUMABUS:     { label: 'Pumabús',     color: '#dab500', stopRadius: 3, displayOrder: 11, dimmed: true },
};

export function agencyMeta(id) {
  return AGENCIES[id] || { label: id, color: '#888888', stopRadius: 3, displayOrder: 99 };
}

// Modes that should be visible by default. The 6 the user asked about, all
// enabled. Dimmed agencies start hidden to keep the map readable.
export const DEFAULT_VISIBLE = ['METRO', 'MB', 'TROLE', 'CBB', 'TL', 'RTP'];
