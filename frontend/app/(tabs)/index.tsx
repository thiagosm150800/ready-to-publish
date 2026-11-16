import { Ionicons } from "@react-native-vector-icons/ionicons";
import { useQueryClient } from "@tanstack/react-query";
import * as Haptics from "expo-haptics";
import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { AppState, Platform, Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import Animated, { FadeInDown, useAnimatedStyle, useSharedValue, withSpring } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { APP_KEYS, APP_LABELS, AppFilters, AppKey, brl, DaySummary, num, uploadRides, useMe, useSettings, useTodaySummary, useUpdateSettings } from "@/src/api";
import { useAuth } from "@/src/auth";
import { ScreenHeader } from "@/src/components/ScreenHeader";
import { ErrorState, LoadingState } from "@/src/components/StateViews";
import { fonts } from "@/src/fonts";
import {
  clearPendingEvents,
  DISCLOSURE_KEY,
  isServiceEnabled,
  nativeAvailable,
  openAccessibilitySettings,
  pushConfig,
  takePendingEvents,
} from "@/src/native/rideFilter";
import { usesNativeTabs } from "@/src/navigation";
import { inSchedule, nextStartLabel, scheduleSummary } from "@/src/schedule";
import { makeStyles, useTheme } from "@/src/theme";
import { storage } from "@/src/utils/storage";

export default function Painel() {
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const { colors } = useTheme();
  const styles = useStyles();
  const router = useRouter();
  const qc = useQueryClient();
  const { user } = useAuth();
  const settings = useSettings();
  const today = useTodaySummary();
  const me = useMe();
  const update = useUpdateSettings();
  const [serviceOn, setServiceOn] = useState(isServiceEnabled());
  const [refreshing, setRefreshing] = useState(false);

  const activateService = async () => {
    const ok = await storage.getItem<boolean>(DISCLOSURE_KEY, false);
    if (ok) openAccessibilitySettings();
    else router.push("/aviso");
  };

  // Upload rides evaluated by the Android service, then refresh history.
  const sync = useCallback(async () => {
    setServiceOn(isServiceEnabled());
    const pending = takePendingEvents();
    if (pending.length) {
      try {
        await uploadRides(pending);
        clearPendingEvents();
      } catch {
        // keep events on device; retried on next focus
      }
    }
    await qc.invalidateQueries({ queryKey: ["rides"] });
    qc.invalidateQueries({ queryKey: ["me"] });
  }, [qc]);

  useFocusEffect(
    useCallback(() => {
      sync();
    }, [sync]),
  );

  useEffect(() => {
    const sub = AppState.addEventListener("change", (s) => s === "active" && sync());
    return () => sub.remove();
  }, [sync]);

  useEffect(() => {
    if (settings.data) pushConfig(settings.data);
  }, [settings.data]);

  // Re-render every minute so the schedule status stays current.
  const [, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), 60000);
    return () => clearInterval(t);
  }, []);

  const header = (
    <ScreenHeader
      title="Painel"
      subtitle={user?.name ? `Olá, ${user.name.split(" ")[0]}` : "Auto-aceite RapidoCar e MooveCar"}
      right={
        <Pressable testID="open-account-button" onPress={() => router.push("/conta")} style={styles.accountBtn} hitSlop={6}>
          <Ionicons name="person-circle-outline" size={30} color={colors.onSurfaceSecondary} />
        </Pressable>
      }
    />
  );

  if (settings.isLoading) return <View style={styles.screen}>{header}<LoadingState label="Carregando painel..." /></View>;
  if (settings.isError || !settings.data)
    return <View style={styles.screen}>{header}<ErrorState onRetry={() => settings.refetch()} /></View>;

  const s = settings.data;
  const onSchedule = inSchedule(s);

  const toggle = (key: AppKey) => {
    if (Platform.OS !== "web") Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
    update.mutate({ apps: { [key]: { enabled: !s.apps[key].enabled } } });
  };

  const banner = !nativeAvailable
    ? { tone: "info" as const, icon: "information-circle" as const, title: "Modo prévia", text: "A automação real só funciona no APK Android." }
    : serviceOn
      ? { tone: "success" as const, icon: "checkmark-circle" as const, title: "Serviço de acessibilidade ativo", text: "Pronto para ler ofertas do RapidoCar e do MooveCar." }
      : { tone: "error" as const, icon: "alert-circle" as const, title: "Serviço de acessibilidade inativo", text: "Ative \"RapidoChecker\" nas configurações de acessibilidade." };
  const toneColor = { info: colors.info, success: colors.success, error: colors.error }[banner.tone];
  const toneBg = { info: colors.infoTint, success: colors.successTint, error: colors.errorTint }[banner.tone];

  return (
    <View style={styles.screen} testID="painel-screen">
      {header}
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: bottomChrome + 24 }]}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={async () => {
              setRefreshing(true);
              await Promise.all([sync(), settings.refetch()]);
              setRefreshing(false);
            }}
            tintColor={colors.brandPrimary}
          />
        }
      >
        <View style={[styles.banner, { borderColor: toneColor, backgroundColor: toneBg }]} testID="service-status-banner">
          <Ionicons name={banner.icon} size={22} color={toneColor} />
          <View style={{ flex: 1 }}>
            <Text style={[styles.bannerTitle, { color: toneColor }]} testID="service-status-text">{banner.title}</Text>
            <Text style={styles.bannerText}>{banner.text}</Text>
          </View>
          {nativeAvailable && !serviceOn ? (
            <Pressable testID="open-accessibility-settings-button" onPress={activateService} style={[styles.bannerBtn, { backgroundColor: toneColor }]}>
              <Text style={styles.bannerBtnText}>Ativar</Text>
            </Pressable>
          ) : null}
        </View>

        {me.data?.expires_at ? <ExpiryWarning expiresAt={me.data.expires_at} /> : null}

        {today.data ? <TodayCard data={today.data} /> : null}

        {APP_KEYS.map((key, i) => (
          <Animated.View key={key} entering={FadeInDown.delay(i * 80)}>
            <AppCard
              appKey={key}
              filters={s.apps[key]}
              disabled={update.isPending}
              outOfHours={!onSchedule}
              resumeLabel={nextStartLabel(s)}
              onToggle={() => toggle(key)}
              onEdit={() => router.push(`/filtros?app=${key}`)}
            />
          </Animated.View>
        ))}

        {s.schedule_enabled ? (
          <Pressable testID="schedule-pill" onPress={() => router.push("/filtros")} style={styles.schedulePill}>
            <Ionicons name="time-outline" size={16} color={onSchedule ? colors.success : colors.warning} />
            <Text style={styles.scheduleText} numberOfLines={1}>
              {onSchedule ? "No horário" : "Fora do horário"} · {scheduleSummary(s)}
            </Text>
          </Pressable>
        ) : null}
      </ScrollView>
    </View>
  );
}

