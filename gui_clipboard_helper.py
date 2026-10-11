"""Universal clipboard and context menu support for Tkinter Entry & Text widgets.
Ensures Ctrl+V (Paste), Ctrl+C (Copy), Ctrl+X (Cut), Ctrl+A (Select All) work
across all keyboard layouts (English, Russian, etc.) and adds right-click context menu.
"""
import tkinter as tk


def enable_universal_clipboard(root_window):
    """Binds universal keyboard shortcuts and right-click context menu to all Entry and Text widgets."""
    def _on_entry_keypress(event):

        is_ctrl = bool(event.state & 0x0004) or (hasattr(event, "keysym") and "Control" in str(event.keysym))
        if not is_ctrl:
            return None

        keycode = getattr(event, "keycode", 0)
        keysym = str(getattr(event, "keysym", "")).lower()

        if keycode == 86 or keysym in ("v", "cyrillic_em"):
            try:
                text = event.widget.clipboard_get()
                try:
                    event.widget.delete("sel.first", "sel.last")
                except Exception:
                    pass
                event.widget.insert("insert", text)
                return "break"
            except Exception:
                return "break"

        elif keycode == 67 or keysym in ("c", "cyrillic_es"):
            try:
                text = event.widget.selection_get()
                event.widget.clipboard_clear()
                event.widget.clipboard_append(text)
                return "break"
            except Exception:
                return "break"

        elif keycode == 88 or keysym in ("x", "cyrillic_che"):
            try:
                text = event.widget.selection_get()
                event.widget.clipboard_clear()
                event.widget.clipboard_append(text)
                event.widget.delete("sel.first", "sel.last")
                return "break"
            except Exception:
                return "break"

        elif keycode == 65 or keysym in ("a", "cyrillic_ef"):
            try:
                if isinstance(event.widget, tk.Entry):
                    event.widget.select_range(0, "end")
                    event.widget.icursor("end")
                elif isinstance(event.widget, tk.Text):
                    event.widget.tag_add("sel", "1.0", "end")
                return "break"
            except Exception:
                return "break"

        return None

    def _show_context_menu(event):
        widget = event.widget
        menu = tk.Menu(widget, tearoff=0, bg="#1e222d", fg="#ffffff", activebackground="#D13639", activeforeground="#ffffff")

        def do_cut():
            try:
                text = widget.selection_get()
                widget.clipboard_clear()
                widget.clipboard_append(text)
                widget.delete("sel.first", "sel.last")
            except Exception:
                pass

        def do_copy():
            try:
                text = widget.selection_get()
                widget.clipboard_clear()
                widget.clipboard_append(text)
            except Exception:
                pass

        def do_paste():
            try:
                text = widget.clipboard_get()
                try:
                    widget.delete("sel.first", "sel.last")
                except Exception:
                    pass
                widget.insert("insert", text)
            except Exception:
                pass

        def do_select_all():
            try:
                if isinstance(widget, tk.Entry):
                    widget.select_range(0, "end")
                    widget.icursor("end")
                elif isinstance(widget, tk.Text):
                    widget.tag_add("sel", "1.0", "end")
            except Exception:
                pass

        has_selection = False
        try:
            has_selection = bool(widget.selection_get())
        except Exception:
            pass

        has_clipboard = False
        try:
            has_clipboard = bool(widget.clipboard_get())
        except Exception:
            pass

        menu.add_command(label="Вставить (Ctrl+V)", command=do_paste, state="normal" if has_clipboard else "disabled")
        menu.add_command(label="Копировать (Ctrl+C)", command=do_copy, state="normal" if has_selection else "disabled")
        menu.add_command(label="Вырезать (Ctrl+X)", command=do_cut, state="normal" if has_selection else "disabled")
        menu.add_separator()
        menu.add_command(label="Выделить всё (Ctrl+A)", command=do_select_all)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    root_window.bind_class("Entry", "<KeyPress>", _on_entry_keypress, add="+")
    root_window.bind_class("Entry", "<Button-3>", _show_context_menu, add="+")
    root_window.bind_class("Text", "<KeyPress>", _on_entry_keypress, add="+")
    root_window.bind_class("Text", "<Button-3>", _show_context_menu, add="+")
