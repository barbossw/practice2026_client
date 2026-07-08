import pygame
import asyncio
import websockets
from websockets.protocol import State
import json
import sys
import time
import math
import os
import random

# Инициализация микшера для музыки
try:
    pygame.mixer.init()
except Exception as e:
    print(f"Не удалось инициализировать аудио: {e}")

# Константы (основанные на сервере)
SERVER_LEFT_WALL = -200.0
SERVER_RIGHT_WALL = 200.0
SERVER_DOWN_WALL = -300.0
SERVER_TOP_WALL = 300.0

PUCK_RADIUS = 20
PLAYER_RADIUS = 50

# Размеры окна Pygame
SCREEN_WIDTH = int(SERVER_RIGHT_WALL - SERVER_LEFT_WALL)   # 400
SCREEN_HEIGHT = int(SERVER_TOP_WALL - SERVER_DOWN_WALL)    # 600

FPS = 120

def to_server_coords(screen_x, screen_y):
    """Преобразует координаты экрана Pygame в систему координат сервера."""
    server_x = screen_x + SERVER_LEFT_WALL
    server_y = SERVER_TOP_WALL - screen_y
    return float(server_x), float(server_y)

def to_screen_coords(server_x, server_y):
    """Преобразует координаты сервера обратно в систему координат экрана."""
    screen_x = server_x - SERVER_LEFT_WALL
    screen_y = SERVER_TOP_WALL - server_y
    return int(screen_x), int(screen_y)

def load_image_safely(path, size):
    if path and os.path.exists(path):
        try:
            img = pygame.image.load(path).convert()
            return pygame.transform.scale(img, size)
        except Exception as e:
            print(f"Не удалось загрузить картинку {path}: {e}")
    return None

