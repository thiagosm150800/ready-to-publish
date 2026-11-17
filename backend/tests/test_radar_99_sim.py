# Simulation (Python port) of RideAccessibilityService.kt 99 radar: findAllLabeled, isRadarScreen, radarScan, radarRefresh gating
import pytest
from test_ride_offer_parsing_sim import Node, offer_text, collect_texts, find_labeled, parse_number, PRICE_RE, KM_RE

NO_BUTTON = "Sem botão Aceitar na tela"
RADAR_BUTTONS = ["Escolher"]
HEADER = ["Escolha uma", "Km até o embarque"]
BODY = ["Escolher", "Ainda buscando", "Atualizar"]


def find_all_labeled(node, labels, out, depth=0):
    if node is None or depth > 40:
        return
    t = node.text if node.text is not None else node.desc
    if t is not None and any(t.strip().lower().startswith(l.lower()) for l in labels):
        out.append(node)
        return
    for c in node.children:
        find_all_labeled(c, labels, out, depth + 1)


def is_radar_screen(root):
    texts = []
    collect_texts(root, texts)
    def has(labels):
        return any(t.strip().lower().startswith(s.lower()) for t in texts for s in labels)
    return has(HEADER) and has(BODY)


class Radar:
    """Port of radarScan / radarRefresh state (radarSeen, lastRadarRefresh, radarHoldUntil)."""

    def __init__(self, app_cfg, cfg=None):
        self.app_cfg, self.cfg = app_cfg, cfg or {}
        self.seen, self.last_refresh, self.hold_until = {}, 0, 0
        self.clicked, self.events, self.refreshes, self.busy = [], [], [], None

    def scan(self, root, now):
        buttons = []
        find_all_labeled(root, RADAR_BUTTONS, buttons)
        if not buttons:
            return NO_BUTTON
        if now < self.hold_until:
            return "Radar: aguardando após escolher"
        if self.cfg.get("exclusive_enabled", True) and self.busy == "app99":
            return "Radar: corrida em andamento"
        self.seen = {k: v for k, v in self.seen.items() if now - v <= 600_000}
        result = "Oferta já avaliada"
        parsed = 0
        for b in buttons:
            pt, kt = offer_text(b, root)
            m = PRICE_RE.search(pt)
            price = parse_number(m.group(1)) if m else None
            if price is None:
                continue
            kms = [x for x in (parse_number(g) for g in KM_RE.findall(kt)) if x is not None]
            if not kms:
                continue
            pickup = kms[0] if len(kms) >= 2 else 0.0
            trip = kms[1] if len(kms) >= 2 else kms[0]
            if trip <= 0:
                continue
            parsed += 1
            sig = f"{price}|{trip}|{pickup}"
            if now - self.seen.get(sig, 0) < 120_000:
                continue
            self.seen[sig] = now
            ppk = round(price / trip * 100) / 100
            reasons = []
            if ppk < self.app_cfg.get("min_price_per_km", 0):
                reasons.append("R$/km abaixo do mínimo")
            if price < self.app_cfg.get("min_fare", 0):
                reasons.append("Valor abaixo do mínimo")
            if pickup > self.app_cfg.get("max_pickup_km", float("inf")):
                reasons.append("Busca muito longe")
            ok = not reasons
            if ok:
                self.clicked.append(b)
                self.hold_until = now + 8000
                if self.cfg.get("exclusive_enabled", True):
                    self.busy = "app99"
            self.events.append(dict(price=price, trip_km=trip, pickup_km=pickup, ppk=ppk, accepted=ok, reasons=reasons))
            if ok:
                return "Aceita"
            result = "Recusada: " + ", ".join(reasons)
        return "Botão Escolher achado, sem preço/km" if parsed == 0 else result

    def refresh(self, roots, now, in_schedule=True):
        a = self.app_cfg
        if not a.get("enabled") or not a.get("radar_enabled"):
            return "off"
        if not in_schedule:
            return "schedule"
        if self.cfg.get("exclusive_enabled", True) and self.busy:
            return "busy"
        if now < self.hold_until:
            return "hold"
        interval = min(30, max(2, a.get("radar_interval_s", 4))) * 1000
        if now - self.last_refresh < interval:
            return "wait"
        root = next((r for r in roots if is_radar_screen(r)), None)
        if root is None:
            return "not-radar-screen"
        if self.scan(root, now) == "Aceita":
            return "accepted"
        self.last_refresh = now
        btn = find_labeled(root, ["Atualizar"])
        self.refreshes.append("tap" if btn else "swipe")
        return "refreshed"


