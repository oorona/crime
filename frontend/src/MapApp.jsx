import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import Map from './components/Map.jsx';
import LayerPanel from './components/LayerPanel.jsx';
import FilterPanel, { lastMonths } from './components/FilterPanel.jsx';
import StationCrimePanel from './components/StationCrimePanel.jsx';
import AreaPanel from './components/AreaPanel.jsx';
import Legend from './components/Legend.jsx';
import MiniChat from './components/MiniChat.jsx';
import { api } from './api.js';
import { useLang } from './i18n.js';

const DEFAULT_AGENCIES = ['METRO', 'MB'];
const DEFAULT_LAYERS = { heat: true, stations: true, colonias: false, alcaldias: false, points: false };
export const DEFAULT_FILTERS = {
  from: null, to: null, categories: [], transportOnly: false, modes: [],
  alcaldia: null, hours: null, dows: [], normalize: 'count', radius: 300,
};

export default function MapApp({ health }) {
  const viewsReady = !!health?.views_populated;
  const lang = useLang();
  const [agencies, setAgencies] = useState([]);
  const [activeBasemap, setActiveBasemap] = useState('osm');
  const [visibleAgencies, setVisibleAgencies] = useState(new Set(DEFAULT_AGENCIES));
  const [crimeLayers, setCrimeLayers] = useState(DEFAULT_LAYERS);
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [coverage, setCoverage] = useState(null);
  const [selectedStation, setSelectedStation] = useState(null);
  const [selectedArea, setSelectedArea] = useState(null);
  const [legendInfo, setLegendInfo] = useState({ metric: 'count', max: null });
  const [isMapReady, setIsMapReady] = useState(false);
  const mapApiRef = useRef(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const urlHandledRef = useRef(false);

  // Coverage → default window = last 12 months of data.
  useEffect(() => {
    if (!viewsReady || coverage) return;
    api.coverage().then(c => {
      setCoverage(c);
      if (c?.cases?.to) setFilters(f => (f.from || f.to) ? f : { ...f, ...lastMonths(c.cases.to.slice(0, 7), 12) });
    }).catch(e => console.warn('coverage failed', e));
  }, [viewsReady, coverage]);

  // Debounce the filters the map + panels see (the panel edits are chatty).
  const [debounced, setDebounced] = useState(filters);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(filters), 350);
    return () => clearTimeout(t);
  }, [filters]);

  // Deep links from the chat: ?station=key | ?stations=k1,k2 | ?alcaldia=name | ?colonia_id=n
  useEffect(() => {
    if (!isMapReady || !viewsReady || urlHandledRef.current) return;
    const station = searchParams.get('station');
    const stations = searchParams.get('stations');
    const alcaldia = searchParams.get('alcaldia');
    const coloniaId = searchParams.get('colonia_id');
    const from = searchParams.get('from'), to = searchParams.get('to');
    if (!station && !stations && !alcaldia && !coloniaId) return;
    urlHandledRef.current = true;
    if (from || to) setFilters(f => ({ ...f, from: from || f.from, to: to || f.to }));
    if (station) { setSelectedStation(station); mapApiRef.current?.highlightStations([station], { fit: true }); }
    else if (stations) mapApiRef.current?.highlightStations(stations.split(','), { fit: true });
    if (alcaldia) { const a = { kind: 'alcaldia', name: alcaldia }; setSelectedArea(a); mapApiRef.current?.highlightArea(a); }
    if (coloniaId) { const a = { kind: 'colonia', id: Number(coloniaId), name: searchParams.get('name') || 'Colonia' }; setSelectedArea(a); mapApiRef.current?.highlightArea(a); }
    setSearchParams({}, { replace: true });
  }, [isMapReady, viewsReady, searchParams, setSearchParams]);

  const onStationClick = useCallback((key) => {
    setSelectedArea(null);
    setSelectedStation(key);
    mapApiRef.current?.highlightStations([key], { fit: false });
  }, []);
  const onAreaClick = useCallback((area) => {
    setSelectedStation(null);
    setSelectedArea(area);
    mapApiRef.current?.highlightArea(area);
  }, []);
  const closePanels = () => { setSelectedStation(null); setSelectedArea(null); mapApiRef.current?.clearHighlight(); };

  const applyFilters = useCallback((patch) => setFilters(f => ({ ...f, ...patch })), []);
  const mapContext = useMemo(() => ({
    date_from: debounced.from, date_to: debounced.to,
    categories: debounced.categories.length ? debounced.categories : null,
    transport_only: debounced.transportOnly || null,
    modes: debounced.modes.length ? debounced.modes : null,
    alcaldia: debounced.alcaldia, station_key: selectedStation,
  }), [debounced, selectedStation]);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <Map
        agencies={agencies}
        onAgenciesLoaded={setAgencies}
        activeBasemap={activeBasemap}
        visibleAgencies={visibleAgencies}
        crimeLayers={crimeLayers}
        filters={debounced}
        viewsReady={viewsReady}
        lang={lang}
        onStationClick={onStationClick}
        onAreaClick={onAreaClick}
        onStationsLoaded={setLegendInfo}
        onMapReady={(mapApi) => { mapApiRef.current = mapApi; setIsMapReady(true); }}
      />
      <FilterPanel filters={filters} setFilters={setFilters} coverage={coverage} />
      <LayerPanel
        agencies={agencies}
        activeBasemap={activeBasemap} setActiveBasemap={setActiveBasemap}
        visibleAgencies={visibleAgencies} setVisibleAgencies={setVisibleAgencies}
        crimeLayers={crimeLayers} setCrimeLayers={setCrimeLayers}
      />
      <Legend layers={crimeLayers} stationMetric={legendInfo.metric} stationMax={legendInfo.max}
        coloniaMetric={debounced.normalize === 'rate' ? 'per_km2' : 'count'}
        heatRes={mapApiRef.current?.getMap ? heatResLabel(mapApiRef.current.getMap().getZoom()) : 500} />
      <MiniChat
        mapApi={mapApiRef}
        isMapReady={isMapReady}
        mapContext={mapContext}
        onApplyFilters={applyFilters}
        onStationClick={onStationClick}
        onAreaClick={onAreaClick}
        chatEnabled={health?.chat_enabled}
      />
      {selectedStation && (
        <StationCrimePanel stationKey={selectedStation} filters={debounced} onClose={closePanels} />
      )}
      {selectedArea && !selectedStation && (
        <AreaPanel area={selectedArea} filters={debounced} onClose={closePanels} onStationClick={onStationClick} />
      )}
    </div>
  );
}

function heatResLabel(z) { return z < 12 ? 1000 : z < 14 ? 500 : 250; }
