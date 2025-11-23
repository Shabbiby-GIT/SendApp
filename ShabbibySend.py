#!/usr/bin/env python3
"""
ShabbibySend - Modern P2P File Transfer Application
Version 2.0 - Enhanced UI & Advanced Features
"""

import socket
import threading
import time
import os
import queue
import json
from datetime import datetime
from tkinter import (
    Tk, Toplevel, Frame, Label, Button, Listbox, Text, Scrollbar, filedialog,
    messagebox, StringVar, PhotoImage, ttk, END, Canvas, HORIZONTAL, VERTICAL, BOTH, LEFT, RIGHT, TOP, BOTTOM, X, Y
)
from tkinter.font import Font
import tkinter as tk

# ---------- Configuration réseau ----------
DISCOVERY_PORT = 6020
TRANSFER_PORT = 5001
PEERS = set()
BUFFER_SIZE = 8192  # Augmenté pour de meilleures performances
DISCOVERY_MSG = b'PRESENCE_XENDER'
gui_queue = queue.Queue()

# ---------- Configuration des thèmes ----------
THEMES = {
    'light': {
        'bg': '#f5f7fa',
        'card_bg': '#ffffff',
        'primary': '#5b7fff',
        'primary_hover': '#4a6eef',
        'secondary': '#7c3aed',
        'accent': '#f59e0b',
        'success': '#10b981',
        'danger': '#ef4444',
        'text_primary': '#1f2937',
        'text_secondary': '#6b7280',
        'border': '#e5e7eb',
        'shadow': '#00000010'
    },
    'dark': {
        'bg': '#0f172a',
        'card_bg': '#1e293b',
        'primary': '#6366f1',
        'primary_hover': '#4f46e5',
        'secondary': '#8b5cf6',
        'accent': '#f59e0b',
        'success': '#10b981',
        'danger': '#ef4444',
        'text_primary': '#f1f5f9',
        'text_secondary': '#94a3b8',
        'border': '#334155',
        'shadow': '#00000030'
    }
}

# ---------- Variables globales ----------
transfer_history = []
transfer_queue = []
stats = {'sent': 0, 'received': 0, 'files_sent': 0, 'files_received': 0}
current_theme = 'light'

# ---------- Fonctions réseau ----------
def my_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
    except:
        ip = '127.0.0.1'
    return ip

