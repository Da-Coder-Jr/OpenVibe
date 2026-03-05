from __future__ import annotations

import asyncio
import json
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Any
import os

import customtkinter as ctk

from openv.conductor.weave import WeaveConductor
from openv.default_config import DB_PATH, load_config
from openv.loom.client import LoomClient, LoomError
from openv.scribe.telemetry import Scribe
from openv.vault.store import SessionRecord, Vault

# Set appearance and theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class MessageBubble(ctk.CTkFrame):
    def __init__(self, master, role: str, content: str, **kwargs):
        super().__init__(master, **kwargs)
        self.role = role
        self.content = content

        # Style based on role
        if role == "user":
            fg_color = "#2563eb" # Blue-600
        elif role == "assistant":
            fg_color = "#374151" # Gray-700
        elif role == "tool":
            fg_color = "#1e293b" # Slate-800
        else:
            fg_color = "#111827"

        self.configure(fg_color=fg_color)

        self.label = ctk.CTkLabel(
            self,
            text=content if content else "...",
            wraplength=600,
            justify="left",
            font=("Inter", 13)
        )
        self.label.pack(padx=12, pady=8)

    def update_text(self, text: str):
        self.label.configure(text=text)


class FileExplorer(ctk.CTkScrollableFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, label_text="Project Files", **kwargs)
        self.refresh()

    def refresh(self):
        for child in self.winfo_children():
            child.destroy()

        try:
            for root_dir, dirs, files in os.walk(".", topdown=True):
                # Simple filter for hidden/venv dirs
                dirs[:] = [d for d in dirs if not d.startswith((".", "venv", "node_modules"))]

                rel_path = os.path.relpath(root_dir, ".")
                if rel_path == ".":
                    level = 0
                else:
                    level = rel_path.count(os.sep) + 1

                if rel_path != ".":
                    lbl = ctk.CTkLabel(self, text="  " * level + "📁 " + os.path.basename(root_dir), anchor="w")
                    lbl.pack(fill="x")

                for f in files:
                    if not f.startswith("."):
                        lbl = ctk.CTkLabel(self, text="  " * (level + 1) + "📄 " + f, anchor="w", font=("Inter", 11))
                        lbl.pack(fill="x")
        except Exception:
            pass


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

        self.root = ctk.CTk()
        self.root.title("OpenVibe Studio")
        self.root.geometry("1400x900")

        self.sessions: list[SessionRecord] = []
        self.current_session_id: str | None = None
        self.current_assistant_bubble: MessageBubble | None = None
        self.assistant_text = ""

        self._build_layout()
        self._load_sessions()

    def _build_layout(self) -> None:
        # Left Sidebar (Sessions)
        self.left_sidebar = ctk.CTkFrame(self.root, width=260, corner_radius=0)
        self.left_sidebar.pack(side="left", fill="y")

        self.logo_label = ctk.CTkLabel(
            self.left_sidebar, text="OpenVibe", font=ctk.CTkFont(size=22, weight="bold")
        )
        self.logo_label.pack(padx=20, pady=(20, 10))

        self.new_session_btn = ctk.CTkButton(
            self.left_sidebar, text="+ New Session", command=self._new_session
        )
        self.new_session_btn.pack(padx=20, pady=10, fill="x")

        self.session_scroll = ctk.CTkScrollableFrame(self.left_sidebar, label_text="Recent Sessions")
        self.session_scroll.pack(padx=10, pady=10, fill="both", expand=True)
        self.session_btns: list[ctk.CTkButton] = []

        # Right Sidebar (File Explorer)
        self.right_sidebar = ctk.CTkFrame(self.root, width=260, corner_radius=0)
        self.right_sidebar.pack(side="right", fill="y")
        self.file_explorer = FileExplorer(self.right_sidebar)
        self.file_explorer.pack(padx=10, pady=10, fill="both", expand=True)

        self.refresh_files_btn = ctk.CTkButton(
            self.right_sidebar, text="Refresh Files", command=self.file_explorer.refresh, height=30
        )
        self.refresh_files_btn.pack(padx=20, pady=10, fill="x")

        # Main Chat Area
        self.main_container = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        self.main_container.pack(side="left", fill="both", expand=True)

        # Header
        self.header = ctk.CTkFrame(self.main_container, height=60, corner_radius=0)
        self.header.pack(side="top", fill="x")
        self.title_label = ctk.CTkLabel(
            self.header, text="Select a session", font=ctk.CTkFont(size=16, weight="semibold")
        )
        self.title_label.pack(side="left", padx=20, pady=15)

        # Chat History
        self.chat_history_frame = ctk.CTkScrollableFrame(self.main_container, fg_color="#0f172a") # Slate-950
        self.chat_history_frame.pack(fill="both", expand=True, padx=20, pady=(10, 0))

        # Thinking indicator (initially hidden)
        self.thinking_label = ctk.CTkLabel(
            self.main_container, text="OpenVibe is thinking...", font=ctk.CTkFont(slant="italic"), text_color="#94a3b8"
        )

        # Input Area
        self.input_container = ctk.CTkFrame(self.main_container, height=100, corner_radius=0, fg_color="transparent")
        self.input_container.pack(side="bottom", fill="x", padx=20, pady=20)

        self.prompt_entry = ctk.CTkEntry(
            self.input_container,
            placeholder_text="Ask anything...",
            height=50,
            font=("Inter", 14)
        )
        self.prompt_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.prompt_entry.bind("<Return>", lambda _: self._send_message())

        self.send_button = ctk.CTkButton(
            self.input_container,
            text="Send",
            width=80,
            height=50,
            command=self._send_message
        )
        self.send_button.pack(side="right")

    def _load_sessions(self) -> None:
        self.sessions = self.vault.list_sessions()
        for btn in self.session_btns:
            btn.destroy()
        self.session_btns.clear()

        for session in self.sessions:
            btn = ctk.CTkButton(
                self.session_scroll,
                text=session.title[:25] + ("..." if len(session.title) > 25 else ""),
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray70", "gray30"),
                anchor="w",
                command=lambda s=session: self._select_session(s.id)
            )
            btn.pack(fill="x", pady=2)
            self.session_btns.append(btn)

    def _select_session(self, session_id: str) -> None:
        self.current_session_id = session_id
        session, _ = self.vault.resume_session(session_id)
        self.title_label.configure(text=session.title)
        self._render_messages()

    def _new_session(self) -> None:
        session = self.vault.create_session("New Session")
        self.current_session_id = session.id
        self._load_sessions()
        self._select_session(session.id)

    def _render_messages(self) -> None:
        if not self.current_session_id:
            return

        # Clear current view
        for child in self.chat_history_frame.winfo_children():
            child.destroy()

        _, messages = self.vault.resume_session(self.current_session_id)
        for msg in messages:
            self._display_message(msg.role, msg.content)

    def _display_message(self, role: str, content: str):
        if not content and role == "assistant":
             return # Skip empty assistant messages if any

        bubble = MessageBubble(self.chat_history_frame, role, content)
        if role == "user":
            bubble.pack(anchor="e", padx=10, pady=5)
        else:
            bubble.pack(anchor="w", padx=10, pady=5)

        # Scroll to bottom
        self.root.after(10, lambda: self.chat_history_frame._parent_canvas.yview_moveto(1.0))

    def _send_message(self) -> None:
        if not self.current_session_id:
            self._new_session()

        content = self.prompt_entry.get().strip()
        if not content:
            return

        self.prompt_entry.delete(0, tk.END)
        self.vault.add_message(self.current_session_id, "user", content)
        self._display_message("user", content)

        self._set_busy(True)
        self.current_assistant_bubble = None
        self.assistant_text = ""
        threading.Thread(target=self._run_turn, args=(self.current_session_id,), daemon=True).start()

    def _set_busy(self, busy: bool):
        if busy:
            self.send_button.configure(state="disabled")
            self.prompt_entry.configure(state="disabled")
            self.thinking_label.pack(side="bottom", pady=5)
        else:
            self.send_button.configure(state="normal")
            self.prompt_entry.configure(state="normal")
            self.thinking_label.pack_forget()

    def _handle_event(self, event):
        if event["type"] == "token":
            self.assistant_text += event["content"]
            if self.current_assistant_bubble is None:
                self.current_assistant_bubble = MessageBubble(self.chat_history_frame, "assistant", self.assistant_text)
                self.current_assistant_bubble.pack(anchor="w", padx=10, pady=5)
            else:
                self.current_assistant_bubble.update_text(self.assistant_text)
            self.chat_history_frame._parent_canvas.yview_moveto(1.0)
        elif event["type"] == "tool_start":
            self.thinking_label.configure(text=f"Executing tool: {event['name']}...")
            self._display_message("tool", f"Tool [{event['name']}] started...")
            self.current_assistant_bubble = None
            self.assistant_text = ""
        elif event["type"] == "tool_end":
            self.thinking_label.configure(text="OpenVibe is thinking...")
            self._display_message("tool", f"Tool [{event['name']}] -> {event['result'].message}")
            if event["name"] in ("smart_write", "shell_execute"):
                self.file_explorer.refresh()
        elif event["type"] == "done":
            self._set_busy(False)
            self._load_sessions()

    def _run_turn(self, session_id: str):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def run():
            try:
                async for event in self.conductor.ask_stream(session_id):
                    self.root.after(0, lambda e=event: self._handle_event(e))
            except Exception as e:
                self.root.after(0, lambda msg=str(e): messagebox.showerror("Error", f"Turn failed: {msg}"))
                self.root.after(0, lambda: self._set_busy(False))

        loop.run_until_complete(run())

    def run(self) -> None:
        self.root.mainloop()

if __name__ == "__main__":
    OpenVGUI().run()
