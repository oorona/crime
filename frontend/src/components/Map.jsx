import React, { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { api, filterQuery } from '../api.js';
import { agencyMeta } from '../data/agencies.js';
import { CATEGORY_COLORS, SEQ_RAMP } from '../data/categories.js';

const CENTER = [-99.1332, 19.4326];
const ZOOM = 11;
const POINTS_MIN_ZOOM = 15;

// Basemap tile sources (no API key required).
const BASEMAPS = {
  osm: {
    label: 'OpenStreetMap',
    tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
    attribution: '© OpenStreetMap contributors · Datos: FGJ CDMX, SEMOVI (CC-BY-4.0)',
    maxzoom: 19,
  },
  'esri-sat': {
    label: 'Satélite (ESRI)',
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
    attribution: 'Tiles © Esri — Source: Esri, i-cubed, USDA, AEX, GeoEye, USGS · Datos: FGJ CDMX (CC-BY-4.0)',
    maxzoom: 19,
  },
};

function buildStyle(basemap) {
  const def = BASEMAPS[basemap] || BASEMAPS.osm;
  return {
    version: 8,
    glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
    sources: {
      basemap: { type: 'raster', tiles: def.tiles, tileSize: 256, attribution: def.attribution, maxzoom: def.maxzoom },
    },
    layers: [{ id: 'basemap', type: 'raster', source: 'basemap' }],
  };
}

export function heatResForZoom(z) {
  return z < 12 ? 1000 : z < 14 ? 500 : 250;
}

// Heat points are hex centroids spaced sqrt(3)*res metres apart. A fixed pixel
// radius leaves gaps between them (isolated dots), so scale the radius with the
// map: ~1.5x the on-screen centroid spacing, which blends neighbours into a
// continuous surface at every zoom. 73823 m/px is zoom 0 at CDMX's latitude.
function heatRadius(res) {
  const k = (1.5 * Math.sqrt(3) * res) / 73823;
  return ['interpolate', ['exponential', 2], ['zoom'], 0, k, 20, k * 2 ** 20];
}

const categoryMatch = ['match', ['get', 'categoria'],
  ...Object.entries(CATEGORY_COLORS).flat(), '#9ca3af'];

export default function Map({
  agencies, onAgenciesLoaded,
  activeBasemap, visibleAgencies,
  crimeLayers, filters, viewsReady,
  onStationClick, onAreaClick, onMapReady, onStationsLoaded,
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const loadedRef = useRef({ shapes: {}, stops: {} });
  const cacheRef = useRef(new window.Map());
  const reqRef = useRef({});            // kind → latest request id (drop stale responses)
  const latest = useRef({ filters, crimeLayers, viewsReady, heatRes: heatResForZoom(ZOOM) });
  latest.current = { ...latest.current, filters, crimeLayers, viewsReady };
  const pointsTimer = useRef(null);
  const stationsFC = useRef(null);
  const areaFC = useRef({ colonias: null, alcaldias: null });

  // ── data loaders (read the latest props from refs so map handlers can call them) ──
  const cachedFetch = async (key, fn) => {
    const c = cacheRef.current;
    if (c.has(key)) return c.get(key);
    const data = await fn();
    c.set(key, data);
    if (c.size > 24) c.delete(c.keys().next().value);
    return data;
  };

  const loadHeat = async () => {
    const map = mapRef.current; const { filters: f } = latest.current;
    const res = heatResForZoom(map.getZoom());
    latest.current.heatRes = res;
    const id = (reqRef.current.heat = (reqRef.current.heat || 0) + 1);
    try {
      const fc = await cachedFetch(`heat|${res}|${filterQuery(f)}`, () => api.crimeHeat(f, { res, geom: 'centroid' }));
      if (id !== reqRef.current.heat) return;
      map.getSource('crime-heat').setData(fc);
      map.setPaintProperty('crime-heat-layer', 'heatmap-radius', heatRadius(res));
    } catch (e) { console.warn('heat load failed', e); }
  };

  const loadStations = async () => {
    const map = mapRef.current; const { filters: f } = latest.current;
    const metric = f.normalize === 'rate' ? 'rate' : 'count';
    const prop = metric === 'rate' ? 'rate_per_million' : 'n_cases';
    const id = (reqRef.current.stations = (reqRef.current.stations || 0) + 1);
    try {
      const fc = await cachedFetch(`stations|${f.radius}|${metric}|${filterQuery(f)}`,
        () => api.stations(f, { radius: f.radius, normalize: metric }));
      if (id !== reqRef.current.stations) return;
      stationsFC.current = fc;
      const max = Math.max(1, ...fc.features.map(ft => ft.properties[prop] || 0));
      map.getSource('stations-crime').setData(fc);
      map.setPaintProperty('stations-crime-circle', 'circle-radius',
        ['interpolate', ['linear'], ['coalesce', ['get', prop], 0], 0, 3, max, 22]);
      map.setPaintProperty('stations-crime-circle', 'circle-color',
        ['interpolate', ['linear'], ['coalesce', ['get', prop], 0],
          0, SEQ_RAMP[0], max * 0.25, SEQ_RAMP[1], max * 0.5, SEQ_RAMP[2], max * 0.75, SEQ_RAMP[3], max, SEQ_RAMP[4]]);
      onStationsLoaded?.({ metric, max });
    } catch (e) { console.warn('stations load failed', e); }
  };

  const loadColonias = async () => {
    const map = mapRef.current; const { filters: f } = latest.current;
    const normalize = f.normalize === 'rate' ? 'per_km2' : 'count';
    const id = (reqRef.current.colonias = (reqRef.current.colonias || 0) + 1);
    try {
      const fc = await cachedFetch(`colonias|${normalize}|${filterQuery(f)}`, () => api.colonias(f, { normalize }));
      if (id !== reqRef.current.colonias) return;
      areaFC.current.colonias = fc;
      map.getSource('colonias').setData(fc);
    } catch (e) { console.warn('colonias load failed', e); }
  };

  const loadAlcaldias = async () => {
    const map = mapRef.current; const { filters: f } = latest.current;
    const id = (reqRef.current.alcaldias = (reqRef.current.alcaldias || 0) + 1);
    try {
      const fc = await cachedFetch(`alcaldias|${filterQuery(f)}`, () => api.alcaldias(f));
      if (id !== reqRef.current.alcaldias) return;
      areaFC.current.alcaldias = fc;
      const max = Math.max(1, ...fc.features.map(ft => ft.properties.n || 0));
      map.getSource('alcaldias').setData(fc);
      map.setPaintProperty('alcaldia-fill', 'fill-color',
        ['interpolate', ['linear'], ['coalesce', ['get', 'n'], 0], 0, SEQ_RAMP[0], max, SEQ_RAMP[4]]);
    } catch (e) { console.warn('alcaldias load failed', e); }
  };

  const loadPoints = () => {
    const map = mapRef.current; const { filters: f, crimeLayers: L, viewsReady: ok } = latest.current;
    if (!ok || !L.points || map.getZoom() < POINTS_MIN_ZOOM) return;
    clearTimeout(pointsTimer.current);
    pointsTimer.current = setTimeout(async () => {
      const b = map.getBounds();
      const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map(v => v.toFixed(5)).join(',');
      const id = (reqRef.current.points = (reqRef.current.points || 0) + 1);
      try {
        const fc = await api.crimePoints(f, { bbox, limit: 5000 });
        if (id !== reqRef.current.points) return;
        map.getSource('crime-points').setData(fc);
      } catch (e) { console.warn('points load failed', e); }
    }, 250);
  };

  // ── one-time map init ─────────────────────────────────────────────────────
  useEffect(() => {
    if (mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: buildStyle(activeBasemap),
      center: CENTER, zoom: ZOOM, minZoom: 9,
    });
    map.addControl(new maplibregl.NavigationControl(), 'bottom-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
    mapRef.current = map;

    map.on('load', async () => {
      let ag = [];
      try { ag = await api.agencies(); } catch (e) { console.warn('agencies failed', e); }
      onAgenciesLoaded(ag);

      for (const s of ['alcaldias', 'colonias', 'crime-heat', 'crime-points', 'stations-crime', 'highlight', 'hotspots']) {
        map.addSource(s, { type: 'geojson', data: emptyFC() });
      }

      // ── area choropleths (bottom) ──
      map.addLayer({ id: 'alcaldia-fill', type: 'fill', source: 'alcaldias', layout: { visibility: 'none' },
        paint: { 'fill-color': SEQ_RAMP[2], 'fill-opacity': 0.35 } });
      map.addLayer({ id: 'alcaldia-line', type: 'line', source: 'alcaldias', layout: { visibility: 'none' },
        paint: { 'line-color': '#e6edf3', 'line-width': 1.2, 'line-opacity': 0.7 } });
      map.addLayer({ id: 'colonia-fill', type: 'fill', source: 'colonias', layout: { visibility: 'none' },
        paint: {
          'fill-color': ['step', ['get', 'quantile'], 'rgba(0,0,0,0)',
            1, SEQ_RAMP[0], 2, SEQ_RAMP[1], 3, SEQ_RAMP[2], 4, SEQ_RAMP[3], 5, SEQ_RAMP[4]],
          'fill-opacity': 0.5,
        } });
      map.addLayer({ id: 'colonia-line', type: 'line', source: 'colonias', layout: { visibility: 'none' },
        paint: { 'line-color': '#0d1117', 'line-width': 0.4, 'line-opacity': 0.6 } });

      // ── heat ──
      map.addLayer({ id: 'crime-heat-layer', type: 'heatmap', source: 'crime-heat', layout: { visibility: 'none' },
        paint: {
          'heatmap-weight': ['^', ['coalesce', ['get', 'n_norm'], 0], 0.75],
          // radius tracks cell spacing, so overlap (and density) is zoom-invariant
          'heatmap-intensity': 1.2,
          'heatmap-radius': heatRadius(heatResForZoom(ZOOM)),
          'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'],
            0, 'rgba(33,102,172,0)', 0.15, '#4575b4', 0.4, '#fee090', 0.65, '#f46d43', 1, '#a50026'],
          'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 14, 0.85, 17, 0.4],
        } });

      // ── transit network ──
      for (const a of ag) {
        const id = a.agency_id;
        map.addSource(`shape-${id}`, { type: 'geojson', data: emptyFC() });
        map.addSource(`stop-${id}`, { type: 'geojson', data: emptyFC() });
        const meta = agencyMeta(id);
        map.addLayer({ id: `shape-${id}-layer`, type: 'line', source: `shape-${id}`, layout: { visibility: 'none' },
          paint: { 'line-color': ['coalesce', ['concat', '#', ['get', 'route_color']], meta.color], 'line-width': 2.5, 'line-opacity': 0.8 } });
        map.addLayer({ id: `stop-${id}-layer`, type: 'circle', source: `stop-${id}`, minzoom: 13, layout: { visibility: 'none' },
          paint: {
            'circle-radius': meta.stopRadius, 'circle-color': meta.color,
            'circle-stroke-color': '#0d1117', 'circle-stroke-width': 1,
            'circle-opacity': ['interpolate', ['linear'], ['zoom'], 13, 0, 14, 1],
            'circle-stroke-opacity': ['interpolate', ['linear'], ['zoom'], 13, 0, 14, 1],
          } });
      }

      // ── individual cases (street zoom) ──
      map.addLayer({ id: 'crime-points-layer', type: 'circle', source: 'crime-points', minzoom: POINTS_MIN_ZOOM, layout: { visibility: 'none' },
        paint: { 'circle-radius': 4, 'circle-color': categoryMatch, 'circle-opacity': 0.85,
                 'circle-stroke-color': '#0d1117', 'circle-stroke-width': 0.8 } });

      // ── Metro stations (graduated circles) ──
      map.addLayer({ id: 'stations-crime-circle', type: 'circle', source: 'stations-crime', layout: { visibility: 'none' },
        paint: { 'circle-radius': 6, 'circle-color': SEQ_RAMP[2], 'circle-opacity': 0.85,
                 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.2 } });
      map.addLayer({ id: 'stations-crime-label', type: 'symbol', source: 'stations-crime', minzoom: 13, layout: {
          'text-field': ['get', 'station_name'], 'text-size': 11, 'text-anchor': 'top', 'text-offset': [0, 1.1],
          'text-allow-overlap': false, visibility: 'none',
        }, paint: { 'text-color': '#ffffff', 'text-halo-color': '#0d1117', 'text-halo-width': 1.6 } });

      // ── chat highlights ──
      map.addLayer({ id: 'hotspots-layer', type: 'circle', source: 'hotspots',
        paint: { 'circle-radius': ['interpolate', ['linear'], ['get', 'k'], 0, 8, 1, 26], 'circle-color': '#f43f5e',
                 'circle-opacity': 0.35, 'circle-stroke-color': '#f43f5e', 'circle-stroke-width': 2 } });
      map.addLayer({ id: 'hotspots-label', type: 'symbol', source: 'hotspots', layout: {
          'text-field': ['get', 'label'], 'text-size': 11, 'text-anchor': 'top', 'text-offset': [0, 1.6] },
        paint: { 'text-color': '#fecdd3', 'text-halo-color': '#0d1117', 'text-halo-width': 1.6 } });
      map.addLayer({ id: 'highlight-area', type: 'line', source: 'highlight', filter: ['!=', ['geometry-type'], 'Point'],
        paint: { 'line-color': '#facc15', 'line-width': 3 } });
      map.addLayer({ id: 'highlight-ring', type: 'circle', source: 'highlight', filter: ['==', ['geometry-type'], 'Point'],
        paint: { 'circle-radius': 16, 'circle-color': 'rgba(250,204,21,0.15)', 'circle-stroke-color': '#facc15', 'circle-stroke-width': 3 } });

      // ── interaction: one click handler, priority order ──
      const clickable = ['stations-crime-circle', 'crime-points-layer', 'colonia-fill', 'alcaldia-fill'];
      map.on('click', (e) => {
        const hits = map.queryRenderedFeatures(e.point, { layers: clickable.filter(l => map.getLayer(l)) });
        if (!hits.length) return;
        for (const layerId of clickable) {
          const f = hits.find(h => h.layer.id === layerId);
          if (!f) continue;
          const p = f.properties;
          if (layerId === 'stations-crime-circle') { onStationClick?.(p.station_key); return; }
          if (layerId === 'crime-points-layer') {
            new maplibregl.Popup({ maxWidth: '300px', className: 'route-popup' })
              .setLngLat(e.lngLat).setHTML(_pointPopupHtml(p)).addTo(map);
            return;
          }
          if (layerId === 'colonia-fill') { onAreaClick?.({ kind: 'colonia', id: p.id, name: p.colonia, alcaldia: p.alcaldia }); return; }
          if (layerId === 'alcaldia-fill') { onAreaClick?.({ kind: 'alcaldia', id: p.id, name: p.alcaldia }); return; }
        }
      });
      map.on('mousemove', (e) => {
        const hits = map.queryRenderedFeatures(e.point, { layers: clickable.filter(l => map.getLayer(l)) });
        map.getCanvas().style.cursor = hits.length ? 'pointer' : '';
      });
      map.on('zoomend', () => {
        const { crimeLayers: L, viewsReady: ok } = latest.current;
        if (ok && L.heat && heatResForZoom(map.getZoom()) !== latest.current.heatRes) loadHeat();
      });
      map.on('moveend', () => loadPoints());

      onMapReady && onMapReady({
        highlightStations: async (keys, { fit = true } = {}) => {
          let fc = stationsFC.current;
          if (!fc) { try { fc = await api.stations(latest.current.filters, { radius: latest.current.filters.radius }); } catch { return; } }
          const feats = fc.features.filter(ft => keys.includes(ft.properties.station_key));
          map.getSource('highlight').setData({ type: 'FeatureCollection', features: feats });
          if (fit && feats.length) fitTo(map, feats, feats.length === 1 ? 15 : 13);
        },
        highlightArea: async ({ kind, id, name }) => {
          let fc = areaFC.current[kind === 'colonia' ? 'colonias' : 'alcaldias'];
          if (!fc) {
            try { fc = kind === 'colonia' ? await api.colonias(latest.current.filters) : await api.alcaldias(latest.current.filters); }
            catch { return; }
            areaFC.current[kind === 'colonia' ? 'colonias' : 'alcaldias'] = fc;
          }
          const feats = fc.features.filter(ft => (id != null && ft.properties.id === id) ||
            (name && (ft.properties.colonia === name || ft.properties.alcaldia === name)));
          map.getSource('highlight').setData({ type: 'FeatureCollection', features: feats });
          if (feats.length) fitTo(map, feats, kind === 'colonia' ? 15 : 12);
        },
        showHotspots: (cells = []) => {
          const max = Math.max(1, ...cells.map(c => c.n || 0));
          const feats = cells.map((c, i) => ({ type: 'Feature',
            geometry: { type: 'Point', coordinates: [c.lon, c.lat] },
            properties: { k: (c.n || 0) / max, label: `#${i + 1} ${c.colonia || ''} (${c.n})` } }));
          map.getSource('hotspots').setData({ type: 'FeatureCollection', features: feats });
          if (feats.length) fitTo(map, feats, 13);
        },
        clearHighlight: () => {
          map.getSource('highlight').setData(emptyFC());
          map.getSource('hotspots').setData(emptyFC());
        },
        flyToStation: async (key) => {
          let fc = stationsFC.current;
          if (!fc) { try { fc = await api.stations(latest.current.filters); } catch { return; } }
          const ft = fc.features.find(f => f.properties.station_key === key);
          if (ft) map.flyTo({ center: ft.geometry.coordinates, zoom: Math.max(map.getZoom(), 14), speed: 1.2 });
        },
        invalidate: () => cacheRef.current.clear(),
        getMap: () => map,
      });
      latest.current.loaded = true;
      // Initial crime layers if the data is already there.
      syncCrimeLayers();
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── basemap toggling ──────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const def = BASEMAPS[activeBasemap];
    if (!def) return;
    const src = map.getSource('basemap');
    if (src && src.tiles) {
      map.removeLayer('basemap');
      map.removeSource('basemap');
      map.addSource('basemap', { type: 'raster', tiles: def.tiles, tileSize: 256, attribution: def.attribution, maxzoom: def.maxzoom });
      map.addLayer({ id: 'basemap', type: 'raster', source: 'basemap' }, map.getStyle().layers[1]?.id);
    }
  }, [activeBasemap]);

  // ── visible agencies → fetch + show/hide layers ───────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !agencies.length) return;
    (async () => {
      for (const a of agencies) {
        const id = a.agency_id;
        const visible = visibleAgencies.has(id);
        if (visible && !loadedRef.current.shapes[id]) {
          try { map.getSource(`shape-${id}`).setData(await api.shapes(id)); loadedRef.current.shapes[id] = true; }
          catch (e) { console.warn('shape load failed', id, e); }
        }
        if (visible && !loadedRef.current.stops[id]) {
          try { map.getSource(`stop-${id}`).setData(await api.stops(id)); loadedRef.current.stops[id] = true; }
          catch (e) { console.warn('stop load failed', id, e); }
        }
        if (map.getLayer(`shape-${id}-layer`)) map.setLayoutProperty(`shape-${id}-layer`, 'visibility', visible ? 'visible' : 'none');
        if (map.getLayer(`stop-${id}-layer`)) map.setLayoutProperty(`stop-${id}-layer`, 'visibility', visible ? 'visible' : 'none');
      }
    })();
  }, [agencies, visibleAgencies]);

  // ── crime layers: visibility + (re)fetch on filter change ────────────────
  const syncCrimeLayers = () => {
    const map = mapRef.current;
    if (!map || !latest.current.loaded) return;
    const { crimeLayers: L, viewsReady: ok } = latest.current;
    const vis = (ids, on) => ids.forEach(id => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none'));
    vis(['alcaldia-fill', 'alcaldia-line'], L.alcaldias);
    vis(['colonia-fill', 'colonia-line'], L.colonias);
    vis(['crime-heat-layer'], L.heat);
    vis(['crime-points-layer'], L.points);
    vis(['stations-crime-circle', 'stations-crime-label'], L.stations);
    if (!ok) return;
    if (L.heat) loadHeat();
    if (L.stations) loadStations();
    if (L.colonias) loadColonias();
    if (L.alcaldias) loadAlcaldias();
    if (L.points) loadPoints();
  };
  useEffect(() => { syncCrimeLayers(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [crimeLayers, filters, viewsReady]);

  return <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />;
}

function fitTo(map, feats, maxZoom) {
  const coords = [];
  const walk = (c) => (typeof c[0] === 'number' ? coords.push(c) : c.forEach(walk));
  feats.forEach(f => walk(f.geometry.coordinates));
  if (!coords.length) return;
  const xs = coords.map(c => c[0]), ys = coords.map(c => c[1]);
  map.fitBounds([[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]],
    { padding: 90, maxZoom, duration: 700 });
}

function emptyFC() { return { type: 'FeatureCollection', features: [] }; }

function _esc(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function _pointPopupHtml(p) {
  const color = CATEGORY_COLORS[p.categoria] || '#9ca3af';
  return `<div style="background:#0d1117;color:#e6edf3;padding:6px 4px;font-size:12px">
    <div style="display:flex;gap:6px;align-items:center;margin-bottom:4px">
      <span style="width:10px;height:10px;border-radius:2px;background:${color};display:inline-block"></span>
      <strong>${_esc(p.delito)}</strong></div>
    <div style="opacity:.8">${_esc(p.categoria)}</div>
    <div style="margin-top:4px">${_esc(p.fecha)}${p.hora_ok ? '' : ' <span style="opacity:.6">(hora no registrada)</span>'}</div>
    <div style="opacity:.8">${_esc(p.colonia || '')}${p.alcaldia ? ', ' + _esc(p.alcaldia) : ''}</div>
    ${p.station ? `<div style="opacity:.8">Metro ${_esc(p.station)} a ${_esc(p.station_m)} m</div>` : ''}
  </div>`;
}
