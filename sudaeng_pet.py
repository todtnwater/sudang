import sys
import os
import math
import random
import time
from collections import deque

from PySide6.QtCore import Qt, QTimer, QPoint, QPointF, QRectF, QTime
from PySide6.QtGui import (
    QPixmap, QPainter, QTransform, QAction, QActionGroup, QCursor,
    QPainterPath, QColor, QPen, QBrush, QFont, QFontMetrics, QLinearGradient,
    QGuiApplication,
)
from PySide6.QtWidgets import QApplication, QWidget, QMenu

FRAME = 64
FOOT = 62
HEAD = 26
TICK_MS = 30
SHEET_NAME = "sudaeng_frames.png"

GRAVITY = 0.9
MAX_FALL = 28.0
SLEEP_AFTER_TICKS = int(60 * 1000 / TICK_MS)
CHAT_MIN_TICKS = int(40 * 1000 / TICK_MS)
CHAT_MAX_TICKS = int(90 * 1000 / TICK_MS)
HUNGRY_AFTER_TICKS = int(10 * 60 * 1000 / TICK_MS)
FOOD_LIFETIME_TICKS = int(60 * 1000 / TICK_MS)
SHELL_SPAWN_FRAME = 12

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
UI_FONT = "Apple SD Gothic Neo" if IS_MAC else "Malgun Gothic"

ANIMS = {
    "idle_front": (0, 15),
    "idle_back": (1, 15),
    "throw_front": (2, 23),
    "throw_back": (3, 23),
    "walk_front": (4, 15),
    "walk_back": (5, 15),
}

CHAT_LINES = [
    "수댕!",
    "수댕수댕~",
    "조개 반짝반짝 닦는 중",
    "놀아줘!",
    "오늘도 화이팅!",
    "물놀이 하고 싶다…",
    "수댕?",
]
HUNGRY_LINES = [
    "배고파… 물고기…",
    "꼬르륵…",
]
PET_LINES = [
    "헤헤",
    "수댕~♥",
    "기분 좋아!",
]

PETS = []
FOODS = []
FX = []
LAST_CHIME_HOUR = [-1]


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def screen_geo_at(x, y):
    screen = QApplication.screenAt(QPoint(int(x), int(y)))
    if screen is None:
        screen = QApplication.screenAt(QCursor.pos())
    if screen is None:
        screen = QApplication.primaryScreen()
    return screen.availableGeometry()


def prepare_overlay(widget):
    widget.setAttribute(Qt.WA_TranslucentBackground)
    widget.setAttribute(Qt.WA_ShowWithoutActivating)
    if IS_MAC:
        widget.setAttribute(Qt.WA_MacAlwaysShowToolWindow)


class SurfaceBase:
    def __init__(self):
        self.enabled = False
        self.cache = []
        self.cache_time = 0.0

    def scan(self):
        return []

    def rect_of(self, hwnd):
        return None

    def occluded_in(self, rects, index, x, y):
        for j in range(index):
            _, l, t, r, b = rects[j]
            if l <= x <= r and t <= y + 3 <= b:
                return True
        return False

    def is_occluded(self, hwnd, x, y):
        rects = self.scan()
        for i, item in enumerate(rects):
            if item[0] == hwnd:
                return self.occluded_in(rects, i, x, y)
        return True

    def find_landing(self, x, prev_y, new_y, screen_top):
        best = None
        rects = self.scan()
        for i, (hwnd, l, t, r, b) in enumerate(rects):
            if t <= screen_top + 2:
                continue
            if l <= x <= r and prev_y <= t <= new_y:
                if self.occluded_in(rects, i, x, t):
                    continue
                if best is None or t < best[1]:
                    best = (hwnd, t, l)
        return best


class MacWindowSurfaces(SurfaceBase):
    def __init__(self):
        super().__init__()
        self.pid = os.getpid()
        try:
            import Quartz
        except Exception:
            return
        self.Q = Quartz
        self.enabled = True

    def scan(self):
        if not self.enabled:
            return []
        now = time.monotonic()
        if now - self.cache_time < 0.05:
            return self.cache
        Q = self.Q
        found = []
        try:
            info = Q.CGWindowListCopyWindowInfo(
                Q.kCGWindowListOptionOnScreenOnly | Q.kCGWindowListExcludeDesktopElements,
                Q.kCGNullWindowID,
            )
        except Exception:
            info = None
        for w in info or []:
            if int(w.get(Q.kCGWindowLayer, 1)) != 0:
                continue
            if int(w.get(Q.kCGWindowOwnerPID, -1)) == self.pid:
                continue
            if float(w.get(Q.kCGWindowAlpha, 1.0)) <= 0.01:
                continue
            bounds = w.get(Q.kCGWindowBounds)
            if not bounds:
                continue
            l = float(bounds["X"])
            t = float(bounds["Y"])
            r = l + float(bounds["Width"])
            b = t + float(bounds["Height"])
            if r - l < 120 or b - t < 60:
                continue
            found.append((int(w.get(Q.kCGWindowNumber, 0)), l, t, r, b))
        self.cache = found
        self.cache_time = now
        return found

    def rect_of(self, hwnd):
        if not self.enabled or hwnd is None:
            return None
        for item in self.scan():
            if item[0] == hwnd:
                return item[1], item[2], item[3], item[4]
        return None


