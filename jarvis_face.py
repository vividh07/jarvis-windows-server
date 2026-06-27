import pygame
import time
import math
import random
import threading

SCREEN_W = 240
SCREEN_H = 135
FPS      = 30
BORDER   = 10

FACE_W = SCREEN_W - (BORDER * 2)
FACE_H = SCREEN_H - (BORDER * 2)
FACE_X = BORDER
FACE_Y = BORDER

BLACK      = (0,   0,   0)
WHITE      = (255, 255, 255)
PURPLE     = (127, 119, 221)
DARK_PURP  = (83,  74,  183)
GREEN      = (29,  158, 117)
RED        = (226, 75,  74)
AMBER      = (239, 159, 39)
DARK_BG    = (13,  13,  15)
GRID_COLOR = (20,  20,  25)

PIXEL = 4

GRID_COLS = FACE_W // PIXEL
GRID_ROWS = FACE_H // PIXEL
CENTER_X = GRID_COLS // 2
SIDE_MARGIN = 4

def draw_grid(surface):
    w, h = surface.get_size()
    for x in range(0, w, PIXEL):
        for y in range(0, h, PIXEL):
            pygame.draw.rect(surface, GRID_COLOR, (x, y, PIXEL - 1, PIXEL - 1))

# Face layout — centered on grid
EYE_W = 6
EYE_H = 5
EYE_GAP = 8
LEFT_EYE_X = CENTER_X - EYE_GAP // 2 - EYE_W
RIGHT_EYE_X = CENTER_X + EYE_GAP // 2
EYE_Y = GRID_ROWS // 2 - 6

MOUTH_W = 14
MOUTH_X = CENTER_X - MOUTH_W // 2
MOUTH_Y = EYE_Y + 10

def left_bar_x(i: int) -> int:
    return SIDE_MARGIN + i * 2

def right_bar_x(i: int) -> int:
    return GRID_COLS - SIDE_MARGIN - 1 - i * 2

def draw_pixel(surface, color, x, y, size=PIXEL):
    pygame.draw.rect(surface, color, (x * size, y * size, size - 1, size - 1))

def draw_pixel_rect(surface, color, x, y, w, h):
    for px in range(x, x + w):
        for py in range(y, y + h):
            draw_pixel(surface, color, px, py)

def draw_eye_open(surface, x, y, color=WHITE):
    draw_pixel_rect(surface, color, x,     y + 1, EYE_W, EYE_H - 2)
    draw_pixel_rect(surface, color, x + 1, y,     EYE_W - 2, EYE_H)
    draw_pixel_rect(surface, DARK_BG, x + 2, y + 1, 2, 3)
    draw_pixel(surface, WHITE, x + 2, y + 1)

def draw_eye_half(surface, x, y, color=WHITE):
    draw_pixel_rect(surface, color, x,     y + 2, EYE_W, EYE_H - 3)
    draw_pixel_rect(surface, color, x + 1, y + 1, EYE_W - 2, EYE_H - 2)
    draw_pixel_rect(surface, DARK_BG, x + 2, y + 2, 2, 2)

def draw_eye_closed(surface, x, y, color=WHITE):
    draw_pixel_rect(surface, color, x + 1, y + 2, EYE_W - 2, 1)

def draw_eye_wide(surface, x, y, color=WHITE):
    draw_pixel_rect(surface, color, x,     y,     EYE_W, EYE_H + 1)
    draw_pixel_rect(surface, color, x + 1, y - 1, EYE_W - 2, EYE_H + 2)
    draw_pixel_rect(surface, DARK_BG, x + 1, y + 1, 3, 3)
    draw_pixel(surface, WHITE, x + 1, y + 1)

def draw_eye_squint(surface, x, y, color=WHITE):
    draw_pixel_rect(surface, color, x + 1, y + 2, EYE_W - 2, 2)
    draw_pixel_rect(surface, color, x,     y + 3, EYE_W,     1)

def draw_eye_look_left(surface, x, y, color=WHITE):
    draw_pixel_rect(surface, color, x,     y + 1, EYE_W, EYE_H - 2)
    draw_pixel_rect(surface, color, x + 1, y,     EYE_W - 2, EYE_H)
    draw_pixel_rect(surface, DARK_BG, x + 1, y + 1, 2, 3)
    draw_pixel(surface, WHITE, x + 1, y + 1)

