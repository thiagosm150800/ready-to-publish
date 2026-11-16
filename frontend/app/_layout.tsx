import { QueryClientProvider } from "@tanstack/react-query";
import { useFonts } from "expo-font";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { ActivityIndicator, LogBox, StyleSheet, View } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { KeyboardProvider } from "react-native-keyboard-controller";

import { AuthProvider, useAuth } from "@/src/auth";
import { ErrorBoundary } from "@/src/components/error-boundary";
import { fontAssets } from "@/src/fonts";
import { queryClient } from "@/src/query-client";
import { colors } from "@/src/theme";

LogBox.ignoreAllLogs(true);

function AppStack() {
  const { ready, token } = useAuth();

  if (!ready) {
    return (
      <View style={[styles.root, styles.center]}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }
  // Protected groups unmount the whole signed-in stack on logout, so no stale screens remain.
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surface } }}>
      <Stack.Protected guard={!!token} redirectTo="/login">
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="aprender" />
        <Stack.Screen name="conta" />
        <Stack.Screen name="aviso" />
      </Stack.Protected>
      <Stack.Protected guard={!token} redirectTo="/">
        <Stack.Screen name="login" />
      </Stack.Protected>
      {/* Owner-only area, protected by the admin password on the server */}
      <Stack.Screen name="admin" />
    </Stack>
  );
}

export default function RootLayout() {
  const [loaded] = useFonts(fontAssets);

  return (
    <GestureHandlerRootView style={styles.root}>
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <KeyboardProvider>
            <StatusBar style="light" />
            {loaded ? (
              <AuthProvider>
                <AppStack />
              </AuthProvider>
            ) : (
              <View style={styles.root} />
            )}
          </KeyboardProvider>
        </QueryClientProvider>
      </ErrorBoundary>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
});
