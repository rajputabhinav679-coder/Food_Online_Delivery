"""A tiny stand-in for Streamlit so the screens can be tested without a browser.

It records every piece of text a screen would show, lets a test "press"
buttons by their label, and raises Rerun / Stop like the real st.rerun() and
st.stop(). It is not a replacement for opening the app once in a browser.
"""
import sys
import types

class Rerun(Exception):
    pass

class Stop(Exception):
    pass

class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        self.pop(name, None)

class Ctx:
    """Stands for columns, tabs, containers, forms, expanders and the sidebar."""
    def __init__(self, st):
        self._st = st

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getattr__(self, name):
        return getattr(self._st, name)

class FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.reset()
        self.secrets = {}
        self.sidebar = Ctx(self)
        self.components = types.ModuleType("streamlit.components")
        self.components.v1 = types.ModuleType("streamlit.components.v1")
        self.components.v1.html = lambda *a, **k: None

    def reset(self):
        self.session_state = SessionState()
        self.texts = []
        self.pressed = []

    # helpers for tests
    def press(self, *labels):
        self.pressed.extend(labels)

    def output(self):
        return "\n".join(self.texts)

    def _say(self, *values):
        for value in values:
            if isinstance(value, str):
                self.texts.append(value)

    # text output
    def _text(self, body="", *args, **kwargs):
        self._say(body)

    write = markdown = caption = subheader = title = header = text = code = _text
    success = error = warning = info = _text

    def toast(self, body, *args, **kwargs):
        self._say(body)

    def metric(self, label, value, *args, **kwargs):
        self._say(label, str(value))

    def image(self, *args, **kwargs):
        pass

    def divider(self):
        pass

    def dataframe(self, data, *args, **kwargs):
        self._say(str(data))

    def set_page_config(self, *args, **kwargs):
        pass

    # layout
    def columns(self, spec, *args, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [Ctx(self) for _ in range(count)]

    def tabs(self, labels):
        self._say(*labels)
        return [Ctx(self) for _ in labels]

    def container(self, *args, **kwargs):
        return Ctx(self)

    def expander(self, label, *args, **kwargs):
        self._say(label)
        return Ctx(self)

    def form(self, *args, **kwargs):
        return Ctx(self)

    def fragment(self, function, run_every=None):
        return function

    def rerun(self):
        raise Rerun()

    def stop(self):
        raise Stop()

    # input widgets
    def button(self, label, key=None, on_click=None, args=(), **kwargs):
        self._say(label)
        for wanted in list(self.pressed):
            if wanted in label:
                self.pressed.remove(wanted)
                if on_click:
                    on_click(*args)
                return True
        return False

    def form_submit_button(self, label, *args, **kwargs):
        return self.button(label)

    def download_button(self, label, *args, **kwargs):
        self._say(label)
        return False

    def _choice(self, label, options, index=0, format_func=str, key=None, **kwargs):
        self._say(label, *[format_func(option) for option in options])
        if key is not None and key in self.session_state:
            return self.session_state[key]
        if index is None or not options:
            return None
        value = options[index]
        if key is not None:
            self.session_state[key] = value
        return value

    radio = selectbox = _choice

    def number_input(self, label, min_value=None, value=None, key=None, **kwargs):
        if key is not None and key in self.session_state:
            return self.session_state[key]
        return value if value is not None else min_value

    def text_input(self, label, value="", key=None, **kwargs):
        self._say(label)
        if key is not None and key in self.session_state:
            return self.session_state[key]
        return value

    text_area = text_input

    def checkbox(self, label, value=False, key=None, **kwargs):
        self._say(label)
        if key is not None and key in self.session_state:
            return self.session_state[key]
        return value

    def toggle(self, label, key=None, **kwargs):
        self._say(label)
        return self.session_state.get(key, True)

    def file_uploader(self, label, *args, **kwargs):
        self._say(label)
        return None

    def date_input(self, label, value=None, *args, **kwargs):
        return value

_NAMES = ["streamlit", "streamlit.components", "streamlit.components.v1"]

def install():
    """Put the fake in place of Streamlit. Returns (fake, undo_function)."""
    fake = FakeStreamlit()
    saved = {name: sys.modules.get(name) for name in _NAMES}
    sys.modules["streamlit"] = fake
    sys.modules["streamlit.components"] = fake.components
    sys.modules["streamlit.components.v1"] = fake.components.v1
    # screens imported while the fake is active must not stay cached
    before = set(sys.modules)

    def undo():
        for name in list(sys.modules):
            if name not in before and name.split(".")[0] in ("ui", "app"):
                del sys.modules[name]
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    return fake, undo
