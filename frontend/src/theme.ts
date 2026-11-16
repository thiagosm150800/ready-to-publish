// Design tokens (keys match the "color" block of /app/design_guidelines.json).
// Dark-first utility app: the same dark palette is used for both schemes.

import { useMemo } from "react";
import { Appearance, StyleSheet, useColorScheme } from "react-native";

export type ColorScheme = "light" | "dark";

const dark = {
  surface: "#0F1115",
  onSurface: "#FFFFFF",
  surfaceSecondary: "#1A1D24",
  onSurfaceSecondary: "#A0A5B1",
  surfaceTertiary: "#252932",
  onSurfaceTertiary: "#D1D5DB",
  surfaceInverse: "#FFFFFF",
  onSurfaceInverse: "#0F1115",
  muted: "#6B7280",

  brand: "#FF6B00",
  onBrand: "#FFFFFF",
  brandPrimary: "#FF6B00",
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#FF8C33",
  onBrandSecondary: "#0F1115",
  brandTertiary: "#331A00",
  onBrandTertiary: "#FFB380",

  success: "#00E676",
  onSuccess: "#00331A",
  warning: "#FFC400",
  onWarning: "#332700",
  error: "#FF3D00",
  onError: "#FFFFFF",
  info: "#00B0FF",
  onInfo: "#002333",

  border: "#2A2F3A",
  borderStrong: "#3F4654",
  divider: "#1F232B",
  scrim: "rgba(15,17,21,0.92)",
  scrimClear: "rgba(15,17,21,0.35)",
  successTint: "rgba(0,230,118,0.12)",
  errorTint: "rgba(255,61,0,0.12)",
  infoTint: "rgba(0,176,255,0.12)",
};

export type ThemeColors = typeof dark;

export const defaultScheme = "dark" satisfies ColorScheme;

export const themes: { light: ThemeColors; dark?: ThemeColors } = { light: dark, dark };

export const colors = dark;

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, "2xl": 32, "3xl": 48 };
export const radius = { sm: 4, md: 8, lg: 12, pill: 999 };

export function setColorScheme(scheme: ColorScheme | null) {
  Appearance.setColorScheme?.(scheme ?? "unspecified");
}

setColorScheme?.(themes.dark ? null : defaultScheme);

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors } {
  const system = useColorScheme();
  const scheme: ColorScheme = (system === "light" || system === "dark") && themes[system] ? system : defaultScheme;
  return { scheme, colors: themes[scheme] ?? themes.light };
}

export function makeStyles<T extends StyleSheet.NamedStyles<T> | StyleSheet.NamedStyles<any>>(
  factory: (colors: ThemeColors) => T & StyleSheet.NamedStyles<any>,
): () => T {
  return function useStyles(): T {
    const { colors } = useTheme();
    return useMemo(() => StyleSheet.create(factory(colors)), [colors]);
  };
}
