import { Ionicons } from "@react-native-vector-icons/ionicons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, RefreshControl, ScrollView, Text, TextInput, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import Animated, { FadeInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { AdminUser, AdminUserUpdate, AdminUsers, adminDeleteUser, adminListUsers, adminLogin, adminUpdateUser, UserStatus } from "@/src/api";
import { fonts } from "@/src/fonts";
import { makeStyles, useTheme } from "@/src/theme";

type Filter = "pending" | "approved" | "expired" | "blocked" | "all";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "pending", label: "Pendentes" },
  { key: "approved", label: "Liberados" },
  { key: "expired", label: "Vencidos" },
  { key: "blocked", label: "Bloqueados" },
  { key: "all", label: "Todos" },
];
const GRANTS = [
  { days: 7, label: "7 dias" },
  { days: 15, label: "15 dias" },
  { days: 30, label: "30 dias" },
  { days: 0, label: "Sem prazo" },
];
const STATUS_LABEL: Record<UserStatus, string> = { pending: "Pendente", approved: "Liberado", blocked: "Bloqueado" };

function fmt(iso: string | null) {
  if (!iso) return "-";
  const d = new Date(iso);
  return `${d.toLocaleDateString("pt-BR")} ${d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
}

export default function Admin() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { colors } = useTheme();
  const styles = useStyles();
  // Admin token lives only in memory: leaving this screen logs the admin out.
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loggingIn, setLoggingIn] = useState(false);
  const [filter, setFilter] = useState<Filter>("pending");
  const [data, setData] = useState<AdminUsers | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      setData(await adminListUsers(token, filter));
    } catch (e) {
      const err = e as Error & { status?: number };
      if (err.status === 401) setToken(null);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token, filter]);

  useEffect(() => {
    load();
  }, [load]);

  const login = async () => {
    setLoginError(null);
    if (!password) return setLoginError("Digite a senha.");
    setLoggingIn(true);
    try {
      const r = await adminLogin(password);
      setToken(r.access_token);
      setPassword("");
    } catch (e) {
      setLoginError(e instanceof Error ? e.message : "Erro ao entrar.");
    } finally {
      setLoggingIn(false);
    }
  };

  const act = async (u: AdminUser, body: AdminUserUpdate) => {
    if (!token) return;
    setBusyId(u.id);
    try {
      await adminUpdateUser(token, u.id, body);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro");
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (u: AdminUser) => {
    if (!token) return;
    setBusyId(u.id);
    try {
      await adminDeleteUser(token, u.id);
      setConfirmDelete(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro");
    } finally {
      setBusyId(null);
    }
  };

  const header = (
    <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
      <Pressable testID="admin-back-button" onPress={() => router.back()} style={styles.iconBtn} hitSlop={8}>
        <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
      </Pressable>
      <Text style={styles.title}>Administrador</Text>
      {token ? (
        <Pressable testID="admin-logout-button" onPress={() => setToken(null)} style={styles.iconBtn} hitSlop={8}>
          <Ionicons name="log-out-outline" size={22} color={colors.onSurfaceSecondary} />
        </Pressable>
      ) : null}
    </View>
  );

  if (!token) {
    return (
      <View style={styles.screen} testID="admin-login-screen">
        {header}
        <KeyboardAwareScrollView bottomOffset={24} keyboardShouldPersistTaps="handled" contentContainerStyle={[styles.loginContent, { paddingBottom: insets.bottom + 24 }]}>
          <View style={styles.lockIcon}>
            <Ionicons name="shield-checkmark" size={32} color={colors.brandPrimary} />
          </View>
          <Text style={styles.lead}>Área exclusiva do responsável. Libere ou bloqueie o acesso dos motoristas pelo CPF.</Text>
          <Text style={styles.label}>Senha do administrador</Text>
          <View style={styles.passRow}>
            <TextInput
              testID="admin-password-input"
              value={password}
              onChangeText={setPassword}
              secureTextEntry={!showPass}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="Senha"
              placeholderTextColor={colors.muted}
              style={styles.passInput}
              onSubmitEditing={login}
            />
            <Pressable testID="admin-toggle-password" onPress={() => setShowPass((v) => !v)} style={styles.eye}>
              <Ionicons name={showPass ? "eye-off" : "eye"} size={20} color={colors.onSurfaceSecondary} />
            </Pressable>
          </View>
          {loginError ? <Text style={styles.error} testID="admin-login-error">{loginError}</Text> : null}
          <Pressable testID="admin-login-button" onPress={login} disabled={loggingIn} style={styles.primary}>
            {loggingIn ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.primaryText}>Entrar</Text>}
          </Pressable>
        </KeyboardAwareScrollView>
      </View>
    );
  }

  return (
    <View style={styles.screen} testID="admin-screen">
      {header}
      <View style={styles.chipRow}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipContent}>
          {FILTERS.map((f) => {
            const active = f.key === filter;
            const count = f.key !== "all" && data ? data.counts[f.key] : null;
            return (
              <Pressable key={f.key} testID={`admin-filter-${f.key}`} onPress={() => setFilter(f.key)} style={[styles.chip, active && styles.chipActive]}>
                <Text style={[styles.chipText, active && styles.chipTextActive]}>
                  {f.label}
                  {count !== null ? ` (${count})` : ""}
                </Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>
      {error ? <Text style={[styles.error, { paddingHorizontal: 16, paddingTop: 8 }]} testID="admin-error">{error}</Text> : null}
      <Text style={styles.webHint} testID="admin-web-url" selectable>
        No computador: {process.env.EXPO_PUBLIC_BACKEND_URL}/api/painel
      </Text>
      <FlatList
        data={data?.users ?? []}
        keyExtractor={(u) => u.id}
        contentContainerStyle={[styles.list, { paddingBottom: insets.bottom + 24 }]}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={colors.brandPrimary} />}
        ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
        ListEmptyComponent={
          loading ? undefined : (
            <View style={styles.empty} testID="admin-empty">
              <Ionicons name="people-outline" size={40} color={colors.muted} />
              <Text style={styles.emptyText}>Nenhum motorista nesta lista.</Text>
            </View>
          )
        }
        renderItem={({ item: u }) => (
          <UserCard
            user={u}
            busy={busyId === u.id}
            confirmingDelete={confirmDelete === u.id}
            onGrant={(days) => act(u, { access_days: days })}
            onTrial={() => act(u, { trial: true })}
            onResetDevice={() => act(u, { reset_device: true })}
            onBlock={() => act(u, { status: "blocked" })}
            onRename={(name) => act(u, { name })}
            onAskDelete={() => setConfirmDelete(confirmDelete === u.id ? null : u.id)}
            onDelete={() => remove(u)}
          />
        )}
      />
    </View>
  );
}

function UserCard(props: {
  user: AdminUser;
  busy: boolean;
  confirmingDelete: boolean;
  onGrant: (days: number) => void;
  onTrial: () => void;
  onResetDevice: () => void;
  onBlock: () => void;
  onRename: (name: string) => void;
  onAskDelete: () => void;
  onDelete: () => void;
}) {
  const { colors } = useTheme();
  const styles = useStyles();
  const u = props.user;
  const [name, setName] = useState(u.name);
  const tone = u.status === "approved" && !u.expired ? colors.success : u.status === "pending" ? colors.warning : colors.error;
  const statusLabel = u.status === "approved" && u.expired ? "Vencido" : STATUS_LABEL[u.status];
  const validity =
    u.status !== "approved" ? null : u.expires_at ? `${u.expired ? "Venceu em" : "Vence em"} ${fmt(u.expires_at)}` : "Sem prazo de vencimento";
  const renew = u.status === "approved" && !u.expired;

  return (
    <Animated.View entering={FadeInDown} style={[styles.card, { borderLeftColor: tone }]} testID={`admin-user-${u.id}`}>
      <View style={styles.cardTop}>
        <Text style={styles.cpf} testID={`admin-user-cpf-${u.id}`}>{u.cpf}</Text>
        <Text style={[styles.status, { color: tone }]} testID={`admin-user-status-${u.id}`}>{statusLabel}</Text>
      </View>
      <TextInput
        testID={`admin-user-name-${u.id}`}
        value={name}
        onChangeText={setName}
        onEndEditing={() => name.trim() !== u.name && props.onRename(name)}
        placeholder="Nome do motorista (opcional)"
        placeholderTextColor={colors.muted}
        style={styles.nameInput}
      />
      <Text style={styles.meta}>Pedido em {fmt(u.created_at)} · Último acesso {fmt(u.last_login_at)}</Text>
      {validity ? (
        <Text style={[styles.validity, { color: tone }]} testID={`admin-user-validity-${u.id}`}>{validity}</Text>
      ) : null}
      <View style={styles.deviceRow}>
        <Ionicons name="phone-portrait-outline" size={16} color={u.has_device ? colors.onSurfaceSecondary : colors.muted} />
        <Text style={styles.deviceText} testID={`admin-user-device-${u.id}`}>
          {u.has_device ? `Aparelho vinculado em ${fmt(u.device_bound_at)}` : "Nenhum aparelho vinculado (o próximo a entrar fica vinculado)"}
        </Text>
        {u.has_device ? (
          <Pressable testID={`admin-reset-device-${u.id}`} disabled={props.busy} onPress={props.onResetDevice} style={styles.deviceBtn}>
            <Text style={styles.deviceBtnText}>Trocar aparelho</Text>
          </Pressable>
        ) : null}
      </View>
      {u.trial_used ? (
        <Text style={styles.meta} testID={`admin-trial-used-${u.id}`}>Teste de 1 dia já usado em {fmt(u.trial_at ?? null)}</Text>
      ) : u.status === "pending" || (u.status === "approved" && u.expired) ? (
        <Pressable
          testID={`admin-trial-${u.id}`}
          disabled={props.busy}
          onPress={props.onTrial}
          style={[styles.trialBtn, { borderColor: colors.brandPrimary }]}
        >
          <Ionicons name="time-outline" size={18} color={colors.brandPrimary} />
          <Text style={[styles.grantText, { color: colors.brandPrimary }]}>Liberar teste de 1 dia (só uma vez)</Text>
        </Pressable>
      ) : null}
      <Text style={styles.grantLabel}>{renew ? "Renovar a partir de hoje:" : "Liberar por:"}</Text>
      <View style={styles.grantRow}>
        {GRANTS.map((g) => (
          <Pressable
            key={g.days}
            testID={`admin-grant-${g.days}-${u.id}`}
            disabled={props.busy}
            onPress={() => props.onGrant(g.days)}
            style={[styles.grantBtn, { backgroundColor: renew ? colors.surface : colors.success, borderColor: renew ? colors.border : colors.success }]}
          >
            <Text style={[styles.grantText, { color: renew ? colors.onSurface : colors.onSuccess }]}>{g.label}</Text>
          </Pressable>
        ))}
      </View>
      <View style={styles.actions}>
        {u.status !== "blocked" ? (
          <Pressable testID={`admin-block-${u.id}`} disabled={props.busy} onPress={props.onBlock} style={[styles.actBtn, { backgroundColor: colors.surfaceTertiary }]}>
            <Text style={[styles.actText, { color: colors.onSurface }]}>Bloquear</Text>
          </Pressable>
        ) : null}
        <Pressable testID={`admin-delete-${u.id}`} disabled={props.busy} onPress={props.onAskDelete} style={styles.trashBtn}>
          <Ionicons name="trash-outline" size={20} color={colors.error} />
        </Pressable>
        {props.busy ? <ActivityIndicator color={colors.brandPrimary} /> : null}
      </View>
      {props.confirmingDelete ? (
        <View style={styles.confirm}>
          <Text style={styles.confirmText}>Excluir este CPF e todos os dados dele?</Text>
          <Pressable testID={`admin-confirm-delete-${u.id}`} onPress={props.onDelete} style={[styles.actBtn, { backgroundColor: colors.error }]}>
            <Text style={[styles.actText, { color: colors.onError }]}>Excluir</Text>
          </Pressable>
        </View>
      ) : null}
    </Animated.View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingBottom: 8, borderBottomWidth: 1, borderBottomColor: c.divider },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  title: { flex: 1, fontFamily: fonts.display, fontSize: 28, color: c.onSurface },
  loginContent: { padding: 24, gap: 12 },
  lockIcon: { width: 64, height: 64, borderRadius: 32, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  lead: { fontFamily: fonts.body, fontSize: 15, color: c.onSurfaceSecondary, marginBottom: 8 },
  label: { fontFamily: fonts.bodyMedium, fontSize: 13, color: c.onSurfaceTertiary },
  passRow: { flexDirection: "row", alignItems: "center", borderRadius: 8, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary },
  passInput: { flex: 1, height: 52, paddingHorizontal: 14, color: c.onSurface, fontFamily: fonts.body, fontSize: 16 },
  eye: { width: 48, height: 52, alignItems: "center", justifyContent: "center" },
  error: { fontFamily: fonts.bodyMedium, fontSize: 14, color: c.error },
  primary: { height: 56, borderRadius: 12, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center", marginTop: 8 },
  primaryText: { fontFamily: fonts.bodySemi, fontSize: 16, color: c.onBrandPrimary },
  chipRow: { height: 56, justifyContent: "center", borderBottomWidth: 1, borderBottomColor: c.divider },
  chipContent: { gap: 8, paddingHorizontal: 16, alignItems: "center" },
  chip: { height: 36, paddingHorizontal: 16, borderRadius: 999, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary, justifyContent: "center", flexShrink: 0 },
  chipActive: { backgroundColor: c.brandPrimary, borderColor: c.brandPrimary },
  chipText: { fontFamily: fonts.bodyMedium, fontSize: 14, color: c.onSurfaceSecondary },
  chipTextActive: { color: c.onBrandPrimary },
  list: { padding: 16, flexGrow: 1 },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: 8, borderLeftWidth: 4, padding: 12, gap: 8 },
  cardTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  cpf: { fontFamily: fonts.display, fontSize: 24, color: c.onSurface },
  status: { fontFamily: fonts.bodySemi, fontSize: 12, letterSpacing: 1 },
  nameInput: { height: 44, borderRadius: 8, backgroundColor: c.surface, borderWidth: 1, borderColor: c.border, paddingHorizontal: 12, color: c.onSurface, fontFamily: fonts.body, fontSize: 14 },
  meta: { fontFamily: fonts.body, fontSize: 11, color: c.muted },
  actions: { flexDirection: "row", alignItems: "center", gap: 8 },
  validity: { fontFamily: fonts.bodySemi, fontSize: 13 },
  deviceRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  deviceText: { flex: 1, fontFamily: fonts.body, fontSize: 12, color: c.onSurfaceSecondary },
  deviceBtn: { height: 36, paddingHorizontal: 12, borderRadius: 8, borderWidth: 1, borderColor: c.border, justifyContent: "center" },
  deviceBtnText: { fontFamily: fonts.bodySemi, fontSize: 12, color: c.onSurface },
  grantLabel: { fontFamily: fonts.bodyMedium, fontSize: 12, color: c.onSurfaceTertiary },
  grantRow: { flexDirection: "row", gap: 6 },
  grantBtn: { flex: 1, height: 44, borderRadius: 8, borderWidth: 1, alignItems: "center", justifyContent: "center" },
  grantText: { fontFamily: fonts.bodySemi, fontSize: 13 },
  trialBtn: { height: 44, borderRadius: 8, borderWidth: 1, flexDirection: "row", gap: 8, alignItems: "center", justifyContent: "center" },
  webHint: { fontFamily: fonts.body, fontSize: 12, color: c.muted, paddingHorizontal: 16, paddingTop: 8 },
  actBtn: { height: 44, paddingHorizontal: 16, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  actText: { fontFamily: fonts.bodySemi, fontSize: 14 },
  trashBtn: { width: 44, height: 44, borderRadius: 8, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: c.border },
  confirm: { flexDirection: "row", alignItems: "center", gap: 8, padding: 8, borderRadius: 8, backgroundColor: c.errorTint },
  confirmText: { flex: 1, fontFamily: fonts.body, fontSize: 13, color: c.onSurfaceTertiary },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12, padding: 24 },
  emptyText: { fontFamily: fonts.body, fontSize: 14, color: c.onSurfaceSecondary },
}));
