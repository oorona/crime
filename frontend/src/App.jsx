import React, { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import MapApp from './MapApp.jsx';
import ChatInterface from './components/ChatInterface.jsx';
import { api } from './api.js';

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
      <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%' }}>
        <TopBar />
        <IngestBanner health={health} />
        <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
          <Routes>
            <Route path="/" element={<MapApp health={health} />} />
            <Route path="/chat" element={<ChatInterface health={health} />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  );
}

function IngestBanner({ health }) {
  if (!health) return null;
  const st = health.ingest?.status;
  if (health.views_populated && st !== 'running' && st !== 'error') return null;
  const running = Object.entries(health.steps || {}).find(([, s]) => s.status === 'running');
  let msg;
  if (st === 'error') msg = `Error en la carga de datos: ${health.ingest.error}`;
  else if (running) {
    const [name, s] = running;
    const p = s.progress ? ` (${s.progress.kept?.toLocaleString()} filas)` : '';
    msg = health.views_populated
      ? `Actualizando datos en segundo plano: ${name}${p}`
      : `Cargando datos (primer arranque): ${name}${p}… el mapa de delitos aparecerá al terminar.`;
  } else msg = health.views_populated ? null : 'Los datos de delitos aún no están cargados. Ejecuta scripts/fetch_data.sh y reinicia el backend.';
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
      <span style={{ fontSize: 13, fontWeight: 700, marginRight: 16 }}>CDMX Crimen · Transporte</span>
      <NavLink to="/" end style={({ isActive }) => link(isActive)}>Mapa</NavLink>
      <NavLink to="/chat" style={({ isActive }) => link(isActive)}>Chat</NavLink>
      <span style={{ marginLeft: 'auto', fontSize: 11, opacity: 0.55 }}>
        Carpetas de investigación FGJ CDMX · afluencia STC Metro · datos.cdmx.gob.mx (CC-BY-4.0)
      </span>
    </header>
  );
}
