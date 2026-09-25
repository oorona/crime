// useChatStream — POST to /api/chat/stream, parse SSE, accumulate state.
//
// State shape:
//   {
//     conversationId: string | null,
//     status: 'idle' | 'streaming' | 'done' | 'error',
//     error: string | null,
//     turns: Turn[],   // ordered list of user/assistant exchanges
//   }
//
// Turn shape:
//   { user: string, assistantText: string, toolCalls: ToolCall[], iterations: number }
//
// ToolCall shape:
//   { callId: string, tool: string, args: object, result: any | null,
//     status: 'pending' | 'done' | 'error' }
//
// Designed to keep the latest in-flight assistant text in turns[last].assistantText
// so the renderer just reads the final entry.
import { useCallback, useEffect, useReducer, useRef } from 'react';

// Per-conversation cache of trace iterations (thinking, tool args/results,
// per-iter prose). Survives page reload and tab navigation but is intentionally
// browser-local — the server doesn't store thinking text. Keyed by
// conversation_id; the value mirrors `turn.iters` arrays for each turn.
const TRACE_STORAGE_PREFIX = 'crime_chat_trace:';
function traceKey(id) { return `${TRACE_STORAGE_PREFIX}${id}`; }
function readTraceCache(id) {
  if (!id) return null;
  try {
    const raw = localStorage.getItem(traceKey(id));
    return raw ? JSON.parse(raw) : null;
  } catch (_) { return null; }
}
function writeTraceCache(id, turns) {
  if (!id) return;
  try {
    const compact = turns.map(t => ({
      iters: (t.iters || []).map(it => ({
        iter: it.iter,
        thinking: it.thinking,
        text: it.text,
        toolCalls: it.toolCalls,
        finished: it.finished,
      })),
      thinking: t.thinking || '',
    }));
    localStorage.setItem(traceKey(id), JSON.stringify(compact));
  } catch (_) { /* quota exceeded — drop silently */ }
}
export function clearTraceCache(id) {
  if (!id) return;
  try { localStorage.removeItem(traceKey(id)); } catch (_) {}
}

const initialState = {
  conversationId: null,
  status: 'idle',
  error: null,
  turns: [],
};

// Update the most recent turn (and the most recent iteration within that
// turn) immutably. The mutator receives a clone of the last turn whose
// `iters` array AND the last entry's toolCalls array have already been
// shallow-copied so it's safe to mutate them in place.
function withLastTurn(state, mutator) {
  const turns = state.turns.slice();
  const idx = turns.length - 1;
  if (idx < 0) return state;
  const last = { ...turns[idx] };
  last.iters = (last.iters || []).map((it, i, arr) => (
    i === arr.length - 1 ? { ...it, toolCalls: [...(it.toolCalls || [])] } : it
  ));
  last.toolCalls = [...(last.toolCalls || [])];
  mutator(last);
  turns[idx] = last;
  return { ...state, turns };
}

function ensureIter(turn, iterNum) {
  let cur = turn.iters[turn.iters.length - 1];
  if (!cur || cur.iter !== iterNum) {
    cur = { iter: iterNum, thinking: '', toolCalls: [], text: '', finished: false };
    turn.iters.push(cur);
  }
  return cur;
}

