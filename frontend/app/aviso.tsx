import { Ionicons } from "@react-native-vector-icons/ionicons";
import * as WebBrowser from "expo-web-browser";
import { useRouter } from "expo-router";
import { Pressable, ScrollView, Text, View } from "react-native";
import Animated, { FadeInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { PRIVACY_URL } from "@/src/api";
import { fonts } from "@/src/fonts";
import { DISCLOSURE_KEY, nativeAvailable, openAccessibilitySettings } from "@/src/native/rideFilter";
import { makeStyles, useTheme } from "@/src/theme";
import { storage } from "@/src/utils/storage";

const ITEMS: { icon: "eye-outline" | "hand-left-outline" | "lock-closed-outline" | "power-outline"; title: string; text: string }[] = [
  { icon: "eye-outline", title: "O que o app lê", text: "Somente os textos das telas do RapidoCar, MooveCar, Urbano Norte e LOG Urbano: valor da corrida, distâncias e nomes de botões." },
  { icon: "hand-left-outline", title: "O que o app faz", text: "Toca em \"Aceitar\" quando a corrida passa nos filtros que você definiu para cada app." },
  { icon: "lock-closed-outline", title: "O que o app NÃO faz", text: "Não lê senhas, mensagens, outros apps nem o que você digita. Seus dados não são vendidos nem compartilhados." },
  { icon: "power-outline", title: "Você controla", text: "Desligue a qualquer momento no botão de auto-aceite ou em Configurações › Acessibilidade." },
];

export default function Aviso() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { colors } = useTheme();
  const styles = useStyles();

  const accept = async () => {
    await storage.setItem(DISCLOSURE_KEY, true);
    if (nativeAvailable) openAccessibilitySettings();
    router.back();
  };

  return (
    <View style={styles.screen} testID="aviso-screen">
      <ScrollView contentContainerStyle={[styles.content, { paddingTop: insets.top + 24 }]}>
        <View style={styles.iconWrap}>
          <Ionicons name="accessibility" size={36} color={colors.brandPrimary} />
        </View>
        <Text style={styles.title}>Uso do Serviço de Acessibilidade</Text>
        <Text style={styles.lead}>
          Para aceitar corridas sozinho, o RapidoChecker usa a API de Acessibilidade do Android. Leia como ela é usada antes de ativar.
        </Text>
        {ITEMS.map((it, i) => (
          <Animated.View key={it.title} entering={FadeInDown.delay(80 * i)} style={styles.item}>
            <Ionicons name={it.icon} size={22} color={colors.brandSecondary} />
            <View style={{ flex: 1 }}>
              <Text style={styles.itemTitle}>{it.title}</Text>
              <Text style={styles.itemText}>{it.text}</Text>
            </View>
          </Animated.View>
        ))}
        <Pressable testID="aviso-privacy-link" onPress={() => WebBrowser.openBrowserAsync(PRIVACY_URL)} style={styles.linkBtn}>
          <Text style={styles.link}>Ler a Política de Privacidade completa</Text>
        </Pressable>
      </ScrollView>
      <View style={[styles.footer, { paddingBottom: insets.bottom + 16 }]}>
        <Pressable testID="aviso-decline-button" onPress={() => router.back()} style={styles.secondary}>
          <Text style={styles.secondaryText}>Agora não</Text>
        </Pressable>
        <Pressable testID="aviso-accept-button" onPress={accept} style={styles.primary}>
          <Text style={styles.primaryText}>Concordo e ativar</Text>
        </Pressable>
      </View>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  content: { paddingHorizontal: 24, gap: 16, paddingBottom: 24 },
  iconWrap: { width: 72, height: 72, borderRadius: 36, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.display, fontSize: 32, lineHeight: 36, color: c.onSurface },
  lead: { fontFamily: fonts.body, fontSize: 15, color: c.onSurfaceSecondary, lineHeight: 22 },
  item: { flexDirection: "row", gap: 12, padding: 12, borderRadius: 12, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  itemTitle: { fontFamily: fonts.bodySemi, fontSize: 14, color: c.onSurface },
  itemText: { fontFamily: fonts.body, fontSize: 13, color: c.onSurfaceSecondary, marginTop: 2, lineHeight: 19 },
  linkBtn: { minHeight: 44, justifyContent: "center" },
  link: { fontFamily: fonts.bodyMedium, fontSize: 14, color: c.brandSecondary, textDecorationLine: "underline" },
  footer: { flexDirection: "row", gap: 12, paddingHorizontal: 16, paddingTop: 12, borderTopWidth: 1, borderTopColor: c.divider },
  secondary: { flex: 1, height: 56, borderRadius: 12, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  secondaryText: { fontFamily: fonts.bodySemi, fontSize: 15, color: c.onSurfaceTertiary },
  primary: { flex: 1.5, height: 56, borderRadius: 12, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  primaryText: { fontFamily: fonts.bodySemi, fontSize: 15, color: c.onBrandPrimary },
}));
