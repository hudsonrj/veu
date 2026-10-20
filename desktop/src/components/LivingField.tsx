import { useEffect, useRef } from "react";

type Props = {
  intensity?: number;
};

/** Campo vivo — o “papel de parede” do Véu. Não é decoração: é a membrana. */
export function LivingField({ intensity = 0.8 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let w = 0;
    let h = 0;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    const filaments = Array.from({ length: 28 }, (_, i) => ({
      phase: Math.random() * Math.PI * 2,
      speed: 0.15 + Math.random() * 0.35,
      amp: 40 + Math.random() * 120,
      y: Math.random(),
      gold: i % 3 !== 0,
    }));

    const resize = () => {
      w = window.innerWidth;
      h = window.innerHeight;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    resize();
    window.addEventListener("resize", resize);

    const draw = (t: number) => {
      const time = t * 0.001;
      ctx.clearRect(0, 0, w, h);

      const g = ctx.createLinearGradient(0, 0, w, h);
      g.addColorStop(0, "#07090c");
      g.addColorStop(0.45, "#0b141c");
      g.addColorStop(1, "#0a1014");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);

      const bloom = ctx.createRadialGradient(
        w * 0.5,
        h * 0.42,
        20,
        w * 0.5,
        h * 0.42,
        Math.max(w, h) * 0.55,
      );
      bloom.addColorStop(0, `rgba(232, 194, 122, ${0.07 * intensity})`);
      bloom.addColorStop(0.45, `rgba(127, 231, 212, ${0.04 * intensity})`);
      bloom.addColorStop(1, "transparent");
      ctx.fillStyle = bloom;
      ctx.fillRect(0, 0, w, h);

      for (const f of filaments) {
        ctx.beginPath();
        const baseY = f.y * h;
        for (let x = 0; x <= w; x += 12) {
          const y =
            baseY +
            Math.sin(x * 0.004 + time * f.speed + f.phase) * f.amp * intensity +
            Math.sin(x * 0.01 - time * f.speed * 0.6) * 18;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = f.gold
          ? `rgba(232, 194, 122, ${0.08 + 0.1 * intensity})`
          : `rgba(127, 231, 212, ${0.06 + 0.08 * intensity})`;
        ctx.lineWidth = f.gold ? 1.2 : 0.8;
        ctx.stroke();
      }

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, [intensity]);

  return <canvas className="living-field" ref={canvasRef} aria-hidden />;
}
