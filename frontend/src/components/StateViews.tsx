import { ActivityIndicator, Pressable, Text, View } from "react-native";

import { fonts } from "@/src/fonts";
import { makeStyles, useTheme } from "@/src/theme";

export function LoadingState({ label }: { label: string }) {
  const { colors } = useTheme();
  const styles = useStyles();
  return (
    <View style={styles.center} testID="loading-state">
      <ActivityIndicator color={colors.brandPrimary} />
      <Text style={styles.text}>{label}</Text>
    </View>
  );
}

export function ErrorState({ onRetry }: { onRetry: () => void }) {
  const styles = useStyles();
  return (
    <View style={styles.center} testID="error-state">
      <Text style={styles.text}>Não foi possível carregar os dados.</Text>
      <Pressable testID="retry-button" onPress={onRetry} style={styles.btn}>
        <Text style={styles.btnText}>Tentar novamente</Text>
      </Pressable>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, gap: 12 },
  text: { fontFamily: fonts.body, color: c.onSurfaceSecondary, fontSize: 14, textAlign: "center" },
  btn: { backgroundColor: c.brandPrimary, paddingHorizontal: 20, height: 44, borderRadius: 8, justifyContent: "center" },
  btnText: { fontFamily: fonts.bodySemi, color: c.onBrandPrimary, fontSize: 14 },
}));