function applyEvent(state, evt) {
  if (evt.type === 'loop.started') {
    return { ...state, conversationId: evt.conversation_id };
  }
  if (evt.type === 'loop.finished') {
    return { ...state, status: 'done' };
  }
  if (evt.type === 'loop.errored') {
    return { ...state, status: 'error', error: evt.message || 'unknown error' };
  }

  return withLastTurn(state, (t) => {
    if (evt.type === 'iter.started') {
      ensureIter(t, evt.iter);
      t.iterations = Math.max(t.iterations || 0, evt.iter);
    } else if (evt.type === 'iter.finished') {
      const cur = t.iters[t.iters.length - 1];
      if (cur && cur.iter === evt.iter) cur.finished = true;
    } else if (evt.type === 'model.thinking') {
      const cur = ensureIter(t, evt.iter);
      cur.thinking = (cur.thinking || '') + (evt.text || '');
      // Maintain a flat `thinking` string for callers that don't want to
      // walk the per-iter array — the existing inline collapsible block
      // still uses this. Insert a separator at iteration boundaries.
      const sep = (t.thinking && t.iters.length > 1 && cur.thinking === (evt.text || ''))
        ? `\n\n— iteración ${evt.iter} —\n`
        : '';
      t.thinking = (t.thinking || '') + sep + (evt.text || '');
    } else if (evt.type === 'model.token') {
      const cur = ensureIter(t, evt.iter);
      cur.text = (cur.text || '') + (evt.text || '');
      t.assistantText = (t.assistantText || '') + (evt.text || '');
    } else if (evt.type === 'model.action') {
      const cur = ensureIter(t, evt.iter);
      const tc = {
        callId: evt.call_id,
        tool: evt.tool,
        args: evt.args || {},
        result: null,
        status: 'pending',
        iter: evt.iter,
      };
      cur.toolCalls.push(tc);
      t.toolCalls.push(tc);
    } else if (evt.type === 'tool.completed') {
      const update = (tc) => (
        tc.callId === evt.call_id
          ? { ...tc, result: evt.result, status: 'done', durationMs: evt.duration_ms }
          : tc
      );
      t.toolCalls = t.toolCalls.map(update);
      // Replace the matching tool call inside whichever iter holds it.
      t.iters = t.iters.map((it) => {
        if (!it.toolCalls.some(tc => tc.callId === evt.call_id)) return it;
        return { ...it, toolCalls: it.toolCalls.map(update) };
      });
    }
  });
}

function reduce(state, action) {
  switch (action.type) {
    case 'reset':
      return { ...initialState, conversationId: action.conversationId ?? null };
    case 'send':
      return {
        ...state,
        status: 'streaming',
        error: null,
        turns: [...state.turns, {
          user: action.message,
          assistantText: '',
          thinking: '',
          toolCalls: [],
          iterations: 0,
          // Per-iteration trace for the detailed reasoning panel. Each entry
          // captures everything that happened in one ReAct iteration: the
          // model's thinking text, the tool calls it decided on, and any
          // prose it produced (final answer).
          iters: [],
        }],
      };
    case 'event':
      return applyEvent(state, action.event);
    case 'load':
      return {
        conversationId: action.conversationId,
        status: 'idle',
        error: null,
        turns: action.turns,
      };
    case 'fail':
      return { ...state, status: 'error', error: action.message };
    default:
      return state;
  }
}

