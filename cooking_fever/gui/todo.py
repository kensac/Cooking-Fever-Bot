"""Objective / task todo utility with progress and time estimates."""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from tkinter import messagebox, simpledialog, ttk
from typing import List, Optional


@dataclass
class _Task:
    title: str
    priority: str
    duration: int
    completed: bool = False


@dataclass
class _Objective:
    title: str
    repeatable: bool
    tasks: List[_Task] = field(default_factory=list)


class TodoApp:
    def __init__(self, master: tk.Misc) -> None:
        self._master = master
        self._objectives: List[_Objective] = []

        paned = tk.PanedWindow(master, sashrelief="raised")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        left = tk.Frame(paned)
        paned.add(left, width=240)
        tk.Label(left, text="Objectives", anchor="w").pack(fill="x")
        self._objective_list = tk.Listbox(left)
        self._objective_list.pack(fill="both", expand=True)
        self._objective_list.bind("<<ListboxSelect>>", lambda _e: self._update_task_grid())
        tk.Button(left, text="Add Objective", command=self._add_objective).pack(fill="x", pady=4)

        right = tk.Frame(paned)
        paned.add(right)
        tk.Label(right, text="Tasks", anchor="w").pack(fill="x")
        self._task_tree = ttk.Treeview(
            right, columns=("done", "priority", "duration"), show="tree headings"
        )
        self._task_tree.heading("#0", text="Task")
        self._task_tree.heading("done", text="Done")
        self._task_tree.heading("priority", text="Priority")
        self._task_tree.heading("duration", text="Duration (mins)")
        self._task_tree.column("done", width=60, anchor="center")
        self._task_tree.column("priority", width=90, anchor="center")
        self._task_tree.column("duration", width=110, anchor="center")
        self._task_tree.pack(fill="both", expand=True)
        self._task_tree.bind("<Double-1>", self._toggle_task)

        self._progress = ttk.Progressbar(right, maximum=100)
        self._progress.pack(fill="x", pady=(6, 2))
        self._remaining = tk.Label(right, text="Estimated time remaining: 0 mins", anchor="w")
        self._remaining.pack(fill="x")
        tk.Button(right, text="Add Task", command=self._add_task).pack(fill="x", pady=4)

    # --- helpers ------------------------------------------------------------

    def _selected_objective(self) -> Optional[_Objective]:
        selection = self._objective_list.curselection()
        if not selection:
            return None
        return self._objectives[selection[0]]

    def _add_objective(self) -> None:
        title = simpledialog.askstring("Add Objective", "Objective title", parent=self._master)
        if not title or not title.strip():
            return
        repeatable = messagebox.askyesno("Add Objective", "Is this objective repeatable?",
                                         parent=self._master)
        objective = _Objective(title.strip(), repeatable)
        self._objectives.append(objective)
        self._objective_list.insert("end", objective.title)

    def _add_task(self) -> None:
        objective = self._selected_objective()
        if objective is None:
            messagebox.showwarning("No Objective", "Select an objective first.", parent=self._master)
            return
        title = simpledialog.askstring("Add Task", "Task title", parent=self._master)
        if not title or not title.strip():
            return
        priority = simpledialog.askstring(
            "Add Task", "Priority (High/Medium/Low)", initialvalue="Medium", parent=self._master
        ) or "Medium"
        duration = simpledialog.askinteger(
            "Add Task", "Duration (mins)", initialvalue=10, minvalue=0, parent=self._master
        ) or 0
        objective.tasks.append(_Task(title.strip(), priority, duration))
        self._update_task_grid()

    def _toggle_task(self, _event) -> None:
        objective = self._selected_objective()
        if objective is None:
            return
        item = self._task_tree.focus()
        if not item:
            return
        index = int(item)
        objective.tasks[index].completed = not objective.tasks[index].completed
        self._update_task_grid()

    def _update_task_grid(self) -> None:
        self._task_tree.delete(*self._task_tree.get_children())
        objective = self._selected_objective()
        if objective is None:
            self._update_progress()
            return
        for index, task in enumerate(objective.tasks):
            self._task_tree.insert(
                "", "end", iid=str(index), text=task.title,
                values=("✓" if task.completed else "", task.priority, task.duration),
            )
        self._update_progress()

    def _update_progress(self) -> None:
        objective = self._selected_objective()
        if objective is None or not objective.tasks:
            self._progress["value"] = 0
            self._remaining.config(text="Estimated time remaining: 0 mins")
            return
        completed = sum(1 for t in objective.tasks if t.completed)
        self._progress["value"] = round(completed * 100 / len(objective.tasks))
        remaining = sum(t.duration for t in objective.tasks if not t.completed)
        self._remaining.config(text=f"Estimated time remaining: {remaining} mins")


def open_window(parent: tk.Misc) -> None:
    window = tk.Toplevel(parent)
    window.title("Todo App with Objectives")
    window.geometry("820x520")
    TodoApp(window)


def run() -> None:
    root = tk.Tk()
    root.title("Todo App with Objectives")
    root.geometry("820x520")
    TodoApp(root)
    root.mainloop()
