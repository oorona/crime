// Tiny fetch helpers. The Vite dev server proxies /api → backend:8000.
async function jget(path) {
  const r = await fetch(path);
  if (!r.ok) {
    const err = new Error(`${path}: ${r.status}`);
    err.status = r.status;
    try { err.body = await r.json(); } catch { /* ignore */ }
    throw err;
  }
  return r.json();
}

// Serialize the UI filter object into the query string every crime endpoint
// understands (see backend services/filters.py). Keys absent → omitted.
export function filterQuery(f = {}, extra = {}) {
  const p = new URLSearchParams();
  if (f.from) p.set('from', f.from);
  if (f.to) p.set('to', f.to);
  if (f.categories?.length) p.set('categories', f.categories.join(','));
  if (f.transportOnly) p.set('transport_only', 'true');
  if (f.modes?.length) p.set('modes', f.modes.join(','));
  if (f.alcaldia) p.set('alcaldia', f.alcaldia);
  if (f.hours) p.set('hours', f.hours);
  if (f.dows?.length) p.set('dows', f.dows.join(','));
  if (f.includeNonCriminal) p.set('include_non_criminal', 'true');
  for (const [k, v] of Object.entries(extra)) {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  }
  return p.toString();
}

export const api = {
  health:          () => jget('/health'),
  agencies:        () => jget('/api/agencies'),
  stops:           (agencyId) => jget(`/api/stops?agency_id=${encodeURIComponent(agencyId)}`),
  searchStops:     (q, limit = 15) => jget(`/api/stops/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  shapes:          (agencyId) => jget(`/api/shapes?agency_id=${encodeURIComponent(agencyId)}`),

  coverage:        () => jget('/api/stats/coverage'),
  categoriesList:  () => jget('/api/stats/categories/list'),
  stations:        (f, extra) => jget(`/api/stations?${filterQuery(f, extra)}`),
  stationsRank:    (f, extra) => jget(`/api/stations/rank?${filterQuery(f, extra)}`),
  stationReport:   (key, f, extra) => jget(`/api/stations/${encodeURIComponent(key)}/report?${filterQuery(f, extra)}`),
  crimePoints:     (f, extra) => jget(`/api/crime/points?${filterQuery(f, extra)}`),
  crimeHeat:       (f, extra) => jget(`/api/crime/heat?${filterQuery(f, extra)}`),
  colonias:        (f, extra) => jget(`/api/crime/colonias?${filterQuery(f, extra)}`),
  alcaldias:       (f, extra) => jget(`/api/crime/alcaldias?${filterQuery(f, extra)}`),
  area:            (f, extra) => jget(`/api/stats/area?${filterQuery(f, extra)}`),
  summary:         (f, extra) => jget(`/api/stats/summary?${filterQuery(f, extra)}`),
  trend:           (f, extra) => jget(`/api/stats/trend?${filterQuery(f, extra)}`),
  profile:         (f, extra) => jget(`/api/stats/profile?${filterQuery(f, extra)}`),
};