class WindowSurfaces(SurfaceBase):
    def __init__(self):
        super().__init__()
        self.enabled = IS_WINDOWS
        if not self.enabled:
            return
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        self.wintypes = wintypes
        self.user32 = ctypes.windll.user32
        self.dwmapi = ctypes.windll.dwmapi
        self.user32.GetWindowLongW.restype = ctypes.c_long
        self.user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.IsIconic.argtypes = [wintypes.HWND]
        self.user32.IsWindow.argtypes = [wintypes.HWND]
        self.user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self.user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.dwmapi.DwmGetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
        ]
        self.enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.skip_classes = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}

    def native_rect_to_logical(self, l, t, r, b):
        cx = (l + r) / 2
        target = None
        for sc in QGuiApplication.screens():
            g = sc.geometry()
            d = sc.devicePixelRatio()
            if g.x() <= cx < g.x() + g.width() * d and g.y() <= t + 5 < g.y() + g.height() * d:
                target = (g.x(), g.y(), d)
                break
        if target is None:
            d = QGuiApplication.primaryScreen().devicePixelRatio()
            return l / d, t / d, r / d, b / d
        ox, oy, d = target
        return (
            ox + (l - ox) / d,
            oy + (t - oy) / d,
            ox + (r - ox) / d,
            oy + (b - oy) / d,
        )

    def is_cloaked(self, hwnd):
        ctypes = self.ctypes
        cloaked = ctypes.c_int(0)
        self.dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        return cloaked.value != 0

    def raw_rect(self, hwnd):
        ctypes = self.ctypes
        rect = self.wintypes.RECT()
        res = self.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
        if res != 0:
            if not self.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
        return rect.left, rect.top, rect.right, rect.bottom

    def scan(self):
        if not self.enabled:
            return []
        now = time.monotonic()
        if now - self.cache_time < 0.05:
            return self.cache
        ctypes = self.ctypes
        user32 = self.user32
        found = []

        def callback(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            ex = user32.GetWindowLongW(hwnd, -20)
            if ex & 0x80 or ex & 0x20:
                return True
            if user32.GetWindowTextLengthW(hwnd) == 0:
                return True
            buf = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, buf, 64)
            if buf.value in self.skip_classes:
                return True
            if self.is_cloaked(hwnd):
                return True
            raw = self.raw_rect(hwnd)
            if raw is None:
                return True
            l, t, r, b = self.native_rect_to_logical(*raw)
            if r - l < 120 or b - t < 60:
                return True
            found.append((int(hwnd), l, t, r, b))
            return True

        proc = self.enum_proc_type(callback)
        user32.EnumWindows(proc, 0)
        self.cache = found
        self.cache_time = now
        return found

    def rect_of(self, hwnd):
        if not self.enabled or hwnd is None:
            return None
        user32 = self.user32
        if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return None
        if self.is_cloaked(hwnd):
            return None
        raw = self.raw_rect(hwnd)
        if raw is None:
            return None
        return self.native_rect_to_logical(*raw)


def create_window_surfaces():
    if IS_WINDOWS:
        return WindowSurfaces()
    if IS_MAC:
        return MacWindowSurfaces()
    return SurfaceBase()


WIN = None


def find_landing(x, prev_y, new_y, use_windows):
    geo = screen_geo_at(x, max(prev_y - 10, 0))
    floor = geo.bottom() + 1
    best = None
    if use_windows and WIN is not None and WIN.enabled:
        best = WIN.find_landing(x, prev_y, new_y, geo.top())
    if new_y >= floor and (best is None or best[1] > floor):
        best = (None, floor, 0)
    return best


def heart_path(cx, cy, size):
    s = size
    p = QPainterPath()
    p.moveTo(cx, cy + s * 0.35)
    p.cubicTo(cx - s * 0.9, cy - s * 0.25, cx - s * 0.45, cy - s * 0.85, cx, cy - s * 0.35)
    p.cubicTo(cx + s * 0.45, cy - s * 0.85, cx + s * 0.9, cy - s * 0.25, cx, cy + s * 0.35)
    return p


def draw_shell(painter, size):
    r = size * 0.45
    base = QPointF(0, r * 0.6)
    radius = r * 1.1
    fan = QPainterPath()
    fan.moveTo(base)
    fan.arcTo(QRectF(base.x() - radius, base.y() - radius, radius * 2, radius * 2), 25, 130)
    fan.closeSubpath()
    grad = QLinearGradient(0, base.y() - radius, 0, base.y())
    grad.setColorAt(0.0, QColor("#F9D27A"))
    grad.setColorAt(1.0, QColor("#E08A2E"))
    painter.setBrush(QBrush(grad))
    painter.setPen(QPen(QColor("#8A4B12"), max(1.0, size * 0.05)))
    painter.drawPath(fan)
    painter.setPen(QPen(QColor("#B8641F"), max(1.0, size * 0.04)))
    for deg in (45, 65, 90, 115, 135):
        a = math.radians(deg)
        painter.drawLine(base, QPointF(base.x() + math.cos(a) * radius * 0.9, base.y() - math.sin(a) * radius * 0.9))
    painter.setBrush(QColor("#C9762A"))
    painter.setPen(QPen(QColor("#8A4B12"), max(1.0, size * 0.04)))
    painter.drawRoundedRect(QRectF(-r * 0.28, base.y() - r * 0.08, r * 0.56, r * 0.3), r * 0.08, r * 0.08)


class FxWindow(QWidget):
    def __init__(self, w, h):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
            | Qt.WindowDoesNotAcceptFocus,
        )
        prepare_overlay(self)
        self.setFixedSize(int(w), int(h))
        self.alive = True
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._step)
        self.timer.start(TICK_MS)
        FX.append(self)

    def place_center(self, x, y):
        self.move(int(x - self.width() / 2), int(y - self.height() / 2))

    def place_bottom(self, x, y):
        self.move(int(x - self.width() / 2), int(y - self.height()))

    def _step(self):
        if not self.alive:
            return
        if not self.step():
            self.dispose()
        else:
            self.update()

    def step(self):
        return True

    def dispose(self):
        if not self.alive:
            return
        self.alive = False
        self.timer.stop()
        if self in FX:
            FX.remove(self)
        self.close()
        self.deleteLater()


