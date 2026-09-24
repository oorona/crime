import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useChatStream } from '../hooks/useChatStream.js';

// Minimal chat affordance pinned to the top-right of the map (under the layer
// panel). Independent useChatStream instance. When a turn finishes, the tool
// calls the agent made are mirrored on the map: stations are highlighted,
// areas outlined, hotspots drawn.
export default function MiniChat({ mapApi, isMapReady, mapContext, onApplyFilters, onStationClick, onAreaClick, chatEnabled }) {
  const { state, send, reset } = useChatStream();
  const [input, setInput] = useState('');
  const [collapsed, setCollapsed] = useState(false);
  const firedForTurnRef = useRef(new Set());
  const scrollEndRef = useRef(null);

  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [state.turns, state.turns[state.turns.length - 1]?.assistantText]);

  useEffect(() => {
    if (!isMapReady || !mapApi.current) return;
    if (state.status !== 'done') return;
    const turnIdx = state.turns.length - 1;
    if (turnIdx < 0 || firedForTurnRef.current.has(turnIdx)) return;
    const turn = state.turns[turnIdx];
    if (!turn?.assistantText) return;
    firedForTurnRef.current.add(turnIdx);
    const calls = (turn.toolCalls || []).filter(tc => tc.status === 'done' && tc.result && !tc.result.error);
    const api = mapApi.current;
    const stationCall = [...calls].reverse().find(tc => tc.tool === 'station_crime_stats');
    const rankCall = [...calls].reverse().find(tc => tc.tool === 'rank_stations');
    const areaCall = [...calls].reverse().find(tc => tc.tool === 'area_summary');
    const hotCall = [...calls].reverse().find(tc => tc.tool === 'hotspots');
    api.clearHighlight();
    if (hotCall?.result?.cells) api.showHotspots(hotCall.result.cells);
    if (stationCall?.result?.station?.station_key) {
      const key = stationCall.result.station.station_key;
      onStationClick?.(key);
      api.highlightStations([key], { fit: true });
    } else if (rankCall?.result?.stations?.length) {
      api.highlightStations(rankCall.result.stations.map(s => s.station_key), { fit: true });
    } else if (areaCall?.result?.area) {
      const a = areaCall.result.area;
      const area = { kind: a.kind, id: a.id, name: a.name };
      onAreaClick?.(area);
    }
  }, [state.status, state.turns, isMapReady, mapApi, onStationClick, onAreaClick]);

  const onSubmit = (e) => {
    e.preventDefault();
    const v = input.trim();
    if (!v || state.status === 'streaming') return;
    setInput('');
    send(v, { mapContext });
  };
  const onNew = useCallback(() => { firedForTurnRef.current = new Set(); reset(null); mapApi.current?.clearHighlight(); }, [reset, mapApi]);

  const lastTurn = state.turns[state.turns.length - 1];
  const chatFilters = extractFilters(lastTurn);
  const showPensando = state.status === 'streaming' && !lastTurn?.assistantText;
  const showMessages = state.turns.length > 0 || showPensando || state.status === 'error';

  return (
    <div className="panel" style={{
      position: 'absolute', bottom: 28, right: 12, width: 360, zIndex: 11,
      display: 'flex', flexDirection: 'column', padding: 0,
      maxHeight: collapsed ? undefined : 'calc(100% - 60px)',
    }}>
      <button type="button" onClick={() => setCollapsed(c => !c)} style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%',
        padding: '8px 12px', background: 'transparent', color: 'inherit', border: 'none',
        borderBottom: collapsed ? 'none' : '1px solid #30363d', cursor: 'pointer',
        fontSize: 13, fontWeight: 600, textAlign: 'left',
      }}>
        <span>🔎 Pregúntale a los datos</span>
        <span style={{ opacity: 0.7, fontSize: 11 }}>{collapsed ? '▸' : '▾'}</span>
      </button>
      {!collapsed && chatEnabled === false && (
        <div style={{ padding: '6px 12px', fontSize: 11, color: '#fbbf24' }}>Chat deshabilitado: falta la clave de Gemini o del MCP en secrets/.</div>
      )}
      {!collapsed && showMessages && (
        <div style={{ padding: 12, overflowY: 'auto', maxHeight: 300, display: 'flex', flexDirection: 'column', gap: 8, minHeight: 0, borderBottom: '1px solid #30363d' }}>
          {state.turns.map((turn, i) => (
            <Exchange key={i} turn={turn} streaming={i === state.turns.length - 1 && state.status === 'streaming'} />
          ))}
          {showPensando && (
            <div style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 10px',
              background: '#0d1117', border: '1px dashed #30363d', borderRadius: 16, fontSize: 12, color: '#94a3b8' }}>
              <Spinner /><span>{workingLabel(lastTurn, state.status)}</span>
            </div>
          )}
          {state.status === 'error' && (
            <div style={{ padding: 8, background: '#3f1d1d', color: '#fca5a5', border: '1px solid #7f1d1d', borderRadius: 4, fontSize: 12 }}>Error: {state.error}</div>
          )}
          <div ref={scrollEndRef} />
        </div>
      )}
      {!collapsed && chatFilters && state.status === 'done' && (
        <div style={{ display: 'flex', gap: 6, padding: '6px 10px', borderBottom: '1px solid #30363d', background: '#0d1117', alignItems: 'center' }}>
          <span style={{ fontSize: 11, opacity: 0.7, flex: 1 }}>El asistente usó otros filtros</span>
          <button type="button" onClick={() => onApplyFilters?.(chatFilters)} style={{ padding: '3px 10px', fontSize: 11, background: '#1f6feb', color: '#fff', border: 'none', borderRadius: 4 }}>
            Aplicar al mapa
          </button>
        </div>
      )}
      {!collapsed && (
        <form onSubmit={onSubmit} style={{ display: 'flex', gap: 6, padding: 10, background: '#0d1117' }}>
          <input type="text" value={input} onChange={(e) => setInput(e.target.value)}
            placeholder="¿Qué estación tiene más robos por usuario?"
            disabled={state.status === 'streaming' || chatEnabled === false}
            style={{ flex: 1, padding: '6px 8px', fontSize: 12, background: '#161b22', color: '#e6edf3', border: '1px solid #30363d', borderRadius: 4, outline: 'none' }} />
          {state.turns.length > 0 && (
            <button type="button" onClick={onNew} title="Nueva pregunta" style={{ padding: '6px 8px', fontSize: 12, background: 'transparent', color: '#94a3b8', border: '1px solid #30363d', borderRadius: 4 }}>↻</button>
          )}
          <button type="submit" disabled={!input.trim() || state.status === 'streaming'} aria-label="Enviar" style={{ display: 'none' }} />
        </form>
      )}
    </div>
  );
}

