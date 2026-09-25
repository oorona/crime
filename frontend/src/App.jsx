import React, { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Link, useLocation } from 'react-router-dom';
import MapApp from './MapApp.jsx';
import ChatInterface from './components/ChatInterface.jsx';
import { api } from './api.js';
import { LangContext, langFromPath, basePath, useLang, useT } from './i18n.js';

export default function App() {
  const [health, setHealth] = useState(null);

  // Poll /health until the statistics views are populated (first boot
  // ingests ~1.3M cases in the background and takes several minutes).
  useEffect(() => {
    let alive = true, timer = null;
    const tick = async () => {
      try {
        const h = await api.health();
        if (!alive) return;
        setHealth(h);
        if (!h.views_populated || h.ingest?.status === 'running') timer = setTimeout(tick, 8000);
      } catch {
        if (alive) timer = setTimeout(tick, 8000);
      }
    };
    tick();
    return () => { alive = false; clearTimeout(timer); };
  }, []);

  return (
    <BrowserRouter>
      <Shell health={health} />
    </BrowserRouter>
  );
}

// Spanish at /, English at /en. The key remounts the pages on a language
// switch so chat state and map labels never mix languages.
function Shell({ health }) {
  const lang = langFromPath(useLocation().pathname);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.title = lang === 'en' ? 'CDMX Crime · Transit' : 'CDMX Crimen · Transporte';
  }, [lang]);
  return (
    <LangContext.Provider value={lang}>
      <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%' }}>
        <TopBar />
        <IngestBanner health={health} />
        <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
          <Routes>
            <Route path="/" element={<MapApp key="es" health={health} />} />
            <Route path="/chat" element={<ChatInterface key="es" health={health} />} />
            <Route path="/en" element={<MapApp key="en" health={health} />} />
            <Route path="/en/chat" element={<ChatInterface key="en" health={health} />} />
          </Routes>
        </div>
      </div>
    </LangContext.Provider>
  );
}

function IngestBanner({ health }) {
  const t = useT();
  if (!health) return null;
  const st = health.ingest?.status;
  if (health.views_populated && st !== 'running' && st !== 'error') return null;
  const running = Object.entries(health.steps || {}).find(([, s]) => s.status === 'running');
  let msg;
  if (st === 'error') msg = t('ingest.error', { error: health.ingest.error });
  else if (running) {
    const [name, s] = running;
    const p = s.progress ? t('ingest.rows', { n: s.progress.kept?.toLocaleString() }) : '';
    msg = t(health.views_populated ? 'ingest.bg' : 'ingest.first', { name, p });
  } else msg = health.views_populated ? null : t('ingest.empty');
  if (!msg) return null;
  return (
    <div style={{
      padding: '4px 12px', fontSize: 12, flexShrink: 0,
      background: st === 'error' ? '#3f1d1d' : '#1c2a3f', color: st === 'error' ? '#fca5a5' : '#93c5fd',
      borderBottom: '1px solid #30363d',
    }}>{msg}</div>
  );
}

function TopBar() {
  const lang = useLang();
  const t = useT();
  const base = basePath(lang);
  // Same page in the other language: strip or add the /en prefix.
  const { pathname, search } = useLocation();
  const rest = lang === 'en' ? pathname.replace(/^\/en/, '') || '/' : pathname;
  const other = lang === 'en' ? rest + search : `/en${rest === '/' ? '' : rest}${search}`;
  const link = (active) => ({
    padding: '6px 14px', fontSize: 13,
    color: active ? '#fff' : '#cbd5e1',
    borderBottom: active ? '2px solid #3b82f6' : '2px solid transparent',
    textDecoration: 'none', fontWeight: active ? 600 : 500,
  });
  return (
    <header style={{
      display: 'flex', alignItems: 'center', gap: 4, padding: '0 12px',
      background: '#0d1117', borderBottom: '1px solid #30363d', height: 40, flexShrink: 0,
    }}>
      <span style={{ fontSize: 13, fontWeight: 700, marginRight: 16 }}>{t('app.title')}</span>
      <NavLink to={base || '/'} end style={({ isActive }) => link(isActive)}>{t('nav.map')}</NavLink>
      <NavLink to={`${base}/chat`} style={({ isActive }) => link(isActive)}>{t('nav.chat')}</NavLink>
      <span style={{ marginLeft: 'auto', fontSize: 11, opacity: 0.55 }}>{t('nav.source')}</span>
      <span style={{ marginLeft: 12, fontSize: 12, display: 'flex', gap: 4 }}>
        {['es', 'en'].map(l => l === lang
          ? <strong key={l} style={{ color: '#fff' }}>{l.toUpperCase()}</strong>
          : <Link key={l} to={other} style={{ color: '#94a3b8', textDecoration: 'none' }}>{l.toUpperCase()}</Link>)}
      </span>
    </header>
  );
}