class HeartBurst(FxWindow):
    def __init__(self, x, y, scale):
        k = scale / 2
        super().__init__(110 * k, 120 * k)
        self.k = k
        self.life = 45
        self.parts = []
        for _ in range(6):
            self.parts.append([
                self.width() / 2 + random.uniform(-25, 25) * k,
                self.height() - 18 * k,
                random.uniform(-0.6, 0.6) * k,
                random.uniform(-2.4, -1.2) * k,
                random.uniform(10, 16) * k,
            ])
        self.place_bottom(x, y)
        self.show()

    def step(self):
        self.life -= 1
        for p in self.parts:
            p[0] += p[2]
            p[1] += p[3]
        return self.life > 0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        alpha = max(0.0, min(1.0, self.life / 20))
        painter.setOpacity(alpha)
        painter.setPen(QPen(QColor("#D94468"), max(1.0, self.k)))
        painter.setBrush(QColor("#FF6B8A"))
        for x, y, vx, vy, size in self.parts:
            painter.drawPath(heart_path(x, y, size))
        painter.end()


class ZzFx(FxWindow):
    def __init__(self, scale):
        k = scale / 2
        super().__init__(70 * k, 80 * k)
        self.k = k
        self.letters = []
        self.count = 0
        self.show()

    def step(self):
        self.count += 1
        if self.count % 28 == 1:
            self.letters.append([8 * self.k, self.height() - 10 * self.k, 0])
        for z in self.letters:
            z[0] += 0.5 * self.k
            z[1] -= 0.9 * self.k
            z[2] += 1
        self.letters = [z for z in self.letters if z[2] < 70]
        return True

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        for x, y, age in self.letters:
            size = int((11 + age * 0.12) * self.k * 1.4)
            font = QFont("Arial", 1)
            font.setPixelSize(max(6, size))
            font.setBold(True)
            painter.setFont(font)
            painter.setOpacity(max(0.0, 1.0 - age / 70))
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(QPointF(x + 1, y + 1), "Z")
            painter.setPen(QColor("#4F6FD0"))
            painter.drawText(QPointF(x, y), "Z")
        painter.end()


class BubbleFx(FxWindow):
    def __init__(self, text, scale, ticks):
        font = QFont(UI_FONT)
        if IS_MAC:
            font.setPixelSize(round((9 + scale) * 4 / 3))
        else:
            font.setPointSize(9 + scale)
        font.setBold(True)
        fm = QFontMetrics(font)
        pad = 8
        tail = 8
        tw = fm.horizontalAdvance(text)
        th = fm.height()
        super().__init__(tw + pad * 2 + 4, th + pad * 2 + tail + 4)
        self.text = text
        self.font = font
        self.pad = pad
        self.tail = tail
        self.life = ticks
        self.total = ticks
        self.show()

    def step(self):
        self.life -= 1
        return self.life > 0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        fade = min(1.0, self.life / 10)
        painter.setOpacity(fade)
        w = self.width() - 4
        h = self.height() - self.tail - 4
        body = QPainterPath()
        body.addRoundedRect(QRectF(2, 2, w, h), 10, 10)
        tail = QPainterPath()
        cx = self.width() / 2
        tail.moveTo(cx - 6, h + 1)
        tail.lineTo(cx, h + self.tail + 1)
        tail.lineTo(cx + 6, h + 1)
        tail.closeSubpath()
        shape = body.united(tail)
        painter.setPen(QPen(QColor("#2B3A55"), 2))
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawPath(shape)
        painter.setFont(self.font)
        painter.setPen(QColor("#1E2A40"))
        painter.drawText(QRectF(2, 2, w, h), Qt.AlignCenter, self.text)
        painter.end()


class ShellFx(FxWindow):
    def __init__(self, pet, x, y, direction):
        k = pet.scale / 2
        super().__init__(28 * k, 28 * k)
        self.pet = pet
        self.k = k
        self.x = x
        self.y = y
        self.dir = direction
        self.vx = direction * 13 * k
        self.vy = -2.2 * k
        self.angle = 0.0
        self.returning = False
        self.home_speed = 2 * k
        self.life = 160
        self.place_center(self.x, self.y)
        self.show()

    def step(self):
        self.life -= 1
        self.angle = (self.angle + 28 * self.dir) % 360
        if not self.returning:
            self.vx -= self.dir * 0.45 * self.k
            self.vy += 0.08 * self.k
            self.x += self.vx
            self.y += self.vy
            if self.vx * self.dir <= 0:
                self.returning = True
        else:
            if not self.pet.alive:
                return False
            hx, hy = self.pet.hand_point()
            dx = hx - self.x
            dy = hy - self.y
            dist = math.hypot(dx, dy)
            self.home_speed = min(self.home_speed + 0.6 * self.k, 15 * self.k)
            if dist <= max(self.home_speed, 12 * self.k):
                return False
            self.x += dx / dist * self.home_speed
            self.y += dy / dist * self.home_speed
        self.place_center(self.x, self.y)
        return self.life > 0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self.angle)
        draw_shell(painter, self.width() * 0.9)
        painter.end()


