import maplibregl, { type Map as MLMap, type StyleSpecification } from "maplibre-gl";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { markWebglFailed, webglAvailable } from "./webgl";

const ESRI =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";

export const baseStyle: StyleSpecification = {
  version: 8,
  projection: { type: "globe" },
  sky: {
    "sky-color": "#04060a",
    "horizon-color": "#0b1522",
    "fog-color": "#04060a",
    "sky-horizon-blend": 0.6,
    "horizon-fog-blend": 0.8,
    "fog-ground-blend": 0.9,
    "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 6, 0.4, 9, 0],
  },
  sources: {
    earth: {
      type: "raster",
      tiles: [ESRI],
      tileSize: 256,
      maxzoom: 19,
      attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
    },
  },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#04060a" } },
    {
      id: "earth",
      type: "raster",
      source: "earth",
      paint: {
        "raster-saturation": -0.35,
        "raster-brightness-max": 0.62,
        "raster-contrast": 0.08,
        "raster-fade-duration": 300,
      },
    },
  ],
};

type Props = {
  onReady: (map: MLMap) => void;
  initial?: { center: [number, number]; zoom: number; pitch?: number; bearing?: number };
  interactive?: boolean;
  /** shown instead of the map when the browser cannot start WebGL */
  fallback?: ReactNode;
};

export function BaseMap({ onReady, initial, interactive = true, fallback }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(() => !webglAvailable());
  useEffect(() => {
    if (!el.current || failed) return;
    let map: MLMap;
    try {
      map = new maplibregl.Map({
        container: el.current,
        style: baseStyle,
        center: initial?.center ?? [121.5, 12.5],
        zoom: initial?.zoom ?? 1.6,
        pitch: initial?.pitch ?? 0,
        bearing: initial?.bearing ?? 0,
        interactive,
        attributionControl: { compact: true },
        maxPitch: 75,
        fadeDuration: 0,
        canvasContextAttributes: { preserveDrawingBuffer: true, antialias: true },
      });
    } catch {
      // a context the browser refuses (GPU blocked, WebGL off) throws here; uncaught, it blanked the whole page
      markWebglFailed();
      setFailed(true);
      return;
    }
    (window as unknown as { __map: MLMap }).__map = map;
    map.on("load", () => onReady(map));
    return () => map.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [failed]);
  if (failed) {
    return <>{fallback ?? <p className="nomap mono">This browser cannot start WebGL, so the map is off. Every case, its sealed captures and its ledger still open.</p>}</>;
  }
  return <div ref={el} style={{ position: "absolute", inset: 0 }} />;
}
