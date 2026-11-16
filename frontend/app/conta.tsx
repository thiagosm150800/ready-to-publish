import { Ionicons } from "@react-native-vector-icons/ionicons";
import { useQueryClient } from "@tanstack/react-query";
import * as WebBrowser from "expo-web-browser";
import { useRouter } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";
import Animated, { FadeInDown, FadeOutDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { apiClearHistory, apiDeleteAccount, PRIVACY_URL } from "@/src/api";
import { useAuth } from "@/src/auth";
import { fonts } from "@/src/fonts";
import { clearPendingEvents } from "@/src/native/rideFilter";
import { makeStyles, useTheme } from "@/src/theme";

type Confirm = "history" | "delete" | null;
type IconName = React.ComponentProps<typeof Ionicons>["name"];

export default function Conta() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { colors } = useTheme();
  const styles = useStyles();
  const { user, signOut } = useAuth();
  const [confirm, setConfirm] = useState<Confirm>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const runConfirm = async () => {
    setBusy(true);
    try {
      if (confirm === "history") {
        const r = await apiClearHistory();
        clearPendingEvents();
        await qc.invalidateQueries();
        setMsg({ ok: true, text: `${r.deleted} corridas apagadas` });
        setConfirm(null);
      } else if (confirm === "delete") {
        await apiDeleteAccount();
        clearPendingEvents();
        await signOut();
      }
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Erro. Tente novamente." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.screen} testID="conta-screen">
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="conta-back-button" onPress={() => router.back()} style={styles.iconBtn} hitSlop={8}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Minha conta</Text>
      </View>

      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 24 }]}>
        <View style={styles.profile}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{(user?.name || "M").slice(0, 1).toUpperCase()}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.name} testID="account-name">{user?.name || "Motorista"}</Text>
            <Text style={styles.email} testID="account-cpf">CPF {user?.cpf}</Text>
          </View>
        </View>

        <View style={styles.group}>
          <Row icon="document-text-outline" label="Política de Privacidade" testID="account-privacy-button" onPress={() => WebBrowser.openBrowserAsync(PRIVACY_URL)} />
          <Row icon="accessibility-outline" label="Aviso de acessibilidade" testID="account-disclosure-button" onPress={() => router.push("/aviso")} />
          <Row icon="trash-outline" label="Apagar histórico de corridas" testID="account-clear-history-button" onPress={() => setConfirm("history")} />
        </View>

        <View style={styles.group}>
          <Row icon="log-out-outline" label="Sair" testID="account-logout-button" onPress={() => signOut()} />
          <Row icon="close-circle-outline" label="Excluir conta e dados" danger testID="account-delete-button" onPress={() => setConfirm("delete")} />
        </View>

        {confirm ? (
          <Animated.View entering={FadeInDown} exiting={FadeOutDown} style={styles.confirm} testID="account-confirm-panel">
            <Text style={styles.confirmTitle}>{confirm === "history" ? "Apagar todo o histórico?" : "Excluir sua conta?"}</Text>
            <Text style={styles.confirmText}>
              {confirm === "history"
                ? "Todas as corridas registradas serão apagadas. Seus filtros continuam salvos."
                : "Sua conta, filtros e histórico serão apagados para sempre. Isso não pode ser desfeito."}
            </Text>
            <View style={styles.confirmRow}>
              <Pressable testID="account-confirm-cancel" onPress={() => setConfirm(null)} style={styles.cancelBtn}>
                <Text style={styles.cancelText}>Cancelar</Text>
              </Pressable>
              <Pressable testID="account-confirm-ok" onPress={runConfirm} disabled={busy} style={styles.dangerBtn}>
                {busy ? <ActivityIndicator color={colors.onError} /> : <Text style={styles.dangerText}>{confirm === "history" ? "Apagar" : "Excluir"}</Text>}
              </Pressable>
            </View>
          </Animated.View>
        ) : null}

        {msg ? (
          <Text style={[styles.msg, !msg.ok && { color: colors.error }]} testID="account-message">
            {msg.text}
          </Text>
        ) : null}
      </ScrollView>
    </View>
  );
}

function Row({ icon, label, onPress, danger, testID }: { icon: IconName; label: string; onPress: () => void; danger?: boolean; testID: string }) {
  const styles = useStyles();
  const { colors } = useTheme();
  return (
    <Pressable testID={testID} onPress={onPress} style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.surfaceTertiary }]}>
      <Ionicons name={icon} size={22} color={danger ? colors.error : colors.onSurfaceTertiary} />
      <Text style={[styles.rowText, danger && { color: colors.error }]}>{label}</Text>
      <Ionicons name="chevron-forward" size={18} color={colors.muted} />
    </Pressable>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingBottom: 8, borderBottomWidth: 1, borderBottomColor: c.divider },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.display, fontSize: 28, color: c.onSurface },
  content: { padding: 16, gap: 16 },
  profile: { flexDirection: "row", alignItems: "center", gap: 12, padding: 16, borderRadius: 12, backgroundColor: c.surfaceSecondary },
  avatar: { width: 52, height: 52, borderRadius: 26, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  avatarText: { fontFamily: fonts.display, fontSize: 26, color: c.onBrandPrimary },
  name: { fontFamily: fonts.bodySemi, fontSize: 16, color: c.onSurface },
  email: { fontFamily: fonts.body, fontSize: 13, color: c.onSurfaceSecondary },
  group: { borderRadius: 12, backgroundColor: c.surfaceSecondary, overflow: "hidden", borderWidth: 1, borderColor: c.border },
  row: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: 56, paddingHorizontal: 16, borderBottomWidth: 1, borderBottomColor: c.divider },
  rowText: { flex: 1, fontFamily: fonts.bodyMedium, fontSize: 15, color: c.onSurface },
  confirm: { padding: 16, borderRadius: 12, borderWidth: 1, borderColor: c.error, backgroundColor: c.errorTint, gap: 8 },
  confirmTitle: { fontFamily: fonts.bodySemi, fontSize: 16, color: c.onSurface },
  confirmText: { fontFamily: fonts.body, fontSize: 13, color: c.onSurfaceTertiary },
  confirmRow: { flexDirection: "row", gap: 12, marginTop: 4 },
  cancelBtn: { flex: 1, height: 48, borderRadius: 8, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  cancelText: { fontFamily: fonts.bodySemi, fontSize: 14, color: c.onSurfaceTertiary },
  dangerBtn: { flex: 1, height: 48, borderRadius: 8, backgroundColor: c.error, alignItems: "center", justifyContent: "center" },
  dangerText: { fontFamily: fonts.bodySemi, fontSize: 14, color: c.onError },
  msg: { fontFamily: fonts.bodyMedium, fontSize: 14, color: c.success, textAlign: "center" },
}));