def format_size(bytes_size):
    """Formate la taille en octets en format lisible"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"

def format_speed(bytes_per_sec):
    """Formate la vitesse de transfert"""
    return f"{format_size(bytes_per_sec)}/s"

def discover_peers():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(('', DISCOVERY_PORT))
    except Exception as e:
        gui_queue.put(("log", f"[DISCOVER] Impossible de binder le port {DISCOVERY_PORT}: {e}", "error"))
        return
    gui_queue.put(("log", f"[DISCOVER] Écoute UDP sur {DISCOVERY_PORT}", "info"))
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            if data == DISCOVERY_MSG:
                ip = addr[0]
                if ip != my_ip() and ip not in PEERS:
                    PEERS.add(ip)
                    gui_queue.put(("peer_add", ip))
                    gui_queue.put(("log", f"✓ Appareil découvert: {ip}", "success"))
        except:
            continue

def announce_presence():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    gui_queue.put(("log", "[ANNOUNCE] Diffusion de présence activée", "info"))
    while True:
        try:
            sock.sendto(DISCOVERY_MSG, ('<broadcast>', DISCOVERY_PORT))
            time.sleep(2)
        except:
            time.sleep(2)
            continue

def start_receiver(nonblocking=True):
    def _receive():
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(('', TRANSFER_PORT))
            s.listen(1)
        except Exception as e:
            gui_queue.put(("log", f"[RECV] Impossible d'écouter {TRANSFER_PORT}: {e}", "error"))
            return
        gui_queue.put(("log", f"[RECV] En attente de connexion sur {TRANSFER_PORT}...", "info"))
        try:
            conn, addr = s.accept()
            gui_queue.put(("log", f"[RECV] Connexion établie avec {addr[0]}", "info"))

            # Recevoir les métadonnées du fichier (JSON)
            metadata_size = int.from_bytes(conn.recv(4), byteorder='big')
            metadata_json = conn.recv(metadata_size).decode('utf-8')
            metadata = json.loads(metadata_json)

            filename = metadata.get('filename', f"recu_{int(time.time())}")
            filesize = metadata.get('filesize', 0)

            save_name = f"RECU_{filename}"
            total_received = 0
            start_time = time.time()

            gui_queue.put(("progress_receive_start", (save_name, filesize)))

            with open(save_name, "wb") as f:
                while total_received < filesize:
                    data = conn.recv(BUFFER_SIZE)
                    if not data:
                        break
                    f.write(data)
                    total_received += len(data)
                    elapsed = time.time() - start_time
                    speed = total_received / elapsed if elapsed > 0 else 0
                    gui_queue.put(("progress_receive", (total_received, filesize, filename, speed)))

            conn.close()
            s.close()

            # Enregistrer dans l'historique
            transfer_history.append({
                'type': 'received',
                'filename': save_name,
                'size': filesize,
                'peer': addr[0],
                'timestamp': datetime.now().strftime("%H:%M:%S"),
                'status': 'completed'
            })

            # Mettre à jour les statistiques
            stats['received'] += filesize
            stats['files_received'] += 1

            gui_queue.put(("log", f"✓ Fichier reçu avec succès: {save_name} ({format_size(filesize)})", "success"))
            gui_queue.put(("notify", f"Fichier reçu : {save_name}"))
            gui_queue.put(("update_stats", None))
            gui_queue.put(("update_history", None))

        except Exception as e:
            gui_queue.put(("log", f"✗ Erreur réception: {e}", "error"))
            try: s.close()
            except: pass

    if nonblocking:
        threading.Thread(target=_receive, daemon=True).start()
    else:
        _receive()

def send_file_to(ip, filepath):
    def _send():
        if not os.path.isfile(filepath):
            gui_queue.put(("notify", "Fichier non trouvé"))
            gui_queue.put(("log", f"✗ Fichier introuvable: {filepath}", "error"))
            return

        try:
            s = socket.socket()
            s.settimeout(15)
            s.connect((ip, TRANSFER_PORT))
        except Exception as e:
            gui_queue.put(("notify", f"Échec connexion {ip}: {e}"))
            gui_queue.put(("log", f"✗ Échec connexion à {ip}: {e}", "error"))
            return

        try:
            filename = os.path.basename(filepath)
            filesize = os.path.getsize(filepath)

            # Envoyer les métadonnées
            metadata = json.dumps({'filename': filename, 'filesize': filesize})
            metadata_bytes = metadata.encode('utf-8')
            s.send(len(metadata_bytes).to_bytes(4, byteorder='big'))
            s.send(metadata_bytes)
            time.sleep(0.1)

            sent = 0
            start_time = time.time()

            gui_queue.put(("progress_send_start", (filename, filesize)))

            with open(filepath, "rb") as f:
                data = f.read(BUFFER_SIZE)
                while data:
                    s.sendall(data)
                    sent += len(data)
                    elapsed = time.time() - start_time
                    speed = sent / elapsed if elapsed > 0 else 0
                    gui_queue.put(("progress_send", (sent, filesize, filename, speed)))
                    data = f.read(BUFFER_SIZE)

            s.close()

            # Enregistrer dans l'historique
            transfer_history.append({
                'type': 'sent',
                'filename': filename,
                'size': filesize,
                'peer': ip,
                'timestamp': datetime.now().strftime("%H:%M:%S"),
                'status': 'completed'
            })

            # Mettre à jour les statistiques
            stats['sent'] += filesize
            stats['files_sent'] += 1

            gui_queue.put(("notify", f"Fichier envoyé à {ip}"))
            gui_queue.put(("log", f"✓ Fichier envoyé avec succès à {ip}: {filename} ({format_size(filesize)})", "success"))
            gui_queue.put(("update_stats", None))
            gui_queue.put(("update_history", None))

        except Exception as e:
            gui_queue.put(("notify", f"Erreur envoi: {e}"))
            gui_queue.put(("log", f"✗ Erreur lors de l'envoi: {e}", "error"))
            try: s.close()
            except: pass

    threading.Thread(target=_send, daemon=True).start()

def send_multiple_files(ip, filepaths):
    """Envoie plusieurs fichiers en séquence"""
    for filepath in filepaths:
        send_file_to(ip, filepath)
        time.sleep(0.5)  # Petit délai entre les fichiers

# ---------- Classes pour widgets personnalisés ----------
class ModernButton(tk.Canvas):
    def __init__(self, parent, text, command=None, bg_color='#5b7fff', fg_color='#ffffff',
                 hover_color='#4a6eef', width=120, height=40, **kwargs):
        super().__init__(parent, width=width, height=height, highlightthickness=0, **kwargs)
        self.command = command
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.hover_color = hover_color
        self.text = text

        self.rect = self.create_rectangle(0, 0, width, height, fill=bg_color, outline='', tags='btn')
        self.text_id = self.create_text(width/2, height/2, text=text, fill=fg_color,
                                       font=('Segoe UI', 10, 'bold'), tags='btn')

        self.bind('<Button-1>', self.on_click)
        self.bind('<Enter>', self.on_enter)
        self.bind('<Leave>', self.on_leave)
        self.tag_bind('btn', '<Button-1>', self.on_click)

    def on_click(self, event=None):
        if self.command:
            self.command()

    def on_enter(self, event):
        self.itemconfig(self.rect, fill=self.hover_color)

    def on_leave(self, event):
        self.itemconfig(self.rect, fill=self.bg_color)

# ---------- GUI Principale ----------
class ModernXenderGUI:
    def __init__(self, root):
        self.root = root
        root.title("ShabbibySend - Transfert de fichiers P2P")
        root.geometry("1200x700")
        root.minsize(1000, 600)

        self.current_theme = 'light'
        self.theme = THEMES[self.current_theme]
        root.configure(bg=self.theme['bg'])

        # Variables
        self.transfer_in_progress = False
        self.current_speed = StringVar(value="0 B/s")
        self.current_progress = StringVar(value="0%")

        # Afficher le splash screen
        self.show_splash()

        # Configuration de la grille principale
        root.grid_rowconfigure(1, weight=1)
        root.grid_columnconfigure(0, weight=1)

        # Créer l'interface
        self.create_header()
        self.create_main_content()
        self.create_footer()

        # Démarrer les threads réseau
        threading.Thread(target=discover_peers, daemon=True).start()
        threading.Thread(target=announce_presence, daemon=True).start()

        # Démarrer la mise à jour de la queue
        self.root.after(200, self.process_queue)

        self.log(f"Application démarrée - IP locale: {my_ip()}", "success")
        self.log("Recherche d'appareils en cours...", "info")

    def show_splash(self):
        """Splash screen moderne avec animation"""
        splash = Toplevel()
        splash.overrideredirect(True)

        screen_width = splash.winfo_screenwidth()
        screen_height = splash.winfo_screenheight()
        splash_width = 500
        splash_height = 300
        x = (screen_width - splash_width) // 2
        y = (screen_height - splash_height) // 2

        splash.geometry(f"{splash_width}x{splash_height}+{x}+{y}")

        # Gradient background
        canvas = Canvas(splash, width=splash_width, height=splash_height, highlightthickness=0)
        canvas.pack()

        # Créer un gradient
        for i in range(splash_height):
            color_value = int(91 + (139 - 91) * (i / splash_height))
            color = f'#{color_value:02x}7fff'
            canvas.create_line(0, i, splash_width, i, fill=color)

        # Titre
        canvas.create_text(splash_width/2, 100, text="ShabbibySend",
                          fill='#ffffff', font=('Segoe UI', 32, 'bold'))
        canvas.create_text(splash_width/2, 145, text="Transfert de fichiers P2P moderne",
                          fill='#e0e7ff', font=('Segoe UI', 12))

        # Barre de progression
        progress_width = 300
        progress_x = (splash_width - progress_width) / 2
        progress_y = 200

        canvas.create_rectangle(progress_x, progress_y, progress_x + progress_width, progress_y + 6,
                                fill='#ffffff', outline='')

        progress_bar = canvas.create_rectangle(progress_x, progress_y, progress_x, progress_y + 6,
                                              fill='#ffffff', outline='')

        loading_text = canvas.create_text(splash_width/2, 230, text="Chargement...",
                                         fill='#ffffff', font=('Segoe UI', 10))

        # Animation de la barre de progression
        def animate(progress=0):
            if progress <= 100:
                new_width = progress_x + (progress_width * progress / 100)
                canvas.coords(progress_bar, progress_x, progress_y, new_width, progress_y + 6)
                canvas.itemconfig(loading_text, text=f"Chargement... {progress}%")
                splash.after(20, animate, progress + 2)
            else:
                splash.destroy()

        animate()

    def create_header(self):
        """Créer l'en-tête moderne avec dégradé"""
        header = Frame(self.root, bg=self.theme['primary'], height=100)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)

        # Conteneur pour le contenu de l'en-tête
        content = Frame(header, bg=self.theme['primary'])
        content.pack(fill='both', expand=True, padx=20, pady=10)

        # Titre et icône
        title_frame = Frame(content, bg=self.theme['primary'])
        title_frame.pack(side='left', fill='y')

        Label(title_frame, text="📁", font=('Segoe UI', 28),
              bg=self.theme['primary'], fg='#ffffff').pack(side='left', padx=(0, 10))

        title_container = Frame(title_frame, bg=self.theme['primary'])
        title_container.pack(side='left', fill='y')

        Label(title_container, text="ShabbibySend", bg=self.theme['primary'],
              fg='#ffffff', font=('Segoe UI', 20, 'bold')).pack(anchor='w')

        self.ip_var = StringVar(value=f"🌐 Votre IP : {my_ip()}")
        Label(title_container, textvariable=self.ip_var, bg=self.theme['primary'],
              fg='#e0e7ff', font=('Segoe UI', 10)).pack(anchor='w')

        # Boutons de l'en-tête
        header_buttons = Frame(content, bg=self.theme['primary'])
        header_buttons.pack(side='right', fill='y')

        # Bouton de thème
        self.theme_btn = Button(header_buttons, text="🌙", font=('Segoe UI', 16),
                               bg=self.theme['primary'], fg='#ffffff', bd=0,
                               cursor='hand2', command=self.toggle_theme)
        self.theme_btn.pack(side='left', padx=5)

        # Bouton rafraîchir
        Button(header_buttons, text="🔄", font=('Segoe UI', 16),
               bg=self.theme['primary'], fg='#ffffff', bd=0,
               cursor='hand2', command=self.refresh_peers).pack(side='left', padx=5)

    def create_main_content(self):
        """Créer le contenu principal"""
        main = Frame(self.root, bg=self.theme['bg'])
        main.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)

        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=2)
        main.grid_columnconfigure(1, weight=3)

        # Panneau gauche - Appareils et actions
        self.create_left_panel(main)

        # Panneau droit - Journal et historique
        self.create_right_panel(main)

    def create_left_panel(self, parent):
        """Panneau gauche avec appareils et contrôles"""
        left = Frame(parent, bg=self.theme['card_bg'], bd=0, relief='flat')
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Ajouter un effet d'ombre
        left.configure(highlightbackground=self.theme['border'], highlightthickness=1)

        left.grid_rowconfigure(1, weight=1)  # zone appareils → extensible
        left.grid_rowconfigure(4, weight=1)  # stats_frame si tu veux qu'elle s'étire
        left.grid_rowconfigure(6, weight=1)  # progress_container
        left.grid_columnconfigure(0, weight=1)

        # Section Appareils
        Label(left, text="📱 Appareils disponibles", bg=self.theme['card_bg'],
              fg=self.theme['text_primary'], font=('Segoe UI', 12, 'bold')).grid(
            row=0, column=0, sticky="w", padx=15, pady=(15, 5))

        # Listbox des pairs avec style
        list_frame = Frame(left, bg=self.theme['card_bg'])
        list_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=5)

        scrollbar = Scrollbar(list_frame)
        scrollbar.pack(side='right', fill='y')

        self.peers_listbox = Listbox(list_frame, yscrollcommand=scrollbar.set,
                                     bg=self.theme['bg'], fg=self.theme['text_primary'],
                                     selectbackground=self.theme['primary'],
                                     selectforeground='#ffffff',
                                     font=('Segoe UI', 10), bd=0, highlightthickness=0,
                                     height=8)
        self.peers_listbox.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=self.peers_listbox.yview)

        # Boutons d'action
        btn_frame = Frame(left, bg=self.theme['card_bg'])
        btn_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=10)

        Button(btn_frame, text="📤 Envoyer fichier(s)", bg=self.theme['primary'],
               fg='#ffffff', font=('Segoe UI', 10, 'bold'), bd=0, cursor='hand2',
               command=self.on_send_file, padx=15, pady=10).pack(side="left", padx=5, pady=3)

        Button(btn_frame, text="📥 Recevoir (Attendre)", bg=self.theme['success'],
               fg='#ffffff', font=('Segoe UI', 10, 'bold'), bd=0, cursor='hand2',
               command=self.on_receive, padx=15, pady=10).pack(side="left", padx=5, pady=3)

        # Section Statistiques
        Label(left, text="📊 Statistiques de session", bg=self.theme['card_bg'],
              fg=self.theme['text_primary'], font=('Segoe UI', 12, 'bold')).grid(
            row=3, column=0, sticky="w", padx=15, pady=(15, 5))

        self.stats_frame = Frame(left, bg=self.theme['card_bg'])
        self.stats_frame.grid(row=4, column=0, sticky="ew", padx=15, pady=5)

        self.create_stats_display()

        # Section Transfert en cours
        Label(left, text="⚡ Transfert en cours", bg=self.theme['card_bg'],
              fg=self.theme['text_primary'], font=('Segoe UI', 12, 'bold')).grid(
            row=5, column=0, sticky="w", padx=15, pady=(15, 5))

        progress_container = Frame(left, bg=self.theme['card_bg'])
        progress_container.grid(row=6, column=0, sticky="ew", padx=15, pady=5)

        self.progress = ttk.Progressbar(progress_container, orient='horizontal',
                                       mode='determinate', length=300)
        self.progress.pack(fill='x', pady=2)

        info_frame = Frame(progress_container, bg=self.theme['card_bg'])
        info_frame.pack(fill='x', pady=5)

        Label(info_frame, textvariable=self.current_progress, bg=self.theme['card_bg'],
              fg=self.theme['text_secondary'], font=('Segoe UI', 9)).pack(side='left')
        Label(info_frame, textvariable=self.current_speed, bg=self.theme['card_bg'],
              fg=self.theme['text_secondary'], font=('Segoe UI', 9)).pack(side='right')

    def create_stats_display(self):
        """Afficher les statistiques"""
        for widget in self.stats_frame.winfo_children():
            widget.destroy()

        stats_data = [
            ("📤 Envoyés", f"{stats['files_sent']} fichiers", format_size(stats['sent'])),
            ("📥 Reçus", f"{stats['files_received']} fichiers", format_size(stats['received']))
        ]

        for icon_text, count, size in stats_data:
            card = Frame(self.stats_frame, bg=self.theme['bg'], bd=0)
            card.pack(fill='x', pady=3)

            Label(card, text=icon_text, bg=self.theme['bg'],
                  fg=self.theme['text_primary'], font=('Segoe UI', 9, 'bold')).pack(anchor='w', padx=10, pady=(5, 0))
            Label(card, text=count, bg=self.theme['bg'],
                  fg=self.theme['text_secondary'], font=('Segoe UI', 8)).pack(anchor='w', padx=10)
            Label(card, text=size, bg=self.theme['bg'],
                  fg=self.theme['primary'], font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=10, pady=(0, 5))

    def create_right_panel(self, parent):
        """Panneau droit avec journal et historique"""
        right = Frame(parent, bg=self.theme['bg'])
        right.grid(row=0, column=1, sticky="nsew")

        right.grid_rowconfigure(1, weight=2)
        right.grid_rowconfigure(3, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # Section Journal
        journal_header = Frame(right, bg=self.theme['card_bg'], height=40)
        journal_header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        journal_header.configure(highlightbackground=self.theme['border'], highlightthickness=1)

        Label(journal_header, text="📝 Journal d'activité", bg=self.theme['card_bg'],
              fg=self.theme['text_primary'], font=('Segoe UI', 12, 'bold')).pack(
            side='left', padx=15, pady=10)

        Button(journal_header, text="🗑️ Effacer", bg=self.theme['bg'],
               fg=self.theme['text_secondary'], font=('Segoe UI', 9), bd=0,
               cursor='hand2', command=self.clear_log).pack(side='right', padx=15)

        # Zone de texte du journal
        log_frame = Frame(right, bg=self.theme['card_bg'])
        log_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        log_frame.configure(highlightbackground=self.theme['border'], highlightthickness=1)

        log_scroll = Scrollbar(log_frame)
        log_scroll.pack(side='right', fill='y')

        self.log_text = Text(log_frame, state='disabled', wrap='word',
                            bg=self.theme['card_bg'], fg=self.theme['text_primary'],
                            font=('Consolas', 9), bd=0, padx=10, pady=10,
                            yscrollcommand=log_scroll.set)
        self.log_text.pack(side='left', fill='both', expand=True)
        log_scroll.config(command=self.log_text.yview)

        # Configuration des tags pour les couleurs
        self.log_text.tag_config('info', foreground=self.theme['primary'])
        self.log_text.tag_config('success', foreground=self.theme['success'])
        self.log_text.tag_config('error', foreground=self.theme['danger'])
        self.log_text.tag_config('warning', foreground=self.theme['accent'])

        # Section Historique
        history_header = Frame(right, bg=self.theme['card_bg'], height=40)
        history_header.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        history_header.configure(highlightbackground=self.theme['border'], highlightthickness=1)

        Label(history_header, text="📜 Historique des transferts", bg=self.theme['card_bg'],
              fg=self.theme['text_primary'], font=('Segoe UI', 12, 'bold')).pack(
            side='left', padx=15, pady=10)

        # Zone de l'historique
        history_frame = Frame(right, bg=self.theme['card_bg'])
        history_frame.grid(row=3, column=0, sticky="nsew")
        history_frame.configure(highlightbackground=self.theme['border'], highlightthickness=1)

        history_scroll = Scrollbar(history_frame)
        history_scroll.pack(side='right', fill='y')

        self.history_text = Text(history_frame, state='disabled', wrap='word',
                                bg=self.theme['card_bg'], fg=self.theme['text_primary'],
                                font=('Segoe UI', 9), bd=0, padx=10, pady=10,
                                yscrollcommand=history_scroll.set)
        self.history_text.pack(side='left', fill='both', expand=True)
        history_scroll.config(command=self.history_text.yview)

        # Tags pour l'historique
        self.history_text.tag_config('sent', foreground=self.theme['primary'])
        self.history_text.tag_config('received', foreground=self.theme['success'])

    def create_footer(self):
        """Créer le pied de page"""
        footer = Frame(self.root, bg=self.theme['card_bg'], height=50)
        footer.grid(row=2, column=0, sticky="ew")
        footer.configure(highlightbackground=self.theme['border'], highlightthickness=1)

        Label(footer, text="© 2025 ShabbibySend - Transfert P2P sécurisé",
              bg=self.theme['card_bg'], fg=self.theme['text_secondary'],
              font=('Segoe UI', 9)).pack(side='left', padx=20, pady=10)

        Button(footer, text="❌ Quitter", bg=self.theme['danger'],
               fg='#ffffff', font=('Segoe UI', 10, 'bold'), bd=0,
               cursor='hand2', command=self.on_quit, padx=20, pady=5).pack(
            side='right', padx=20, pady=10)

    def toggle_theme(self):
        """Basculer entre mode clair et sombre"""
        self.current_theme = 'dark' if self.current_theme == 'light' else 'light'
        self.theme = THEMES[self.current_theme]
        self.theme_btn.config(text="☀️" if self.current_theme == 'dark' else "🌙")

        # Recréer l'interface avec le nouveau thème
        self.log("Changement de thème...", "info")

        # Mettre à jour les couleurs (simplifié - une vraie implémentation nécessiterait
        # de recréer tous les widgets ou d'utiliser un système de thème plus sophistiqué)
        self.root.configure(bg=self.theme['bg'])

    def log(self, message, level='info'):
        """Ajouter un message au journal"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.config(state='normal')
        self.log_text.insert(END, f"[{timestamp}] ", 'info')
        self.log_text.insert(END, f"{message}\n", level)
        self.log_text.see(END)
        self.log_text.config(state='disabled')

    def clear_log(self):
        """Effacer le journal"""
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, END)
        self.log_text.config(state='disabled')

    def update_history(self):
        """Mettre à jour l'affichage de l'historique"""
        self.history_text.config(state='normal')
        self.history_text.delete(1.0, END)

        for entry in reversed(transfer_history[-20:]):  # Afficher les 20 derniers
            icon = "📤" if entry['type'] == 'sent' else "📥"
            tag = 'sent' if entry['type'] == 'sent' else 'received'

            self.history_text.insert(END, f"{icon} ", tag)
            self.history_text.insert(END, f"[{entry['timestamp']}] ")
            self.history_text.insert(END, f"{entry['filename']} ", tag)
            self.history_text.insert(END, f"({format_size(entry['size'])}) ")
            self.history_text.insert(END, f"{'→' if entry['type'] == 'sent' else '←'} {entry['peer']}\n")

        self.history_text.config(state='disabled')

    def update_peers_list(self):
        """Mettre à jour la liste des pairs"""
        self.peers_listbox.delete(0, END)
        for ip in sorted(PEERS):
            self.peers_listbox.insert(END, f"  🖥️  {ip}")

    def notify(self, message):
        """Afficher une notification"""
        self.root.after(0, lambda: messagebox.showinfo("📢 Notification", message))

    def on_send_file(self):
        """Envoyer un ou plusieurs fichiers"""
        selected = self.peers_listbox.curselection()
        if not selected:
            messagebox.showwarning("⚠️ Aucun destinataire",
                                  "Veuillez sélectionner un appareil dans la liste.")
            return

        ip_text = self.peers_listbox.get(selected[0])
        ip = ip_text.split("🖥️")[1].strip()

        # Permettre la sélection multiple
        filepaths = filedialog.askopenfilenames(title="Choisir un ou plusieurs fichiers")
        if not filepaths:
            return

        self.log(f"Préparation de l'envoi de {len(filepaths)} fichier(s) vers {ip}", "info")

        if len(filepaths) == 1:
            send_file_to(ip, filepaths[0])
        else:
            send_multiple_files(ip, filepaths)

    def on_receive(self):
        """Activer le mode réception"""
        start_receiver(nonblocking=True)
        self.log("Mode réception activé : en attente de connexion...", "info")
        messagebox.showinfo("📥 Mode réception",
                          "Mode réception activé. L'application attend une connexion entrante.")

    def refresh_peers(self):
        """Rafraîchir manuellement la liste des pairs"""
        self.log("Rafraîchissement de la liste des appareils...", "info")
        self.update_peers_list()

    def on_quit(self):
        """Quitter l'application"""
        if messagebox.askyesno("❌ Quitter", "Voulez-vous vraiment quitter l'application ?"):
            self.root.destroy()

    def process_queue(self):
        """Traiter la queue des messages réseau"""
        while not gui_queue.empty():
            try:
                item = gui_queue.get_nowait()
                typ = item[0]

                if typ == "log":
                    _, message, level = item
                    self.log(message, level)

                elif typ == "peer_add":
                    self.update_peers_list()

                elif typ == "notify":
                    _, message = item
                    self.notify(message)

                elif typ == "progress_send_start":
                    _, (filename, filesize) = item
                    self.progress['value'] = 0
                    self.current_progress.set("0%")
                    self.current_speed.set("0 B/s")
                    self.log(f"Envoi démarré: {filename} ({format_size(filesize)})", "info")

                elif typ == "progress_send":
                    _, (sent, total, filename, speed) = item
                    progress = int((sent / total) * 100)
                    self.progress['value'] = progress
                    self.current_progress.set(f"{progress}%")
                    self.current_speed.set(format_speed(speed))

                elif typ == "progress_receive_start":
                    _, (filename, filesize) = item
                    self.progress['value'] = 0
                    self.current_progress.set("0%")
                    self.current_speed.set("0 B/s")
                    self.log(f"Réception démarrée: {filename} ({format_size(filesize)})", "info")

                elif typ == "progress_receive":
                    _, (received, total, filename, speed) = item
                    if total > 0:
                        progress = int((received / total) * 100)
                        self.progress['value'] = progress
                        self.current_progress.set(f"{progress}%")
                        self.current_speed.set(format_speed(speed))

                elif typ == "update_stats":
                    self.create_stats_display()

                elif typ == "update_history":
                    self.update_history()

            except queue.Empty:
                break
            except Exception as e:
                print(f"Erreur dans process_queue: {e}")

        self.root.after(200, self.process_queue)

# ---------- Point d'entrée ----------
if __name__ == "__main__":
    root = Tk()
    app = ModernXenderGUI(root)
    root.mainloop()