export function useChatStream() {
  const [state, dispatch] = useReducer(reduce, initialState);
  const abortRef = useRef(null);

  // Mirror trace data into localStorage whenever it changes. We persist
  // continuously during execution rather than only on completion so a
  // refresh mid-stream still recovers everything received so far.
  useEffect(() => {
    if (state.conversationId && state.turns.length > 0) {
      writeTraceCache(state.conversationId, state.turns);
    }
  }, [state.conversationId, state.turns]);

  const send = useCallback(async (message, options = {}) => {
    dispatch({ type: 'send', message });
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      const body = {
        message,
        conversation_id: state.conversationId,
      };
      // The English entry point (/en) pins the reply language server side.
      if (options.lang) body.lang = options.lang;
      if (options.mapContext && typeof options.mapContext === 'object') {
        const ctx = Object.fromEntries(Object.entries(options.mapContext).filter(([, v]) => v != null && v !== ''));
        if (Object.keys(ctx).length) body.map_context = ctx;
      }
      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
        signal: ac.signal,
      });
      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      // Stream loop: SSE frames are separated by blank lines (\n\n).
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let sep;
        while ((sep = buf.indexOf('\n\n')) >= 0) {
          const frame = buf.slice(0, sep);
          buf = buf.slice(sep + 2);
          for (const line of frame.split('\n')) {
            if (line.startsWith('data:')) {
              const json = line.slice(5).trim();
              if (!json) continue;
              try {
                dispatch({ type: 'event', event: JSON.parse(json) });
              } catch (e) {
                console.warn('bad SSE frame', json, e);
              }
            }
            // Lines starting with ":" are comments (heartbeats) — ignore.
          }
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError') {
        dispatch({ type: 'fail', message: e.message });
      }
    } finally {
      abortRef.current = null;
    }
  }, [state.conversationId]);

  const reset = useCallback((conversationId) => {
    if (abortRef.current) abortRef.current.abort();
    dispatch({ type: 'reset', conversationId });
  }, []);

  // Load an existing conversation from the server and project it into turns.
  // Then merge the locally-cached trace (thinking text, per-iter prose) on
  // top so the trace panel can show the full reasoning even though the
  // server only persists user/assistant/tool messages.
  const load = useCallback(async (conversationId) => {
    if (abortRef.current) abortRef.current.abort();
    const r = await fetch(`/api/chat/conversations/${encodeURIComponent(conversationId)}/messages`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    const turns = projectTurns(data.messages || []);
    const cached = readTraceCache(conversationId);
    if (cached && Array.isArray(cached)) {
      for (let i = 0; i < turns.length && i < cached.length; i++) {
        const cTurn = cached[i];
        if (!cTurn) continue;
        if (cTurn.thinking) turns[i].thinking = cTurn.thinking;
        // For each iter we already reconstructed from db rows, overlay the
        // cached thinking + text. We trust the db for tool calls (already
        // there) but use cache when its toolCalls match by tool name and
        // contain real callIds (more reliable than 'hist-N' placeholders).
        const cIters = cTurn.iters || [];
        if (cIters.length === 0) continue;
        if (turns[i].iters.length === 0) {
          turns[i].iters = cIters;
        } else {
          for (let j = 0; j < turns[i].iters.length && j < cIters.length; j++) {
            if (cIters[j].thinking) turns[i].iters[j].thinking = cIters[j].thinking;
            if (cIters[j].text && !turns[i].iters[j].text) {
              turns[i].iters[j].text = cIters[j].text;
            }
          }
        }
      }
    }
    dispatch({ type: 'load', conversationId, turns });
  }, []);

  return { state, send, reset, load };
}

// Convert a flat message list (user / assistant / tool rows in db order) into
// the turn-shaped state the UI renders. Each user row starts a new turn; the
// assistant rows that follow contribute to the same turn's text and tool_calls.
// Tool rows attach results to the matching tool_call by tool name + position.
function projectTurns(messages) {
  const turns = [];
  let current = null;
  let pendingCalls = [];   // toolCalls in the current turn awaiting matching tool rows

  const newTurn = (userText) => ({
    user: userText,
    assistantText: '',
    thinking: '',           // not persisted; trace panel shows '(no disponible en historial)'
    toolCalls: [],
    iterations: 0,
    iters: [],
  });

  const iterFor = (turn, iterNum) => {
    let cur = turn.iters[turn.iters.length - 1];
    if (!cur || cur.iter !== iterNum) {
      cur = { iter: iterNum, thinking: '', toolCalls: [], text: '', finished: true };
      turn.iters.push(cur);
    }
    return cur;
  };

  for (const m of messages) {
    if (m.role === 'user') {
      if (current) turns.push(current);
      current = newTurn(m.content?.text || '');
      pendingCalls = [];
    } else if (m.role === 'assistant') {
      if (!current) { current = newTurn(''); pendingCalls = []; }
      const iterNum = m.content?.iter || (current.iters.length + 1);
      const cur = iterFor(current, iterNum);
      if (m.content?.text) {
        current.assistantText = (current.assistantText || '') + m.content.text;
        cur.text = (cur.text || '') + m.content.text;
      }
      const calls = m.content?.tool_calls || [];
      for (const c of calls) {
        const tc = {
          callId: `hist-${current.toolCalls.length}`,
          tool: c.tool,
          args: c.args || {},
          result: null,
          status: 'pending',
          iter: iterNum,
        };
        current.toolCalls.push(tc);
        cur.toolCalls.push(tc);
        pendingCalls.push(tc);
      }
      current.iterations = Math.max(current.iterations, iterNum);
    } else if (m.role === 'tool') {
      const idx = pendingCalls.findIndex((tc) => tc.tool === m.content?.tool && tc.status === 'pending');
      if (idx >= 0) {
        pendingCalls[idx].result = m.content?.result;
        pendingCalls[idx].status = 'done';
        pendingCalls.splice(idx, 1);
      }
    }
  }
  if (current) turns.push(current);
  return turns;
}
