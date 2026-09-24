import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useChatStream, clearTraceCache } from '../hooks/useChatStream.js';
import TracePanel from './TracePanel.jsx';
import VerticalSplitter from './Splitter.jsx';

const TRACE_WIDTH_KEY = 'crime_chat_trace_width';
const DEFAULT_TRACE_WIDTH = 420;

export default function ChatInterface() {
  const { state, send, reset, load } = useChatStream();
  const [input, setInput] = useState('');
  const [conversations, setConversations] = useState([]);
  const [historyTick, setHistoryTick] = useState(0);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [traceOpen, setTraceOpen] = useState(false);
  const [traceTurnIdx, setTraceTurnIdx] = useState(null);  // null = follow latest
  const [traceWidth, setTraceWidth] = useState(() => {
    try {
      const v = parseInt(localStorage.getItem(TRACE_WIDTH_KEY) || '', 10);
      return Number.isFinite(v) && v >= 280 && v <= 1200 ? v : DEFAULT_TRACE_WIDTH;
    } catch (_) { return DEFAULT_TRACE_WIDTH; }
  });
  const onTraceResize = (w) => {
    setTraceWidth(w);
    try { localStorage.setItem(TRACE_WIDTH_KEY, String(w)); } catch (_) {}
  };
  const messagesEndRef = useRef(null);
  const pendingDeleteTimerRef = useRef(null);

  // Reload the sidebar conversation list whenever a turn finishes streaming
  // (so a brand-new conversation immediately appears in the rail) or on mount.
  useEffect(() => {
    let cancelled = false;
    fetch('/api/chat/conversations').then(r => r.json()).then((data) => {
      if (!cancelled) setConversations(data || []);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [historyTick, state.conversationId]);

  useEffect(() => {
    if (state.status === 'done' || state.status === 'error') {
      setHistoryTick(t => t + 1);
    }
  }, [state.status]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [state.turns, state.turns[state.turns.length - 1]?.assistantText]);

  const onSubmit = (e) => {
    e.preventDefault();
    const v = input.trim();
    if (!v || state.status === 'streaming') return;
    setInput('');
    send(v);
  };

  const onPickConversation = (id) => {
    if (id === state.conversationId) return;
    load(id).catch((err) => console.warn('load conversation failed', err));
  };

  const onNewChat = () => {
    reset(null);
  };

  // Two-step inline delete: first click reveals the confirm/cancel pair,
  // second click on ✓ actually deletes. Auto-revert after 4s.
  const onDeleteRequest = (id, e) => {
    e.stopPropagation();
    if (pendingDeleteTimerRef.current) clearTimeout(pendingDeleteTimerRef.current);
    setPendingDelete(id);
    pendingDeleteTimerRef.current = setTimeout(() => setPendingDelete(null), 4000);
  };

  const onDeleteCancel = (e) => {
    e.stopPropagation();
    if (pendingDeleteTimerRef.current) clearTimeout(pendingDeleteTimerRef.current);
    setPendingDelete(null);
  };

  const onDeleteConfirm = async (id, e) => {
    e.stopPropagation();
    if (pendingDeleteTimerRef.current) clearTimeout(pendingDeleteTimerRef.current);
    setPendingDelete(null);
    await fetch(`/api/chat/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' });
    clearTraceCache(id);
    if (id === state.conversationId) reset(null);
    setHistoryTick(t => t + 1);
  };

  useEffect(() => () => {
    if (pendingDeleteTimerRef.current) clearTimeout(pendingDeleteTimerRef.current);
  }, []);

  return (
    <div style={{ display: 'flex', width: '100%', height: '100%' }}>
      <aside style={{
        width: 240, flexShrink: 0,
        borderRight: '1px solid #30363d',
        background: '#0d1117',
        display: 'flex', flexDirection: 'column',
      }}>
        <button
          onClick={onNewChat}
          style={{
            margin: 8, padding: '6px 10px', fontSize: 13,
            background: '#1f6feb', color: '#fff',
            border: 'none', borderRadius: 4, cursor: 'pointer',
          }}>
          + Nueva conversación
        </button>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {conversations.map((c) => (
            <div
              key={c.id}
              onClick={() => onPickConversation(c.id)}
              style={{
                padding: '8px 12px', cursor: 'pointer',
                borderBottom: '1px solid #21262d',
                background: c.id === state.conversationId ? '#21262d' : 'transparent',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                gap: 6,
              }}>
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <div style={{
                  fontSize: 13, fontWeight: 500,
                  whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden',
                }}>{c.title || '(sin título)'}</div>
                <div style={{ fontSize: 11, opacity: 0.6 }}>
                  {c.msg_count} mensajes
                </div>
              </div>
              {pendingDelete === c.id ? (
                <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                  <button
                    onClick={(e) => onDeleteConfirm(c.id, e)}
                    title="Confirmar borrado"
                    style={{
                      background: '#7f1d1d', border: 'none', color: '#fff',
                      fontSize: 12, cursor: 'pointer', padding: '2px 8px',
                      borderRadius: 4, fontWeight: 600,
                    }}>✓</button>
                  <button
                    onClick={onDeleteCancel}
                    title="Cancelar"
                    style={{
                      background: '#21262d', border: '1px solid #30363d',
                      color: '#cbd5e1', fontSize: 12, cursor: 'pointer',
                      padding: '2px 8px', borderRadius: 4,
                    }}>✕</button>
                </div>
              ) : (
                <button
                  onClick={(e) => onDeleteRequest(c.id, e)}
                  title="Eliminar"
                  style={{
                    background: 'transparent', border: 'none', color: '#94a3b8',
                    fontSize: 14, cursor: 'pointer', padding: 4, flexShrink: 0,
                  }}>×</button>
              )}
            </div>
          ))}
          {conversations.length === 0 && (
            <div style={{ padding: 12, fontSize: 12, opacity: 0.6 }}>
              Sin conversaciones aún.
            </div>
          )}
        </div>
      </aside>

      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, position: 'relative' }}>
        {state.turns.length > 0 && !traceOpen && (
          <button
            onClick={() => { setTraceTurnIdx(null); setTraceOpen(true); }}
            title="Ver razonamiento detallado"
            style={{
              position: 'absolute', top: 12, right: 12, zIndex: 5,
              padding: '6px 10px', fontSize: 12,
              background: '#161b22', color: '#cbd5e1',
              border: '1px solid #30363d', borderRadius: 4,
              cursor: 'pointer',
            }}>
            🧠 Ver razonamiento
          </button>
        )}
        <div style={{
          flex: 1, overflowY: 'auto', padding: 16,
          display: 'flex', flexDirection: 'column', gap: 12,
        }}>
          {state.turns.length === 0 && (
            <Welcome />
          )}
          {state.turns.map((turn, i) => (
            <Turn
              key={i}
              turn={turn}
              streaming={i === state.turns.length - 1 && state.status === 'streaming'}
              onShowTrace={() => { setTraceTurnIdx(i); setTraceOpen(true); }}
            />
          ))}
          {state.status === 'error' && (
            <div style={{
              padding: 10, background: '#3f1d1d', color: '#fca5a5',
              border: '1px solid #7f1d1d', borderRadius: 4, fontSize: 13,
            }}>Error: {state.error}</div>
          )}
          <div ref={messagesEndRef} />
        </div>
        <form onSubmit={onSubmit} style={{
          padding: 12, borderTop: '1px solid #30363d', display: 'flex', gap: 8,
          background: '#0d1117',
        }}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Pregunta sobre delitos en la CDMX… ej. '¿qué estación tiene más robos por usuario en 2024?'"
            disabled={state.status === 'streaming'}
            style={{
              flex: 1, padding: '8px 10px', fontSize: 13,
              background: '#161b22', color: '#e6edf3',
              border: '1px solid #30363d', borderRadius: 4, outline: 'none',
            }}
          />
          <button
            type="submit"
            disabled={!input.trim() || state.status === 'streaming'}
            style={{
              padding: '8px 16px', fontSize: 13,
              background: state.status === 'streaming' ? '#30363d' : '#238636',
              color: '#fff', border: 'none', borderRadius: 4,
              cursor: state.status === 'streaming' ? 'wait' : 'pointer',
            }}>
            {state.status === 'streaming' ? 'Pensando…' : 'Enviar'}
          </button>
        </form>
      </main>
      {traceOpen && state.turns.length > 0 && (
        <>
          <VerticalSplitter onResize={onTraceResize} min={280} max={Math.min(1200, Math.floor(window.innerWidth * 0.8))} />
          <TracePanel
            turn={state.turns[traceTurnIdx ?? state.turns.length - 1]}
            streaming={
              (traceTurnIdx ?? state.turns.length - 1) === state.turns.length - 1
              && state.status === 'streaming'
            }
            onClose={() => setTraceOpen(false)}
            width={traceWidth}
          />
        </>
      )}
    </div>
  );
}

function Welcome() {
  return (
    <div style={{
      maxWidth: 560, margin: '40px auto', padding: 16,
      fontSize: 13, lineHeight: 1.6, opacity: 0.85,
    }}>
      <h2 style={{ marginTop: 0 }}>Analista de delitos y transporte CDMX</h2>
      <p>
        Pregunta sobre patrones en las carpetas de investigación de la FGJ (2019 en adelante)
        alrededor del Metro, por colonia o alcaldía, por hora, categoría o periodo. Por ejemplo:
      </p>
      <ul>
        <li>¿Qué estación del Metro tiene más robos por millón de usuarios?</li>
        <li>Compara el robo a transeúnte en Cuauhtémoc en 2019 vs 2023.</li>
        <li>¿A qué hora y qué día hay más robos cerca de Hidalgo?</li>
        <li>¿Dónde están los puntos calientes de robo de vehículo en Iztapalapa?</li>
        <li>¿Cómo ha cambiado la tendencia de extorsión mes a mes?</li>
      </ul>
      <p style={{ fontSize: 12, opacity: 0.7 }}>
        Los datos son denuncias, no incidencia real; el asistente indica la ventana de fechas y las salvedades en cada respuesta.
      </p>
    </div>
  );
}

function Turn({ turn, streaming, onShowTrace }) {
  // Tool chips and the inline thinking block live in the right-side trace
  // panel — the main chat shows only the user/assistant exchange, plus a
  // small status pill while the agent is working so the user sees activity.
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <UserBubble text={turn.user} />
      {streaming && !turn.assistantText && (
        <WorkingIndicator
          toolCalls={turn.toolCalls}
          iterCount={(turn.iters || []).length}
          onShowTrace={onShowTrace}
        />
      )}
      <AssistantBubble
        text={turn.assistantText}
        streaming={streaming}
        toolCalls={turn.toolCalls}
        onShowTrace={onShowTrace}
        iterCount={(turn.iters || []).length}
      />
    </div>
  );
}

function WorkingIndicator({ toolCalls, iterCount, onShowTrace }) {
  const last = toolCalls && toolCalls.length > 0 ? toolCalls[toolCalls.length - 1] : null;
  const label = last
    ? `Llamando ${last.tool}…`
    : 'Pensando…';
  return (
    <div
      onClick={onShowTrace}
      title="Ver razonamiento detallado"
      style={{
        alignSelf: 'flex-start',
        display: 'inline-flex', alignItems: 'center', gap: 8,
        padding: '6px 10px',
        background: '#0d1117', border: '1px dashed #30363d',
        borderRadius: 16,
        fontSize: 12, color: '#94a3b8',
        cursor: onShowTrace ? 'pointer' : 'default',
      }}>
      <Spinner />
      <span>{label}</span>
      {iterCount > 0 && (
        <span style={{ fontSize: 11, opacity: 0.7 }}>
          · iter {iterCount}
        </span>
      )}
    </div>
  );
}

function Spinner() {
  return (
    <span style={{
      display: 'inline-block', width: 10, height: 10,
      border: '2px solid #475569', borderTopColor: '#3b82f6',
      borderRadius: 5,
      animation: 'metro-spin 700ms linear infinite',
    }} />
  );
}

function ThinkingBlock({ text, streaming }) {
  const [open, setOpen] = useState(true);
  return (
    <details
      open={open}
      onToggle={(e) => setOpen(e.target.open)}
      style={{
        alignSelf: 'flex-start', maxWidth: '85%',
        padding: '6px 10px', borderRadius: 6,
        background: '#0f1419', border: '1px dashed #30363d',
        fontSize: 12, color: '#9ca3af',
      }}>
      <summary style={{ cursor: 'pointer', fontWeight: 600, opacity: 0.85 }}>
        🧠 Razonamiento del modelo {streaming && <span style={{ opacity: 0.6 }}>· pensando…</span>}
      </summary>
      <div style={{
        marginTop: 6, fontStyle: 'italic', whiteSpace: 'pre-wrap',
        lineHeight: 1.5, fontSize: 12,
      }}>
        {text}
        {streaming && <span style={{ opacity: 0.4 }}> ▍</span>}
      </div>
    </details>
  );
}

function UserBubble({ text }) {
  return (
    <div style={{
      alignSelf: 'flex-end', maxWidth: '75%',
      padding: '8px 12px', borderRadius: 8,
      background: '#1f6feb', color: '#fff',
      whiteSpace: 'pre-wrap', fontSize: 13,
    }}>{text}</div>
  );
}

function AssistantBubble({ text, streaming, toolCalls, onShowTrace, iterCount }) {
  const showOnMapHref = buildMapHref(toolCalls);
  if (!text && !streaming) return null;
  return (
    <div style={{
      alignSelf: 'flex-start', maxWidth: '75%',
      padding: '10px 14px', borderRadius: 8,
      background: '#161b22', color: '#e6edf3',
      border: '1px solid #30363d',
      whiteSpace: 'pre-wrap', fontSize: 13,
    }}>
      {text || (streaming ? <span style={{ opacity: 0.6 }}>…</span> : null)}
      {streaming && text && <span style={{ opacity: 0.4 }}> ▍</span>}
      <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {showOnMapHref && (
          <Link to={showOnMapHref} style={{
            display: 'inline-block', padding: '4px 10px',
            fontSize: 12, color: '#fff', background: '#1f6feb',
            borderRadius: 4, textDecoration: 'none',
          }}>Ver en el mapa</Link>
        )}
        {onShowTrace && iterCount > 0 && (
          <button onClick={onShowTrace} style={{
            padding: '4px 10px', fontSize: 12,
            background: 'transparent', color: '#cbd5e1',
            border: '1px solid #30363d', borderRadius: 4, cursor: 'pointer',
          }}>
            🧠 Ver razonamiento ({iterCount} {iterCount === 1 ? 'iter' : 'iters'})
          </button>
        )}
      </div>
    </div>
  );
}

function ToolCallChip({ call }) {
  const [open, setOpen] = useState(false);
  const isDone = call.status === 'done';
  const summary = formatSummary(call);
  return (
    <div style={{
      alignSelf: 'flex-start', maxWidth: '75%',
      padding: '6px 10px', borderRadius: 6,
      background: '#0d1117', border: '1px solid #21262d',
      fontSize: 12, fontFamily: 'monospace', opacity: 0.9,
    }}>
      <div
        onClick={() => setOpen(o => !o)}
        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{
          width: 8, height: 8, borderRadius: 4,
          background: isDone ? '#22c55e' : '#facc15',
          display: 'inline-block', flexShrink: 0,
        }} />
        <span style={{ fontWeight: 600 }}>{call.tool}</span>
        <span style={{ opacity: 0.7 }}>{summary}</span>
      </div>
      {open && (
        <pre style={{
          marginTop: 6, padding: 6,
          background: '#010409', borderRadius: 4,
          fontSize: 11, overflowX: 'auto', maxHeight: 200,
        }}>{JSON.stringify({ args: call.args, result: call.result }, null, 2)}</pre>
      )}
    </div>
  );
}

// Deep link into the map for the last spatial tool call of a turn.
function buildMapHref(toolCalls) {
  const done = (toolCalls || []).filter(tc => tc.status === 'done' && tc.result && !tc.result.error);
  const params = new URLSearchParams();
  const last = (name) => [...done].reverse().find(tc => tc.tool === name);
  const st = last('station_crime_stats');
  const rank = last('rank_stations');
  const area = last('area_summary');
  const anyArgs = done[done.length - 1]?.args || {};
  if (anyArgs.date_from) params.set('from', anyArgs.date_from);
  if (anyArgs.date_to) params.set('to', anyArgs.date_to);
  if (st?.result?.station?.station_key) params.set('station', st.result.station.station_key);
  else if (rank?.result?.stations?.length) params.set('stations', rank.result.stations.map(s => s.station_key).join(','));
  else if (area?.result?.area) {
    const a = area.result.area;
    if (a.kind === 'colonia') { params.set('colonia_id', a.id); params.set('name', a.name); }
    else params.set('alcaldia', a.name);
  } else return null;
  return `/?${params.toString()}`;
}

function formatSummary(call) {
  const a = call.args || {};
  if (call.tool === 'search_station') return `(${JSON.stringify(a.query || '')})`;
  if (call.tool === 'station_crime_stats') return `(${a.station_key || '?'}${a.radius_m ? `, ${a.radius_m} m` : ''})`;
  if (call.tool === 'rank_stations') return `(${a.metric || 'rate'})`;
  if (call.tool === 'area_summary') return `(${a.alcaldia || a.colonia || '?'})`;
  if (call.tool === 'compare_periods') return `(${a.a_from}→${a.a_to} vs ${a.b_from}→${a.b_to})`;
  if (call.tool === 'data_coverage' || call.tool === 'list_categories') return '()';
  return '';
}
