# Simulation (Python port) of RideAccessibilityService.kt targetRoots + onAccessibilityEvent dispatch (iteration 18: allowFallback, lastTextSample, kmFallback)
import pytest
from test_ride_offer_parsing_sim import Node, find_labeled, offer_text, KM_RE, PRICE_RE, collect_texts

NO_BUTTON = "Sem botão Aceitar na tela"
APP_KEYS = ["rapido", "moove"]
TYPE_WINDOWS_CHANGED = 4194304
TYPE_WINDOW_CONTENT_CHANGED = 2048


class Root(Node):
    def __init__(self, pkg, children=None):
        super().__init__(children=children)
        self.packageName = pkg


def target_roots(target, event_root, windows, active, allow_fallback=False):
    """Port of targetRoots(target, event, allowFallback = false). event_root = event.source.window.root."""
    if not target:
        return []
    out = []

    def add(r):
        if r is not None and all(x is not r for x in out):
            out.append(r)

    def matches(r):
        return r.packageName is not None and target in r.packageName.lower()

    if allow_fallback:
        add(event_root)
    for w in windows or []:
        if w is not None and matches(w):
            add(w)
    if active is not None and matches(active):
        add(active)
    if not out and allow_fallback:
        add(active)
    return out


def match_app(pkg_lower, apps):
    for k in APP_KEYS:
        t = (apps.get(k, {}).get("target_package") or "").strip().lower()
        if t and t in pkg_lower:
            return k
    return None


def dispatch_keys(pkg, event_type, apps):
    """Port of the keys when-expression in onAccessibilityEvent."""
    if pkg is not None:
        k = match_app(pkg.lower(), apps)
        return [k] if k else []
    if event_type == TYPE_WINDOWS_CHANGED:
        return list(APP_KEYS)
    return []


APPS = {"rapido": {"target_package": "rapido", "enabled": True}, "moove": {"target_package": "moove", "enabled": True}}


def moove_popup():
    btn = Node(children=[Node("Aceitar corrida (13)")], clickable=True)
    return Root("com.moove.motorista", [Node(children=[Node("R$ 9,60"), Node("Embarque - (4,66 km)"), Node("Destino - (2,76 km)"), btn])]), btn


def roots_for_event(key, pkg, event_root, windows, active, apps=APPS):
    """Port of onAccessibilityEvent line 81: targetRoots(target, event, allowFallback = pkg != null)."""
    target = (apps[key].get("target_package") or "").strip().lower()
    return target_roots(target, event_root, windows, active, allow_fallback=pkg is not None)


class TestTargetRoots:
    # Event from this app (pkg != null) -> old fallback behaviour kept
    def test_fallback_to_active_when_no_window_matches(self):
        active = Root("com.whatever.launcher")
        other = Root("com.android.systemui")
        assert target_roots("moove", None, [other, active], active, allow_fallback=True) == [active]

    def test_fallback_when_windows_list_empty(self):
        active = Root("br.app.driver")
        assert target_roots("moove", None, [], active, allow_fallback=True) == [active]

    def test_overlay_event_window_included_even_if_not_active(self):
        overlay, _ = moove_popup()
        active_map = Root("com.google.android.apps.maps")
        roots = target_roots("moove", overlay, [active_map], active_map, allow_fallback=True)
        assert roots == [overlay]  # active non-moove window not added because a match exists

    def test_all_moove_windows_plus_event_root_dedup(self):
        overlay, _ = moove_popup()
        main = Root("com.moove.motorista")
        roots = target_roots("moove", overlay, [main, overlay], main, allow_fallback=True)
        assert roots == [overlay, main]

    # No fallback (package-less event / retry): only windows whose package contains the target
    def test_no_fallback_ignores_foreign_active_and_event_root(self):
        foreign = Root("com.whatsapp")
        assert target_roots("moove", foreign, [foreign], foreign) == []

    def test_no_fallback_still_returns_matching_windows(self):
        overlay, _ = moove_popup()
        main = Root("com.moove.motorista")
        assert target_roots("moove", None, [Root("launcher"), main, overlay], main) == [main, overlay]

    def test_default_param_is_no_fallback(self):
        active = Root("com.whatever.launcher")
        assert target_roots("moove", None, [], active) == []

    def test_empty_target_returns_empty(self):
        assert target_roots("", Root("x"), [Root("x")], Root("x"), allow_fallback=True) == []

    def test_no_active_no_windows_returns_empty(self):
        assert target_roots("moove", None, [], None, allow_fallback=True) == []

    def test_retry_null_event_uses_windows(self):
        overlay, _ = moove_popup()
        assert target_roots("moove", None, [Root("launcher"), overlay], Root("launcher")) == [overlay]

    def test_retry_has_no_active_fallback(self):
        # retryIfStillShown calls targetRoots(target, null) -> allowFallback=false. When no window reports
        # the Moove package (the case the old fallback covered) the 700 ms retry tap finds nothing.
        active = Root("br.app.driver")
        assert target_roots("moove", None, [], active) == []

    def test_button_found_in_overlay_root(self):
        overlay, btn = moove_popup()
        roots = target_roots("moove", overlay, [], Root("launcher"), allow_fallback=True)
        assert find_labeled(roots[0], ["Aceitar", "Accept"]) is btn.children[0]


