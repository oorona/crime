import React, { useMemo, useState } from 'react';

// TracePanel — slides in from the right of the chat main pane and shows the
// full ReAct trace for one turn: every iteration's thinking text, every tool
// call with its args + result, and the model's prose output. The goal is for
// a reader to be able to reconstruct exactly how the agent solved the
// problem without having to read the raw SSE stream.
export default function TracePanel({ turn, onClose, streaming, width = 420 }) {
  if (!turn) {
    return (
      <Shell onClose={onClose} width={width}>
        <div style={emptyStyle}>Aún no hay razonamiento que mostrar.</div>
      </Shell>
    );
  }
  const iters = turn.iters && turn.iters.length > 0
    ? turn.iters
    : [/* fallback for legacy turns with only flat thinking */];
  return (
    <Shell onClose={onClose} width={width}>
      <UserBlock text={turn.user} />
      {iters.length === 0 && turn.thinking && (
        <FallbackBlock text={turn.thinking} />
      )}
      {iters.map((it, i) => (
        <IterationBlock
          key={i}
          iter={it}
          isFinal={i === iters.length - 1 && (turn.assistantText || it.text)}
          finalText={i === iters.length - 1 ? turn.assistantText : ''}
          streaming={streaming && i === iters.length - 1}
        />
      ))}
      {streaming && (
        <div style={{ padding: 12, fontSize: 12, color: '#9ca3af', fontStyle: 'italic' }}>
          esperando próxima iteración…
        </div>
      )}
    </Shell>
  );
}

function Shell({ children, onClose, width }) {
  return (
    <aside style={{
      width, flexShrink: 0,
      borderLeft: '1px solid #30363d',
      background: '#0a0d12',
      display: 'flex', flexDirection: 'column',
      minHeight: 0,
    }}>
      <header style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 12px',
        borderBottom: '1px solid #30363d',
        background: '#0d1117',
      }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>🧠 Razonamiento detallado</span>
        <button
          onClick={onClose}
          title="Cerrar"
          style={{
            background: 'transparent', border: 'none', color: '#94a3b8',
            fontSize: 18, cursor: 'pointer', lineHeight: 1, padding: 4,
          }}>×</button>
      </header>
      <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
        {children}
      </div>
    </aside>
  );
}

function UserBlock({ text }) {
  if (!text) return null;
  return (
    <div style={{
      padding: '8px 10px', marginBottom: 8,
      background: '#1f2937', color: '#cbd5e1',
      borderRadius: 4, fontSize: 12, whiteSpace: 'pre-wrap',
    }}>
      <div style={{ fontWeight: 600, fontSize: 11, opacity: 0.7, marginBottom: 4 }}>
        ▶ Pregunta del usuario
      </div>
      {text}
    </div>
  );
}

function FallbackBlock({ text }) {
  return (
    <Section title="Razonamiento (sin desglose por iteración)">
      <div style={thinkStyle}>{text}</div>
    </Section>
  );
}

