import React, { useCallback, useEffect, useRef, useState } from 'react';

export interface CanvasTransform {
  x: number;
  y: number;
  scale: number;
}

const MIN_SCALE = 0.15;
const MAX_SCALE = 2.5;

export function useCanvasTransform() {
  const [transform, setTransform] = useState<CanvasTransform>({
    x: 40,
    y: 40,
    scale: 1,
  });

  const containerRef = useRef<HTMLDivElement | null>(null);
  const isDraggingRef = useRef(false);
  const lastMousePosRef = useRef({ x: 0, y: 0 });

  const zoom = useCallback(
    (delta: number, clientX?: number, clientY?: number) => {
      setTransform((prev) => {
        const newScale = Math.min(
          MAX_SCALE,
          Math.max(MIN_SCALE, prev.scale + delta)
        );
        if (newScale === prev.scale) return prev;

        if (clientX !== undefined && clientY !== undefined && containerRef.current) {
          const rect = containerRef.current.getBoundingClientRect();
          const mouseX = clientX - rect.left;
          const mouseY = clientY - rect.top;

          const ratio = 1 - newScale / prev.scale;
          return {
            scale: newScale,
            x: prev.x + (mouseX - prev.x) * ratio,
            y: prev.y + (mouseY - prev.y) * ratio,
          };
        }

        return {
          ...prev,
          scale: newScale,
        };
      });
    },
    []
  );

  const zoomIn = useCallback(() => zoom(0.15), [zoom]);
  const zoomOut = useCallback(() => zoom(-0.15), [zoom]);

  const resetView = useCallback(() => {
    setTransform({ x: 40, y: 40, scale: 1 });
  }, []);

  const fitScreen = useCallback(() => {
    setTransform({ x: 20, y: 20, scale: 0.85 });
  }, []);

  // Attach native non-passive wheel listener to strictly prevent browser window zoom
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const handleWheelNative = (e: WheelEvent) => {
      // Strictly prevent browser page zoom (Ctrl+Wheel / Meta+Wheel / Pinch)
      e.preventDefault();
      e.stopPropagation();

      if (e.ctrlKey || e.metaKey) {
        // Smooth pinch/zoom on canvas only
        const delta = e.deltaY < 0 ? 0.08 : -0.08;
        zoom(delta, e.clientX, e.clientY);
      } else {
        // Pan canvas with mouse wheel
        setTransform((prev) => ({
          ...prev,
          x: prev.x - e.deltaX,
          y: prev.y - e.deltaY,
        }));
      }
    };

    const handleGesture = (e: Event) => {
      e.preventDefault();
    };

    el.addEventListener('wheel', handleWheelNative, { passive: false });
    el.addEventListener('gesturestart', handleGesture, { passive: false });
    el.addEventListener('gesturechange', handleGesture, { passive: false });

    return () => {
      el.removeEventListener('wheel', handleWheelNative);
      el.removeEventListener('gesturestart', handleGesture);
      el.removeEventListener('gesturechange', handleGesture);
    };
  }, [zoom]);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0 && e.button !== 1) return;
    const target = e.target as HTMLElement;
    // Don't drag if interacting with an input, textarea, button or interactive card content
    if (
      target.closest('button') ||
      target.closest('input') ||
      target.closest('textarea') ||
      target.closest('select') ||
      target.closest('.no-drag')
    ) {
      return;
    }
    isDraggingRef.current = true;
    lastMousePosRef.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDraggingRef.current) return;
    const dx = e.clientX - lastMousePosRef.current.x;
    const dy = e.clientY - lastMousePosRef.current.y;
    lastMousePosRef.current = { x: e.clientX, y: e.clientY };

    setTransform((prev) => ({
      ...prev,
      x: prev.x + dx,
      y: prev.y + dy,
    }));
  }, []);

  const onMouseUp = useCallback(() => {
    isDraggingRef.current = false;
  }, []);

  return {
    containerRef,
    transform,
    setTransform,
    zoomIn,
    zoomOut,
    resetView,
    fitScreen,
    onMouseDown,
    onMouseMove,
    onMouseUp,
  };
}