def draw_styled_circle(surface, color, x, y, radius, theme_name, outline_width=3):
    """Отрисовка игроков с полупрозрачным стилем и рамками."""
    if theme_name == "Classic":
        pygame.draw.circle(surface, color, (x, y), radius)
        pygame.draw.circle(surface, (255, 255, 255), (x, y), radius, outline_width)
    else:
        temp_surface = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
        r, g, b = color
        
        # Полупрозрачная заливка 
        pygame.draw.circle(temp_surface, (r, g, b, 60), (radius, radius), radius)
        # Внешний светящийся контур
        pygame.draw.circle(temp_surface, (r, g, b, 255), (radius, radius), radius, outline_width)
        # Внутреннее кольцо-деталь (как на скриншотах)
        inner_radius = max(2, radius // 3)
        pygame.draw.circle(temp_surface, (r, g, b, 255), (radius, radius), inner_radius, 2)
        
        surface.blit(temp_surface, (x - radius, y - radius))

def draw_styled_puck(surface, color, x, y, radius, theme_name):
    """Отрисовка шайбы."""
    if theme_name == "Classic":
        pygame.draw.circle(surface, color, (x, y), radius)
    else:
        temp_surface = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
        r, g, b = color
        
        pygame.draw.circle(temp_surface, (r, g, b, 80), (radius, radius), radius)
        pygame.draw.circle(temp_surface, (r, g, b, 255), (radius, radius), radius, 3)
        inner_radius = max(2, radius // 2)
        pygame.draw.circle(temp_surface, (r, g, b, 255), (radius, radius), inner_radius, 2)
        
        surface.blit(temp_surface, (x - radius, y - radius))

async def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Air Hockey - Client")
    font = pygame.font.Font(None, 48)
    small_font = pygame.font.Font(None, 36)
    ping_font = pygame.font.Font(None, 24)

    # === НАСТРОЙКИ ТЕМ ===
    THEMES = [
        {
            "name": "Classic",
            "bg_color": (240, 248, 255),
            "line_color": (100, 100, 100),
            "p1_color": (30, 144, 255),   # Синий
            "p2_color": (220, 20, 60),    # Красный
            "puck_color": (50, 50, 50),
            "text_color": (0, 0, 0),
            "bg_image": None
        },
        {
            "name": "Neon",
            "bg_color": (0, 0, 0),
            "line_color": (0, 255, 255),
            "p1_color": (57, 255, 20),    # Неоновый зеленый
            "p2_color": (255, 20, 147),   # Неоновый розовый
            "puck_color": (138, 43, 226), # Фиолетовый
            "text_color": (0, 255, 255),
            "bg_image": load_image_safely("image.png", (SCREEN_WIDTH, SCREEN_HEIGHT))
        },
        {
            "name": "Peach",
            "bg_color": (255, 218, 185),
            "line_color": (255, 255, 255),
            "p1_color": (139, 69, 19),    # Коричневый
            "p2_color": (205, 133, 63),   # Темно-персиковый
            "puck_color": (255, 248, 220),# Кремовый
            "text_color": (139, 69, 19),
            "bg_image": load_image_safely("image_2.png", (SCREEN_WIDTH, SCREEN_HEIGHT))
        },
        {
            "name": "Space",
            "bg_color": (10, 10, 30),
            "line_color": (0, 255, 255),
            "p1_color": (0, 150, 255),    # Земля (Синий)
            "p2_color": (200, 50, 50),    # Марс (Красный)
            "puck_color": (200, 200, 200),# Луна (Серый)
            "text_color": (255, 255, 255),
            "bg_image": load_image_safely("image_3.png", (SCREEN_WIDTH, SCREEN_HEIGHT))
        }
    ]
    current_theme_idx = 0
    
    # === НАСТРОЙКИ ЗВУКА И ПОИСК МУЗЫКИ ===
    music_volume = 0.5
    music_loaded = False
    music_dir = "music"
    
    if os.path.exists(music_dir) and os.path.isdir(music_dir):
        # Ищем все аудиофайлы в папке
        music_files = [os.path.join(music_dir, f) for f in os.listdir(music_dir) if f.endswith(('.mp3', '.ogg', '.wav'))]
        if music_files:
            try:
                # Берем случайный трек из папки
                track = random.choice(music_files)
                pygame.mixer.music.load(track)
                pygame.mixer.music.set_volume(music_volume)
                pygame.mixer.music.play(-1)
                music_loaded = True
                print(f"Музыка '{track}' загружена.")
            except Exception as e:
                print(f"Ошибка загрузки музыки: {e}")
        else:
            print("В папке 'music' нет аудиофайлов (.mp3, .ogg, .wav).")
    else:
        print("Папка 'music' не найдена. Создайте её и положите туда музыку.")

    uri = "wss://practice2026-qw8b.onrender.com/ws_connect"
    app_state = "MENU"
    dragging_slider = False
    
    # Глобальный флаг работы программы для плавного выхода
    running = True

    while running:
        theme = THEMES[current_theme_idx]
        
        # === ГЛАВНОЕ МЕНЮ ===
        if app_state == "MENU":
            mouse_pos = pygame.mouse.get_pos()
            
            play_btn_rect = pygame.Rect(SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 - 60, 200, 60)
            settings_btn_rect = pygame.Rect(SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 + 20, 200, 60)
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False # Плавный выход
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if play_btn_rect.collidepoint(event.pos):
                        app_state = "CONNECTING"
                    elif settings_btn_rect.collidepoint(event.pos):
                        app_state = "SETTINGS"

            if theme["bg_image"]:
                screen.blit(theme["bg_image"], (0, 0))
            else:
                screen.fill(theme["bg_color"])
            
            play_color = (39, 174, 96) if play_btn_rect.collidepoint(mouse_pos) else (46, 204, 113)
            pygame.draw.rect(screen, play_color, play_btn_rect, border_radius=15)
            play_text = font.render("1 vs 1", True, (255, 255, 255))
            screen.blit(play_text, (play_btn_rect.centerx - play_text.get_width() // 2, play_btn_rect.centery - play_text.get_height() // 2))
            
            settings_color = (41, 128, 185) if settings_btn_rect.collidepoint(mouse_pos) else (52, 152, 219)
            pygame.draw.rect(screen, settings_color, settings_btn_rect, border_radius=15)
            settings_text = small_font.render("Настройки", True, (255, 255, 255))
            screen.blit(settings_text, (settings_btn_rect.centerx - settings_text.get_width() // 2, settings_btn_rect.centery - settings_text.get_height() // 2))
            
            pygame.display.flip()
            await asyncio.sleep(1/FPS)

        # === МЕНЮ НАСТРОЕК ===
        elif app_state == "SETTINGS":
            mouse_pos = pygame.mouse.get_pos()
            
            theme_btn_rect = pygame.Rect(SCREEN_WIDTH // 2 - 125, SCREEN_HEIGHT // 2 - 100, 250, 60)
            back_btn_rect = pygame.Rect(SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 + 100, 200, 60)
            
            slider_track_rect = pygame.Rect(SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 + 20, 200, 10)
            slider_handle_rect = pygame.Rect(slider_track_rect.x + int(music_volume * slider_track_rect.width) - 10, slider_track_rect.y - 10, 20, 30)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if theme_btn_rect.collidepoint(event.pos):
                        current_theme_idx = (current_theme_idx + 1) % len(THEMES)
                    elif back_btn_rect.collidepoint(event.pos):
                        app_state = "MENU"
                    elif slider_track_rect.collidepoint(event.pos) or slider_handle_rect.collidepoint(event.pos):
                        dragging_slider = True
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    dragging_slider = False

            if dragging_slider:
                rel_x = mouse_pos[0] - slider_track_rect.x
                music_volume = max(0.0, min(1.0, rel_x / slider_track_rect.width))
                if music_loaded:
                    pygame.mixer.music.set_volume(music_volume)

            if theme["bg_image"]:
                screen.blit(theme["bg_image"], (0, 0))
            else:
                screen.fill(theme["bg_color"])

            theme_color = (142, 68, 173) if theme_btn_rect.collidepoint(mouse_pos) else (155, 89, 182)
            pygame.draw.rect(screen, theme_color, theme_btn_rect, border_radius=15)
            theme_text = small_font.render(f"Тема: {theme['name']}", True, (255, 255, 255))
            screen.blit(theme_text, (theme_btn_rect.centerx - theme_text.get_width() // 2, theme_btn_rect.centery - theme_text.get_height() // 2))

            vol_label = small_font.render("Громкость музыки", True, theme["text_color"])
            screen.blit(vol_label, (SCREEN_WIDTH // 2 - vol_label.get_width() // 2, slider_track_rect.y - 40))
            
            pygame.draw.rect(screen, (50, 50, 50, 180), slider_track_rect, border_radius=5)
            filled_rect = pygame.Rect(slider_track_rect.x, slider_track_rect.y, int(music_volume * slider_track_rect.width), slider_track_rect.height)
            pygame.draw.rect(screen, (46, 204, 113), filled_rect, border_radius=5)
            pygame.draw.rect(screen, (255, 255, 255), slider_handle_rect, border_radius=5)

            back_color = (231, 76, 60) if back_btn_rect.collidepoint(mouse_pos) else (192, 57, 43)
            pygame.draw.rect(screen, back_color, back_btn_rect, border_radius=15)
            back_text = small_font.render("Назад", True, (255, 255, 255))
            screen.blit(back_text, (back_btn_rect.centerx - back_text.get_width() // 2, back_btn_rect.centery - back_text.get_height() // 2))

            pygame.display.flip()
            await asyncio.sleep(1/FPS)

        # === ПОДКЛЮЧЕНИЕ И ИГРА ===
        elif app_state == "CONNECTING":
            screen.fill(theme["bg_color"])
            wait_text = small_font.render("Подключение к серверу...", True, theme["text_color"])
            screen.blit(wait_text, (SCREEN_WIDTH // 2 - wait_text.get_width() // 2, SCREEN_HEIGHT // 2))
            pygame.display.flip()

            try:
                # Блок async with сам гарантирует отправку Close Frame при выходе из него
                async with websockets.connect(uri, ping_interval=1.0) as websocket:
                    app_state = "PLAYING"
                    
                    game_state = {
                        "player1": {"position": {"first": 0.0, "second": -200.0}},
                        "player2": {"position": {"first": 0.0, "second": 200.0}},
                        "puck": {"position": {"first": 0.0, "second": 0.0}},
                        "score": {"first": 0, "second": 0}
                    }
                    
                    paddle_x = SCREEN_WIDTH // 2
                    paddle_y = SCREEN_HEIGHT - 100
                    paddle_vx = 0.0
                    paddle_vy = 0.0
                    is_dragging = False

                    connection_info = {
                        "last_packet_time": time.time(),
                        "disconnect_reason": None,
                        "game_started": False,
                        "pause_sending": False 
                    }

                    async def receive_messages():
                        try:
                            async for message in websocket:
                                data = json.loads(message)
                                if data.get("type") == "GameState":
                                    new_score = data["data"]["score"]
                                    if new_score["first"] != game_state["score"]["first"] or new_score["second"] != game_state["score"]["second"]:
                                        connection_info["pause_sending"] = True
                                    else:
                                        connection_info["pause_sending"] = False

                                    connection_info["game_started"] = True
                                    connection_info["last_packet_time"] = time.time()
                                    game_state.update(data["data"])
                                elif data.get("type") == "Message":
                                    msg = data.get("data", "")
                                    print(f"Сообщение от сервера: {msg}")
                                    if "stop" in msg.lower() or "disconnect" in msg.lower() or "reached" in msg.lower():
                                        connection_info["disconnect_reason"] = "Игра остановлена сервером!"
                        except websockets.exceptions.ConnectionClosed:
                            if connection_info["disconnect_reason"] is None:
                                connection_info["disconnect_reason"] = "Соединение разорвано сервером!"
                        except asyncio.CancelledError:
                            pass
                            
                    receive_task = asyncio.create_task(receive_messages())

                    # ВАЖНО: Добавлено `and running`, чтобы при закрытии окна на крестик
                    # игра мгновенно выходила из цикла и безопасно закрывала сокет
                    # ВАЖНО: Добавлено `and running`
                    while app_state == "PLAYING" and running:
                        theme = THEMES[current_theme_idx]
                        
                        # 1. Если сервер сам остановил игру
                        if connection_info["disconnect_reason"] is not None:
                            app_state = "DISCONNECTED_SCREEN"
                            # ЯВНО ЗАКРЫВАЕМ СОКЕТ
                            if websocket.state == State.OPEN:
                                await websocket.close()
                            break 

                        # 2. Если оппонент отключился (таймаут)
                        if connection_info["game_started"]:
                            if time.time() - connection_info["last_packet_time"] > 1.5:
                                connection_info["disconnect_reason"] = "Оппонент отключился!"
                                app_state = "DISCONNECTED_SCREEN"
                                # ЯВНО ЗАКРЫВАЕМ СОКЕТ
                                if websocket.state == State.OPEN:
                                    await websocket.close()
                                break 

                        # 3. Обработка событий Pygame
                        for event in pygame.event.get():
                            if event.type == pygame.QUIT:
                                # ЯВНО ЗАКРЫВАЕМ СОКЕТ перед выходом
                                if websocket.state == State.OPEN:
                                    await websocket.close()
                                running = False
                            
                            if event.type == pygame.KEYDOWN:
                                if event.key == pygame.K_ESCAPE:
                                    connection_info["disconnect_reason"] = "Вы вышли в меню"
                                    app_state = "DISCONNECTED_SCREEN"
                                    # ЯВНО ЗАКРЫВАЕМ СОКЕТ
                                    if websocket.state == State.OPEN:
                                        await websocket.close()
                                    break 

                            if connection_info["game_started"]:
                                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                                    mouse_x, mouse_y = event.pos
                                    distance = math.hypot(mouse_x - paddle_x, mouse_y - paddle_y)
                                    if distance <= PLAYER_RADIUS:
                                        is_dragging = True

                                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                                    is_dragging = False


                        # Если было прерывание по ESC или крестику
                        if app_state != "PLAYING" or not running:
                            break

                        MAX_SPEED = 9.0

                        if is_dragging and connection_info["game_started"]:
                            mouse_x, mouse_y = pygame.mouse.get_pos()
                            dx = mouse_x - paddle_x
                            dy = mouse_y - paddle_y
                            distance = math.hypot(dx, dy)
                            
                            if distance > MAX_SPEED:
                                dx = (dx / distance) * MAX_SPEED
                                dy = (dy / distance) * MAX_SPEED
                            
                            paddle_vx = dx
                            paddle_vy = dy
                            
                            paddle_x += paddle_vx
                            paddle_y += paddle_vy
                        else:
                            paddle_x += paddle_vx
                            paddle_y += paddle_vy
                            paddle_vx *= 0.92
                            paddle_vy *= 0.92
                            if abs(paddle_vx) < 0.1: paddle_vx = 0
                            if abs(paddle_vy) < 0.1: paddle_vy = 0

                        if paddle_x < PLAYER_RADIUS: paddle_x = PLAYER_RADIUS
                        elif paddle_x > SCREEN_WIDTH - PLAYER_RADIUS: paddle_x = SCREEN_WIDTH - PLAYER_RADIUS
                            
                        if paddle_y < SCREEN_HEIGHT // 2 + PLAYER_RADIUS: paddle_y = SCREEN_HEIGHT // 2 + PLAYER_RADIUS
                        elif paddle_y > SCREEN_HEIGHT - PLAYER_RADIUS: paddle_y = SCREEN_HEIGHT - PLAYER_RADIUS

                        if not connection_info["pause_sending"]:
                            try:
                                server_x, server_y = to_server_coords(paddle_x, paddle_y)
                                payload = {"position": {"x": server_x, "y": server_y}}
                                if websocket.state == State.OPEN:
                                    await websocket.send(json.dumps(payload))
                            except websockets.exceptions.ConnectionClosed:
                                pass 
                        else:
                            is_dragging = False
                            paddle_vx = 0
                            paddle_vy = 0
                            p1_pos = game_state["player1"]["position"]
                            paddle_x, paddle_y = to_screen_coords(p1_pos["first"], p1_pos["second"])

                        # Отрисовка
                        if theme["bg_image"]:
                            screen.blit(theme["bg_image"], (0, 0))
                        else:
                            screen.fill(theme["bg_color"])
                            pygame.draw.line(screen, theme["line_color"], (0, SCREEN_HEIGHT // 2), (SCREEN_WIDTH, SCREEN_HEIGHT // 2), 3)

                        p1_pos = game_state["player1"]["position"]
                        p2_pos = game_state["player2"]["position"]
                        puck_pos = game_state["puck"]["position"]
                        score = game_state["score"]

                        p1_x, p1_y = to_screen_coords(p1_pos["first"], p1_pos["second"])
                        outline_width = 5 if is_dragging else 3
                        draw_styled_circle(screen, theme["p1_color"], p1_x, p1_y, PLAYER_RADIUS, theme["name"], outline_width)

                        p2_x, p2_y = to_screen_coords(p2_pos["first"], p2_pos["second"])
                        draw_styled_circle(screen, theme["p2_color"], p2_x, p2_y, PLAYER_RADIUS, theme["name"])

                        puck_x, puck_y = to_screen_coords(puck_pos["first"], puck_pos["second"])
                        draw_styled_puck(screen, theme["puck_color"], puck_x, puck_y, PUCK_RADIUS, theme["name"])

                        if not connection_info["game_started"]:
                            wait_bg = wait_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
                            pygame.draw.rect(screen, theme["bg_color"], wait_bg.inflate(20, 20))
                            screen.blit(wait_text, wait_bg)
                        else:
                            score_text = font.render(f"{score['first']} - {score['second']}", True, theme["text_color"])
                            screen.blit(score_text, (SCREEN_WIDTH // 2 - score_text.get_width() // 2, 20))
                            
                            ping_ms = 0
                            if websocket.state == State.OPEN and not math.isnan(websocket.latency):
                                ping_ms = int(websocket.latency * 1000)
                            
                            ping_color = (46, 204, 113) if ping_ms < 80 else (241, 196, 15) if ping_ms < 150 else (231, 76, 60)
                            ping_render = ping_font.render(f"Ping: {ping_ms} ms", True, ping_color)
                            ping_bg = ping_render.get_rect(topleft=(10, 10))
                            pygame.draw.rect(screen, (0, 0, 0, 128), ping_bg.inflate(10, 4))
                            screen.blit(ping_render, (10, 10))

                        pygame.display.flip()
                        await asyncio.sleep(1/FPS)
                
                # Завершаем фоновую задачу ПЕРЕД выходом из async with
                receive_task.cancel()
                try:
                    await receive_task
                except asyncio.CancelledError:
                    pass

            except ConnectionRefusedError:
                print("Не удалось подключиться к серверу.")
                app_state = "MENU"
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Ошибка: {e}")
                app_state = "MENU"
                await asyncio.sleep(1)
                
        # === ЭКРАН ОТКЛЮЧЕНИЯ ===
        elif app_state == "DISCONNECTED_SCREEN":
            start_time = time.time()
            
            while time.time() - start_time < 2.0 and running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False

                screen.fill(theme["bg_color"])
                
                msg_text = small_font.render(connection_info.get("disconnect_reason", "Игра окончена!"), True, (220, 20, 60))
                screen.blit(msg_text, (SCREEN_WIDTH // 2 - msg_text.get_width() // 2, SCREEN_HEIGHT // 2 - 20))
                
                return_text = small_font.render("Возврат в меню...", True, theme["text_color"])
                screen.blit(return_text, (SCREEN_WIDTH // 2 - return_text.get_width() // 2, SCREEN_HEIGHT // 2 + 20))
                
                pygame.display.flip()
                await asyncio.sleep(1/FPS)
            
            if running:
                app_state = "MENU"

    # Корректное завершение после выхода из всех циклов
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    asyncio.run(main())