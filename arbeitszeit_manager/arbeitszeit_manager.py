import tkinter as tk
from tkinter import simpledialog, messagebox, ttk, filedialog
from tkcalendar import Calendar
import sqlite3
import shutil
import os
import json
import csv
from datetime import datetime

CONFIG_FILE = 'config.json'


class ConfigManager:

    def __init__(self):
        self.config = self.load_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as file:
                return json.load(file)
        return {"backup_path": "", "export_path": ""}

    def save_config(self):
        with open(CONFIG_FILE, 'w') as file:
            json.dump(self.config, file)

    def set_backup_path(self, path):
        self.config['backup_path'] = path
        self.save_config()

    def set_export_path(self, path):
        self.config['export_path'] = path
        self.save_config()


class DatabaseManager:

    def __init__(self, db_name='arbeitszeiten.db'):
        self.db_name = db_name
        self.conn = sqlite3.connect(self.db_name)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS arbeitszeiten
                               (id INTEGER PRIMARY KEY, startzeit TEXT, endzeit TEXT, datum TEXT, ueberstunden REAL)'''
                            )
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS notizen
                               (id INTEGER PRIMARY KEY, datum TEXT UNIQUE, notiz TEXT, urlaubstag INTEGER DEFAULT 0, urlaubsstatus TEXT)'''
                            )
        self.conn.commit()

    def insert_arbeitszeit(self, startzeit, endzeit, datum, arbeitsstunden):
        self.cursor.execute(
            'INSERT INTO arbeitszeiten (startzeit, endzeit, datum, ueberstunden) VALUES (?, ?, ?, ?)',
            (startzeit, endzeit, datum, arbeitsstunden))
        self.conn.commit()

    def insert_or_update_notiz(self, datum, notiz, urlaubstag, urlaubsstatus):
        self.cursor.execute(
            'INSERT OR REPLACE INTO notizen (datum, notiz, urlaubstag, urlaubsstatus) VALUES (?, ?, ?, ?)',
            (datum, notiz, urlaubstag, urlaubsstatus))
        self.conn.commit()

    def get_urlaubstage(self):
        self.cursor.execute(
            'SELECT datum, urlaubsstatus FROM notizen WHERE urlaubstag=1')
        return self.cursor.fetchall()

    def get_notizen(self):
        self.cursor.execute(
            'SELECT datum, notiz, urlaubsstatus FROM notizen ORDER BY datum')
        return self.cursor.fetchall()

    def get_arbeitszeiten(self):
        self.cursor.execute('SELECT * FROM arbeitszeiten')
        return self.cursor.fetchall()

    def close(self):
        self.conn.close()


class TimeTracker:

    def __init__(self, db_manager, backup_func):
        self.db_manager = db_manager
        self.startzeit = None
        self.backup_func = backup_func

    def start(self):
        self.startzeit = datetime.now()

    def stop(self):
        if self.startzeit is None:
            raise Exception("Startzeit nicht gesetzt")

        endzeit = datetime.now()
        arbeitsstunden = (endzeit - self.startzeit).seconds / 3600.0
        datum = datetime.now().strftime('%Y-%m-%d')
        self.db_manager.insert_arbeitszeit(self.startzeit.strftime('%H:%M:%S'),
                                           endzeit.strftime('%H:%M:%S'), datum,
                                           arbeitsstunden)
        self.startzeit = None
        self.backup_func()
        return arbeitsstunden, endzeit


class CalendarManager:

    def __init__(self, db_manager, calendar_widget, backup_func):
        self.db_manager = db_manager
        self.calendar = calendar_widget
        self.backup_func = backup_func

    def datum_geklickt(self, event):
        datum = self.calendar.selection_get().strftime('%Y-%m-%d')
        notiz = simpledialog.askstring("Notiz eingeben", f"Notiz für {datum}:")

        if notiz is not None:
            urlaub = messagebox.askyesno("Urlaub", "Ist das ein Urlaubstag?")
            urlaubstag = 1 if urlaub else 0
            urlaubsstatus = None
            if urlaubstag:
                urlaubsstatus = simpledialog.askstring(
                    "Urlaubsstatus",
                    "Status eingeben (beantragt/genehmigt/abgelehnt):")
                if urlaubsstatus not in [
                        'beantragt', 'genehmigt', 'abgelehnt'
                ]:
                    urlaubsstatus = 'beantragt'

            self.db_manager.insert_or_update_notiz(datum, notiz, urlaubstag,
                                                   urlaubsstatus)
            self.aktualisiere_kalender()
            self.backup_func()

    def aktualisiere_kalender(self):
        self.calendar.calevent_remove('all')

        eintraege = self.db_manager.get_urlaubstage()
        for datum_str, status in eintraege:
            datum = datetime.strptime(datum_str, '%Y-%m-%d')
            if status == "beantragt":
                self.calendar.calevent_create(datum, "Urlaub beantragt",
                                              "beantragt")
            elif status == "genehmigt":
                self.calendar.calevent_create(datum, "Urlaub genehmigt",
                                              "genehmigt")
            elif status == "abgelehnt":
                self.calendar.calevent_create(datum, "Urlaub abgelehnt",
                                              "abgelehnt")

        self.calendar.tag_config('beantragt', background='orange')
        self.calendar.tag_config('genehmigt', background='lightgreen')
        self.calendar.tag_config('abgelehnt', background='red')


