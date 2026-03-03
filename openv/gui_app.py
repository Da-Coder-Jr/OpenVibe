from __future__ import annotations

import asyncio
import threading
import tkinter as tk
from tkinter import messagebox
from tkinter.scrolledtext import ScrolledText

from openv.conductor.weave import WeaveConductor
from openv.default_config import DB_PATH, load_config
from openv.loom.client import LoomClient, LoomError
from openv.scribe.telemetry import Scribe
from openv.vault.store import SessionRecord, Vault


class OpenVGUI:
    def __init__(self) -> None:
        self.config = load_config()
        self.scribe = Scribe()
        self.vault = Vault(DB_PATH)
        self.loom = LoomClient(
            base_url=self.config["ollama"]["base_url"],
            timeout=int(self.config["ollama"]["timeout"]),
            scribe=self.scribe,
        )
        self.conductor = WeaveConductor(
            vault=self.vault,
            loom=self.loom,
            scribe=self.scribe,
            model=self.config["ollama"]["model"],
        )

        self.root = tk.Tk()
        self.root.title("OpenVibe Studio")
        self.root.geometry("1080x720")

        self.sessions: list[SessionRecord] = []
        self.current_session_id: str | None = None
        self._build_layout()
        self._load_sessions()

    def _build_layout(self) -> None:
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        left_panel = tk.Frame(self.root, bg="#111827", padx=10, pady=10)
        left_panel.grid(row=0, column=0, sticky="nsw")
        tk.Label(
            left_panel,
            text="OpenVibe",
            fg="#22d3ee",
            bg="#111827",
            font=("Helvetica", 16, "bold"),
        ).pack(anchor="w")
        tk.Button(left_panel, text="+ New Session", command=self._new_session).pack(fill="x", pady=(10, 6))

        self.session_list = tk.Listbox(
            left_panel,
            width=32,
            height=35,
            bg="#1f2937",
            fg="#f9fafb",
            highlightthickness=0,
            selectbackground="#374151",
        )
        self.session_list.pack(fill="both", expand=True)
        self.session_list.bind("<<ListboxSelect>>", self._on_select_session)

        right_panel = tk.Frame(self.root, bg="#0b1220", padx=10, pady=10)
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.grid_rowconfigure(1, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)

        self.title_var = tk.StringVar(value="No session selected")
        tk.Label(
            right_panel,
            textvariable=self.title_var,
            bg="#0b1220",
            fg="#d1d5db",
            font=("Helvetica", 14, "bold"),
        ).grid(row=0, column=0, sticky="w")

        self.chat_box = ScrolledText(
            right_panel,
            wrap="word",
            bg="#111827",
            fg="#f3f4f6",
            insertbackground="#f3f4f6",
            font=("Consolas", 11),
            padx=8,
            pady=8,
        )
        self.chat_box.grid(row=1, column=0, sticky="nsew", pady=(8, 10))
        self.chat_box.configure(state="disabled")

        input_row = tk.Frame(right_panel, bg="#0b1220")
        input_row.grid(row=2, column=0, sticky="ew")
        input_row.grid_columnconfigure(0, weight=1)

        self.prompt = tk.Entry(input_row, bg="#1f2937", fg="#f9fafb", insertbackground="#f9fafb")
        self.prompt.grid(row=0, column=0, sticky="ew", ipady=8)
        self.prompt.bind("<Return>", lambda _evt: self._send_message())

        self.send_btn = tk.Button(input_row, text="Send", command=self._send_message)
        self.send_btn.grid(row=0, column=1, padx=(8, 0))

    def _load_sessions(self) -> None:
        self.sessions = self.vault.list_sessions()
        self.session_list.delete(0, tk.END)
        for row in self.sessions:
            label = f"{row.title}  [{row.id[:8]}]"
            self.session_list.insert(tk.END, label)

    def _new_session(self) -> None:
        session = self.vault.create_session("OpenV GUI Session")
        self.current_session_id = session.id
        self._load_sessions()
        self._render_messages()

    def _on_select_session(self, _event: tk.Event[tk.Misc]) -> None:
        selected = self.session_list.curselection()
        if not selected:
            return
        self.current_session_id = self.sessions[selected[0]].id
        self._render_messages()

    def _render_messages(self) -> None:
        if not self.current_session_id:
            return
        session, messages = self.vault.resume_session(self.current_session_id)
        self.title_var.set(f"{session.title} • {session.id[:8]}")
        self.chat_box.configure(state="normal")
        self.chat_box.delete("1.0", tk.END)
        for message in messages:
            self.chat_box.insert(tk.END, f"{message.role}> {message.content}\n\n")
        self.chat_box.configure(state="disabled")
        self.chat_box.see(tk.END)

    def _append_message(self, role: str, content: str) -> None:
        self.chat_box.configure(state="normal")
        self.chat_box.insert(tk.END, f"{role}> {content}\n\n")
        self.chat_box.configure(state="disabled")
        self.chat_box.see(tk.END)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.send_btn.configure(state=state)
        self.prompt.configure(state=state)

    def _send_message(self) -> None:
        if not self.current_session_id:
            self._new_session()
        if not self.current_session_id:
            return

        user_text = self.prompt.get().strip()
        if not user_text:
            return

        self.prompt.delete(0, tk.END)
        self.vault.add_message(self.current_session_id, "user", user_text)
        self._append_message("user", user_text)
        self._append_message("assistant", "…thinking…")
        self._set_busy(True)

        thread = threading.Thread(target=self._run_assistant_turn, args=(self.current_session_id,), daemon=True)
        thread.start()

    def _run_assistant_turn(self, session_id: str) -> None:
        try:
            response = asyncio.run(self.conductor.ask_once(session_id))
            self.vault.add_message(session_id, "assistant", response)
        except LoomError as exc:
            self.root.after(0, lambda: self._finalize_turn(f"Loom error: {exc}"))
            return
        except Exception as exc:
            self.root.after(0, lambda: self._finalize_turn(f"Unexpected error: {exc}"))
            return
        self.root.after(0, lambda: self._finalize_turn(response))

    def _finalize_turn(self, assistant_text: str) -> None:
        self._render_messages()
        if assistant_text and ("Unexpected" in assistant_text or "Loom error" in assistant_text):
            messagebox.showerror("OpenV GUI", assistant_text)
        self._set_busy(False)
        self._load_sessions()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    OpenVGUI().run()
