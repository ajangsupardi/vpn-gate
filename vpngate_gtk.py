#!/usr/bin/env python3
"""VPN Gate Client — native GTK4 + libadwaita GUI (PyGObject).

Targets Adw 1.5 / GTK 4.14 API (Ubuntu 24.04/Zorin 18).
Styling: BMW M dark token system (black canvas, sharp corners, M stripe).
"""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

SYS_DIR = Path(__file__).resolve().parent
if str(SYS_DIR) not in sys.path:
    sys.path.insert(0, str(SYS_DIR))

import vpngate_core as core
import vpngate_nm as nm
import vpngate_ovpn as ovpn

APP_ID = "io.github.ajangsupardi.vpngate"
APP_NAME = "VPN Gate Client"

# BMW M design tokens (black canvas, sharp corners, M tricolor stripe)
CSS = """
/* ── Color tokens ── */
@define-color bmw_canvas          #000000;
@define-color bmw_card            #1a1a1a;  /* surface-card */
@define-color bmw_elevated        #262626;  /* surface-elevated */
@define-color bmw_soft            #0d0d0d;  /* surface-soft */
@define-color bmw_hairline        #3c3c3c;
@define-color bmw_ink             #ffffff;  /* on-dark */
@define-color bmw_body            #bbbbbb;
@define-color bmw_strong          #e6e6e6;
@define-color bmw_muted           #7e7e7e;
@define-color bmw_blue_light      #0066b1;  /* M stripe stop 1 */
@define-color bmw_blue_dark       #1c69d4;  /* M stripe stop 2 */
@define-color bmw_red             #e22718;  /* M stripe stop 3 */
@define-color bmw_success         #0fa336;

/* ── Global: pure black canvas, white ink ── */
window {
    background-color: @bmw_canvas;
    background-image: none;
    color: @bmw_ink;
    font-family: "Inter", "Cantarell", sans-serif;
}

.adw-toolbar-view,
.adw-application-window,
.adw-window,
.adw-toolbar {
    background-color: @bmw_canvas;
    background-image: none;
    color: @bmw_ink;
}

/* ── Top nav: black 64px bar + M stripe divider below ── */
.adw-header-bar {
    background-color: @bmw_canvas;
    background-image: none;
    color: @bmw_ink;
    border-bottom: none;
    padding: 8px 24px;
    min-height: 64px;
}

.adw-header-bar label {
    color: @bmw_ink;
}

/* M tricolor stripe: 3 solid segments, 4px tall, brand accent only */
.m-stripe {
    min-height: 4px;
}
.m-blue-light { background-color: @bmw_blue_light; background-image: none; }
.m-blue-dark  { background-color: @bmw_blue_dark;  background-image: none; }
.m-red        { background-color: @bmw_red;        background-image: none; }

/* ── Cards: surface-card, sharp corners, hairline, NO shadows ── */
.card {
    background-color: @bmw_canvas;
    background-image: none;
    border-radius: 0;
    border: 1px solid @bmw_hairline;
    box-shadow: none;
    padding: 24px;
    margin: 0;
}

/* Search = text-input spec: surface-card, 0 radius, 48px, hairline.
   Entry inside is fully stripped; focus thickens THIS border to white. */
.search-card {
    background-color: @bmw_card;
    background-image: none;
    border-radius: 0;
    border: 1px solid @bmw_hairline;
    box-shadow: none;
    padding: 2px 12px;
    min-height: 0;
}

.search-card:focus-within {
    border-color: @bmw_ink;
}

/* ── Buttons: sharp rectangles, uppercase voice (BMW M button).
   Primary = transparent/canvas + white 1px outline; fill only on hover. ── */
button {
    border-radius: 0;
    background-color: transparent;
    background-image: none;
    color: @bmw_ink;
    border: 1px solid @bmw_ink;
    padding: 10px 24px;
    font-weight: 700;
    font-size: 14px;
}

button.primary,
button.suggested-action {
    background-color: transparent;
    background-image: none;
    color: @bmw_ink;
    border: 1px solid @bmw_ink;
}

button.primary:hover,
button.suggested-action:hover {
    background-color: @bmw_ink;
    background-image: none;
    color: @bmw_canvas;
    border-color: @bmw_ink;
}

button.primary:disabled,
button.suggested-action:disabled,
button.destructive-action:disabled {
    background-color: transparent;
    background-image: none;
    color: @bmw_muted;
    border: 1px solid @bmw_hairline;
}

/* Disconnect: same outline silhouette, M-red voice (never a fill) */
button.destructive-action {
    background-color: transparent;
    background-image: none;
    color: @bmw_red;
    border: 1px solid @bmw_red;
}

button.destructive-action:hover {
    background-color: @bmw_red;
    background-image: none;
    color: @bmw_ink;
    border-color: @bmw_red;
}

/* Refresh: circular icon button, surface-card (BMW M button-icon) */
button.flat {
    background-color: @bmw_card;
    background-image: none;
    color: @bmw_ink;
    border: none;
    padding: 0;
    min-width: 48px;
    min-height: 48px;
    border-radius: 9999px;
}

button.flat:hover {
    background-color: @bmw_elevated;
}

/* Window controls (min/max/close): plain icons only, like the
   reload button — never boxed. NOTE: these buttons carry ONLY the
   minimize/maximize/close classes (no titlebutton class), so the
   selector must not require it. */
headerbar windowcontrols button {
    background-color: transparent;
    background-image: none;
    border: none;
    box-shadow: none;
    outline: none;
    border-radius: 9999px;
    padding: 6px;
    min-width: 0;
    min-height: 0;
}

headerbar windowcontrols button:hover {
    background-color: rgba(255, 255, 255, 0.12);
    background-image: none;
    border: none;
    box-shadow: none;
}

/* Header action buttons stay compact next to window controls */
headerbar button.suggested-action,
headerbar button.destructive-action {
    padding: 8px 20px;
    font-size: 13px;
}

/* In-row action button (sits beside the search field, right-aligned) */
button.row-action {
    padding: 6px 18px;
    font-size: 13px;
}

/* ── Header title: uppercase 700 voice ── */
.app-title {
    color: @bmw_ink;
    font-weight: 700;
    font-size: 14px;
}

/* ── ColumnView: rows split by 1px hairlines, no chrome ── */
columnview {
    background-color: transparent;
    background-image: none;
    color: @bmw_body;
}

columnview row {
    background-color: transparent;
    background-image: none;
}

columnview row:hover {
    background-color: @bmw_card;
}

columnview row:selected {
    background-color: @bmw_elevated;
}

/* Headers: uppercase 700 label voice */
columnview header {
    background-color: transparent;
    background-image: none;
    border-bottom: 1px solid @bmw_hairline;
    padding: 12px 16px;
    font-weight: 700;
    font-size: 14px;
    color: @bmw_ink;
}

columnview header button {
    color: @bmw_ink;
    font-weight: 700;
    border: none;
    border-radius: 0;
    padding: 0;
}

/* Cells: light-weight body voice */
columnview label {
    color: @bmw_body;
    font-weight: 300;
    padding: 12px 16px;
}

columnview row:selected label {
    color: @bmw_strong;
}

/* Score: heavy display value (spec-cell voice) */
.score-label {
    color: @bmw_ink;
    font-weight: 700;
}

/* Row separators: hairline */
columnview separator {
    background-color: @bmw_hairline;
    background-image: none;
    min-height: 1px;
}

/* ── ScrolledWindow: no edge glow, visible slim scrollbar ── */
scrolledwindow {
    background-color: transparent;
    background-image: none;
}

scrolledwindow overshoot,
scrolledwindow undershoot {
    background: none;
    background-image: none;
    border: none;
    box-shadow: none;
}

scrollbar {
    background-color: transparent;
    background-image: none;
    border: none;
}

/* (slider keeps stock Adwaita light styling — overriding its
   border/background trips negative-size warnings on some themes) */

/* ── Status bar: footer strip — canvas, hairline top, muted text.
   Padding kiri disamakan dengan sel tabel (12px) agar teks sejajar
   lurus dengan kolom di atasnya. ── */
.status-bar {
    background-color: @bmw_canvas;
    background-image: none;
    border-radius: 0;
    border: none;
    border-top: 1px solid @bmw_hairline;
    box-shadow: none;
    padding: 12px;
    margin-top: 16px;
    color: @bmw_body;
}

.status-bar label {
    color: @bmw_muted;
    font-weight: 300;
}

.status-bar .ip-label {
    color: @bmw_strong;
    font-weight: 400;
}

/* ── Toast overlay ── */
.adw-toast-overlay {
    background-color: transparent;
    background-image: none;
}

/* ── Spinner: white ── */
spinner {
    color: @bmw_ink;
}

/* ── Entry: fully stripped, light body voice, white caret ── */
entry {
    background-color: transparent;
    background-image: none;
    color: @bmw_ink;
    font-weight: 300;
    font-size: 13px;
    border: none;
    box-shadow: none;
    outline: none;
    padding: 2px 0;
    caret-color: @bmw_ink;
}

entry:hover,
entry:focus,
entry:active {
    background-color: transparent;
    background-image: none;
    border: none;
    box-shadow: none;
    outline: none;
}

entry selection {
    background-color: @bmw_elevated;
    color: @bmw_ink;
}

/* ── Selection highlight ── */
selection {
    background-color: @bmw_elevated;
    color: @bmw_ink;
}

/* ── Connection status: success green for the connected state ── */
.connected-indicator {
    color: @bmw_success;
    font-weight: 700;
}

.disconnected-indicator {
    color: @bmw_muted;
}
"""

