import { motion } from "framer-motion";

export function BrandMark() {
  return (
    <motion.h1
      className="brand"
      initial={{ opacity: 0, y: 28, letterSpacing: "0.55em" }}
      animate={{ opacity: 1, y: 0, letterSpacing: "0.18em" }}
      transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
    >
      véu
      <style>{`
        .brand {
          margin: 0;
          font-family: var(--font-display);
          font-weight: 800;
          font-size: clamp(4.5rem, 18vw, 9.5rem);
          line-height: 0.9;
          text-transform: lowercase;
          color: var(--mist);
          text-shadow:
            0 0 40px rgba(232, 194, 122, 0.25),
            0 0 120px rgba(127, 231, 212, 0.12);
        }
      `}</style>
    </motion.h1>
  );
}