function AppCard(props: {
  appKey: AppKey;
  filters: AppFilters;
  disabled: boolean;
  outOfHours: boolean;
  resumeLabel: string;
  onToggle: () => void;
  onEdit: () => void;
}) {
  const { colors } = useTheme();
  const styles = useStyles();
  const on = props.filters.enabled;
  const scale = useSharedValue(1);
  const pressStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  const f = props.filters;

  return (
    <View style={[styles.card, on && { borderColor: colors.brandPrimary }]} testID={`app-card-${props.appKey}`}>
      <Animated.View style={pressStyle}>
        <Pressable
          testID={`auto-accept-toggle-${props.appKey}`}
          accessibilityRole="switch"
          accessibilityState={{ checked: on }}
          disabled={props.disabled}
          onPressIn={() => (scale.value = withSpring(0.97))}
          onPressOut={() => (scale.value = withSpring(1))}
          onPress={props.onToggle}
          style={[styles.toggle, on ? styles.toggleOn : styles.toggleOff]}
        >
          <View style={[styles.powerRing, { borderColor: on ? colors.onBrandPrimary : colors.borderStrong }]}>
            <Ionicons name="power" size={32} color={on ? colors.onBrandPrimary : colors.onSurfaceSecondary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={[styles.appName, { color: on ? colors.onBrandPrimary : colors.onSurfaceSecondary }]}>{APP_LABELS[props.appKey].toUpperCase()}</Text>
            <Text numberOfLines={1} adjustsFontSizeToFit style={[styles.toggleState, { color: on ? colors.onBrandPrimary : colors.onSurface }]} testID={`auto-accept-state-${props.appKey}`}>
              {on ? "LIGADO" : "DESLIGADO"}
            </Text>
            <Text style={[styles.toggleHint, { color: on ? colors.onBrandPrimary : colors.muted }]}>
              {on ? (props.outOfHours ? `Fora do horário · volta ${props.resumeLabel}` : "Aceitando corridas nos filtros") : "Toque para ligar o auto-aceite"}
            </Text>
          </View>
        </Pressable>
      </Animated.View>
      <Pressable testID={`filters-summary-${props.appKey}`} onPress={props.onEdit} style={styles.summary}>
        <SummaryItem label="Mín R$/km" value={brl(f.min_price_per_km)} />
        <View style={styles.vDivider} />
        <SummaryItem label="Mín corrida" value={brl(f.min_fare)} />
        <View style={styles.vDivider} />
        <SummaryItem label="Busca até" value={`${num(f.max_pickup_km)} km`} />
        <Ionicons name="chevron-forward" size={18} color={colors.muted} />
      </Pressable>
    </View>
  );
}

const WARN_DAYS = 3;

function ExpiryWarning({ expiresAt }: { expiresAt: string }) {
  const { colors } = useTheme();
  const styles = useStyles();
  const end = new Date(expiresAt);
  const msLeft = end.getTime() - Date.now();
  if (msLeft > WARN_DAYS * 86400000 || msLeft <= 0) return null;
  const days = Math.ceil(msLeft / 86400000);
  const when = days <= 1 ? "em menos de 1 dia" : `em ${days} dias`;
  const date = `${end.toLocaleDateString("pt-BR")} às ${end.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
  return (
    <View style={[styles.banner, { borderColor: colors.warning, backgroundColor: colors.surfaceSecondary }]} testID="expiry-warning">
      <Ionicons name="hourglass-outline" size={22} color={colors.warning} />
      <View style={{ flex: 1 }}>
        <Text style={[styles.bannerTitle, { color: colors.warning }]} testID="expiry-warning-title">Seu acesso vence {when}</Text>
        <Text style={styles.bannerText}>Válido até {date}. Fale com o responsável para renovar.</Text>
      </View>
    </View>
  );
}

function TodayCard({ data }: { data: DaySummary }) {
  const { colors } = useTheme();
  const styles = useStyles();
  return (
    <View style={styles.todayCard} testID="today-summary">
      <Text style={styles.todayTitle}>Hoje</Text>
      {APP_KEYS.map((key) => (
        <View key={key} style={styles.todayRow} testID={`today-${key}`}>
          <Text style={styles.todayApp}>{APP_LABELS[key]}</Text>
          <View style={styles.todayStat}>
            <Ionicons name="checkmark-circle" size={16} color={colors.success} />
            <Text style={styles.todayValue} testID={`today-accepted-${key}`}>{data[key].accepted}</Text>
            <Text style={styles.todayLabel}>aceitas</Text>
          </View>
          <View style={styles.todayStat}>
            <Ionicons name="close-circle" size={16} color={colors.error} />
            <Text style={styles.todayValue} testID={`today-rejected-${key}`}>{data[key].rejected}</Text>
            <Text style={styles.todayLabel}>recusadas</Text>
          </View>
        </View>
      ))}
    </View>
  );
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  const styles = useStyles();
  return (
    <View style={{ flex: 1 }}>
      <Text style={styles.summaryLabel}>{label}</Text>
      <Text style={styles.summaryValue} numberOfLines={1} adjustsFontSizeToFit>{value}</Text>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  content: { padding: 16, gap: 16 },
  accountBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  banner: { flexDirection: "row", alignItems: "center", gap: 12, padding: 12, borderRadius: 12, borderWidth: 1 },
  bannerTitle: { fontFamily: fonts.bodySemi, fontSize: 14 },
  bannerText: { fontFamily: fonts.body, fontSize: 12, color: c.onSurfaceSecondary, marginTop: 2 },
  bannerBtn: { height: 44, paddingHorizontal: 16, borderRadius: 8, justifyContent: "center" },
  bannerBtnText: { fontFamily: fonts.bodySemi, color: c.onError, fontSize: 14 },
  card: { borderRadius: 12, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary, overflow: "hidden" },
  toggle: { minHeight: 120, padding: 16, flexDirection: "row", alignItems: "center", gap: 16 },
  toggleOn: { backgroundColor: c.brandPrimary },
  toggleOff: { backgroundColor: c.surfaceTertiary },
  powerRing: { width: 64, height: 64, borderRadius: 32, borderWidth: 3, alignItems: "center", justifyContent: "center" },
  appName: { fontFamily: fonts.bodySemi, fontSize: 12, letterSpacing: 2 },
  toggleState: { fontFamily: fonts.display, fontSize: 34, lineHeight: 40 },
  toggleHint: { fontFamily: fonts.body, fontSize: 12 },
  summary: { flexDirection: "row", alignItems: "center", padding: 12, gap: 8, minHeight: 56 },
  summaryLabel: { fontFamily: fonts.body, fontSize: 11, color: c.onSurfaceSecondary },
  summaryValue: { fontFamily: fonts.display, fontSize: 18, color: c.onSurface },
  todayCard: { borderRadius: 12, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary, padding: 12, gap: 8 },
  todayTitle: { fontFamily: fonts.bodySemi, fontSize: 12, letterSpacing: 2, color: c.onSurfaceSecondary },
  todayRow: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: 32 },
  todayApp: { flex: 1, fontFamily: fonts.bodyMedium, fontSize: 14, color: c.onSurface },
  todayStat: { flexDirection: "row", alignItems: "center", gap: 4, minWidth: 96 },
  todayValue: { fontFamily: fonts.display, fontSize: 20, color: c.onSurface },
  todayLabel: { fontFamily: fonts.body, fontSize: 12, color: c.onSurfaceSecondary },
  vDivider: { width: 1, alignSelf: "stretch", backgroundColor: c.border },
  schedulePill: { flexDirection: "row", alignItems: "center", gap: 8, minHeight: 44, paddingHorizontal: 12, borderRadius: 8, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  scheduleText: { flex: 1, fontFamily: fonts.bodyMedium, fontSize: 13, color: c.onSurfaceTertiary },
}));