# ---------------------------------------------------------------- headless ---
def headless_list(country: str, limit: int, sort: str, refresh: bool) -> int:
    try:
        servers = core.load(force_refresh=refresh)
    except Exception as e:  # noqa: BLE001
        print(f"fetch failed: {e}", file=sys.stderr)
        return 1
    if country:
        servers = [s for s in servers if s.country_short.upper() == country.upper()]
    servers = core.sort_servers(servers, key=sort)
    print(f"{len(servers)} servers" + (f" [{country.upper()}]" if country else ""))
    print(f"{'COUNTRY':<22}{'HOST':<24}{'IP':<16}{'PING':>7} {'SPEED':>11} {'SCORE':>10} {'SES':>5}")
    for s in servers[:limit]:
        ping = f"{s.ping_ms}ms" if s.ping_ms >= 0 else "-"
        print(
            f"{s.country_label:<22.22}{s.host:<24.24}{s.ip:<16}"
            f"{ping:>7} {s.speed_mbps:>7.1f}Mb {s.score:>10} {s.sessions:>5}"
        )
    return 0


def headless_dry_run(host: str) -> int:
    try:
        servers = core.load()
    except Exception as e:  # noqa: BLE001
        print(f"fetch failed: {e}", file=sys.stderr)
        return 1
    match = [s for s in servers if s.host == host or s.ddns == host]
    if not match:
        print(f"host not found: {host}", file=sys.stderr)
        return 1
    ovpn_path, auth_path = ovpn.write_profile(match[0])
    problems = ovpn.validate(ovpn_path.read_text(encoding="utf-8", errors="replace"))
    print(f"wrote {ovpn_path}")
    print(f"wrote {auth_path}")
    print("validate: " + ("OK" if not problems else "; ".join(problems)))
    return 0 if not problems else 2