// Filters the agent passed to its last tool call, mapped to the UI filter shape.
function extractFilters(turn) {
  const calls = (turn?.toolCalls || []).filter(tc => tc.status === 'done' && tc.args);
  const tc = calls[calls.length - 1];
  if (!tc) return null;
  const a = tc.args;
  const out = {};
  if (a.date_from) out.from = a.date_from;
  if (a.date_to) out.to = a.date_to;
  if (Array.isArray(a.categories) && a.categories.length) out.categories = a.categories;
  if (a.transport_only) out.transportOnly = true;
  if (Array.isArray(a.modes) && a.modes.length) out.modes = a.modes;
  if (a.hours) out.hours = a.hours;
  if (Array.isArray(a.dows) && a.dows.length) out.dows = a.dows;
  return Object.keys(out).length ? out : null;
}

function Exchange({ turn, streaming }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ alignSelf: 'flex-end', maxWidth: '85%', padding: '6px 10px', borderRadius: 8, background: '#1f6feb', color: '#fff', whiteSpace: 'pre-wrap', fontSize: 12 }}>{turn.user}</div>
      {(turn.assistantText || streaming) && (
        <div style={{ alignSelf: 'flex-start', maxWidth: '92%', padding: '6px 10px', borderRadius: 8, background: '#161b22', color: '#e6edf3', border: '1px solid #30363d', whiteSpace: 'pre-wrap', fontSize: 12 }}>
          {turn.assistantText || <span style={{ opacity: 0.6 }}>…</span>}
          {streaming && turn.assistantText && <span style={{ opacity: 0.4 }}> ▍</span>}
        </div>
      )}
    </div>
  );
}

const TOOL_LABEL = {
  data_coverage: 'Consultando cobertura…', list_categories: 'Listando categorías…',
  search_station: 'Buscando estación…', station_crime_stats: 'Calculando estadísticas de la estación…',
  rank_stations: 'Ordenando estaciones…', crime_trend: 'Calculando tendencia…',
  category_breakdown: 'Desglosando categorías…', time_profile: 'Perfil por hora/día…',
  area_summary: 'Resumiendo la zona…', hotspots: 'Buscando puntos calientes…',
  compare_periods: 'Comparando periodos…', victim_profile: 'Perfil de víctimas…', crime_summary: 'Resumiendo…',
};
function workingLabel(turn, status) {
  if (status !== 'streaming') return 'Pensando…';
  const calls = turn?.toolCalls || [];
  let recent = null;
  for (let i = calls.length - 1; i >= 0; i--) if (calls[i].status === 'pending') { recent = calls[i]; break; }
  if (!recent && calls.length > 0) recent = calls[calls.length - 1];
  if (!recent) return 'Pensando…';
  return TOOL_LABEL[recent.tool] || `Llamando ${recent.tool}…`;
}
function Spinner() {
  return <span style={{ display: 'inline-block', width: 10, height: 10, border: '2px solid #475569', borderTopColor: '#3b82f6', borderRadius: 5, animation: 'metro-spin 700ms linear infinite' }} />;
}
