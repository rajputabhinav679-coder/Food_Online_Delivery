"""Navigation helpers used by every page.

* render_top_bar()  - "Back", "Refresh" and "Auto refresh" controls that
                      are shown on top of every page.
* section_nav()     - section selector (replaces st.tabs) that remembers the
                      sections you visited so that "Back" can return to them.
* run_auto_refresh() - runs a function as a fragment that refreshes itself
                      every few seconds (can be switched off by the user).
"""
import streamlit as st
import streamlit.components.v1 as components
from config.app_config import AUTO_REFRESH_SECONDS

MAX_HISTORY = 20

def _current_key(scope):
    return f"nav_{scope}"

def _last_key(scope):
    return f"nav_last_{scope}"

def _history_key(scope):
    return f"nav_hist_{scope}"

# BACK BUTTON LOGIC
def _go_back(scope):
    # 1) an open checkout is closed first
    if scope == "customer" and st.session_state.get("checkout_open"):
        st.session_state.checkout_open = False
        return
    # 2) otherwise go to the previous section
    history = st.session_state.get(_history_key(scope), [])
    if history:
        previous = history.pop()
        st.session_state[_current_key(scope)] = previous
        st.session_state[_last_key(scope)] = previous

def _on_section_change(scope):
    new_section = st.session_state.get(_current_key(scope))
    last_section = st.session_state.get(_last_key(scope))
    if last_section and last_section != new_section:
        history = st.session_state.setdefault(_history_key(scope), [])
        history.append(last_section)
        del history[:-MAX_HISTORY]
    st.session_state[_last_key(scope)] = new_section

def goto_section(scope, section):
    """Open another section on the next run (call before st.rerun())."""
    st.session_state[f"goto_{scope}"] = section

# TOP BAR (BACK + REFRESH + AUTO REFRESH)
def render_top_bar(scope):
    if "auto_refresh_on" not in st.session_state:
        st.session_state["auto_refresh_on"] = True
    history = st.session_state.get(_history_key(scope), [])
    can_go_back = bool(history) or (
        scope == "customer" and st.session_state.get("checkout_open", False)
    )
    back_col, refresh_col, auto_col, _space = st.columns([1, 1, 2, 4])
    with back_col:
        st.button(
            "⬅️ Back",
            key=f"back_{scope}",
            on_click=_go_back,
            args=(scope,),
            disabled=not can_go_back,
            use_container_width=True
        )
    with refresh_col:
        # clicking any button reruns the page = fresh data
        st.button("🔄 Refresh", key=f"refresh_{scope}", use_container_width=True)
    with auto_col:
        st.toggle(f"Auto refresh ({AUTO_REFRESH_SECONDS}s)", key="auto_refresh_on")

# SECTION SELECTOR
def section_nav(scope, options, labels=None):
    """Show the section selector and return the selected section."""
    labels = labels or {}
    current_key = _current_key(scope)
    last_key = _last_key(scope)
    history_key = _history_key(scope)
    if st.session_state.get(current_key) not in options:
        st.session_state[current_key] = options[0]
        st.session_state[last_key] = options[0]
    st.session_state.setdefault(history_key, [])
    st.session_state.setdefault(last_key, st.session_state[current_key])
    # jump requested by the program (for example after placing an order)
    target = st.session_state.pop(f"goto_{scope}", None)
    if target in options and target != st.session_state[current_key]:
        st.session_state[history_key].append(st.session_state[current_key])
        st.session_state[current_key] = target
        st.session_state[last_key] = target
    st.radio(
        "Section",
        options,
        key=current_key,
        format_func=lambda option: labels.get(option, option),
        horizontal=True,
        label_visibility="collapsed",
        on_change=_on_section_change,
        args=(scope,)
    )
    return st.session_state[current_key]

# AUTO REFRESH
def run_auto_refresh(function, *args, **kwargs):
    """Run function as a fragment that reruns itself every few seconds.

    If the user switches "Auto refresh" off, the function is still shown
    but does not refresh by itself.
    """
    seconds = (AUTO_REFRESH_SECONDS if st.session_state.get("auto_refresh_on", True) else None)
    st.fragment(function, run_every=seconds)(*args, **kwargs)
HIDE_PASSWORD_JS = """
<script>
const p = window.parent;
p.clearInterval(p.__pwHideTimer);
p.__pwHideTimer = p.setInterval(() => {
  p.document.querySelectorAll('[data-testid="stTextInput"]').forEach(box => {
    const input = box.querySelector('input');
    const toggle = box.querySelector('button, [role="button"]');
    if (!input || !toggle) return;
    if (input.type === 'text') {
      input.__shownAt = input.__shownAt || Date.now();
      if (Date.now() - input.__shownAt >= %d) { toggle.click(); input.__shownAt = 0; }
    } else { input.__shownAt = 0; }
  });
}, 500);
</script>
"""

def auto_hide_passwords(seconds=5):
    """A password shown with the eye icon is hidden again after some seconds."""
    components.html(HIDE_PASSWORD_JS % (seconds * 1000), height=0)
