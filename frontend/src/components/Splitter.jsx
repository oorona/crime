import React, { useCallback, useEffect, useRef } from 'react';

// Vertical drag handle for resizing a side panel anchored to the right edge
// of the viewport. On mousedown it captures pointer events and reports the
// new width on every move via `onResize(px)`. Width is clamped to [min, max].
export default function VerticalSplitter({ onResize, min = 280, max = 900 }) {
  const draggingRef = useRef(false);

  const onMouseMove = useCallback((e) => {
    if (!draggingRef.current) return;
    // The panel sits flush against window's right edge → its width is the
    // distance from the cursor to that edge.
    const next = Math.min(max, Math.max(min, window.innerWidth - e.clientX));
    onResize(next);
  }, [onResize, min, max]);

  const onMouseUp = useCallback(() => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, []);

  useEffect(() => {
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [onMouseMove, onMouseUp]);

  const onMouseDown = (e) => {
    e.preventDefault();
    draggingRef.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  return (
    <div
      onMouseDown={onMouseDown}
      title="Arrastra para redimensionar"
      style={{
        flexShrink: 0,
        width: 6,
        cursor: 'col-resize',
        background: 'transparent',
        position: 'relative',
        zIndex: 4,
      }}>
      <div style={{
        position: 'absolute', top: 0, bottom: 0, left: 2, right: 2,
        background: '#21262d',
        transition: 'background 120ms',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = '#3b82f6'; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = '#21262d'; }}
      />
    </div>
  );
}