def draw_eye_look_right(surface, x, y, color=WHITE):
    draw_pixel_rect(surface, color, x,     y + 1, EYE_W, EYE_H - 2)
    draw_pixel_rect(surface, color, x + 1, y,     EYE_W - 2, EYE_H)
    draw_pixel_rect(surface, DARK_BG, x + 3, y + 1, 2, 3)
    draw_pixel(surface, WHITE, x + 3, y + 1)

def draw_eye_up(surface, x, y, color=WHITE):
    draw_pixel_rect(surface, color, x,     y + 1, EYE_W, EYE_H - 2)
    draw_pixel_rect(surface, color, x + 1, y,     EYE_W - 2, EYE_H)
    draw_pixel_rect(surface, DARK_BG, x + 2, y, 2, 3)
    draw_pixel(surface, WHITE, x + 2, y)

def draw_mouth_neutral(surface, color=WHITE):
    draw_pixel_rect(surface, color, MOUTH_X, MOUTH_Y, MOUTH_W, 1)

def draw_mouth_smile(surface, color=WHITE):
    draw_pixel_rect(surface, color, MOUTH_X + 1, MOUTH_Y,     MOUTH_W - 2, 1)
    draw_pixel(surface,      color, MOUTH_X,     MOUTH_Y + 1)
    draw_pixel(surface,      color, MOUTH_X + MOUTH_W - 1, MOUTH_Y + 1)

def draw_mouth_open(surface, frame, color=WHITE):
    heights = [1, 2, 3, 2, 1, 2, 3, 2, 1, 2, 3, 2, 1, 2]
    offset  = frame % len(heights)
    for i in range(MOUTH_W):
        h = heights[(i + offset) % len(heights)]
        draw_pixel_rect(surface, color, MOUTH_X + i, MOUTH_Y + 3 - h, 1, h)

def draw_mouth_confused(surface, color=AMBER):
    pattern = [1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0]
    for i, up in enumerate(pattern):
        draw_pixel(surface, color, MOUTH_X + i, MOUTH_Y + up)

class IdleExpression:
    def __init__(self):
        self.frame       = 0
        self.blink_timer = 0
        self.blink_state = 'open'
        self.look_timer  = 0
        self.look_dir    = 'forward'

    def update(self):
        self.frame += 1
        self.blink_timer += 1
        if self.blink_state == 'open' and self.blink_timer > 90:
            self.blink_state = 'closing'
            self.blink_timer = 0
        elif self.blink_state == 'closing' and self.blink_timer > 3:
            self.blink_state = 'closed'
            self.blink_timer = 0
        elif self.blink_state == 'closed' and self.blink_timer > 4:
            self.blink_state = 'opening'
            self.blink_timer = 0
        elif self.blink_state == 'opening' and self.blink_timer > 3:
            self.blink_state = 'open'
            self.blink_timer = 0
        self.look_timer += 1
        if self.look_timer > 150:
            self.look_dir   = random.choice(['forward', 'left', 'right', 'forward'])
            self.look_timer = 0

    def draw(self, surface):
        for eye_x in [LEFT_EYE_X, RIGHT_EYE_X]:
            if self.blink_state == 'open':
                if self.look_dir == 'left':
                    draw_eye_look_left(surface, eye_x, EYE_Y, PURPLE)
                elif self.look_dir == 'right':
                    draw_eye_look_right(surface, eye_x, EYE_Y, PURPLE)
                else:
                    draw_eye_open(surface, eye_x, EYE_Y, PURPLE)
            elif self.blink_state == 'closing':
                draw_eye_half(surface, eye_x, EYE_Y, PURPLE)
            elif self.blink_state == 'closed':
                draw_eye_closed(surface, eye_x, EYE_Y, PURPLE)
            elif self.blink_state == 'opening':
                draw_eye_half(surface, eye_x, EYE_Y, PURPLE)
        draw_mouth_smile(surface, PURPLE)

class ListeningExpression:
    def __init__(self):
        self.frame       = 0
        self.pulse_timer = 0

    def update(self):
        self.frame       += 1
        self.pulse_timer += 1

    def draw(self, surface):
        draw_eye_wide(surface, LEFT_EYE_X,  EYE_Y, GREEN)
        draw_eye_wide(surface, RIGHT_EYE_X, EYE_Y, GREEN)
        draw_mouth_neutral(surface, GREEN)
        pulse = int(self.pulse_timer / 8) % 3
        for i in range(3):
            color = GREEN if i <= pulse else DARK_BG
            draw_pixel(surface, color, CENTER_X - 2 + i * 2, 2)
        wave = int(self.pulse_timer / 4) % 4
        for i in range(4):
            h = 3 if i == wave else 1
            draw_pixel_rect(surface, GREEN, left_bar_x(i), 12 - h, 1, h * 2)
            draw_pixel_rect(surface, GREEN, right_bar_x(i), 12 - h, 1, h * 2)