class AppGUI:

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Arbeitszeit Dokumentation")
        self.config_manager = ConfigManager()
        self.db_manager = DatabaseManager()
        self.personalnummer = ""
        self.name = ""

        # Initialize GUI elements first
        self.cal = None  # Initialize as None first
        self.setup_gui()

        # Now create managers after GUI elements exist
        self.calendar_manager = CalendarManager(self.db_manager, self.cal,
                                                self.backup_datenbank)
        self.time_tracker = TimeTracker(self.db_manager, self.backup_datenbank)

        # Bind calendar after manager exists
        self.cal.bind("<<CalendarSelected>>",
                      self.calendar_manager.datum_geklickt)

        # Update displays
        self.calendar_manager.aktualisiere_kalender()
        self.update_zeit()
        self.update_uebersicht()

        self.root.mainloop()

    def setup_gui(self):
        self.label_zeit = tk.Label(self.root, font=("Arial", 14))
        self.label_zeit.pack()

        frame_user = tk.Frame(self.root)
        frame_user.pack(pady=5)
        tk.Label(frame_user, text="Personalnummer:").grid(row=0, column=0)
        self.entry_personalnummer = tk.Entry(frame_user)
        self.entry_personalnummer.grid(row=0, column=1)
        tk.Label(frame_user, text="Name:").grid(row=1, column=0)
        self.entry_name = tk.Entry(frame_user)
        self.entry_name.grid(row=1, column=1)

        self.label_startzeit = tk.Label(self.root,
                                        text="Startzeit: Noch nicht gestartet")
        self.label_startzeit.pack()

        self.label_endzeit = tk.Label(self.root,
                                      text="Endzeit: Noch nicht beendet")
        self.label_endzeit.pack()

        self.label_arbeitsstunden = tk.Label(
            self.root, text="Geleistete Stunden heute: 0")
        self.label_arbeitsstunden.pack()

        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=5)
        tk.Button(button_frame,
                  text="Dienstzeit Starten",
                  command=self.start_dienstzeit).grid(row=0, column=0)
        tk.Button(button_frame,
                  text="Dienstzeit Beenden",
                  command=self.stop_dienstzeit).grid(row=0, column=1)
        tk.Button(button_frame,
                  text="Export Monat",
                  command=self.exportiere_bericht).grid(row=0, column=2)
        tk.Button(button_frame,
                  text="Backup Speicherort",
                  command=self.speicherort_waehlen).grid(row=0, column=3)

        self.cal = Calendar(self.root,
                            selectmode='day',
                            date_pattern='yyyy-mm-dd')
        self.cal.pack(pady=20)
        # Calendar binding will be done after calendar_manager is initialized

        self.tree = ttk.Treeview(self.root,
                                 columns=("Datum", "Notiz", "Status"),
                                 show='headings')
        self.tree.heading("Datum", text="Datum")
        self.tree.heading("Notiz", text="Notiz")
        self.tree.heading("Status", text="Status")
        self.tree.pack(pady=10, fill="both", expand=True)

    def start_dienstzeit(self):
        self.personalnummer = self.entry_personalnummer.get()
        self.name = self.entry_name.get()
        if not self.personalnummer or not self.name:
            messagebox.showerror("Fehler", "Personalnummer und Name eingeben!")
            return
        self.time_tracker.start()
        self.label_startzeit.config(
            text=f"Startzeit: {datetime.now().strftime('%H:%M:%S')}")

    def stop_dienstzeit(self):
        try:
            arbeitsstunden, endzeit = self.time_tracker.stop()
            self.label_endzeit.config(
                text=f"Endzeit: {endzeit.strftime('%H:%M:%S')}")
            self.label_arbeitsstunden.config(
                text=f"Geleistete Stunden heute: {arbeitsstunden:.2f}")
            self.update_uebersicht()
            messagebox.showinfo("Erfassung", "Dienstzeit beendet")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def update_zeit(self):
        self.label_zeit.config(text=datetime.now().strftime('%H:%M:%S'))
        self.root.after(1000, self.update_zeit)

    def update_uebersicht(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        for datum, notiz, status in self.db_manager.get_notizen():
            self.tree.insert("",
                             tk.END,
                             values=(datum, notiz, status if status else "-"))

    def backup_datenbank(self):
        backup_path = self.config_manager.config.get('backup_path', '')
        if backup_path and os.path.exists(backup_path):
            shutil.copy('arbeitszeiten.db',
                        os.path.join(backup_path, 'arbeitszeiten_backup.db'))

    def speicherort_waehlen(self):
        pfad = filedialog.askdirectory()
        if pfad:
            self.config_manager.set_backup_path(pfad)
            self.config_manager.set_export_path(pfad)

    def exportiere_bericht(self):
        export_path = self.config_manager.config.get('export_path', '')
        if not export_path:
            messagebox.showerror("Fehler", "Kein Exportpfad festgelegt!")
            return
        filename = os.path.join(
            export_path,
            f"Arbeitszeitbericht_{datetime.now().strftime('%Y_%m')}.csv")
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                "Personalnummer", "Name", "Datum", "Startzeit", "Endzeit",
                "Arbeitsstunden", "Notiz", "Urlaubsstatus"
            ])
            for eintrag in self.db_manager.get_arbeitszeiten():
                arbeitszeit_id, start, end, datum, std = eintrag
                self.db_manager.cursor.execute(
                    'SELECT notiz, urlaubsstatus FROM notizen WHERE datum=?',
                    (datum, ))
                notiz_daten = self.db_manager.cursor.fetchone()
                if notiz_daten:
                    notiz, urlaubsstatus = notiz_daten
                else:
                    notiz, urlaubsstatus = '', ''
                writer.writerow([
                    self.personalnummer, self.name, datum, start, end,
                    f"{std:.2f}", notiz, urlaubsstatus
                ])
        messagebox.showinfo("Erfolg", f"Bericht gespeichert: {filename}")


if __name__ == "__main__":
    AppGUI()