class FoodItem(FxWindow):
    def __init__(self, x, y):
        super().__init__(34, 34)
        self.kind = random.choice(["fish", "berry"])
        self.px = float(x)
        self.py = float(y)
        self.vy = 0.0
        self.landed = False
        self.bounced = False
        self.age = 0
        self.eater = None
        self.ignored = set()
        self.eaten = 0.0
        FOODS.append(self)
        self.place_bottom(self.px, self.py)
        self.show()

    def step(self):
        self.age += 1
        if not self.landed:
            prev = self.py
            self.vy = min(self.vy + GRAVITY, MAX_FALL)
            self.py += self.vy
            hit = find_landing(self.px, prev, self.py, True)
            if hit is not None:
                self.py = hit[1]
                if not self.bounced and self.vy > 6:
                    self.vy = -self.vy * 0.35
                    self.bounced = True
                else:
                    self.vy = 0.0
                    self.landed = True
        self.place_bottom(self.px, self.py)
        if self.eaten >= 1.0:
            return False
        return self.age < FOOD_LIFETIME_TICKS

    def set_eaten(self, ratio):
        self.eaten = max(0.0, min(1.0, ratio))

    def dispose(self):
        if self in FOODS:
            FOODS.remove(self)
        super().dispose()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        remain = 1.0 - self.eaten
        fade = 1.0
        if self.age > FOOD_LIFETIME_TICKS - 30:
            fade = max(0.0, (FOOD_LIFETIME_TICKS - self.age) / 30)
        painter.setOpacity(fade)
        painter.translate(self.width() / 2, self.height() - 2)
        painter.scale(max(0.15, remain), max(0.15, remain))
        if self.kind == "fish":
            painter.setPen(QPen(QColor("#2F5E8C"), 1.5))
            painter.setBrush(QColor("#7FB3E6"))
            tail = QPainterPath()
            tail.moveTo(-6, -8)
            tail.lineTo(-15, -14)
            tail.lineTo(-15, -2)
            tail.closeSubpath()
            painter.drawPath(tail)
            painter.drawEllipse(QRectF(-10, -15, 22, 14))
            painter.setBrush(QColor("#1E2A40"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(5, -11, 3, 3))
        else:
            painter.setPen(QPen(QColor("#8C2B2B"), 1.5))
            painter.setBrush(QColor("#E5484D"))
            painter.drawEllipse(QRectF(-9, -18, 18, 18))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 170))
            painter.drawEllipse(QRectF(-5, -14, 5, 5))
            painter.setBrush(QColor("#4CAF50"))
            painter.setPen(QPen(QColor("#2E7D32"), 1))
            painter.drawEllipse(QRectF(-1, -23, 10, 6))
        painter.end()