class ThinkingExpression:
    def __init__(self):
        self.frame      = 0
        self.dot_timer  = 0
        self.active_dot = 0

    def update(self):
        self.frame     += 1
        self.dot_timer += 1
        if self.dot_timer > 12:
            self.active_dot = (self.active_dot + 1) % 4
            self.dot_timer  = 0

    def draw(self, surface):
        draw_eye_up(surface, LEFT_EYE_X,  EYE_Y, AMBER)
        draw_eye_up(surface, RIGHT_EYE_X, EYE_Y, AMBER)
        draw_mouth_neutral(surface, AMBER)
        dot_positions = [(CENTER_X - 2, 2), (CENTER_X, 1), (CENTER_X + 2, 2), (CENTER_X, 3)]
        for i, (dx, dy) in enumerate(dot_positions):
            color = AMBER if i == self.active_dot else DARK_PURP
            draw_pixel(surface, color, dx, dy)
        gear_anim = int(self.frame / 6) % 4
        gear_x = GRID_COLS - 5
        gear_y    = 6
        draw_pixel_rect(surface, AMBER, gear_x + 1, gear_y,     2, 4)
        draw_pixel_rect(surface, AMBER, gear_x,     gear_y + 1, 4, 2)
        if gear_anim == 0:
            draw_pixel(surface, AMBER, gear_x,     gear_y)
            draw_pixel(surface, AMBER, gear_x + 3, gear_y + 3)
        elif gear_anim == 1:
            draw_pixel(surface, AMBER, gear_x + 3, gear_y)
            draw_pixel(surface, AMBER, gear_x,     gear_y + 3)
        elif gear_anim == 2:
            draw_pixel(surface, AMBER, gear_x + 3, gear_y)
            draw_pixel(surface, AMBER, gear_x,     gear_y + 3)
        elif gear_anim == 3:
            draw_pixel(surface, AMBER, gear_x,     gear_y)
            draw_pixel(surface, AMBER, gear_x + 3, gear_y + 3)

class SpeakingExpression:
    def __init__(self):
        self.frame       = 0
        self.blink_timer = 0
        self.blink_open  = True

    def update(self):
        self.frame       += 1
        self.blink_timer += 1
        if self.blink_timer > 60:
            self.blink_open  = not self.blink_open
            self.blink_timer = 0

    def draw(self, surface):
        for eye_x in [LEFT_EYE_X, RIGHT_EYE_X]:
            if self.blink_open:
                draw_eye_open(surface, eye_x, EYE_Y, WHITE)
            else:
                draw_eye_closed(surface, eye_x, EYE_Y, WHITE)
        draw_mouth_open(surface, self.frame, WHITE)
        speaker_frame = int(self.frame / 4) % 3
        for i in range(3):
            size = 1 if i != speaker_frame else 2
            draw_pixel_rect(surface, WHITE, left_bar_x(i), 10 + i * 3, size, size)
            draw_pixel_rect(surface, WHITE, right_bar_x(i), 10 + i * 3, size, size)

class MusicExpression:
    def __init__(self, bpm=120):
        self.frame = 0
        self.bpm = max(60, min(int(bpm), 200))
        self.beat_period = FPS * 60.0 / self.bpm

    def update(self):
        self.frame += 1

    def on_beat(self):
        phase = self.frame % self.beat_period
        return phase < self.beat_period * 0.22

    def draw(self, surface):
        beat = self.on_beat()
        eye_y = EYE_Y - 1 if beat else EYE_Y
        if beat:
            draw_eye_wide(surface, LEFT_EYE_X, eye_y, PURPLE)
            draw_eye_wide(surface, RIGHT_EYE_X, eye_y, PURPLE)
            draw_mouth_open(surface, self.frame, PURPLE)
        else:
            draw_eye_open(surface, LEFT_EYE_X, eye_y, PURPLE)
            draw_eye_open(surface, RIGHT_EYE_X, eye_y, PURPLE)
            draw_mouth_smile(surface, PURPLE)

        bar_heights = [5, 3, 4, 2] if beat else [2, 1, 2, 1]
        for i, h in enumerate(bar_heights):
            draw_pixel_rect(surface, PURPLE, left_bar_x(i), 12 - h, 1, h * 2)
            draw_pixel_rect(surface, PURPLE, right_bar_x(i), 12 - h, 1, h * 2)

        pulse = int(self.frame / max(1, self.beat_period / 4)) % 3
        for i in range(3):
            color = PURPLE if i <= pulse else DARK_BG
            draw_pixel(surface, color, CENTER_X - 2 + i * 2, 2)

