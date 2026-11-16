import { StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { fonts } from "@/src/fonts";
import { makeStyles } from "@/src/theme";

export function ScreenHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: React.ReactNode }) {
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  return (
    <View style={[styles.wrap, { paddingTop: insets.top + 12 }]}>
      <View style={styles.texts}>
        <Text style={styles.title} testID="screen-title">{title}</Text>
        {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
      </View>
      {right}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  wrap: {
    backgroundColor: c.surface,
    paddingHorizontal: 16,
    paddingBottom: 12,
    flexDirection: "row",
    alignItems: "flex-end",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: c.divider,
  },
  texts: { flex: 1 },
  title: { fontFamily: fonts.display, fontSize: 32, color: c.onSurface, letterSpacing: 0.5, lineHeight: 36 },
  subtitle: { fontFamily: fonts.body, fontSize: 13, color: c.onSurfaceSecondary, marginTop: 2 },
}));