def run_headless(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="vpngate_gtk.py", description=APP_NAME)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--country", default="")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--sort", default="score", choices=["score", "ping", "speed", "sessions", "country"])
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--dry-run-host", default="")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--disconnect-all", action="store_true")
    ns = ap.parse_args(argv)
    if ns.status:
        print("active:", nm.active_vpngate() or "-")
        print("public ip:", nm.get_public_ip())
        return 0
    if ns.disconnect_all:
        print("removed:", nm.disconnect_all())
        return 0
    if ns.dry_run_host:
        return headless_dry_run(ns.dry_run_host)
    if ns.list:
        return headless_list(ns.country, ns.limit, ns.sort, ns.refresh)
    ap.print_help()
    return 0


HEADLESS_FLAGS = {"--list", "--dry-run-host", "--status", "--disconnect-all", "-h", "--help"}

# --------------------------------------------------------------------- GUI ---
def _has_display() -> bool:
    import os

    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def run_gui(app_argv: list[str]) -> int:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Pango", "1.0")
    from gi.repository import Adw, GObject, Gio, GLib, Gtk, Gdk, Pango

    # Force DARK variant: BMW M has no light surface.
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)

    # Apply design system CSS
    css_provider = Gtk.CssProvider.new()
    css_provider.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

    class ServerRow(GObject.GObject):
        __gtype_name__ = "VpnGateRow"
        country = GObject.Property(type=str, default="")
        host = GObject.Property(type=str, default="")
        ip = GObject.Property(type=str, default="")
        ping_ms = GObject.Property(type=int, default=-1)
        speed_mbps = GObject.Property(type=float, default=0.0)
        score = GObject.Property(type=int, default=0)
        sessions = GObject.Property(type=int, default=0)
        operator = GObject.Property(type=str, default="")

    def text_column(title: str, prop: str, numeric: bool = False, css_class: str = "",
                    expand: bool = False, fixed_width: int = 0):
        factory = Gtk.SignalListItemFactory.new()

        def on_setup(_f, item):
            label = Gtk.Label()
            label.set_xalign(0.0)
            label.set_single_line_mode(True)
            label.set_ellipsize(Pango.EllipsizeMode.END)  # clip, don't push columns wide
            if css_class:
                label.add_css_class(css_class)
            item.set_child(label)

        def on_bind(_f, item):
            row = item.get_item()
            label = item.get_child()
            v = row.get_property(prop)
            if prop == "ping_ms":
                label.set_text(f"{v} ms" if v >= 0 else "-")
            elif prop == "speed_mbps":
                label.set_text(f"{float(v):.1f}")
            else:
                label.set_text(str(v))

        factory.connect("setup", on_setup)
        factory.connect("bind", on_bind)
        col = Gtk.ColumnViewColumn.new(title, factory)
        expr = Gtk.PropertyExpression.new(ServerRow, None, prop)
        col.set_sorter(Gtk.NumericSorter.new(expr) if numeric else Gtk.StringSorter.new(expr))
        col.set_resizable(True)
        # Responsive: text columns absorb free width, numeric columns stay slim.
        col.set_expand(expand)
        if fixed_width > 0:
            col.set_fixed_width(fixed_width)
        return col

    class App(Adw.Application):
        def __init__(self):
            super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
            self.servers: list[core.Server] = []
            self.by_host: dict[str, core.Server] = {}
            self.conn_id: str | None = nm.active_vpngate()
            self.search_text = ""
            self.store = Gio.ListStore.new(ServerRow)
            self.filter = Gtk.CustomFilter.new(self._match, None)
            self.filter_model: Gtk.FilterListModel | None = None

        def _match(self, item, _data):
            q = self.search_text.strip().lower()
            if not q:
                return True
            hay = f"{item.country} {item.host} {item.ip} {item.operator}".lower()
            return q in hay

        def do_activate(self):  # noqa: N802
            win = self.props.active_window
            if win:
                win.present()
                return
            win = Adw.ApplicationWindow(application=self, title=APP_NAME)
            win.set_default_size(980, 620)

            toolbar = Adw.ToolbarView()
            header = Adw.HeaderBar()
            title = Gtk.Label.new("VPN GATE CLIENT")
            title.add_css_class("app-title")
            header.set_title_widget(title)
            toolbar.add_top_bar(header)

            # M tricolor stripe divider (BMW M signature accent):
            # 3 solid segments, 4px tall, never a button fill.
            stripe = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            stripe.add_css_class("m-stripe")
            for cls in ("m-blue-light", "m-blue-dark", "m-red"):
                seg = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
                seg.add_css_class(cls)
                seg.set_hexpand(True)
                stripe.append(seg)
            toolbar.add_top_bar(stripe)

            btn_refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
            btn_refresh.add_css_class("flat")
            btn_refresh.set_tooltip_text("Refresh server list")
            btn_refresh.connect("clicked", self.on_refresh_clicked)
            header.pack_start(btn_refresh)

            # Single CONNECT/DISCONNECT toggle. Lives in the search row,
            # right-aligned — not in the header.
            self.busy = False
            self.btn_conn = Gtk.Button.new_with_label("CONNECT")
            self.btn_conn.add_css_class("suggested-action")
            self.btn_conn.add_css_class("row-action")
            self.btn_conn.set_sensitive(False)
            # FILL the row height so button and search field are always
            # exactly equal in height.
            self.btn_conn.set_valign(Gtk.Align.FILL)
            self.btn_conn.connect("clicked", self.on_conn_clicked)

            self.toast = Adw.ToastOverlay()
            toolbar.set_content(self.toast)

            # Main content card: full-bleed (edge to edge). Only the Host
            # column expands to absorb free width; everything else sizes to
            # content, so columns never stretch sparse and never overflow.
            content_card = Gtk.Box.new(Gtk.Orientation.VERTICAL, 8)
            content_card.add_css_class("card")
            content_card.set_margin_start(12)
            content_card.set_margin_end(12)
            content_card.set_margin_top(12)
            content_card.set_margin_bottom(12)
            self.toast.set_child(content_card)

            # Action row: search card on the left, CONNECT button OUTSIDE
            # the card on the right, sharing the row side by side.
            action_row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 12)
            action_row.set_margin_top(4)
            action_row.set_margin_bottom(4)
            action_row.set_margin_start(4)
            action_row.set_margin_end(4)

            search_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            search_box.add_css_class("search-card")
            search_box.set_hexpand(True)

            self.search = Gtk.SearchEntry()
            self.search.set_placeholder_text("Search country, host, IP, operator… (e.g. JP)")
            self.search.set_hexpand(True)
            self.search.set_valign(Gtk.Align.CENTER)
            self.search.connect("search-changed", self.on_search_changed)
            search_box.append(self.search)

            action_row.append(search_box)
            action_row.append(self.btn_conn)

            content_card.append(action_row)

            self.view = Gtk.ColumnView()
            self.view.set_show_row_separators(True)
            # Lock column order: header drags reorder columns by default,
            # which users hit accidentally when trying to scroll.
            self.view.set_reorderable(False)
            self.score_col = text_column("SCORE", "score", numeric=True,
                                         css_class="score-label")
            # Only Host expands (absorbs free width like a file manager's
            # name column). Everything else sizes to content: no sparse
            # gaps, no overflow, no clipped edge columns.
            cols = [
                ("COUNTRY", "country", False, False),
                ("HOST", "host", False, True),
                ("IP", "ip", False, False),
                ("PING MS", "ping_ms", True, False),
                ("MBPS", "speed_mbps", True, False),
            ]
            for title, prop, numeric, expand in cols:
                self.view.append_column(text_column(title, prop, numeric, expand=expand))
            self.view.append_column(self.score_col)
            cols_tail = [
                ("SESSIONS", "sessions", True, False),
            ]
            for title, prop, numeric, expand in cols_tail:
                self.view.append_column(text_column(title, prop, numeric, expand=expand))
            self.view.connect("activate", lambda *_: self.on_conn_clicked())

            self.filter_model = Gtk.FilterListModel.new(self.store, self.filter)
            sort_model = Gtk.SortListModel.new(self.filter_model, self.view.get_sorter())
            self.selection = Gtk.SingleSelection.new(sort_model)
            # Always keep a selection: autoselect first row whenever the
            # model changes, never allow empty selection.
            self.selection.set_autoselect(True)
            self.selection.set_can_unselect(False)
            self.selection.connect("selection-changed", self.on_selection_changed)
            self.view.set_model(self.selection)

            scrolled = Gtk.ScrolledWindow()
            scrolled.set_vexpand(True)
            scrolled.set_hexpand(True)
            # Classic scrollbars: always visible/draggable so the user can
            # always reach edge columns (overlay hides the hscrollbar).
            # Edge glow stays off via CSS overshoot rules.
            scrolled.set_overlay_scrolling(False)
            scrolled.set_child(self.view)
            content_card.append(scrolled)

            # Status bar card
            status_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
            status_box.add_css_class("status-bar")
            status_box.set_margin_top(8)

            self.spinner = Gtk.Spinner()
            self.lbl_status = Gtk.Label.new("Press Refresh to load servers.")
            self.lbl_status.set_xalign(0.0)  # left-aligned footer text
            self.lbl_status.set_hexpand(True)
            self.lbl_ip = Gtk.Label.new("")
            self.lbl_ip.add_css_class("ip-label")
            status_box.append(self.spinner)
            status_box.append(self.lbl_status)
            status_box.append(self.lbl_ip)
            content_card.append(status_box)

            win.set_content(toolbar)
            self.win = win
            self.btn_refresh = btn_refresh
            win.present()
            self.initial_load()
            threading.Thread(target=self._sweep_job, daemon=True).start()

        def _sweep_job(self):
            """Remove inactive leftover vpngate-* profiles + files on startup."""
            try:
                n = nm.sweep_orphans()
            except Exception:  # noqa: BLE001
                return
            if n > 0:
                GLib.idle_add(self._toast, f"Cleaned {n} leftover VPN profile(s)")

        # -- helpers --------------------------------------------------
        def _toast(self, msg: str):
            self.toast.add_toast(Adw.Toast.new(msg))

        def _set_busy(self, busy: bool, msg: str = ""):
            self.busy = busy
            if busy:
                self.spinner.set_visible(True)
                self.spinner.start()
            else:
                self.spinner.stop()
                # Hidden (not just stopped) so idle text aligns flush
                # with the table columns above.
                self.spinner.set_visible(False)
            self.btn_refresh.set_sensitive(not busy)
            if msg:
                self.lbl_status.set_text(msg)
            self._refresh_conn_button()

        def _refresh_conn_button(self):
            """Single CONNECT/DISCONNECT toggle, fully state-driven."""
            for cls in ("suggested-action", "destructive-action"):
                self.btn_conn.remove_css_class(cls)
            if self.conn_id:
                self.btn_conn.set_label("DISCONNECT")
                self.btn_conn.add_css_class("destructive-action")
                self.btn_conn.set_sensitive(not self.busy)
            else:
                self.btn_conn.set_label("CONNECT")
                self.btn_conn.add_css_class("suggested-action")
                has = self.selection.get_selected_item() is not None
                self.btn_conn.set_sensitive(has and not self.busy)

        # -- data -----------------------------------------------------
        def refresh_async(self, force: bool = True, silent: bool = False):
            # Lock search ONLY when there is no list at all (first run).
            # Otherwise the user keeps typing while fresh data loads.
            self.search.set_sensitive(bool(self.servers))
            if not silent:
                self._set_busy(True, "Fetching server list…")
            threading.Thread(target=self._refresh_job, args=(force, silent),
                             daemon=True).start()

        def initial_load(self):
            # Instant: paint from cache first so search works immediately,
            # then update silently in the background.
            cached: list[core.Server] = []
            try:
                if core.CACHE_FILE.exists():
                    cached = core.parse_csv(
                        core.CACHE_FILE.read_text(encoding="utf-8"))
            except OSError:
                cached = []
            if cached:
                self._refresh_done(cached, "", silent=True)
                self.refresh_async(force=True, silent=True)
            else:
                self.refresh_async(force=True, silent=False)

        def _refresh_job(self, force: bool, silent: bool = False):
            try:
                servers = core.load(force_refresh=force)
                err = ""
            except Exception as e:  # noqa: BLE001
                servers, err = [], str(e)
            GLib.idle_add(self._refresh_done, servers, err, silent)

        def _refresh_done(self, servers, err, silent: bool = False):
            self._set_busy(False)
            self.search.set_sensitive(True)
            if err:
                if not silent:
                    self.lbl_status.set_text(f"Fetch failed: {err[:160]}")
                    self._toast("Fetch failed — showing cache" if self.servers else "Fetch failed")
                return
            self.servers = servers
            self.by_host = {s.host: s for s in servers}
            self.store.remove_all()
            for s in servers:
                r = ServerRow()
                r.country = s.country_label
                r.host = s.host
                r.ip = s.ip
                r.ping_ms = s.ping_ms
                r.speed_mbps = s.speed_mbps
                r.score = s.score
                r.sessions = s.sessions
                r.operator = s.operator
                self.store.append(r)
            self.view.sort_by_column(self.score_col, Gtk.SortType.DESCENDING)
            # Guarantee a selection: after refill+sort the auto-select does
            # not always fire, leaving row 0 highlighted-but-unselected with
            # CONNECT disabled. Force position 0 explicitly, then sync button.
            try:
                if self.selection.get_selected_item() is None and self.selection.get_n_items() > 0:
                    self.selection.set_selected(0)
            except Exception:  # noqa: BLE001
                pass
            self._refresh_conn_button()
            self.lbl_status.set_text(f"{len(servers)} servers loaded. Double-click a row to connect (TCP:443).")
            if not silent:
                self._toast(f"{len(servers)} servers loaded")
            self._refresh_ip_label()

        def _refresh_ip_label(self):
            threading.Thread(target=self._ip_job, daemon=True).start()

        def _ip_job(self):
            ip = nm.get_public_ip()
            GLib.idle_add(self.lbl_ip.set_text, f"IP: {ip}")

        # -- ui events ------------------------------------------------
        def on_search_changed(self, entry):
            self.search_text = entry.get_text()
            self.filter.changed(Gtk.FilterChange.DIFFERENT)

        def on_selection_changed(self, *_a):
            if self.conn_id or self.busy:
                return
            self._refresh_conn_button()

        def on_refresh_clicked(self, _b):
            self.refresh_async(force=True)

        def _selected_server(self) -> core.Server | None:
            item = self.selection.get_selected_item()
            if item is None:
                return None
            return self.by_host.get(item.host)

        def on_conn_clicked(self, _b=None):
            if self.busy:
                return
            if self.conn_id:
                cid = self.conn_id or nm.active_vpngate()
                if not cid:
                    self._toast("No active VPN Gate connection")
                    return
                self._set_busy(True, f"Disconnecting {cid}…")
                threading.Thread(target=self._disconnect_job, args=(cid,), daemon=True).start()
                return
            srv = self._selected_server()
            if srv is None:
                self._toast("Select a server first")
                return
            self._set_busy(True, f"Connecting to {srv.host}…")
            threading.Thread(target=self._connect_job, args=(srv,), daemon=True).start()

        def _connect_job(self, srv: core.Server):
            try:
                ovpn_path, _auth = ovpn.write_profile(srv)
                conn = nm.sanitize(srv.host)
                # Remove stale profile with same name first.
                nm.down(conn)
                nm.delete(conn)
                cid = nm.import_connection(ovpn_path, conn)
                nm.up(cid, timeout=25)
                # Routes/DNS need seconds to settle after 'up' — retry instead
                # of freezing a "?" into the UI on the first fast failure.
                ip = nm.get_public_ip_retry(timeout=15, attempts=3, delay=5)
                GLib.idle_add(self._connect_done, cid, ip, "")
            except Exception as e:  # noqa: BLE001
                GLib.idle_add(self._connect_done, None, "", str(e)[:400])

        def _connect_done(self, cid, ip, err):
            self._set_busy(False)
            if err:
                self.lbl_status.set_text(f"Connect failed: {err}")
                self._toast("Connect failed — try another server")
                self._refresh_conn_button()
                return
            self.conn_id = cid
            if ip == "?":
                # Tunnel is up (NM said so) but public IP unverifiable yet —
                # show tunnel IP as proof and keep verifying in background.
                tun = nm.tunnel_ipv4() or "?"
                self.lbl_status.set_text(f"Connected: {cid} (verifying public IP…)")
                self.lbl_ip.set_text(f"tunnel: {tun}")
                self._toast("Connected — verifying public IP…")
                threading.Thread(target=self._reverify_ip_job, args=(cid,),
                                 daemon=True).start()
                self._refresh_conn_button()
                return
            self.lbl_status.set_text(f"Connected: {cid}")
            self.lbl_ip.set_text(f"IP: {ip}")
            self._toast("Connected")
            self._refresh_conn_button()

        def _reverify_ip_job(self, cid: str):
            ip = nm.get_public_ip_retry(timeout=15, attempts=4, delay=10)
            GLib.idle_add(self._reverify_ip_done, cid, ip)

        def _reverify_ip_done(self, cid, ip):
            if self.conn_id != cid or ip == "?":
                return
            self.lbl_ip.set_text(f"IP: {ip}")
            self.lbl_status.set_text(f"Connected: {cid}")
            self._toast("Public IP verified")

        def _disconnect_job(self, cid: str):
            try:
                warn = nm.forget_profile(cid)
                err = ""
            except Exception as e:  # noqa: BLE001
                err, warn = str(e)[:300], ""
            GLib.idle_add(self._disconnect_done, err, warn)

        def _disconnect_done(self, err, warn):
            self._set_busy(False)
            if err:
                self.lbl_status.set_text(f"Disconnect issue: {err}")
                self._refresh_conn_button()
                return
            self.conn_id = None
            if warn:
                self.lbl_status.set_text(f"Disconnected with leftovers: {warn[:160]}")
                self._toast("Disconnected — some files remained, see status")
            else:
                self.lbl_status.set_text("Disconnected — profile and files removed.")
                self._toast("Disconnected")
            self._refresh_conn_button()
            self._refresh_ip_label()

    app = App()
    return app.run(app_argv)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if any(a in HEADLESS_FLAGS for a in argv):
        return run_headless(argv)
    if not _has_display():
        # No display (SSH/CI): fall back to headless list instead of crashing.
        print("no display detected — running headless --list", file=sys.stderr)
        return headless_list("", 20, "score", False)
    return run_gui(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
