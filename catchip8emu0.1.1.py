"""
AC's CHIP-8 Emu 0.1.1
Credits: DeepSeek AI / CatSeek Harness
Full MGBAS-Style GUI with Audio Controls
FILES = OFF (All in memory)
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import random
import sys
import time
import os
import threading
import struct
import math

# ─── AUDIO ──────────────────────────────────────────────────
try:
    import pyaudio
    import numpy as np
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("PyAudio not installed. Audio disabled. Install: pip install pyaudio")

# ─── CHIP‑8 SPECS ───────────────────────────────────────────────
MEM_SIZE = 4096
STACK_SIZE = 16
NUM_KEYS = 16
NUM_REGS = 16
SCREEN_W, SCREEN_H = 64, 32
SCALE = 10


# ─── AUDIO ENGINE ──────────────────────────────────────────────
class AudioEngine:
    def __init__(self):
        self.enabled = True
        self.volume = 0.5
        self.frequency = 440
        self.sample_rate = 44100
        self.beep_duration = 0.05
        self._playing = False
        self._p = None
        self._stream = None
        
        if AUDIO_AVAILABLE:
            try:
                self._p = pyaudio.PyAudio()
                self._stream = self._p.open(
                    format=pyaudio.paFloat32,
                    channels=1,
                    rate=self.sample_rate,
                    output=True,
                    frames_per_buffer=1024
                )
            except Exception as e:
                print(f"Audio init failed: {e}")
                self._p = None
                self._stream = None

    def play_beep(self):
        if not self.enabled or not AUDIO_AVAILABLE or self._stream is None:
            return
        
        def _beep_thread():
            try:
                frames = int(self.sample_rate * self.beep_duration)
                t = np.linspace(0, self.beep_duration, frames)
                wave = np.sin(2 * np.pi * self.frequency * t) * self.volume * 0.5
                data = wave.astype(np.float32).tobytes()
                self._stream.write(data)
            except Exception:
                pass
        
        threading.Thread(target=_beep_thread, daemon=True).start()

    def set_volume(self, vol):
        self.volume = max(0.0, min(1.0, vol))

    def set_frequency(self, freq):
        self.frequency = max(100, min(1000, freq))

    def toggle_mute(self):
        self.enabled = not self.enabled
        return self.enabled

    def close(self):
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except:
                pass
        if self._p:
            try:
                self._p.terminate()
            except:
                pass


# ─── CHIP‑8 CORE ──────────────────────────────────────────────
class Chip8:
    def __init__(self, audio):
        self.audio = audio
        self.reset()
        self._load_font()

    def reset(self):
        self.mem = bytearray(MEM_SIZE)
        self.v = [0] * NUM_REGS
        self.i = 0
        self.pc = 0x200
        self.sp = 0
        self.stack = [0] * STACK_SIZE
        self.delay_timer = 0
        self.sound_timer = 0
        self.key = [0] * NUM_KEYS
        self.screen = [[0] * SCREEN_W for _ in range(SCREEN_H)]
        self.draw_flag = True
        self.running = True
        self.paused = False
        self.speed = 500
        self._loaded_rom = None

    def _load_font(self):
        font = [
            0xF0, 0x90, 0x90, 0x90, 0xF0,
            0x20, 0x60, 0x20, 0x20, 0x70,
            0xF0, 0x10, 0xF0, 0x80, 0xF0,
            0xF0, 0x10, 0xF0, 0x10, 0xF0,
            0x90, 0x90, 0xF0, 0x10, 0x10,
            0xF0, 0x80, 0xF0, 0x10, 0xF0,
            0xF0, 0x80, 0xF0, 0x90, 0xF0,
            0xF0, 0x10, 0x20, 0x40, 0x40,
            0xF0, 0x90, 0xF0, 0x90, 0xF0,
            0xF0, 0x90, 0xF0, 0x10, 0xF0,
            0xF0, 0x90, 0xF0, 0x90, 0x90,
            0xE0, 0x90, 0xE0, 0x90, 0xE0,
            0xF0, 0x80, 0x80, 0x80, 0xF0,
            0xE0, 0x90, 0x90, 0x90, 0xE0,
            0xF0, 0x80, 0xF0, 0x80, 0xF0,
            0xF0, 0x80, 0xF0, 0x80, 0x80
        ]
        for i, byte in enumerate(font):
            self.mem[i] = byte

    def load_rom(self, path):
        try:
            with open(path, 'rb') as f:
                data = f.read()
            self.reset()
            self.mem[0x200:0x200 + len(data)] = data
            self._loaded_rom = path
            self.running = True
            return True
        except Exception as e:
            return False

    def opcode(self):
        return (self.mem[self.pc] << 8) | self.mem[self.pc + 1]

    def step(self):
        if self.paused or not self.running:
            return

        op = self.opcode()
        x = (op & 0x0F00) >> 8
        y = (op & 0x00F0) >> 4
        n = op & 0x000F
        nn = op & 0x00FF
        nnn = op & 0x0FFF

        self.pc += 2

        # ─── INSTRUCTION SET ──────────────────────────────
        if op == 0x00E0:
            self.screen = [[0] * SCREEN_W for _ in range(SCREEN_H)]
            self.draw_flag = True
        elif op == 0x00EE:
            self.sp -= 1
            self.pc = self.stack[self.sp]
        elif (op & 0xF000) == 0x1000:
            self.pc = nnn
        elif (op & 0xF000) == 0x2000:
            self.stack[self.sp] = self.pc
            self.sp += 1
            self.pc = nnn
        elif (op & 0xF000) == 0x3000:
            if self.v[x] == nn:
                self.pc += 2
        elif (op & 0xF000) == 0x4000:
            if self.v[x] != nn:
                self.pc += 2
        elif (op & 0xF00F) == 0x5000:
            if self.v[x] == self.v[y]:
                self.pc += 2
        elif (op & 0xF000) == 0x6000:
            self.v[x] = nn
        elif (op & 0xF000) == 0x7000:
            self.v[x] = (self.v[x] + nn) & 0xFF
        elif (op & 0xF00F) == 0x8000:
            self.v[x] = self.v[y]
        elif (op & 0xF00F) == 0x8001:
            self.v[x] |= self.v[y]
        elif (op & 0xF00F) == 0x8002:
            self.v[x] &= self.v[y]
        elif (op & 0xF00F) == 0x8003:
            self.v[x] ^= self.v[y]
        elif (op & 0xF00F) == 0x8004:
            self.v[x] += self.v[y]
            self.v[0xF] = 1 if self.v[x] > 0xFF else 0
            self.v[x] &= 0xFF
        elif (op & 0xF00F) == 0x8005:
            self.v[0xF] = 1 if self.v[x] >= self.v[y] else 0
            self.v[x] = (self.v[x] - self.v[y]) & 0xFF
        elif (op & 0xF00F) == 0x8006:
            self.v[0xF] = self.v[x] & 0x1
            self.v[x] >>= 1
        elif (op & 0xF00F) == 0x8007:
            self.v[0xF] = 1 if self.v[y] >= self.v[x] else 0
            self.v[x] = (self.v[y] - self.v[x]) & 0xFF
        elif (op & 0xF00F) == 0x800E:
            self.v[0xF] = (self.v[x] & 0x80) >> 7
            self.v[x] = (self.v[x] << 1) & 0xFF
        elif (op & 0xF00F) == 0x9000:
            if self.v[x] != self.v[y]:
                self.pc += 2
        elif (op & 0xF000) == 0xA000:
            self.i = nnn
        elif (op & 0xF000) == 0xB000:
            self.pc = nnn + self.v[0]
        elif (op & 0xF000) == 0xC000:
            self.v[x] = random.randint(0, 255) & nn
        elif (op & 0xF000) == 0xD000:
            height = n
            xpos = self.v[x] % SCREEN_W
            ypos = self.v[y] % SCREEN_H
            self.v[0xF] = 0
            for row in range(height):
                sprite = self.mem[self.i + row]
                for col in range(8):
                    if (sprite & (0x80 >> col)):
                        px = (xpos + col) % SCREEN_W
                        py = (ypos + row) % SCREEN_H
                        if self.screen[py][px] == 1:
                            self.v[0xF] = 1
                        self.screen[py][px] ^= 1
            self.draw_flag = True
        elif (op & 0xF0FF) == 0xE09E:
            if self.key[self.v[x]]:
                self.pc += 2
        elif (op & 0xF0FF) == 0xE0A1:
            if not self.key[self.v[x]]:
                self.pc += 2
        elif (op & 0xF0FF) == 0xF007:
            self.v[x] = self.delay_timer
        elif (op & 0xF0FF) == 0xF00A:
            for i in range(16):
                if self.key[i]:
                    self.v[x] = i
                    break
            else:
                self.pc -= 2
        elif (op & 0xF0FF) == 0xF015:
            self.delay_timer = self.v[x]
        elif (op & 0xF0FF) == 0xF018:
            self.sound_timer = self.v[x]
            if self.v[x] > 0 and self.audio:
                self.audio.play_beep()
        elif (op & 0xF0FF) == 0xF01E:
            self.i = (self.i + self.v[x]) & 0xFFFF
        elif (op & 0xF0FF) == 0xF029:
            self.i = self.v[x] * 5
        elif (op & 0xF0FF) == 0xF033:
            val = self.v[x]
            self.mem[self.i] = val // 100
            self.mem[self.i + 1] = (val // 10) % 10
            self.mem[self.i + 2] = val % 10
        elif (op & 0xF0FF) == 0xF055:
            for j in range(x + 1):
                self.mem[self.i + j] = self.v[j]
        elif (op & 0xF0FF) == 0xF065:
            for j in range(x + 1):
                self.v[j] = self.mem[self.i + j]

        if self.delay_timer > 0:
            self.delay_timer -= 1
        if self.sound_timer > 0:
            self.sound_timer -= 1


# ─── AC's CHIP-8 EMU GUI ──────────────────────────────────
class ACsChip8Emu(tk.Tk):
    def __init__(self):
        super().__init__()
        self.audio = AudioEngine()
        self.cpu = Chip8(self.audio)
        
        # ─── WINDOW TITLE ──────────────────────────────────
        self.title("AC's CHIP-8 Emu 0.1.1")
        self.geometry("750x720")
        self.resizable(False, False)

        # Style
        self.style = ttk.Style()
        self.style.theme_use('clam')

        # Menu Bar
        self.create_menu()

        # Main frame
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Canvas for screen
        self.canvas = tk.Canvas(main_frame, width=SCREEN_W*SCALE, height=SCREEN_H*SCALE, bg='black', highlightthickness=2, highlightbackground='#333')
        self.canvas.pack(pady=5)

        # ─── CONTROL PANEL ────────────────────────────────
        control_frame = ttk.LabelFrame(main_frame, text="Controls")
        control_frame.pack(fill=tk.X, pady=5)

        row1 = ttk.Frame(control_frame)
        row1.pack(fill=tk.X, pady=2)

        ttk.Label(row1, text="Speed:").pack(side=tk.LEFT, padx=5)
        self.speed_var = tk.IntVar(value=500)
        speed_scale = ttk.Scale(row1, from_=50, to=1000, orient=tk.HORIZONTAL, variable=self.speed_var, length=150)
        speed_scale.pack(side=tk.LEFT, padx=5)
        self.speed_label = ttk.Label(row1, text="500 Hz")
        self.speed_label.pack(side=tk.LEFT, padx=5)

        ttk.Button(row1, text="⏸ Pause", command=self.toggle_pause).pack(side=tk.LEFT, padx=5)
        ttk.Button(row1, text="🔄 Reset", command=self.reset_emulator).pack(side=tk.LEFT, padx=5)
        ttk.Button(row1, text="📂 Load ROM", command=self.load_rom).pack(side=tk.LEFT, padx=5)

        # ─── AUDIO CONTROLS ───────────────────────────────
        audio_frame = ttk.LabelFrame(main_frame, text="Audio")
        audio_frame.pack(fill=tk.X, pady=5)

        row2 = ttk.Frame(audio_frame)
        row2.pack(fill=tk.X, pady=2)

        ttk.Label(row2, text="Volume:").pack(side=tk.LEFT, padx=5)
        self.volume_var = tk.DoubleVar(value=0.5)
        volume_scale = ttk.Scale(row2, from_=0.0, to=1.0, orient=tk.HORIZONTAL, variable=self.volume_var, length=150, command=self.update_volume)
        volume_scale.pack(side=tk.LEFT, padx=5)
        self.volume_label = ttk.Label(row2, text="50%")
        self.volume_label.pack(side=tk.LEFT, padx=5)

        self.mute_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="🔇 Mute", variable=self.mute_var, command=self.toggle_mute).pack(side=tk.LEFT, padx=10)

        ttk.Label(row2, text="Beep Freq:").pack(side=tk.LEFT, padx=5)
        self.freq_var = tk.IntVar(value=440)
        freq_spin = ttk.Spinbox(row2, from_=100, to=1000, increment=10, textvariable=self.freq_var, width=6, command=self.update_frequency)
        freq_spin.pack(side=tk.LEFT, padx=5)
        ttk.Label(row2, text="Hz").pack(side=tk.LEFT)

        # ─── STATUS BAR ────────────────────────────────────
        self.status = ttk.Label(self, text="Ready | No ROM loaded", relief=tk.SUNKEN, anchor=tk.W)
        self.status.pack(fill=tk.X, side=tk.BOTTOM, ipady=2)

        # Key bindings
        self.bind_keys()

        # Start emulation
        self.running = True
        self.after(0, self.emulate_loop)

        # Load default ROM if provided
        if len(sys.argv) > 1:
            self.load_rom_file(sys.argv[1])

    def create_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Load ROM...", command=self.load_rom)
        file_menu.add_command(label="Reset", command=self.reset_emulator)
        file_menu.add_command(label="Pause", command=self.toggle_pause)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)

        # Emulation menu
        emu_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Emulation", menu=emu_menu)
        emu_menu.add_command(label="Pause", command=self.toggle_pause)
        emu_menu.add_separator()
        emu_menu.add_command(label="Speed 100 Hz", command=lambda: self.set_speed(100))
        emu_menu.add_command(label="Speed 300 Hz", command=lambda: self.set_speed(300))
        emu_menu.add_command(label="Speed 500 Hz", command=lambda: self.set_speed(500))
        emu_menu.add_command(label="Speed 1000 Hz", command=lambda: self.set_speed(1000))

        # Audio menu
        audio_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Audio", menu=audio_menu)
        audio_menu.add_command(label="Toggle Mute", command=self.toggle_mute)
        audio_menu.add_separator()
        audio_menu.add_command(label="Volume 0%", command=lambda: self.set_volume(0))
        audio_menu.add_command(label="Volume 25%", command=lambda: self.set_volume(0.25))
        audio_menu.add_command(label="Volume 50%", command=lambda: self.set_volume(0.5))
        audio_menu.add_command(label="Volume 75%", command=lambda: self.set_volume(0.75))
        audio_menu.add_command(label="Volume 100%", command=lambda: self.set_volume(1.0))

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Controls", command=self.show_controls)
        help_menu.add_command(label="About", command=self.show_about)

    def bind_keys(self):
        key_map = {
            '1': 0x1, '2': 0x2, '3': 0x3, '4': 0xC,
            'q': 0x4, 'w': 0x5, 'e': 0x6, 'r': 0xD,
            'a': 0x7, 's': 0x8, 'd': 0x9, 'f': 0xE,
            'z': 0xA, 'x': 0x0, 'c': 0xB, 'v': 0xF,
        }

        def key_down(event):
            if event.char in key_map:
                self.cpu.key[key_map[event.char]] = 1

        def key_up(event):
            if event.char in key_map:
                self.cpu.key[key_map[event.char]] = 0

        self.bind('<KeyPress>', key_down)
        self.bind('<KeyRelease>', key_up)
        self.focus_set()

    def draw_screen(self):
        self.canvas.delete('all')
        for y in range(SCREEN_H):
            for x in range(SCREEN_W):
                if self.cpu.screen[y][x]:
                    self.canvas.create_rectangle(
                        x*SCALE, y*SCALE,
                        x*SCALE + SCALE, y*SCALE + SCALE,
                        fill='#00FF00', outline=''
                    )

    def emulate_loop(self):
        if not self.running:
            return

        speed = self.speed_var.get()
        self.speed_label.config(text=f"{speed} Hz")

        if self.cpu.running and not self.cpu.paused:
            for _ in range(max(1, speed // 60)):
                self.cpu.step()

        if self.cpu.draw_flag:
            self.draw_screen()
            self.cpu.draw_flag = False

        rom_name = os.path.basename(self.cpu._loaded_rom) if self.cpu._loaded_rom else "No ROM"
        audio_status = "🔊" if not self.mute_var.get() and self.audio.enabled else "🔇"
        self.status.config(text=f"{audio_status} ROM: {rom_name} | PC: {hex(self.cpu.pc)} | I: {hex(self.cpu.i)} | DT: {self.cpu.delay_timer} | {'▶' if not self.cpu.paused else '⏸'}")

        self.after(16, self.emulate_loop)

    def load_rom(self):
        file_path = filedialog.askopenfilename(
            title="Select CHIP-8 ROM",
            filetypes=[("CHIP-8 ROMs", "*.ch8 *.rom"), ("All files", "*.*")]
        )
        if file_path:
            self.load_rom_file(file_path)

    def load_rom_file(self, path):
        if self.cpu.load_rom(path):
            messagebox.showinfo("Success", f"ROM loaded!\n{os.path.basename(path)}")
        else:
            messagebox.showerror("Error", f"Failed to load ROM")

    def toggle_pause(self):
        self.cpu.paused = not self.cpu.paused

    def reset_emulator(self):
        if self.cpu._loaded_rom:
            self.cpu.load_rom(self.cpu._loaded_rom)
        else:
            self.cpu.reset()

    def set_speed(self, speed):
        self.speed_var.set(speed)

    def update_volume(self, val):
        vol = float(val)
        self.volume_label.config(text=f"{int(vol * 100)}%")
        self.audio.set_volume(vol)
        self.volume_var.set(vol)

    def set_volume(self, vol):
        self.volume_var.set(vol)
        self.volume_label.config(text=f"{int(vol * 100)}%")
        self.audio.set_volume(vol)

    def toggle_mute(self):
        muted = self.audio.toggle_mute()
        self.mute_var.set(not muted)

    def update_frequency(self):
        try:
            freq = self.freq_var.get()
            self.audio.set_frequency(freq)
        except:
            pass

    def show_controls(self):
        controls = """AC's CHIP-8 Emu 0.1.1 - Controls