class ConfusedExpression:
    def __init__(self):
        self.frame  = 0
        self.wobble = 0

    def update(self):
        self.frame  += 1
        self.wobble  = int(math.sin(self.frame * 0.1) * 1)

    def draw(self, surface):
        draw_eye_open(surface,   LEFT_EYE_X,  EYE_Y + self.wobble, RED)
        draw_eye_squint(surface, RIGHT_EYE_X, EYE_Y - self.wobble, RED)
        draw_mouth_confused(surface, AMBER)
        qm_x = CENTER_X - 1
        qm_y = 1
        draw_pixel_rect(surface, AMBER, qm_x,     qm_y,     3, 1)
        draw_pixel(surface,      AMBER, qm_x + 2, qm_y + 1)
        draw_pixel(surface,      AMBER, qm_x + 1, qm_y + 2)
        draw_pixel(surface,      AMBER, qm_x + 1, qm_y + 4)

class JarvisFace:
    def __init__(self):
        pygame.init()
        self.screen       = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Jarvis")
        self.clock        = pygame.time.Clock()
        self.face_surface = pygame.Surface((FACE_W, FACE_H))
        self.expressions  = {
            'idle':      IdleExpression(),
            'listening': ListeningExpression(),
            'thinking':  ThinkingExpression(),
            'speaking':  SpeakingExpression(),
            'confused':  ConfusedExpression(),
            'music':     MusicExpression(),
        }
        self.current_state = 'idle'
        self.running       = True

    def set_state(self, state: str):
        bpm = 120
        if state.startswith('music_'):
            try:
                bpm = int(state.split('_', 1)[1])
            except ValueError:
                pass
            state = 'music'

        if state in self.expressions or state == 'music':
            print(f"Face: {state}" + (f" ({bpm} bpm)" if state == 'music' else ""))
            self.current_state = state
            expr_map = {
                'idle':      IdleExpression,
                'listening': ListeningExpression,
                'thinking':  ThinkingExpression,
                'speaking':  SpeakingExpression,
                'confused':  ConfusedExpression,
                'music':     lambda: MusicExpression(bpm),
            }
            self.expressions[state] = expr_map[state]()

    def render_frame(self):
        self.screen.fill(BLACK)
        self.face_surface.fill(DARK_BG)
        draw_grid(self.face_surface)
        expr = self.expressions[self.current_state]
        expr.update()
        expr.draw(self.face_surface)
        self.screen.blit(self.face_surface, (BORDER, BORDER))
        pygame.draw.rect(
            self.screen, DARK_PURP,
            (BORDER - 1, BORDER - 1, FACE_W + 2, FACE_H + 2), 1
        )
        pygame.display.flip()

    def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.display.iconify()
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_1:
                        self.set_state('idle')
                    elif event.key == pygame.K_2:
                        self.set_state('listening')
                    elif event.key == pygame.K_3:
                        self.set_state('thinking')
                    elif event.key == pygame.K_4:
                        self.set_state('speaking')
                    elif event.key == pygame.K_5:
                        self.set_state('confused')
            self.render_frame()
            self.clock.tick(FPS)
        pygame.quit()

import multiprocessing
import ctypes

def face_process(state_value):
    """Run face in separate process."""
    face = JarvisFace()
    last_state = 'idle'

    def apply_state(raw: str):
        face.set_state(raw)

    while face.running:
        current = state_value.value.decode().strip()
        if current != last_state:
            apply_state(current)
            last_state = current
            
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.display.iconify()
                
        face.render_frame()
        face.clock.tick(FPS)
    
    pygame.quit()

class FaceController:
    def __init__(self):
        self.state_value = multiprocessing.Array(ctypes.c_char, 24)
        self.state_value.value = b'idle'
        self.process = multiprocessing.Process(
            target=face_process,
            args=(self.state_value,),
            daemon=True
        )
        self.process.start()
    
    def set_state(self, state: str):
        print(f"Face: {state}")
        self.state_value.value = state.encode()

def create_face_controller():
    return FaceController()