def card(price, ppk, pick, trip, addr1="Rua das Azaléias, 15, Parque Das Laranjeiras",
         addr2="Cartão de TODOS Umuarama, Avenida Ipiranga, 3670 - Zona I"):
    return Node(children=[Node("Pop"), Node(price), Node("100% dos ganhos"), Node(ppk),
                          Node("4,70 • 31 corridas • Cartão verif."), Node(pick), Node(addr1), Node(trip), Node(addr2),
                          Node("Escolher", clickable=True)])


def screen(*cards):
    lst = Node(children=[Node("Escolha uma"), Node("Km até o embarque"), *cards, Node("Isso é tudo por enquanto")])
    return Node(children=[Node("Solicitações"), lst])


def empty_screen():
    return Node(children=[Node("Solicitações"), Node("Escolha uma"), Node("Km até o embarque"),
                          Node("Ainda buscando solicitações"), Node("Aguarde ou veja o Mapa de Chamadas"),
                          Node("Mapa de Chamadas", clickable=True), Node("Atualizar", clickable=True)])


CFG = {"enabled": True, "radar_enabled": True, "radar_interval_s": 4, "min_price_per_km": 2.0, "min_fare": 8.0, "max_pickup_km": 4.0}


# Parsing of the screenshot-2 card
def test_screenshot_card_values():
    root = screen(card("R$10,80", "R$2,13/km", "(6 min 2,6 km)", "(5 min 2,5 km)"))
    r = Radar(CFG)
    assert r.scan(root, 1_000_000) == "Aceita"
    e = r.events[0]
    assert (e["price"], e["pickup_km"], e["trip_km"], e["ppk"]) == (10.8, 2.6, 2.5, 4.32)
    assert r.clicked[0].text == "Escolher"


# "R$2,13/km" never read as km; "Escolha uma" not taken as an Escolher button
def test_per_km_not_km_and_header_not_button():
    assert KM_RE.findall("R$2,13/km") == []
    out = []
    find_all_labeled(screen(card("R$10,80", "R$2,13/km", "(6 min 2,6 km)", "(5 min 2,5 km)")), RADAR_BUTTONS, out)
    assert len(out) == 1


# 2 cards: the first fails, the second passes -> second Escolher tapped, both logged
def test_two_cards_second_chosen():
    c1 = card("R$7,00", "R$1,00/km", "(9 min 6,0 km)", "(12 min 7,0 km)")
    c2 = card("R$10,80", "R$2,13/km", "(6 min 2,6 km)", "(5 min 2,5 km)")
    r = Radar(CFG)
    assert r.scan(screen(c1, c2), 1_000_000) == "Aceita"
    assert r.clicked == [c2.children[-1]]
    assert [e["accepted"] for e in r.events] == [False, True]
    assert r.events[0]["price"] == 7.0 and r.events[0]["trip_km"] == 7.0


# Same offer judged / logged once per 2 minutes
def test_dedup_two_minutes():
    c1 = card("R$7,00", "R$1,00/km", "(9 min 6,0 km)", "(12 min 7,0 km)")
    r = Radar(CFG)
    t = 1_000_000
    assert r.scan(screen(c1), t).startswith("Recusada")
    for dt in (4000, 60_000, 119_000):
        assert r.scan(screen(c1), t + dt) == "Oferta já avaliada"
    assert len(r.events) == 1
    assert r.scan(screen(c1), t + 121_000).startswith("Recusada")
    assert len(r.events) == 2


