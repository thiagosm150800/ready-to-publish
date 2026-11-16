import { Ionicons } from "@react-native-vector-icons/ionicons";
import * as WebBrowser from "expo-web-browser";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Image, Pressable, Text, TextInput, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import Animated, { FadeIn, FadeInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { apiCpfLogin, isValidCpf, maskCpf, PRIVACY_URL } from "@/src/api";
import { useAuth } from "@/src/auth";
import { getDeviceId } from "@/src/device";
import { fonts } from "@/src/fonts";
import { makeStyles, useTheme } from "@/src/theme";

type Notice = { tone: "warning" | "error"; title: string; text: string } | null;

export default function Login() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { colors } = useTheme();
  const styles = useStyles();
  const { signIn, exitReason, clearExitReason } = useAuth();
  const [cpf, setCpf] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [loading, setLoading] = useState(false);

  // Explain automatic sign-outs (expired period, access revoked).
  useEffect(() => {
    if (!exitReason) return;
    const expired = exitReason.toLowerCase().includes("venceu");
    setNotice(
      expired
        ? { tone: "error", title: "Prazo de acesso vencido", text: "Seu período de acesso terminou. Fale com o responsável para renovar." }
        : { tone: "error", title: "Você saiu do app", text: `${exitReason}. Fale com o responsável.` },
    );
    clearExitReason();
  }, [exitReason, clearExitReason]);

  const submit = async () => {
    setError(null);
    setNotice(null);
    if (!isValidCpf(cpf)) {
      setError("CPF inválido. Confira os números.");
      return;
    }
    setLoading(true);
    try {
      const res = await apiCpfLogin(cpf, await getDeviceId());
      if (res.status === "approved") await signIn(res.access_token, res.user);
      else if (res.status === "pending")
        setNotice({ tone: "warning", title: "Aguardando liberação", text: "Seu CPF foi registrado. Assim que o acesso for liberado, toque em Entrar novamente." });
      else if (res.status === "other_device")
        setNotice({ tone: "error", title: "CPF liberado em outro aparelho", text: "Cada CPF só pode ser usado em um celular. Peça ao responsável para liberar este aparelho." });
      else if (res.status === "expired")
        setNotice({ tone: "error", title: "Prazo de acesso vencido", text: "Seu período de acesso terminou. Fale com o responsável para renovar." });
      else setNotice({ tone: "error", title: "Acesso bloqueado", text: "Este CPF não tem acesso ao app. Fale com o responsável." });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível entrar.");
    } finally {
      setLoading(false);
    }
  };

  const noticeColor = notice?.tone === "error" ? colors.error : colors.warning;

  return (
    <View style={styles.screen} testID="login-screen">
      <KeyboardAwareScrollView
        bottomOffset={24}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={[styles.content, { paddingTop: insets.top + 48, paddingBottom: insets.bottom + 24 }]}
      >
        <Animated.View entering={FadeIn.duration(400)} style={styles.brand}>
          <View style={styles.logo}>
            <Image source={require("@/assets/images/logo.png")} style={styles.logoImg} resizeMode="contain" testID="app-logo" />
          </View>
          <Text style={styles.title}>RapidoChecker</Text>
          <Text style={styles.subtitle}>Auto-aceite de corridas no RapidoCar e no MooveCar.</Text>
        </Animated.View>

        <View style={styles.form}>
          <Text style={styles.label}>CPF</Text>
          <TextInput
            testID="auth-cpf-input"
            value={cpf}
            onChangeText={(v) => setCpf(maskCpf(v))}
            placeholder="000.000.000-00"
            placeholderTextColor={colors.muted}
            style={styles.input}
            keyboardType="number-pad"
            maxLength={14}
            onSubmitEditing={submit}
          />
          {error ? <Text style={styles.error} testID="auth-error">{error}</Text> : null}

          {notice ? (
            <Animated.View entering={FadeInDown} style={[styles.notice, { borderColor: noticeColor }]} testID="auth-notice">
              <Ionicons name={notice.tone === "error" ? "close-circle" : "hourglass-outline"} size={22} color={noticeColor} />
              <View style={{ flex: 1 }}>
                <Text style={[styles.noticeTitle, { color: noticeColor }]} testID="auth-notice-title">{notice.title}</Text>
                <Text style={styles.noticeText}>{notice.text}</Text>
              </View>
            </Animated.View>
          ) : null}

          <Pressable testID="auth-submit-button" onPress={submit} disabled={loading} style={({ pressed }) => [styles.submit, (pressed || loading) && { opacity: 0.85 }]}>
            {loading ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.submitText}>Entrar</Text>}
          </Pressable>
          <Text style={styles.hint}>Primeiro acesso? Digite seu CPF e toque em Entrar. O responsável libera seu acesso.</Text>
        </View>

        <View style={{ flex: 1 }} />
        <Pressable testID="login-privacy-link" onPress={() => WebBrowser.openBrowserAsync(PRIVACY_URL)} style={styles.linkBtn}>
          <Text style={styles.privacyText}>
            Ao continuar você concorda com a <Text style={styles.link}>Política de Privacidade</Text>
          </Text>
        </Pressable>
        <Pressable testID="open-admin-button" onPress={() => router.push("/admin")} style={styles.linkBtn}>
          <Text style={styles.adminText}>Área do administrador</Text>
        </Pressable>
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  content: { paddingHorizontal: 24, gap: 24, flexGrow: 1 },
  brand: { gap: 8 },
  // Logo artwork has a white background, so it sits on a white card in both themes.
  logo: { width: 160, height: 128, borderRadius: 16, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center", padding: 12, marginBottom: 8 },
  logoImg: { width: "100%", height: "100%" },
  title: { fontFamily: fonts.display, fontSize: 44, lineHeight: 48, color: c.onSurface },
  subtitle: { fontFamily: fonts.body, fontSize: 15, color: c.onSurfaceSecondary },
  form: { gap: 12 },
  label: { fontFamily: fonts.bodyMedium, fontSize: 13, color: c.onSurfaceTertiary },
  input: { height: 60, borderRadius: 8, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, paddingHorizontal: 16, color: c.onSurface, fontFamily: fonts.display, fontSize: 28, letterSpacing: 1 },
  error: { fontFamily: fonts.bodyMedium, fontSize: 14, color: c.error },
  notice: { flexDirection: "row", gap: 12, padding: 12, borderRadius: 12, borderWidth: 1, backgroundColor: c.surfaceSecondary },
  noticeTitle: { fontFamily: fonts.bodySemi, fontSize: 15 },
  noticeText: { fontFamily: fonts.body, fontSize: 13, color: c.onSurfaceSecondary, marginTop: 2 },
  submit: { height: 56, borderRadius: 12, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center", marginTop: 4 },
  submitText: { fontFamily: fonts.bodySemi, fontSize: 16, color: c.onBrandPrimary },
  hint: { fontFamily: fonts.body, fontSize: 12, color: c.muted },
  linkBtn: { minHeight: 44, justifyContent: "center" },
  privacyText: { fontFamily: fonts.body, fontSize: 12, color: c.muted, textAlign: "center" },
  link: { color: c.brandSecondary, textDecorationLine: "underline" },
  adminText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: c.onSurfaceSecondary, textAlign: "center" },
}));