function IterationBlock({ iter, finalText, streaming }) {
  const [open, setOpen] = useState(true);
  const callsCount = (iter.toolCalls || []).length;
  const hasFinal = finalText && finalText.length > 0;
  return (
    <details
      open={open}
      onToggle={(e) => setOpen(e.target.open)}
      style={{
        marginBottom: 10,
        background: '#0d1117',
        border: '1px solid #21262d',
        borderRadius: 6,
      }}>
      <summary style={{
        cursor: 'pointer',
        padding: '8px 12px',
        fontSize: 12, fontWeight: 600,
        color: '#e6edf3',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 6,
        userSelect: 'none',
      }}>
        <span>
          <span style={{ display: 'inline-block', minWidth: 18, textAlign: 'center' }}>{iter.iter}</span>
          <span style={{ marginLeft: 6 }}>Iteración {iter.iter}</span>
        </span>
        <span style={{ fontSize: 10, opacity: 0.6, fontWeight: 400 }}>
          {callsCount > 0 && `${callsCount} herramienta${callsCount > 1 ? 's' : ''}`}
          {callsCount > 0 && hasFinal && ' · '}
          {hasFinal && 'respuesta final'}
        </span>
      </summary>
      <div style={{ padding: '0 12px 10px 12px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {/* Phase 1: REASON — model's chain-of-thought before deciding on action */}
        <PhaseSection
          icon="🤔"
          phase="Razonar"
          subtitle="Reason"
          color="#a78bfa">
          {iter.thinking ? (
            <div style={thinkStyle}>{iter.thinking}{streaming && !iter.toolCalls.length && !finalText && <Caret />}</div>
          ) : streaming && !iter.toolCalls.length ? (
            <div style={{ ...thinkStyle, opacity: 0.6 }}>esperando…<Caret /></div>
          ) : (
            <div style={emptyPhaseStyle}>(el modelo no expuso razonamiento en este paso)</div>
          )}
        </PhaseSection>

        {/* Phase 2: ACT — tool calls the model decided to make. Shows args only. */}
        <PhaseSection
          icon="🛠"
          phase="Actuar"
          subtitle="Act"
          color="#fbbf24">
          {(iter.toolCalls || []).length === 0 ? (
            <div style={emptyPhaseStyle}>
              {hasFinal
                ? '(no hay acciones — el modelo respondió directamente)'
                : '(sin llamadas a herramientas en este paso)'}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {iter.toolCalls.map((tc, i) => (
                <ActionLine key={tc.callId || i} call={tc} />
              ))}
            </div>
          )}
        </PhaseSection>

        {/* Phase 3: OBSERVE — results returned by the tools, paired by call_id */}
        <PhaseSection
          icon="👁"
          phase="Observar"
          subtitle="Observe"
          color="#34d399">
          {(iter.toolCalls || []).length === 0 ? (
            <div style={emptyPhaseStyle}>(sin observaciones)</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {iter.toolCalls.map((tc, i) => (
                <ObservationLine key={tc.callId || i} call={tc} />
              ))}
            </div>
          )}
        </PhaseSection>

        {/* Final answer — only on the last iter, separately. */}
        {hasFinal && (
          <PhaseSection
            icon="💬"
            phase="Responder"
            subtitle="Answer"
            color="#60a5fa">
            <div style={{ ...thinkStyle, fontStyle: 'normal', color: '#e6edf3' }}>
              {finalText}{streaming && <Caret />}
            </div>
          </PhaseSection>
        )}
      </div>
    </details>
  );
}

function PhaseSection({ icon, phase, subtitle, color, children }) {
  return (
    <div style={{
      border: '1px solid #21262d',
      borderLeft: `3px solid ${color}`,
      borderRadius: 4,
      background: '#0d1117',
      padding: '8px 10px',
    }}>
      <div style={{
        fontSize: 11, fontWeight: 700,
        color, letterSpacing: 0.4,
        marginBottom: 6,
        display: 'flex', alignItems: 'baseline', gap: 6,
      }}>
        <span style={{ fontSize: 13 }}>{icon}</span>
        <span style={{ textTransform: 'uppercase' }}>{phase}</span>
        <span style={{ fontSize: 10, color: '#6b7280', fontWeight: 500 }}>· {subtitle}</span>
      </div>
      {children}
    </div>
  );
}

function ActionLine({ call }) {
  const isDone = call.status === 'done';
  const dur = call.durationMs ? ` · ${call.durationMs}ms` : '';
  return (
    <div style={{
      border: '1px solid #21262d', borderRadius: 4,
      background: '#010409',
      fontFamily: 'monospace',
    }}>
      <div style={{
        padding: '5px 8px', fontSize: 12,
        display: 'flex', alignItems: 'center', gap: 6,
        borderBottom: '1px solid #21262d',
      }}>
        <span style={{
          display: 'inline-block', width: 7, height: 7, borderRadius: 4,
          background: isDone ? '#22c55e' : '#facc15', flexShrink: 0,
        }} />
        <span style={{ fontWeight: 600, color: '#e6edf3' }}>{call.tool}</span>
        <span style={{ marginLeft: 'auto', fontSize: 10, color: '#6b7280' }}>
          {isDone ? `done${dur}` : 'pending…'}
        </span>
      </div>
      <KeyValue label="args" value={call.args} />
    </div>
  );
}

function ObservationLine({ call }) {
  const isDone = call.status === 'done';
  return (
    <div style={{
      border: '1px solid #21262d', borderRadius: 4,
      background: '#010409',
      fontFamily: 'monospace',
    }}>
      <div style={{
        padding: '5px 8px', fontSize: 12,
        display: 'flex', alignItems: 'center', gap: 6,
        borderBottom: '1px solid #21262d',
      }}>
        <span style={{ color: '#6b7280', fontSize: 10 }}>resultado de</span>
        <span style={{ fontWeight: 600, color: '#e6edf3' }}>{call.tool}</span>
      </div>
      {isDone ? (
        <KeyValue label="result" value={call.result} maxRows={20} />
      ) : (
        <div style={{
          padding: '6px 10px', fontSize: 11,
          color: '#facc15', fontStyle: 'italic',
        }}>esperando respuesta de la herramienta…</div>
      )}
    </div>
  );
}

function KeyValue({ label, value, maxRows = 8 }) {
  const json = useMemo(() => safeStringify(value), [value]);
  const [open, setOpen] = useState(false);
  const lines = json.split('\n');
  const truncated = lines.length > maxRows && !open;
  const shown = truncated ? lines.slice(0, maxRows).join('\n') : json;
  return (
    <div style={{ borderTop: '1px solid #21262d', padding: '6px 10px' }}>
      <div style={{ fontSize: 10, color: '#6b7280', marginBottom: 2 }}>{label}</div>
      <pre style={{
        margin: 0, fontSize: 11, color: '#cbd5e1',
        whiteSpace: 'pre-wrap', wordBreak: 'break-word',
      }}>{shown}{truncated && '\n…'}</pre>
      {lines.length > maxRows && (
        <button
          onClick={() => setOpen(o => !o)}
          style={{
            background: 'transparent', border: 'none', color: '#60a5fa',
            cursor: 'pointer', fontSize: 11, padding: 0, marginTop: 4,
          }}>
          {open ? 'mostrar menos' : `mostrar ${lines.length - maxRows} líneas más`}
        </button>
      )}
    </div>
  );
}

function Section({ title, tight, children }) {
  return (
    <div style={{ marginTop: tight ? 0 : 6 }}>
      <div style={{
        fontSize: 10, fontWeight: 600, color: '#94a3b8',
        textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4,
      }}>{title}</div>
      {children}
    </div>
  );
}

function Caret() {
  return <span style={{ opacity: 0.4 }}> ▍</span>;
}

const thinkStyle = {
  whiteSpace: 'pre-wrap',
  fontSize: 12,
  lineHeight: 1.5,
  color: '#9ca3af',
  fontStyle: 'italic',
};

const emptyPhaseStyle = {
  fontSize: 11,
  color: '#6b7280',
  fontStyle: 'italic',
};

const emptyStyle = {
  padding: 16,
  fontSize: 12,
  color: '#6b7280',
  fontStyle: 'italic',
};

function safeStringify(v) {
  try {
    return JSON.stringify(v, null, 2);
  } catch (_) {
    return String(v);
  }
}
