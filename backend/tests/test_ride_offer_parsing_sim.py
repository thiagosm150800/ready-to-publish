# Simulation (Python port) of RideAccessibilityService.kt offer parsing / scoping / button matching
import re
import pytest

# Iteration 18: port of the NBSP-aware Kotlin patterns. re.ASCII mimics java.util.regex defaults
# (\s, \d, \w ASCII-only), so NBSP behaviour matches the JVM instead of Python's Unicode \s.
PRICE_RE = re.compile(r"R\$[\s\u00A0\u202F]*(\d{1,3}(?:\.\d{3})*,\d{1,2}|\d+(?:[.,]\d{1,2})?)", re.ASCII)
KM_RE = re.compile(r"(\d+(?:[.,]\d+)?)[\s\u00A0\u202F]*km\b", re.IGNORECASE | re.ASCII)
# Pre-iteration-18 patterns with JVM-like (ASCII) \s, kept to show the NBSP defect that was fixed.
OLD_PRICE_RE = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*,\d{1,2}|\d+(?:[.,]\d{1,2})?)", re.ASCII)
OLD_KM_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*km\b", re.IGNORECASE | re.ASCII)


class Node:
    def __init__(self, text=None, desc=None, children=None, clickable=False, bounds=(0, 0, 100, 50)):
        self.text, self.desc, self.clickable, self.bounds = text, desc, clickable, bounds
        self.children = children or []
        self.parent = None
        for c in self.children:
            c.parent = self


def parse_number(raw):
    s = raw.strip()
    n = s.replace(".", "").replace(",", ".") if "," in s else s
    try:
        return float(n)
    except ValueError:
        return None


def collect_texts(node, out, depth=0):
    if node is None or depth > 40:
        return
    for t in (node.text, node.desc):
        if t and t.strip():
            out.append(t)
    for c in node.children:
        collect_texts(c, out, depth + 1)


def find_labeled(node, labels):
    if node is None:
        return None
    t = node.text if node.text is not None else node.desc
    if t is not None:
        t = t.strip()
        if any(t.lower() == l.lower() or t.lower().startswith(l.lower()) for l in labels):
            return node
    for c in node.children:
        f = find_labeled(c, labels)
        if f:
            return f
    return None


def offer_text(button, root):
    """Port of Kotlin offerText -> (price_text, km_text)."""
    price_text = None
    price_count = 0
    km_fallback = None
    scope = button.parent
    while scope is not None:
        texts = []
        collect_texts(scope, texts)
        a = " | ".join(texts)
        if price_text is None and PRICE_RE.search(a):
            price_text = a
            price_count = len(PRICE_RE.findall(a))
        if price_text is not None:
            if len(PRICE_RE.findall(a)) > price_count:
                # iteration 18 (kmFallback): take km from this larger level if none found yet
                if km_fallback is None and KM_RE.search(a):
                    km_fallback = a
                break
            kc = len(KM_RE.findall(a))
            if kc >= 2:
                return price_text, a
            if kc >= 1 and km_fallback is None:
                km_fallback = a
        scope = scope.parent
    if price_text is not None:
        return price_text, (km_fallback or price_text)
    texts = []
    collect_texts(root, texts)
    whole = " | ".join(texts)
    return (price_text or whole), (km_fallback or whole)


def tap_point(bounds):
    """Port of tap(): center clamped to >= 0; None if rect empty."""
    l, t, r, b = bounds
    if r <= l or b <= t:
        return None
    return max(0.0, (l + r) / 2.0), max(0.0, (t + b) / 2.0)


def retry_should_tap(roots, labels, price):
    """Port of retryIfStillShown: tap only if the same offer price is still shown."""
    for r in roots:
        still = find_labeled(r, labels)
        if still is None:
            continue
        m = PRICE_RE.search(offer_text(still, r)[0])
        same = parse_number(m.group(1)) if m else None
        return still if same == price else None
    return None


