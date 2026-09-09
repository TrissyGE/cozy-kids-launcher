"""Confirm compositor-managed fullscreen for an owned X11/XWayland app.

Runs only in the tile supervisor, never in the HTTP server or Tk process. No
keyboard/mouse grabs, global shortcuts, title matching or wmctrl dependency.
"""

import ctypes as c


class ClientMessage(c.Structure):
    _fields_ = [
        ("type", c.c_int), ("serial", c.c_ulong), ("send_event", c.c_int),
        ("display", c.c_void_p), ("window", c.c_ulong),
        ("message_type", c.c_ulong), ("format", c.c_int),
        ("data", c.c_long * 5),
    ]


class XEvent(c.Union):
    _fields_ = [("client", ClientMessage), ("padding", c.c_long * 24)]


class X11Fullscreen:
    """Request fullscreen only for normal windows belonging to supplied PIDs."""

    def __init__(self):
        self.display = None
        self.previous_handler = None
        self.handler_installed = False
        self.atoms = {}
        self.requested = set()
        self.library = lib = c.CDLL("libX11.so.6")
        signatures = {
            "XOpenDisplay": ([c.c_char_p], c.c_void_p),
            "XDefaultRootWindow": ([c.c_void_p], c.c_ulong),
            "XInternAtom": ([c.c_void_p, c.c_char_p, c.c_int], c.c_ulong),
            "XGetWindowProperty": ([c.c_void_p, c.c_ulong, c.c_ulong,
                                    c.c_long, c.c_long, c.c_int, c.c_ulong,
                                    c.POINTER(c.c_ulong), c.POINTER(c.c_int),
                                    c.POINTER(c.c_ulong), c.POINTER(c.c_ulong),
                                    c.POINTER(c.c_void_p)], c.c_int),
            "XFree": ([c.c_void_p], c.c_int),
            "XSendEvent": ([c.c_void_p, c.c_ulong, c.c_int, c.c_long,
                            c.POINTER(XEvent)], c.c_int),
            "XSync": ([c.c_void_p, c.c_int], c.c_int),
            "XCloseDisplay": ([c.c_void_p], c.c_int),
            "XSetErrorHandler": ([c.c_void_p], c.c_void_p),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(lib, name)
            function.argtypes, function.restype = arguments, result
        try:
            self.display = lib.XOpenDisplay(None)
            if not self.display:
                raise OSError("Cannot connect to the X11 display for fullscreen")
            # A window can disappear between enumeration and a property read.
            # This supervisor owns its only X connection; ignore such X errors
            # and let bounded confirmation fail, not Xlib's fatal default.
            self.error_handler = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_void_p)(lambda *_: 0)
            self.previous_handler = lib.XSetErrorHandler(self.error_handler)
            self.handler_installed = True
            self.root = lib.XDefaultRootWindow(self.display)
            supported = self.values(self.root, "_NET_SUPPORTED", "ATOM")
            if self.atom("_NET_WM_STATE_FULLSCREEN") not in supported:
                raise OSError("The window manager does not advertise fullscreen")
        except Exception:
            self.close()
            raise

    def atom(self, name):
        if name not in self.atoms:
            self.atoms[name] = self.library.XInternAtom(self.display, name.encode("ascii"), 0)
        return self.atoms[name]

    def values(self, window, name, expected_type):
        actual_type, count, remaining = c.c_ulong(), c.c_ulong(), c.c_ulong()
        actual_format, data = c.c_int(), c.c_void_p()
        expected = self.atom(expected_type)
        status = self.library.XGetWindowProperty(
            self.display, window, self.atom(name), 0, 4096, 0, expected,
            c.byref(actual_type), c.byref(actual_format), c.byref(count),
            c.byref(remaining), c.byref(data),
        )
        try:
            if status or actual_type.value != expected or actual_format.value != 32:
                return []
            if not data or remaining.value or count.value > 4096:
                return []
            # Xlib returns format-32 properties as native longs, also on LP64.
            values = c.cast(data, c.POINTER(c.c_ulong))
            return [int(values[index]) for index in range(count.value)]
        finally:
            if data:
                self.library.XFree(data)

    def request(self, window):
        event = XEvent()
        event.client.type = 33  # ClientMessage
        event.client.send_event = 1
        event.client.display = self.display
        event.client.window = window
        event.client.message_type = self.atom("_NET_WM_STATE")
        event.client.format = 32
        event.client.data[0] = 1  # _NET_WM_STATE_ADD, never toggle
        event.client.data[1] = self.atom("_NET_WM_STATE_FULLSCREEN")
        event.client.data[3] = 1  # application source
        sent = self.library.XSendEvent(
            self.display, self.root, 0, (1 << 19) | (1 << 20), c.byref(event),
        )
        self.library.XSync(self.display, 0)
        return bool(sent)

    def confirm(self, owned_pids):
        """True only after the WM reports fullscreen on an owned main window."""
        owned_pids = set(owned_pids)
        for window in self.values(self.root, "_NET_CLIENT_LIST", "WINDOW"):
            pids = self.values(window, "_NET_WM_PID", "CARDINAL")
            if len(pids) != 1 or pids[0] not in owned_pids:
                continue
            types = self.values(window, "_NET_WM_WINDOW_TYPE", "ATOM")
            if types and types[0] != self.atom("_NET_WM_WINDOW_TYPE_NORMAL"):
                continue
            if self.values(window, "WM_TRANSIENT_FOR", "WINDOW"):
                continue
            states = self.values(window, "_NET_WM_STATE", "ATOM")
            if self.atom("_NET_WM_STATE_FULLSCREEN") in states:
                return True
            if window not in self.requested and self.request(window):
                self.requested.add(window)
        return False

    def close(self):
        if self.display:
            self.library.XCloseDisplay(self.display)
            self.display = None
        if self.handler_installed:
            self.library.XSetErrorHandler(self.previous_handler)
            self.handler_installed = False