# Empty list: refresh taps "Atualizar"; with offers (no Atualizar) it swipes
def test_refresh_tap_vs_swipe_and_interval():
    r = Radar(CFG)
    assert r.refresh([empty_screen()], 10_000) == "refreshed" and r.refreshes == ["tap"]
    assert r.refresh([empty_screen()], 12_000) == "wait"
    c1 = card("R$7,00", "R$1,00/km", "(9 min 6,0 km)", "(12 min 7,0 km)")
    assert r.refresh([screen(c1)], 14_000) == "refreshed" and r.refreshes == ["tap", "swipe"]


# Gating: off / schedule / busy / hold / not on the radar screen
def test_refresh_gating():
    assert Radar({**CFG, "enabled": False}).refresh([empty_screen()], 1000010000) == "off"
    assert Radar({**CFG, "radar_enabled": False}).refresh([empty_screen()], 1000010000) == "off"
    assert Radar(CFG).refresh([empty_screen()], 1000010000, in_schedule=False) == "schedule"
    assert Radar(CFG).refresh([Node(children=[Node("Mapa"), Node("Você está online")])], 1000010000) == "not-radar-screen"
    r = Radar(CFG, {"exclusive_enabled": False})
    c2 = card("R$10,80", "R$2,13/km", "(6 min 2,6 km)", "(5 min 2,5 km)")
    assert r.refresh([screen(c2)], 1000010000) == "accepted"
    assert r.refresh([empty_screen()], 1000015000) == "hold"
    assert r.refresh([empty_screen()], 1000018500) == "refreshed"
    r2 = Radar(CFG)
    r2.refresh([screen(c2)], 1000010000)
    assert r2.refresh([empty_screen()], 1000030000) == "busy"


# Interval is clamped 2..30 like coerceIn
def test_interval_clamp():
    r = Radar({**CFG, "radar_interval_s": 100})
    r.refresh([empty_screen()], 100_000)
    assert r.refresh([empty_screen()], 129_000) == "wait"
    assert r.refresh([empty_screen()], 130_000) == "refreshed"


# RISK (documented): the event path (onAccessibilityEvent -> radarScan) does NOT check radarHoldUntil,
# so right after tapping Escolher on card A, an event with the list still visible can tap card B too.
def test_event_path_ignores_hold_double_accept():
    a = card("R$10,80", "R$2,13/km", "(6 min 2,6 km)", "(5 min 2,5 km)")
    b = card("R$12,00", "R$2,40/km", "(4 min 1,5 km)", "(10 min 5,0 km)")
    r = Radar(CFG)
    assert r.scan(screen(a, b), 1_000_000) == "Aceita"
    # next content-changed event 300ms later, both cards still listed (busy==app99 is not a block for app99 itself)
    second = r.scan(screen(a, b), 1_000_300)
    assert second == "Radar: aguardando após escolher"  # fixed: the hold blocks a second tap
    assert len(r.clicked) == 1


# RISK (documented): flat list (no per-card container) -> every Escolher reads the FIRST card's price
def test_flat_list_reads_first_card_for_all_buttons():
    lst = Node(children=[Node("Escolha uma"), Node("R$7,00"), Node("(9 min 6,0 km)"), Node("(12 min 7,0 km)"), Node("Escolher"),
                         Node("R$10,80"), Node("(6 min 2,6 km)"), Node("(5 min 2,5 km)"), Node("Escolher")])
    root = Node(children=[Node("Solicitações"), lst])
    r = Radar(CFG)
    res = r.scan(root, 1_000_000)
    assert res.startswith("Recusada")  # second card (passes) never tapped: both buttons read card 1
    assert len(r.events) == 1