def evaluate(pair):
    price_text, km_text = pair if isinstance(pair, tuple) else (pair, pair)
    m = PRICE_RE.search(price_text)
    price = parse_number(m.group(1))
    kms = [parse_number(x) for x in KM_RE.findall(km_text)]
    pickup = kms[0] if len(kms) >= 2 else 0.0
    trip = kms[1] if len(kms) >= 2 else kms[0]
    return price, pickup, trip, round(price / trip * 100.0) / 100.0


def screenshot_tree():
    background = Node(children=[
        Node(children=[Node("Premium"), Node("R$ 15,00")]),
        Node(children=[Node("MooveX"), Node("R$ 9,00")]),
        Node(children=[Node("Comum"), Node("R$ 10,98")]),
    ])
    button = Node(children=[Node("Aceitar corrida (13)")], clickable=True)
    popup = Node(children=[
        Node(children=[
            Node("R$ 9,60"),
            Node("Embarque - (4,66 km)"), Node("PR-323, 2676 - Parque Industrial"),
            Node("Destino - (2,76 km)"),
            Node("R. José Roberto Janeiro, 4556 - Jardim Petropolis, Umuarama"),
            Node(children=[Node("MooveX"), Node("Pix")]),
        ]),
        button,
        Node("RECUSAR", clickable=True),
    ])
    root = Node(children=[background, popup, Node(desc="Moove bubble")])
    return root, button


class TestPopupParsing:
    def test_button_found_with_default_label(self):
        root, button = screenshot_tree()
        found = find_labeled(root, ["Aceitar", "Accept"])
        assert found is not None and found.text == "Aceitar corrida (13)"
        # label node itself is not clickable -> clickNode walks to parent (clickable) in Kotlin
        assert found.parent is button and button.clickable

    def test_scoped_offer_values(self):
        root, _ = screenshot_tree()
        btn = find_labeled(root, ["Aceitar", "Accept"])
        price, pickup, trip, ppk = evaluate(offer_text(btn, root))
        assert (price, pickup, trip, ppk) == (9.60, 4.66, 2.76, 3.48)

    def test_old_behavior_picked_background_price(self):
        root, _ = screenshot_tree()
        texts = []
        collect_texts(root, texts)
        price, *_ = evaluate(" | ".join(texts))
        assert price == 15.00

    def test_separate_overlay_window_root(self):
        # pop-up as its own window root (getWindows())
        _, _ = screenshot_tree()
        root, _ = screenshot_tree()
        popup = root.children[1]
        popup.parent = None
        btn = find_labeled(popup, ["Aceitar"])
        assert evaluate(offer_text(btn, popup))[0] == 9.60

    def test_parse_number_variants(self):
        assert parse_number("1.234,56") == 1234.56
        assert parse_number("9,60") == 9.60
        assert parse_number("12.5") == 12.5
        assert PRICE_RE.search("R$1.234,56").group(1) == "1.234,56"

    def test_edge_card_single_km_ancestor_two_km_bg_price(self):
        # Iter14 note 1: card has price + only 1 km; ancestor has 2+ km and a background price
        bg = Node(children=[Node("R$ 15,00"), Node("3 km"), Node("5 km")])
        btn = Node(children=[Node("Aceitar")], clickable=True)
        card = Node(children=[Node("R$ 9,60"), Node("2,76 km"), btn])
        root = Node(children=[bg, card])
        lbl = find_labeled(root, ["Aceitar"])
        pt, kt = offer_text(lbl, root)
        price, pickup, trip, _ = evaluate((pt, kt))
        print("edge-case picked:", price, pickup, trip)
        assert price == 9.60  # background price no longer leaks

    def test_edge_km_from_ancestor_mixes_background_km(self):
        # Ancestor that also holds the background list (more prices) must not be used for km
        bg = Node(children=[Node("R$ 15,00"), Node("3 km"), Node("5 km")])
        btn = Node(children=[Node("Aceitar")], clickable=True)
        card = Node(children=[Node("R$ 9,60"), Node("2,76 km"), btn])
        root = Node(children=[bg, card])
        _, pickup, trip, _ = evaluate(offer_text(find_labeled(root, ["Aceitar"]), root))
        assert (pickup, trip) == (0.0, 2.76)

    def test_card_single_km_no_ancestor_km(self):
        btn = Node(children=[Node("Aceitar")], clickable=True)
        card = Node(children=[Node("R$ 9,60"), Node("2,76 km"), btn])
        root = Node(children=[Node("Premium"), Node("R$ 15,00"), card])
        assert evaluate(offer_text(find_labeled(root, ["Aceitar"]), root))[:3] == (9.60, 0.0, 2.76)

    def test_price_in_card_km_in_parent(self):
        # price header in small card, km rows in sibling inside a larger pop-up container
        btn = Node(children=[Node("Aceitar corrida (9)")], clickable=True)
        header = Node(children=[Node("R$ 9,60"), btn])
        popup = Node(children=[header, Node("Embarque - (4,66 km)"), Node("Destino - (2,76 km)")])
        root = Node(children=[Node(children=[Node("Premium R$ 15,00")]), popup])
        assert evaluate(offer_text(find_labeled(root, ["Aceitar"]), root)) == (9.60, 4.66, 2.76, 3.48)

    def test_tap_clamps_negative_center(self):
        assert tap_point((-300, -100, 100, 40)) == (0.0, 0.0)
        assert tap_point((10, 10, 10, 50)) is None
        assert tap_point((0, 0, 200, 100)) == (100.0, 50.0)

    def test_retry_only_when_same_price(self):
        root, _ = screenshot_tree()
        assert retry_should_tap([root], ["Aceitar"], 9.60) is not None
        assert retry_should_tap([root], ["Aceitar"], 12.00) is None  # different offer -> no tap
        empty = Node(children=[Node("Corrida aceita")])
        assert retry_should_tap([empty], ["Aceitar"], 9.60) is None  # pop-up gone -> no tap


