import React, { useEffect, useState } from 'react';

// Floating panel with a header bar that toggles a collapsed state.
// `position` is forwarded to the outer div so the caller controls placement
// (top/left/right). When collapsed, only the header bar is visible.
//
// `collapseSignal` is an optional incrementing value (e.g. a tick counter):
// every time it changes, the panel auto-collapses. Useful for "collapse all
// when the map animation starts" — the user can still reopen manually.
export default function CollapsiblePanel({
  title,
  position = {},
  width = 240,
  defaultCollapsed = false,
  zIndex = 10,
  collapseSignal,
  children,
}) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  useEffect(() => {
    if (collapseSignal !== undefined && collapseSignal !== null) {
      setCollapsed(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collapseSignal]);
  return (
    <div
      className="panel"
      style={{
        position: 'absolute',
        ...position,
        width,
        zIndex,
        maxHeight: collapsed ? undefined : 'calc(100% - 24px)',
        display: 'flex',
        flexDirection: 'column',
        padding: 0,
      }}>
      <button
        type="button"
        onClick={() => setCollapsed(c => !c)}
        title={collapsed ? 'Expandir' : 'Colapsar'}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          width: '100%',
          padding: '8px 12px',
          background: 'transparent',
          color: 'inherit',
          border: 'none',
          borderBottom: collapsed ? 'none' : '1px solid #30363d',
          cursor: 'pointer',
          fontSize: 13,
          fontWeight: 600,
          textAlign: 'left',
        }}>
        <span>{title}</span>
        <span style={{ opacity: 0.7, fontSize: 11 }}>{collapsed ? '▸' : '▾'}</span>
      </button>
      {!collapsed && (
        <div style={{ padding: 12, overflowY: 'auto', minHeight: 0 }}>
          {children}
        </div>
      )}
    </div>
  );
}