CHIP-8 Keyboard Mapping:

1 2 3 4    →    1 2 3 C
Q W E R    →    4 5 6 D
A S D F    →    7 8 9 E
Z X C V    →    A 0 B F

Controls:
• Load ROM: File → Load ROM
• Pause: Click Pause button or press Esc
• Reset: Click Reset button
• Speed: Drag the slider or use Emulation menu
• Volume: Drag the Volume slider
• Mute: Click Mute checkbox or Audio menu

Credits: DeepSeek AI / CatSeek Harness"""
        messagebox.showinfo("Controls", controls)

    def show_about(self):
        about = """AC's CHIP-8 Emu 0.1.1

Full MGBAS-Style GUI with Audio Controls

Features:
• Full CHIP-8 instruction set
• Audio with volume control
• Speed control (50-1000 Hz)
• Pause/Resume
• Reset
• File dialog for ROMs
• Status bar

Credits:
• DeepSeek AI - Core logic
• CatSeek Harness - GUI framework
• AC - Customization & SOUP

🐱 Powered by CatSeek Energy
🍜 SOUP Mode: Always On
🔊 FILES = OFF (All in memory)"""
        messagebox.showinfo("About AC's CHIP-8 Emu", about)

    def on_closing(self):
        self.running = False
        self.cpu.running = False
        self.audio.close()
        self.destroy()


# ─── MAIN ────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ACsChip8Emu()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()