# Iteration 18: NBSP / narrow-NBSP formatted values (pt-BR NumberFormat output)
class TestNbspParsing:
    def test_price_nbsp(self):
        assert PRICE_RE.search("R$\u00a09,60").group(1) == "9,60"

    def test_price_narrow_nbsp(self):
        assert PRICE_RE.search("R$\u202f1.234,56").group(1) == "1.234,56"

    def test_km_nbsp(self):
        assert KM_RE.findall("Embarque - (4,66\u00a0km) | Destino - (2,76\u202fkm)") == ["4,66", "2,76"]

    def test_old_ascii_patterns_missed_nbsp(self):
        # JVM \s does not match NBSP: the old patterns would drop the price (and read no km)
        assert OLD_PRICE_RE.search("R$\u00a09,60") is None
        assert OLD_KM_RE.findall("4,66\u00a0km") == []

    def test_full_nbsp_popup_evaluates(self):
        btn = Node(children=[Node("Aceitar corrida (13)")], clickable=True)
        popup = Node(children=[Node(children=[Node("R$\u00a09,60"), Node("Embarque - (4,66\u00a0km)"),
                                              Node("Destino - (2,76\u00a0km)")]), btn])
        root = Node(children=[Node(children=[Node("Premium"), Node("R$\u00a015,00")]), popup])
        assert evaluate(offer_text(find_labeled(root, ["Aceitar"]), root)) == (9.60, 4.66, 2.76, 3.48)

    def test_regular_space_still_matches(self):
        assert PRICE_RE.search("R$ 9,60").group(1) == "9,60"
        assert PRICE_RE.search("R$9").group(1) == "9"
        assert KM_RE.findall("4,66 km 2km") == ["4,66", "2"]

    def test_per_km_price_not_read_as_km(self):
        assert KM_RE.findall("R$ 2,05/km") == []