class SudaengPet(QWidget):
    def __init__(self, sheet, start_x=None):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool,
        )
        prepare_overlay(self)
        self.setMouseTracking(True)
        self.setWindowTitle("수댕이")

        self.sheet = sheet
        self.alive = True
        self.scale = 2
        self.frames = {}
        self.build_frames()

        self.state = "idle"
        self.facing = "front"
        self.mirror = False
        self.walk_facing = "front"
        self.frame_idx = 0
        self.anim_acc = 0
        self.loops_left = 2
        self.paused = False
        self.mode = "free"
        self.gravity = False

        self.ticks = 0
        self.last_interaction = 0
        self.last_ate = 0
        self.next_chat = random.randint(CHAT_MIN_TICKS, CHAT_MAX_TICKS)

        self.px = 0.0
        self.py = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.target_x = 0.0
        self.target_y = 0.0
        self.walk_speed = 1.3 * self.scale
        self.hop_phase = 0.0
        self.jump_y = 0.0
        self.jump_v = 0.0
        self.ride = None
        self.ride_left = 0.0

        self.press_global = None
        self.drag_offset = QPoint(0, 0)
        self.dragged = False
        self.drag_samples = deque(maxlen=6)

        self.last_hover_x = None
        self.last_hover_sign = 0
        self.rub_ticks = []
        self.last_pet_tick = -1000

        self.shell_thrown = False
        self.seek_food = None
        self.eat_food = None
        self.eat_ticks = 0
        self.bubble = None
        self.zz = None

        self.apply_size()
        geo = QApplication.primaryScreen().availableGeometry()
        if start_x is None:
            start_x = geo.right() - self.width() / 2 - 80
        self.px = float(start_x)
        self.py = float(geo.bottom() + 1)
        self.clamp_free()
        self.sync_window()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK_MS)
        PETS.append(self)

    def build_frames(self):
        size = FRAME * self.scale
        flip = QTransform().scale(-1, 1)
        self.frames = {}
        for name, (row, count) in ANIMS.items():
            normal = []
            mirrored = []
            for i in range(count):
                piece = self.sheet.copy(i * FRAME, row * FRAME, FRAME, FRAME)
                piece = piece.scaled(size, size, Qt.IgnoreAspectRatio, Qt.FastTransformation)
                normal.append(piece)
                mirrored.append(piece.transformed(flip, Qt.FastTransformation))
            self.frames[(name, False)] = normal
            self.frames[(name, True)] = mirrored

    def margin(self):
        return 24 * self.scale

    def apply_size(self):
        self.setFixedSize(FRAME * self.scale, FRAME * self.scale + self.margin())

    def foot_offset(self):
        return self.margin() + FOOT * self.scale

    def sync_window(self):
        self.move(int(self.px - self.width() / 2), int(self.py - self.foot_offset()))

    def geo(self):
        return screen_geo_at(self.px, self.py - 10)

    def bounds(self):
        g = self.geo()
        half = self.width() / 2
        return (
            g.left() + half,
            g.right() + 1 - half,
            g.top() + self.foot_offset(),
            g.bottom() + 1,
        )

    def clamp_free(self):
        x0, x1, y0, y1 = self.bounds()
        self.px = min(max(self.px, x0), x1)
        self.py = min(max(self.py, y0), y1)

    def head_point(self):
        return self.px, self.py - (FOOT - HEAD) * self.scale - self.jump_y

    def hand_point(self):
        side = self.shell_side()
        return self.px + side * 20 * self.scale, self.py - 28 * self.scale - self.jump_y

    def shell_side(self):
        if self.facing == "front":
            return 1 if self.mirror else -1
        return -1 if self.mirror else 1

    def anim_name(self):
        if self.state == "walk":
            return "walk_" + self.facing
        if self.state == "throw":
            return "throw_" + self.facing
        return "idle_" + self.facing

    def current_frames(self):
        return self.frames[(self.anim_name(), self.mirror)]

    def ticks_per_frame(self):
        if self.state == "sleep":
            return 6
        if self.state == "fly":
            return 1
        return 2

    def set_state(self, state):
        if self.state == "sleep" and state != "sleep":
            self.stop_zz()
        self.state = state
        self.frame_idx = 0
        self.anim_acc = 0
        if state != "walk":
            self.hop_phase = 0.0
        if state == "throw":
            self.shell_thrown = False

    def start_idle(self, loops=None):
        self.set_state("idle")
        self.loops_left = loops if loops is not None else random.randint(1, 3)

    def start_throw(self):
        if self.state in ("drag", "fly"):
            return
        self.seek_food = None
        self.set_state("throw")

    def start_fall(self, vx=0.0, vy=0.0):
        self.ride = None
        self.seek_food = None
        self.vx = vx
        self.vy = vy
        self.set_state("fly")

    def start_sleep(self):
        self.set_state("sleep")
        self.facing = "front"
        self.stop_zz()
        self.zz = ZzFx(self.scale)
        self.update_fx_positions()

    def stop_zz(self):
        if self.zz is not None:
            self.zz.dispose()
            self.zz = None

    def wake(self):
        if self.state != "sleep":
            return
        self.start_idle(2)
        self.say("!?", 40)
        self.hop()

    def interact(self):
        self.last_interaction = self.ticks
        if self.state == "sleep":
            self.wake()

    def hop(self):
        if self.jump_y == 0:
            self.jump_v = 6 * self.scale
            self.jump_y = 0.1

    def say(self, text, ticks=90):
        if self.bubble is not None:
            self.bubble.dispose()
        self.bubble = BubbleFx(text, self.scale, ticks)
        self.update_fx_positions()

    def hearts(self):
        hx, hy = self.head_point()
        HeartBurst(hx, hy + 6 * self.scale, self.scale)

    def turn_around(self):
        self.facing = "back" if self.facing == "front" else "front"
        self.mirror = random.random() < 0.5
        self.start_idle(random.randint(2, 3))

    def begin_walk(self, tx, ty, speed, facing=None):
        self.target_x = tx
        self.target_y = ty
        self.walk_speed = speed
        if self.state != "walk":
            self.set_state("walk")
            if self.gravity:
                self.walk_facing = facing if facing is not None else random.choice(["front", "back"])
        elif facing is not None:
            self.walk_facing = facing

    def start_wander(self):
        reach = 175 * self.scale
        if self.gravity:
            x0, x1, _, _ = self.bounds()
            tx = self.px + random.uniform(-reach, reach)
            if self.ride is not None and random.random() > 0.2:
                r = WIN.rect_of(self.ride) if WIN is not None else None
                if r is not None:
                    tx = min(max(tx, r[0] + 10), r[2] - 10)
            tx = min(max(tx, x0), x1)
            self.begin_walk(tx, self.py, 1.3 * self.scale)
            return
        x0, x1, y0, y1 = self.bounds()
        dx = random.uniform(-reach, reach)
        dy = random.uniform(reach * 0.3, reach)
        if random.random() < 0.5:
            dy = -dy
        tx = self.px + dx
        ty = self.py + dy
        if tx < x0 or tx > x1:
            tx = self.px - dx
        if ty < y0 or ty > y1:
            ty = self.py - dy
        tx = min(max(tx, x0), x1)
        ty = min(max(ty, y0), y1)
        self.begin_walk(tx, ty, 1.3 * self.scale)

    def nearest_food(self):
        best = None
        best_d = None
        for food in FOODS:
            if not food.alive or not food.landed:
                continue
            if food.eater is not None and food.eater is not self:
                continue
            if self in food.ignored:
                continue
            d = math.hypot(food.px - self.px, food.py - self.py)
            if best_d is None or d < best_d:
                best = food
                best_d = d
        return best

    def go_to_food(self, food):
        self.seek_food = food
        side = -1 if food.px < self.px else 1
        tx = food.px - side * 18 * self.scale
        ty = food.py
        if self.gravity:
            ty = self.py
        else:
            x0, x1, y0, y1 = self.bounds()
            tx = min(max(tx, x0), x1)
            ty = min(max(ty, y0), y1)
        self.begin_walk(tx, ty, 2.0 * self.scale, "front")

    def start_eat(self, food):
        self.seek_food = None
        self.eat_food = food
        food.eater = self
        self.eat_ticks = 0
        self.facing = "front"
        self.mirror = food.px > self.px
        self.set_state("eat")

    def decide_next(self):
        if self.paused:
            self.start_idle(1)
            return
        food = self.nearest_food()
        if food is not None:
            self.go_to_food(food)
            return
        if self.mode == "follow":
            if random.random() < 0.15:
                self.start_throw()
            else:
                self.start_idle()
            return
        r = random.random()
        if r < 0.5:
            self.start_wander()
        elif r < 0.65:
            self.start_throw()
        elif r < 0.8:
            self.turn_around()
        else:
            self.start_idle()

    def on_anim_loop(self):
        if self.state == "throw":
            self.start_idle()
        elif self.state == "idle":
            self.loops_left -= 1
            if self.loops_left <= 0:
                self.decide_next()

    def update_facing(self, dx, dy):
        if self.gravity:
            self.facing = self.walk_facing
        elif dy < -0.3:
            self.facing = "back"
        else:
            self.facing = "front"
        if abs(dx) > 0.5:
            if self.facing == "front":
                self.mirror = dx > 0
            else:
                self.mirror = dx < 0

    def advance_anim(self):
        self.anim_acc += 1
        if self.anim_acc >= self.ticks_per_frame():
            self.anim_acc = 0
            self.frame_idx += 1
            if self.state == "throw" and not self.shell_thrown and self.frame_idx >= SHELL_SPAWN_FRAME:
                self.shell_thrown = True
                hx, hy = self.hand_point()
                ShellFx(self, hx, hy, self.shell_side())
            if self.frame_idx >= len(self.current_frames()):
                self.frame_idx = 0
                self.on_anim_loop()

    def mode_logic(self):
        if self.state not in ("idle", "walk"):
            return
        if self.paused:
            if self.state == "walk":
                self.start_idle(1)
            return
        if self.seek_food is not None:
            if not self.seek_food.alive:
                self.seek_food = None
                self.start_idle(1)
            return
        food = self.nearest_food()
        if food is not None:
            self.go_to_food(food)
            return
        cur = QCursor.pos()
        cx = float(cur.x())
        cy = float(cur.y())
        hx, hy = self.head_point()
        if self.mode == "follow":
            dx = cx - self.px
            dy = 0.0 if self.gravity else cy - (self.py - 32 * self.scale)
            dist = math.hypot(dx, dy)
            if dist > 70 * self.scale:
                tx = cx
                ty = self.py if self.gravity else cy + 32 * self.scale
                x0, x1, y0, y1 = self.bounds()
                tx = min(max(tx, x0), x1)
                ty = min(max(ty, y0), y1)
                self.begin_walk(tx, ty, 2.4 * self.scale, "front")
            elif self.state == "walk":
                self.facing = "front"
                self.mirror = cx > self.px
                self.start_idle(2)
        elif self.mode == "flee":
            dx = self.px - cx
            dy = 0.0 if self.gravity else (self.py - 32 * self.scale) - cy
            dist = math.hypot(dx, dy)
            if dist < 130 * self.scale:
                if dist < 0.01:
                    dx, dy, dist = 1.0, 0.0, 1.0
                ux = dx / dist
                uy = dy / dist
                x0, x1, y0, y1 = self.bounds()
                run = 220 * self.scale
                tx = min(max(self.px + ux * run, x0), x1)
                ty = self.py if self.gravity else min(max(self.py + uy * run, y0), y1)
                if math.hypot(tx - self.px, ty - self.py) < 40 * self.scale:
                    if self.gravity:
                        tx = x1 if self.px - x0 < x1 - self.px else x0
                    else:
                        px2 = -uy
                        py2 = ux
                        if (self.px + px2 * run - cx) * dx < 0:
                            px2 = -px2
                            py2 = -py2
                        tx = min(max(self.px + px2 * run, x0), x1)
                        ty = min(max(self.py + py2 * run, y0), y1)
                self.begin_walk(tx, ty, 3.6 * self.scale, "front")

    def step_walk(self):
        speed = self.walk_speed
        dx = self.target_x - self.px
        dy = 0.0 if self.gravity else self.target_y - self.py
        dist = math.hypot(dx, dy)
        if dist <= speed:
            self.px = self.target_x
            if not self.gravity:
                self.py = self.target_y
            self.on_arrive()
        else:
            self.update_facing(dx, dy)
            self.px += dx / dist * speed
            if not self.gravity:
                self.py += dy / dist * speed
            self.hop_phase += 0.32

    def on_arrive(self):
        food = self.seek_food
        if food is not None:
            if food.alive and abs(food.px - self.px) < 45 * self.scale and abs(food.py - self.py) < 40 * self.scale:
                self.start_eat(food)
                return
            if food.alive:
                food.ignored.add(self)
            self.seek_food = None
        self.start_idle()

    def step_fly(self):
        prev = self.py
        self.vy = min(self.vy + GRAVITY, MAX_FALL)
        self.px += self.vx
        self.py += self.vy
        x0, x1, y0, y1 = self.bounds()
        if self.px < x0:
            self.px = x0
            self.vx = abs(self.vx) * 0.6
        if self.px > x1:
            self.px = x1
            self.vx = -abs(self.vx) * 0.6
        if self.py < y0:
            self.py = y0
            self.vy = abs(self.vy) * 0.5
        if abs(self.vx) > 0.5:
            self.mirror = self.vx > 0
        hit = find_landing(self.px, prev, self.py, self.gravity)
        if hit is None:
            return
        hwnd, top, left = hit
        self.py = top
        if self.vy > 6:
            self.vy = -self.vy * 0.42
            self.vx *= 0.75
        else:
            self.vx = 0.0
            self.vy = 0.0
            self.ride = hwnd if self.gravity else None
            self.ride_left = left
            self.start_idle(2)

    def step_eat(self):
        food = self.eat_food
        if food is None or not food.alive:
            self.eat_food = None
            self.start_idle(1)
            return
        self.eat_ticks += 1
        if self.eat_ticks % 15 == 0:
            self.hop()
        food.set_eaten(self.eat_ticks / 50)
        if self.eat_ticks >= 50:
            food.dispose()
            self.eat_food = None
            self.last_ate = self.ticks
            self.hearts()
            self.say("냠냠!", 60)
            self.start_idle(2)

    def stick_to_surface(self):
        if self.state in ("fly", "drag"):
            return
        g = self.geo()
        if self.ride is not None:
            r = WIN.rect_of(self.ride) if WIN is not None else None
            if r is None or r[1] <= g.top() + 2:
                self.start_fall()
                return
            l, t, rr, b = r
            self.px += l - self.ride_left
            self.ride_left = l
            self.py = t
            if self.px < l or self.px > rr:
                self.start_fall()
                return
            if self.ticks % 10 == 0 and WIN.is_occluded(self.ride, self.px, t):
                self.start_fall()
        else:
            floor = g.bottom() + 1
            if self.py < floor - 1:
                self.start_fall()
            else:
                self.py = floor
                x0, x1, _, _ = self.bounds()
                self.px = min(max(self.px, x0), x1)

    def check_sleep(self):
        if self.state != "idle" or self.mode == "follow" or self.seek_food is not None:
            return
        if self.ticks - self.last_interaction > SLEEP_AFTER_TICKS:
            self.start_sleep()

    def check_chat(self):
        if self.ticks < self.next_chat:
            return
        self.next_chat = self.ticks + random.randint(CHAT_MIN_TICKS, CHAT_MAX_TICKS)
        if self.state not in ("idle", "walk"):
            return
        if self.ticks - self.last_ate > HUNGRY_AFTER_TICKS:
            self.say(random.choice(HUNGRY_LINES))
        else:
            self.say(random.choice(CHAT_LINES))

    def check_chime(self):
        if not PETS or PETS[0] is not self:
            return
        now = QTime.currentTime()
        if now.minute() == 0 and LAST_CHIME_HOUR[0] != now.hour():
            LAST_CHIME_HOUR[0] = now.hour()
            if self.state == "sleep":
                self.wake()
            self.say(str(now.hour()) + "시야! 수댕!", 150)
            self.hop()

    def update_fx_positions(self):
        hx, hy = self.head_point()
        if self.bubble is not None:
            if not self.bubble.alive:
                self.bubble = None
            else:
                self.bubble.place_bottom(hx, hy - 2)
        if self.zz is not None:
            self.zz.place_bottom(hx + 26 * self.scale, hy + 8 * self.scale)

    def tick(self):
        self.ticks += 1
        self.advance_anim()
        self.check_sleep()
        self.check_chat()
        self.check_chime()
        self.mode_logic()

        if self.state == "walk":
            self.step_walk()
        elif self.state == "fly":
            self.step_fly()
        elif self.state == "eat":
            self.step_eat()

        if self.gravity:
            self.stick_to_surface()

        if self.jump_y > 0 or self.jump_v > 0:
            self.jump_y += self.jump_v
            self.jump_v -= 0.6 * self.scale
            if self.jump_y <= 0:
                self.jump_y = 0.0
                self.jump_v = 0.0

        if self.state != "drag":
            self.sync_window()
        self.update_fx_positions()
        self.update()

    def paintEvent(self, event):
        frames = self.current_frames()
        pix = frames[self.frame_idx % len(frames)]
        bob = 0.0
        if self.state == "walk":
            bob = abs(math.sin(self.hop_phase)) * 5 * self.scale
        y = self.margin() - bob - self.jump_y
        y = max(0.0, y)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        painter.drawPixmap(0, int(y), pix)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.interact()
            self.press_global = event.globalPosition().toPoint()
            self.drag_offset = self.press_global - self.frameGeometry().topLeft()
            self.dragged = False
            self.drag_samples.clear()
            self.drag_samples.append((time.monotonic(), self.press_global.x(), self.press_global.y()))

    def mouseMoveEvent(self, event):
        now = event.globalPosition().toPoint()
        if self.press_global is None:
            self.hover_move(now.x())
            return
        self.drag_samples.append((time.monotonic(), now.x(), now.y()))
        if not self.dragged and (now - self.press_global).manhattanLength() > 4:
            self.dragged = True
            self.ride = None
            self.seek_food = None
            if self.eat_food is not None:
                self.eat_food.eater = None
                self.eat_food = None
            self.facing = "front"
            self.set_state("drag")
        if self.dragged:
            pos = now - self.drag_offset
            self.px = pos.x() + self.width() / 2
            self.py = pos.y() + self.foot_offset()
            self.move(pos)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self.dragged:
            vx = 0.0
            vy = 0.0
            if len(self.drag_samples) >= 2:
                t0, x0, y0 = self.drag_samples[0]
                t1, x1, y1 = self.drag_samples[-1]
                dt = t1 - t0
                if dt > 0.001:
                    vx = (x1 - x0) / dt * TICK_MS / 1000
                    vy = (y1 - y0) / dt * TICK_MS / 1000
            vx = max(-40.0, min(40.0, vx))
            vy = max(-40.0, min(40.0, vy))
            speed = math.hypot(vx, vy)
            if self.gravity or speed > 4:
                self.start_fall(vx, vy)
            else:
                self.clamp_free()
                self.sync_window()
                self.start_idle(2)
        else:
            self.hop()
        self.press_global = None
        self.dragged = False

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.interact()
            self.start_throw()

    def hover_move(self, x):
        if self.last_hover_x is not None:
            d = x - self.last_hover_x
            if d != 0:
                sign = 1 if d > 0 else -1
                if self.last_hover_sign != 0 and sign != self.last_hover_sign:
                    self.rub_ticks.append(self.ticks)
                self.last_hover_sign = sign
        self.last_hover_x = x
        self.rub_ticks = [t for t in self.rub_ticks if self.ticks - t < 35]
        if len(self.rub_ticks) >= 4 and self.ticks - self.last_pet_tick > 40:
            self.rub_ticks = []
            self.on_petted()

    def leaveEvent(self, event):
        self.last_hover_x = None
        self.last_hover_sign = 0
        self.rub_ticks = []

    def on_petted(self):
        self.last_pet_tick = self.ticks
        self.interact()
        if self.state == "walk":
            self.start_idle(2)
        if self.state in ("idle", "walk"):
            self.facing = "front"
        self.hearts()
        self.hop()
        self.say(random.choice(PET_LINES), 60)

    def change_scale(self, value):
        self.scale = value
        self.build_frames()
        self.apply_size()
        if not self.gravity:
            self.clamp_free()
        if self.state == "walk":
            self.start_idle(1)
        if self.bubble is not None:
            self.bubble.dispose()
            self.bubble = None
        if self.zz is not None:
            self.stop_zz()
            self.zz = ZzFx(self.scale)
        self.sync_window()
        self.update_fx_positions()
        self.update()

    def set_mode(self, mode):
        self.interact()
        self.mode = mode
        if self.state == "walk":
            self.start_idle(1)
        if mode == "follow":
            self.say("따라갈게!", 50)
        elif mode == "flee":
            self.say("잡아봐라~", 50)

    def set_gravity(self, on):
        self.interact()
        self.gravity = on
        if self.state == "walk":
            self.start_idle(1)
        if on:
            self.start_fall()
        else:
            self.ride = None

    def toggle_pause(self, checked):
        self.paused = checked
        if checked and self.state == "walk":
            self.start_idle(1)

    def drop_food(self, pos):
        side = random.choice([-1, 1])
        x = pos.x() + side * random.uniform(80, 160) * self.scale / 2
        g = self.geo()
        x = min(max(x, g.left() + 20), g.right() - 20)
        y = max(pos.y() - 60 * self.scale / 2, g.top() + 40)
        FoodItem(x, y)
        for pet in list(PETS):
            pet.interact()

    def spawn_friend(self):
        g = self.geo()
        x = random.uniform(g.left() + 100, g.right() - 100)
        pet = SudaengPet(self.sheet, x)
        pet.scale = self.scale
        pet.build_frames()
        pet.apply_size()
        pet.gravity = self.gravity
        pet.mode = self.mode
        pet.py = float(g.top() + pet.foot_offset())
        pet.px = x
        pet.show()
        pet.start_fall(random.uniform(-3, 3), 0)

    def dispose_pet(self):
        if not self.alive:
            return
        self.alive = False
        self.timer.stop()
        if self.bubble is not None:
            self.bubble.dispose()
            self.bubble = None
        self.stop_zz()
        if self.eat_food is not None:
            self.eat_food.eater = None
            self.eat_food = None
        if self in PETS:
            PETS.remove(self)
        self.close()
        self.deleteLater()
        if not PETS:
            quit_all()

    def contextMenuEvent(self, event):
        self.interact()
        click_pos = event.globalPos()
        menu = QMenu(self)

        throw_action = QAction("조개 던지기", menu)
        throw_action.triggered.connect(self.start_throw)
        menu.addAction(throw_action)

        food_action = QAction("먹이 주기", menu)
        food_action.triggered.connect(lambda checked=False, p=click_pos: self.drop_food(p))
        menu.addAction(food_action)

        mode_menu = menu.addMenu("움직임")
        mode_group = QActionGroup(mode_menu)
        for key, label in (("free", "자유롭게"), ("follow", "마우스 따라오기"), ("flee", "마우스 피해 도망가기")):
            act = QAction(label, mode_menu)
            act.setCheckable(True)
            act.setChecked(self.mode == key)
            act.triggered.connect(lambda checked=False, m=key: self.set_mode(m))
            mode_group.addAction(act)
            mode_menu.addAction(act)

        gravity_action = QAction("중력 모드 (창 위 걷기)", menu)
        gravity_action.setCheckable(True)
        gravity_action.setChecked(self.gravity)
        gravity_action.toggled.connect(self.set_gravity)
        menu.addAction(gravity_action)

        pause_action = QAction("가만히 있기", menu)
        pause_action.setCheckable(True)
        pause_action.setChecked(self.paused)
        pause_action.toggled.connect(self.toggle_pause)
        menu.addAction(pause_action)

        size_menu = menu.addMenu("크기")
        size_group = QActionGroup(size_menu)
        for value in (1, 2, 3, 4):
            act = QAction(str(value) + "배", size_menu)
            act.setCheckable(True)
            act.setChecked(self.scale == value)
            act.triggered.connect(lambda checked=False, v=value: self.change_scale(v))
            size_group.addAction(act)
            size_menu.addAction(act)

        menu.addSeparator()
        friend_action = QAction("수댕이 한 마리 더", menu)
        friend_action.triggered.connect(self.spawn_friend)
        menu.addAction(friend_action)

        bye_action = QAction("이 수댕이 보내기", menu)
        bye_action.triggered.connect(self.dispose_pet)
        menu.addAction(bye_action)

        quit_action = QAction("모두 종료", menu)
        quit_action.triggered.connect(quit_all)
        menu.addAction(quit_action)

        menu.exec(click_pos)


def quit_all():
    for fx in list(FX):
        fx.dispose()
    for pet in list(PETS):
        pet.alive = False
        pet.timer.stop()
    QApplication.instance().quit()


def main():
    global WIN
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    WIN = create_window_surfaces()
    sheet = QPixmap(resource_path(SHEET_NAME))
    if sheet.isNull():
        raise SystemExit(SHEET_NAME + " 파일을 찾을 수 없습니다. 스크립트와 같은 폴더에 두세요.")
    pet = SudaengPet(sheet)
    pet.show()
    pet.say("수댕!", 60)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
