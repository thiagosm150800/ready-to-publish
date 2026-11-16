import { Ionicons } from "@react-native-vector-icons/ionicons";
import { Tabs } from "expo-router";
import { NativeTabs } from "expo-router/native-tabs";
import { Platform } from "react-native";

import { fonts } from "@/src/fonts";
import { usesNativeTabs } from "@/src/navigation";
import { useTheme } from "@/src/theme";

type IconName = React.ComponentProps<typeof Ionicons>["name"];

const TABS: { name: string; label: string; icon: IconName; sf: string }[] = [
  { name: "index", label: "Painel", icon: "speedometer", sf: "gauge.with.dots.needle.67percent" },
  { name: "filtros", label: "Filtros", icon: "options", sf: "slider.horizontal.3" },
  { name: "historico", label: "Histórico", icon: "time", sf: "clock.fill" },
];

export default function TabsLayout() {
  const { colors } = useTheme();

  if (usesNativeTabs) {
    return (
      <NativeTabs tintColor={colors.brandPrimary}>
        {TABS.map((t) => (
          <NativeTabs.Trigger key={t.name} name={t.name}>
            <NativeTabs.Trigger.Icon sf={t.sf as any} />
            <NativeTabs.Trigger.Label>{t.label}</NativeTabs.Trigger.Label>
          </NativeTabs.Trigger>
        ))}
      </NativeTabs>
    );
  }

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surfaceSecondary,
          borderTopColor: colors.border,
          ...(Platform.OS === "web" ? { height: 64 } : {}),
        },
        tabBarItemStyle: { alignSelf: "center" },
        tabBarLabelStyle: { fontFamily: fonts.bodyMedium, fontSize: 11 },
        sceneStyle: { backgroundColor: colors.surface },
      }}
    >
      {TABS.map((t) => (
        <Tabs.Screen
          key={t.name}
          name={t.name}
          options={{
            title: t.label,
            tabBarButtonTestID: `tab-${t.name}`,
            tabBarIcon: ({ color, size }) => <Ionicons name={t.icon} color={color} size={size} />,
          }}
        />
      ))}
    </Tabs>
  );
}
