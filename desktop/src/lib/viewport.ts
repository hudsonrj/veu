/** Breakpoints mobile-first do Véu OS. */

export type ViewportMode = "phone" | "tablet" | "desktop";

/** iPhone / Android phone */
export const BP_PHONE_MAX = 743;
/** iPad mini · tablets estreitos (portrait) */
export const BP_TABLET_MIN = 744;
/** iPad / tablet largo → desktop shell */
export const BP_DESKTOP_MIN = 1024;

export function modeFromWidth(width: number): ViewportMode {
  if (width >= BP_DESKTOP_MIN) return "desktop";
  if (width >= BP_TABLET_MIN) return "tablet";
  return "phone";
}

export function isCompactMode(mode: ViewportMode): boolean {
  return mode === "phone" || mode === "tablet";
}
