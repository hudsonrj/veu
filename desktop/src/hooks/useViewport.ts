import { useEffect, useState } from "react";
import { modeFromWidth, type ViewportMode } from "../lib/viewport";

export function useViewport(): { mode: ViewportMode; width: number; height: number } {
  const [state, setState] = useState(() => {
    if (typeof window === "undefined") {
      return { mode: "desktop" as ViewportMode, width: 1280, height: 800 };
    }
    const width = window.innerWidth;
    const height = window.innerHeight;
    return { mode: modeFromWidth(width), width, height };
  });

  useEffect(() => {
    const onResize = () => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      setState({ mode: modeFromWidth(width), width, height });
    };
    onResize();
    window.addEventListener("resize", onResize);
    window.addEventListener("orientationchange", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("orientationchange", onResize);
    };
  }, []);

  return state;
}
