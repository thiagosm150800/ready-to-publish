import { Image } from "expo-image";
import { useState } from "react";
import { FlatList, Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { APP_KEYS, APP_LABELS, brl, num, Ride, RideAppFilter, RideStatus, useRides } from "@/src/api";
import { ScreenHeader } from "@/src/components/ScreenHeader";
import { ErrorState, LoadingState } from "@/src/components/StateViews";
import { fonts } from "@/src/fonts";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, useTheme } from "@/src/theme";

const EMPTY_IMG =
  "https://images.unsplash.com/photo-1506426305266-2b7e740fd828?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85&w=800";

const FILTERS: { key: RideStatus; label: string }[] = [
  { key: "all", label: "Todas" },
  { key: "accepted", label: "Aceitas" },
  { key: "rejected", label: "Recusadas" },
];

function formatTime(iso: string) {
  const d = new Date(iso);
  return `${d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })} ${d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
}

export default function Historico() {
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const { colors } = useTheme();
  const styles = useStyles();
  const [status, setStatus] = useState<RideStatus>("all");
  const [app, setApp] = useState<RideAppFilter>("all");
  const rides = useRides(status, app);

  return (
    <View style={styles.screen} testID="historico-screen">
      <ScreenHeader title="Histórico" subtitle="Ofertas lidas e decisões tomadas" />
      <View style={styles.chipRow}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipContent}>
          {APP_KEYS.map((k) => {
            const active = app === k;
            return (
              <Pressable
                key={k}
                testID={`history-app-${k}`}
                onPress={() => setApp(active ? "all" : k)}
                hitSlop={{ top: 6, bottom: 6 }}
                style={[styles.chip, active && styles.chipActive]}
              >
                <Text style={[styles.chipText, active && styles.chipTextActive]}>{APP_LABELS[k]}</Text>
              </Pressable>
            );
          })}
          <View style={styles.chipDivider} />
          {FILTERS.map((f) => {
            const active = f.key === status;
            return (
              <Pressable
                key={f.key}
                testID={`history-filter-${f.key}`}
                onPress={() => setStatus(f.key)}
                hitSlop={{ top: 6, bottom: 6 }}
                style={[styles.chip, active && styles.chipActive]}
              >
                <Text style={[styles.chipText, active && styles.chipTextActive]}>{f.label}</Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>

      {rides.isLoading ? (
        <LoadingState label="Carregando histórico..." />
      ) : rides.isError ? (
        <ErrorState onRetry={() => rides.refetch()} />
      ) : (
        <FlatList
          data={rides.data}
          keyExtractor={(r) => r.id}
          contentContainerStyle={[styles.list, { paddingBottom: bottomChrome + 24 }, !rides.data?.length && { flexGrow: 1 }]}
          refreshControl={<RefreshControl refreshing={rides.isRefetching} onRefresh={() => { rides.refetch(); }} tintColor={colors.brandPrimary} />}
          ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
          renderItem={({ item }) => <RideRow ride={item} />}
          ListEmptyComponent={
            <View style={styles.empty} testID="history-empty">
              <Image source={{ uri: EMPTY_IMG }} style={styles.emptyImg} contentFit="cover" />
              <Text style={styles.emptyText}>Nenhuma corrida registrada ainda.</Text>
            </View>
          }
        />
      )}
    </View>
  );
}

function RideRow({ ride }: { ride: Ride }) {
  const { colors } = useTheme();
  const styles = useStyles();
  const tone = ride.accepted ? colors.success : colors.error;
  return (
    <View style={[styles.row, { borderLeftColor: tone }]} testID={`ride-row-${ride.id}`}>
      <View style={styles.rowTop}>
        <Text style={styles.rowPrice}>{brl(ride.price)}</Text>
        <Text style={[styles.rowStatus, { color: tone }]}>{ride.accepted ? "ACEITA" : "RECUSADA"}</Text>
      </View>
      <View style={styles.rowMeta}>
        <Text style={styles.meta}>{brl(ride.price_per_km)}/km</Text>
        <Text style={styles.metaDot}>·</Text>
        <Text style={styles.meta}>{num(ride.trip_km)} km</Text>
        <Text style={styles.metaDot}>·</Text>
        <Text style={styles.meta}>busca {num(ride.pickup_km)} km</Text>
      </View>
      <View style={styles.rowBottom}>
        <View style={styles.tags}>
          <View style={styles.tag}><Text style={styles.tagText}>{APP_LABELS[ride.app] ?? "RapidoCar"}</Text></View>
          {ride.reasons.map((r) => (
            <View key={r} style={styles.tag}><Text style={styles.tagText}>{r}</Text></View>
          ))}
        </View>
        <Text style={styles.time}>{formatTime(ride.created_at)}</Text>
      </View>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  chipRow: { height: 56, justifyContent: "center", borderBottomWidth: 1, borderBottomColor: c.divider },
  chipContent: { gap: 8, paddingHorizontal: 16, alignItems: "center" },
  chip: { height: 36, paddingHorizontal: 16, borderRadius: 999, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary, justifyContent: "center", flexShrink: 0 },
  chipActive: { backgroundColor: c.brandPrimary, borderColor: c.brandPrimary },
  chipText: { fontFamily: fonts.bodyMedium, fontSize: 14, color: c.onSurfaceSecondary },
  chipTextActive: { color: c.onBrandPrimary },
  chipDivider: { width: 1, height: 24, backgroundColor: c.border, flexShrink: 0 },
  list: { padding: 16 },
  row: { backgroundColor: c.surfaceSecondary, borderRadius: 8, borderLeftWidth: 4, padding: 12, gap: 6 },
  rowTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  rowPrice: { fontFamily: fonts.display, fontSize: 26, color: c.onSurface, lineHeight: 30 },
  rowStatus: { fontFamily: fonts.bodySemi, fontSize: 12, letterSpacing: 1.5 },
  rowMeta: { flexDirection: "row", alignItems: "center", gap: 6 },
  meta: { fontFamily: fonts.displaySemi, fontSize: 16, color: c.onSurfaceTertiary },
  metaDot: { color: c.muted },
  rowBottom: { flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", gap: 8 },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: 6, flex: 1 },
  tag: { backgroundColor: c.brandTertiary, borderRadius: 4, paddingHorizontal: 8, paddingVertical: 2 },
  tagText: { fontFamily: fonts.bodyMedium, fontSize: 11, color: c.onBrandTertiary },
  time: { fontFamily: fonts.body, fontSize: 11, color: c.muted },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", gap: 16, padding: 24 },
  emptyImg: { width: 220, height: 140, borderRadius: 12, opacity: 0.7 },
  emptyText: { fontFamily: fonts.bodyMedium, fontSize: 15, color: c.onSurfaceSecondary },
}));
