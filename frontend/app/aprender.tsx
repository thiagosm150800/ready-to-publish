import { Ionicons } from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { AppState, Pressable, ScrollView, Text, View } from "react-native";
import Animated, { FadeInDown, FadeOutDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { APP_KEYS, APP_LABELS, AppKey, useSettings, useUpdateSettings } from "@/src/api";
import { fonts } from "@/src/fonts";
import { CapturedScreen, Diagnostics, getCapturedScreens, getDiagnostics, nativeAvailable, pushConfig, setLearning } from "@/src/native/rideFilter";
import { makeStyles, useTheme } from "@/src/theme";

type ListKey = "accept_texts";

const TARGETS: Record<AppKey, { key: ListKey; label: string }[]> = {
  rapido: [{ key: "accept_texts", label: "Botão Aceitar" }],
  moove: [{ key: "accept_texts", label: "Botão Aceitar" }],
  urbano: [{ key: "accept_texts", label: "Botão Aceitar" }],
};

// Demo screen shown in the preview (no native module) so the flow can be tried.
const DEMO: Record<AppKey, CapturedScreen> = {
  rapido: { package: "exemplo.rapidocar", at: Date.now(), texts: ["Nova corrida", "R$ 18,50", "1,2 km", "7,4 km", "Aceitar", "Recusar"] },
  moove: { package: "exemplo.moovecar", at: Date.now(), texts: ["Nova solicitação", "R$ 22,00", "0,8 km", "9,1 km", "Aceitar corrida", "Ignorar"] },
  urbano: { package: "exemplo.urbanonorte", at: Date.now(), texts: ["Nova corrida", "R$ 15,00", "1,0 km", "5,2 km", "Aceitar", "Recusar"] },
};

export default function Aprender() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ app?: string }>();
  const { colors } = useTheme();
  const styles = useStyles();
  const settings = useSettings();
  const update = useUpdateSettings();
  const [app, setApp] = useState<AppKey>(APP_KEYS.includes(params.app as AppKey) ? (params.app as AppKey) : "rapido");
  const [learning, setLearningState] = useState(false);
  const [screens, setScreens] = useState(() => getCapturedScreens());
  const [picked, setPicked] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [diag, setDiag] = useState<Diagnostics | null>(() => getDiagnostics());

  const refresh = useCallback(() => {
    const s = getCapturedScreens();
    setScreens(s);
    setDiag(getDiagnostics());
    if (s) setLearningState(s.learning);
  }, []);

  useEffect(() => {
    refresh();
    const sub = AppState.addEventListener("change", (st) => st === "active" && refresh());
    return () => sub.remove();
  }, [refresh]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2000);
    return () => clearTimeout(t);
  }, [toast]);

  const toggleLearning = () => {
    const next = !learning;
    setLearning(next);
    setLearningState(next);
  };

  const screen = nativeAvailable ? screens?.[app] ?? null : DEMO[app];
  const s = settings.data;

  const assign = (key: ListKey, label: string) => {
    if (!picked || !s) return;
    const current = s.apps[app][key];
    if (current.some((t) => t.toLowerCase() === picked.toLowerCase())) {
      setToast(`"${picked}" já está em ${label}`);
      setPicked(null);
      return;
    }
    update.mutate({ apps: { [app]: { [key]: [picked, ...current] } } }, {
      onSuccess: (ns) => {
        pushConfig(ns);
        setToast(`"${picked}" adicionado em ${label}`);
        setPicked(null);
      },
      onError: () => setToast("Erro ao salvar. Tente novamente."),
    });
  };

  return (
    <View style={styles.screen} testID="aprender-screen">
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="aprender-back-button" onPress={() => router.back()} style={styles.back} hitSlop={8}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Modo aprendizado</Text>
          <Text style={styles.subtitle}>Ensine o bot a ler suas telas</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 24 }]}>
        {!nativeAvailable ? (
          <View style={styles.infoBox} testID="aprender-preview-notice">
            <Ionicons name="information-circle" size={20} color={colors.info} />
            <Text style={styles.infoText}>Prévia com textos de exemplo. No APK Android aparecem os textos reais da tela.</Text>
          </View>
        ) : (
          <Pressable testID="learning-toggle" onPress={toggleLearning} style={[styles.card, styles.row, learning && { borderColor: colors.brandPrimary }]}>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardTitle}>{learning ? "Lendo telas..." : "Começar a ler telas"}</Text>
              <Text style={styles.cardText}>
                1. Ligue aqui. 2. Abra o RapidoCar, a MooveCar ou o Urbano Norte na tela desejada. 3. Volte para este app e toque nos textos.
              </Text>
            </View>
            <View style={[styles.switchTrack, learning && styles.switchTrackOn]}>
              <View style={[styles.switchThumb, learning && styles.switchThumbOn]} />
            </View>
          </Pressable>
        )}

        <View style={styles.segment}>
          {APP_KEYS.map((k) => (
            <Pressable
              key={k}
              testID={`aprender-app-${k}`}
              onPress={() => {
                setApp(k);
                setPicked(null);
              }}
              style={[styles.segBtn, app === k && styles.segBtnActive]}
            >
              <Text numberOfLines={1} adjustsFontSizeToFit style={[styles.segText, app === k && styles.segTextActive]}>{APP_LABELS[k]}</Text>
            </Pressable>
          ))}
        </View>

        {nativeAvailable ? (
          <Pressable testID="aprender-refresh-button" onPress={refresh} style={styles.refresh}>
            <Ionicons name="refresh" size={16} color={colors.onSurfaceTertiary} />
            <Text style={styles.refreshText}>Atualizar leitura</Text>
          </Pressable>
        ) : null}

        {!screen ? (
          <View style={styles.empty} testID="aprender-empty">
            <Ionicons name="scan-outline" size={40} color={colors.muted} />
            <Text style={styles.emptyText}>
              Nenhuma tela lida ainda. Ligue a leitura e abra o {APP_LABELS[app]} numa oferta de corrida.
            </Text>
          </View>
        ) : (
          <View style={styles.card} testID="captured-texts">
            <Text style={styles.cardText}>
              {screen.package} · {new Date(screen.at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
            </Text>
            <Text style={styles.cardTitle}>Toque num texto para usar</Text>
            <View style={styles.chips}>
              {screen.texts.map((t, i) => (
                <Pressable
                  key={`${t}-${i}`}
                  testID={`captured-text-${i}`}
                  onPress={() => setPicked(t === picked ? null : t)}
                  style={[styles.chip, picked === t && styles.chipActive]}
                >
                  <Text style={[styles.chipText, picked === t && styles.chipTextActive]} numberOfLines={1}>
                    {t}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
        )}

        {picked ? (
          <Animated.View entering={FadeInDown} style={styles.card} testID="assign-panel">
            <Text style={styles.cardTitle}>{`Usar "${picked}" como:`}</Text>
            {/recus|ignor|r\$|\bkm\b|^\d/i.test(picked) ? (
              <View style={styles.warnBox} testID="assign-warning">
                <Ionicons name="warning" size={16} color={colors.warning} />
                <Text style={styles.warnText}>Cuidado: isso parece um valor, distância ou botão de recusar. Escolha o texto exato do botão certo.</Text>
              </View>
            ) : null}
            {TARGETS[app].map((t) => (
              <Pressable
                key={t.key}
                testID={`assign-${t.key}`}
                disabled={update.isPending}
                onPress={() => assign(t.key, t.label)}
                style={styles.assignBtn}
              >
                <Text style={styles.assignText}>{t.label}</Text>
                <Ionicons name="add-circle" size={20} color={colors.brandPrimary} />
              </Pressable>
            ))}
          </Animated.View>
        ) : null}

        <DiagCard diag={diag} app={app} />

        {s ? (
          <View style={styles.card} testID="current-texts">
            <Text style={styles.cardTitle}>Textos atuais</Text>
            {TARGETS[app].map((t) => (
              <Text key={t.key} style={styles.cardText}>
                <Text style={{ color: colors.onSurface }}>{t.label}: </Text>
                {s.apps[app][t.key].join(", ")}
              </Text>
            ))}
          </View>
        ) : null}
      </ScrollView>

      {toast ? (
        <Animated.View entering={FadeInDown} exiting={FadeOutDown} style={[styles.toast, { bottom: insets.bottom + 16 }]} testID="aprender-toast">
          <Text style={styles.toastText}>{toast}</Text>
        </Animated.View>
      ) : null}
    </View>
  );
}

function DiagCard({ diag, app }: { diag: Diagnostics | null; app: AppKey }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const time = (ms?: number) => (ms ? new Date(ms).toLocaleTimeString("pt-BR") : "—");
  const d = diag?.[app];
  return (
    <View style={styles.card} testID="diagnostics-card">
      <View style={styles.row}>
        <Ionicons name="pulse-outline" size={18} color={colors.brandPrimary} />
        <Text style={styles.cardTitle}>Diagnóstico · {APP_LABELS[app]}</Text>
      </View>
      {!nativeAvailable ? (
        <Text style={styles.cardText} testID="diagnostics-preview">Disponível no APK Android: mostra o que o robô está vendo na tela.</Text>
      ) : !diag ? (
        <Text style={styles.cardText} testID="diagnostics-empty">Atualize o APK para ver o diagnóstico.</Text>
      ) : (
        <>
          <Text style={styles.cardText} testID="diagnostics-listening">
            Serviço ligado às {time(diag.connected_at)} · ouvindo: {(diag.listening ?? []).join(", ") || "—"}
          </Text>
          <Text style={styles.cardText} testID="diagnostics-last-pkg">
            Último app visto: {diag.last_pkg || "—"} às {time(diag.last_pkg_at)}
          </Text>
          {d ? (
            <>
              <Text style={[styles.cardText, { color: colors.onSurface }]} testID="diagnostics-status">
                {time(d.at)} · {d.status}
              </Text>
              <Text style={styles.cardText}>Evento de: {d.event_pkg || "—"} · janelas lidas: {d.roots?.join(", ") || "nenhuma"}</Text>
              {d.texts?.length ? <Text style={styles.cardText} numberOfLines={6}>Textos vistos: {d.texts.join(" | ")}</Text> : null}
            </>
          ) : (
            <Text style={[styles.cardText, { color: colors.warning }]} testID="diagnostics-no-events">
              Nenhum evento do {APP_LABELS[app]} recebido. Abra o app com uma oferta na tela e toque em Atualizar leitura.
            </Text>
          )}
        </>
      )}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 8, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: c.divider },
  back: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.display, fontSize: 28, color: c.onSurface, lineHeight: 32 },
  subtitle: { fontFamily: fonts.body, fontSize: 13, color: c.onSurfaceSecondary },
  content: { padding: 16, gap: 12 },
  infoBox: { flexDirection: "row", gap: 8, alignItems: "center", padding: 12, borderRadius: 12, borderWidth: 1, borderColor: c.info, backgroundColor: c.infoTint },
  infoText: { flex: 1, fontFamily: fonts.body, fontSize: 13, color: c.onSurfaceTertiary },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: 12, padding: 12, gap: 8, borderWidth: 1, borderColor: c.border },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  cardTitle: { fontFamily: fonts.bodySemi, fontSize: 14, color: c.onSurface },
  cardText: { fontFamily: fonts.body, fontSize: 12, color: c.onSurfaceSecondary },
  switchTrack: { width: 52, height: 30, borderRadius: 15, backgroundColor: c.surfaceTertiary, borderWidth: 1, borderColor: c.borderStrong, padding: 3 },
  switchTrackOn: { backgroundColor: c.brandPrimary, borderColor: c.brandPrimary },
  switchThumb: { width: 22, height: 22, borderRadius: 11, backgroundColor: c.onSurfaceSecondary },
  switchThumbOn: { backgroundColor: c.onBrandPrimary, transform: [{ translateX: 22 }] },
  segment: { flexDirection: "row", backgroundColor: c.surfaceSecondary, borderRadius: 8, padding: 4, gap: 4 },
  segBtn: { flexGrow: 1, flexBasis: "auto", paddingHorizontal: 8, height: 44, borderRadius: 6, alignItems: "center", justifyContent: "center" },
  segBtnActive: { backgroundColor: c.brandPrimary },
  segText: { fontFamily: fonts.bodySemi, fontSize: 13, color: c.onSurfaceSecondary },
  segTextActive: { color: c.onBrandPrimary },
  refresh: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", height: 44, paddingHorizontal: 12 },
  refreshText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: c.onSurfaceTertiary },
  empty: { alignItems: "center", gap: 12, padding: 24 },
  emptyText: { fontFamily: fonts.body, fontSize: 14, color: c.onSurfaceSecondary, textAlign: "center" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { minHeight: 40, maxWidth: "100%", paddingHorizontal: 12, borderRadius: 8, borderWidth: 1, borderColor: c.border, backgroundColor: c.surface, justifyContent: "center" },
  chipActive: { borderColor: c.brandPrimary, backgroundColor: c.brandTertiary },
  chipText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: c.onSurfaceTertiary },
  chipTextActive: { color: c.onBrandTertiary },
  assignBtn: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", height: 48, paddingHorizontal: 12, borderRadius: 8, backgroundColor: c.surfaceTertiary },
  assignText: { fontFamily: fonts.bodyMedium, fontSize: 14, color: c.onSurface },
  warnBox: { flexDirection: "row", gap: 8, alignItems: "center", padding: 8, borderRadius: 8, borderWidth: 1, borderColor: c.warning },
  warnText: { flex: 1, fontFamily: fonts.body, fontSize: 12, color: c.warning },
  toast: { position: "absolute", left: 16, right: 16, backgroundColor: c.surfaceInverse, borderRadius: 8, padding: 12 },
  toastText: { fontFamily: fonts.bodySemi, fontSize: 14, color: c.onSurfaceInverse, textAlign: "center" },
}));