class TestDispatch:
    def test_moove_event_pkg_matches(self):
        assert dispatch_keys("com.moove.motorista", TYPE_WINDOW_CONTENT_CHANGED, APPS) == ["moove"]

    def test_null_pkg_content_changed_dropped(self):
        assert dispatch_keys(None, TYPE_WINDOW_CONTENT_CHANGED, APPS) == []

    def test_pkg_without_target_substring_dropped(self):
        # If the real Moove Motorista package does not contain the target_package text, all events are dropped
        assert dispatch_keys("br.com.gaudium.driver", TYPE_WINDOW_CONTENT_CHANGED, APPS) == []

    def test_FIXED_windows_changed_rapido_key_no_longer_reads_moove_screen(self):
        # Null-package TYPE_WINDOWS_CHANGED -> both keys; 'rapido' gets no root (status 'Nenhuma janela lida'),
        # so the Moove offer is never judged/saved as rapidocar.
        overlay, _ = moove_popup()
        keys = dispatch_keys(None, TYPE_WINDOWS_CHANGED, APPS)
        assert keys == ["rapido", "moove"]
        assert roots_for_event("rapido", None, None, [overlay], overlay) == []
        assert roots_for_event("moove", None, None, [overlay], overlay) == [overlay]

    def test_FIXED_windows_changed_foreign_app_not_tapped(self):
        # Package-less event while WhatsApp is active: neither key reads WhatsApp's "Aceitar".
        wa = Root("com.whatsapp", [Node("Aceitar", clickable=True)])
        for k in dispatch_keys(None, TYPE_WINDOWS_CHANGED, APPS):
            assert roots_for_event(k, None, wa, [wa], wa) == []

    def test_moove_event_with_unreported_window_pkg_uses_active(self):
        # Moove event but the window root reports no package -> old fallback still applies
        btn = Node(children=[Node("Aceitar corrida (13)")], clickable=True)
        active = Root(None, [Node(children=[Node("R$ 9,60"), Node("4,66 km"), Node("2,76 km"), btn])])
        assert roots_for_event("moove", "com.moove.motorista", None, [active], active) == [active]


def simulate_text_samples(step_ms, duration_ms, last_text_sample=0):
    """Port of lines 70 (saveDiag(false)), 96-97 (lastTextSample >= 1500) and saveDiag throttle."""
    last_diag_save = 0
    collected = []
    for now in range(10_000, 10_000 + duration_ms, step_ms):
        if now - last_diag_save >= 1000:  # saveDiag(false) at line 70
            last_diag_save = now
        if now - last_text_sample >= 1500:  # line 96 - own timestamp
            last_text_sample = now
            collected.append(now)
    return collected


class TestDiagThrottle:
    def test_FIXED_texts_collected(self):
        collected = simulate_text_samples(137, 20_000)
        assert len(collected) >= 12  # ~ one sample per 1.5 s over 20 s
        assert all(b - a >= 1500 for a, b in zip(collected, collected[1:]))

    def test_texts_on_first_event(self):
        assert simulate_text_samples(137, 200)[0] == 10_000


class TestOfferScopeEdge:
    def test_FIXED_per_km_price_in_parent_takes_km_fallback(self):
        # price+button in a sub-card, km + "R$ x/km" in parent -> loop breaks but km comes from the parent
        btn = Node("Aceitar", clickable=True)
        sub = Node(children=[Node("R$ 12,50"), btn])
        Node(children=[sub, Node("R$ 2,05/km"), Node("1,2 km"), Node("6,1 km")])
        price_text, km_text = offer_text(btn, sub.parent)
        assert PRICE_RE.search(price_text).group(1) == "12,50"
        assert KM_RE.findall(km_text) == ["1,2", "6,1"]

    def test_card_km_kept_over_parent_km(self):
        # card already had 1 km -> parent with more prices does not override it
        btn = Node("Aceitar", clickable=True)
        sub = Node(children=[Node("R$ 12,50"), Node("3,0 km"), btn])
        Node(children=[sub, Node("R$ 15,00"), Node("8 km"), Node("9 km")])
        _, km_text = offer_text(btn, sub.parent)
        assert KM_RE.findall(km_text) == ["3,0"]

    def test_parent_with_more_prices_and_no_km_still_sem_km(self):
        btn = Node("Aceitar", clickable=True)
        sub = Node(children=[Node("R$ 12,50"), btn])
        Node(children=[sub, Node("R$ 15,00")])
        _, km_text = offer_text(btn, sub.parent)
        assert KM_RE.findall(km_text) == []
