import pygame
import asyncio
import websockets
from websockets.protocol import State
import json
import sys
import time
import math


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

# Цвета
COLOR_BG = (240, 248, 255)
COLOR_LINE = (100, 100, 100)
COLOR_PLAYER1 = (30, 144, 255)  # Ваш игрок (Синий)
COLOR_PLAYER2 = (220, 20, 60)   # Оппонент (Красный)
COLOR_PUCK = (50, 50, 50)
COLOR_TEXT = (0, 0, 0)
COLOR_BUTTON = (46, 204, 113)
COLOR_BUTTON_HOVER = (39, 174, 96)

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

async def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Air Hockey - Client")
    font = pygame.font.Font(None, 48)
    small_font = pygame.font.Font(None, 36)

    uri = "wss://practice2026-qw8b.onrender.com/ws_connect"
    
    # Состояние приложения: "MENU" -> "CONNECTING" -> "PLAYING"
    app_state = "MENU"

    while True:
        if app_state == "MENU":
            mouse_pos = pygame.mouse.get_pos()
            button_rect = pygame.Rect(SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 - 40, 200, 80)
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                # Если нажали ЛКМ в меню
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if button_rect.collidepoint(event.pos):
                        app_state = "CONNECTING"

            screen.fill(COLOR_BG)
            
            # Эффект наведения на кнопку
            btn_color = COLOR_BUTTON_HOVER if button_rect.collidepoint(mouse_pos) else COLOR_BUTTON
            pygame.draw.rect(screen, btn_color, button_rect, border_radius=15)
            
            text = font.render("1 vs 1", True, (255, 255, 255))
            screen.blit(text, (button_rect.centerx - text.get_width() // 2, button_rect.centery - text.get_height() // 2))
            
            pygame.display.flip()
            await asyncio.sleep(1/FPS)

        elif app_state == "CONNECTING":
            screen.fill(COLOR_BG)
            wait_text = small_font.render("Подключение к серверу...", True, COLOR_TEXT)
            screen.blit(wait_text, (SCREEN_WIDTH // 2 - wait_text.get_width() // 2, SCREEN_HEIGHT // 2))
            pygame.display.flip()

            try:
                async with websockets.connect(uri) as websocket:
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
                        "game_started": False 
                    }

                    async def receive_messages():
                        try:
                            async for message in websocket:
                                data = json.loads(message)
                                if data.get("type") == "GameState":
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

                    while app_state == "PLAYING":
                        # 1. Проверяем причины для отключения
                        if connection_info["disconnect_reason"] is not None:
                            app_state = "DISCONNECTED_SCREEN"
                            # ЯВНО ЗАКРЫВАЕМ СОКЕТ
                            if websocket.state == State.OPEN:
                                await websocket.close()
                            break 

                        # Проверяем таймаут (если второй игрок вышел или сервер завис)
                        if connection_info["game_started"]:
                            if time.time() - connection_info["last_packet_time"] > 1.5:
                                connection_info["disconnect_reason"] = "Оппонент отключился!"
                                app_state = "DISCONNECTED_SCREEN"
                                # ЯВНО ЗАКРЫВАЕМ СОКЕТ, чтобы освободить свой слот!
                                if websocket.state == State.OPEN:
                                    await websocket.close()
                                break 

                        # 2. Обработка событий
                        for event in pygame.event.get():
                            if event.type == pygame.QUIT:
                                # ВАЖНО: Закрываем сокет перед sys.exit()
                                if websocket.state == State.OPEN:
                                    await websocket.close()
                                pygame.quit()
                                sys.exit()
                            
                            # Выход в меню через ESCAPE
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

                        # Если вышли по ESC, прерываем игровой цикл
                        if app_state != "PLAYING":
                            break

                        # 3. Физика биты
                        if is_dragging and connection_info["game_started"]:
                            mouse_x, mouse_y = pygame.mouse.get_pos()
                            paddle_vx = mouse_x - paddle_x
                            paddle_vy = mouse_y - paddle_y
                            paddle_x = mouse_x
                            paddle_y = mouse_y
                        else:
                            paddle_x += paddle_vx
                            paddle_y += paddle_vy
                            paddle_vx *= 0.92
                            paddle_vy *= 0.92
                            if abs(paddle_vx) < 0.1: paddle_vx = 0
                            if abs(paddle_vy) < 0.1: paddle_vy = 0

                        # Ограничения движения
                        if paddle_x < PLAYER_RADIUS:
                            paddle_x = PLAYER_RADIUS
                            paddle_vx = 0
                        elif paddle_x > SCREEN_WIDTH - PLAYER_RADIUS:
                            paddle_x = SCREEN_WIDTH - PLAYER_RADIUS
                            paddle_vx = 0
                            
                        if paddle_y < SCREEN_HEIGHT // 2 + PLAYER_RADIUS:
                            paddle_y = SCREEN_HEIGHT // 2 + PLAYER_RADIUS
                            paddle_vy = 0
                        elif paddle_y > SCREEN_HEIGHT - PLAYER_RADIUS:
                            paddle_y = SCREEN_HEIGHT - PLAYER_RADIUS
                            paddle_vy = 0

                        # 4. Отправка пакетов
                        try:
                            server_x, server_y = to_server_coords(paddle_x, paddle_y)
                            payload = {"position": {"x": server_x, "y": server_y}}
                            if websocket.state == State.OPEN:
                                await websocket.send(json.dumps(payload))
                        except websockets.exceptions.ConnectionClosed:
                            pass 

                        # 5. Отрисовка
                        screen.fill(COLOR_BG)
                        pygame.draw.line(screen, COLOR_LINE, (0, SCREEN_HEIGHT // 2), (SCREEN_WIDTH, SCREEN_HEIGHT // 2), 3)

                        p2_pos = game_state["player2"]["position"]
                        puck_pos = game_state["puck"]["position"]
                        score = game_state["score"]

                        outline_width = 0 if is_dragging else 3
                        pygame.draw.circle(screen, COLOR_PLAYER1, (int(paddle_x), int(paddle_y)), PLAYER_RADIUS)
                        pygame.draw.circle(screen, (0, 0, 139), (int(paddle_x), int(paddle_y)), PLAYER_RADIUS, outline_width)

                        p2_x, p2_y = to_screen_coords(p2_pos["first"], p2_pos["second"])
                        pygame.draw.circle(screen, COLOR_PLAYER2, (p2_x, p2_y), PLAYER_RADIUS)

                        puck_x, puck_y = to_screen_coords(puck_pos["first"], puck_pos["second"])
                        pygame.draw.circle(screen, COLOR_PUCK, (puck_x, puck_y), PUCK_RADIUS)

                        if not connection_info["game_started"]:
                            wait_bg = wait_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
                            pygame.draw.rect(screen, COLOR_BG, wait_bg.inflate(20, 20))
                            screen.blit(wait_text, wait_bg)
                        else:
                            score_text = font.render(f"{score['first']} - {score['second']}", True, COLOR_TEXT)
                            screen.blit(score_text, (SCREEN_WIDTH // 2 - score_text.get_width() // 2, 20))

                        pygame.display.flip()
                        await asyncio.sleep(0.016)
                
                # Отменяем фоновую задачу только после того, как сокет гарантированно закрыт
                if not receive_task.done():
                    receive_task.cancel()

            except ConnectionRefusedError:
                print("Не удалось подключиться к серверу.")
                app_state = "MENU"
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Ошибка: {e}")
                app_state = "MENU"
                await asyncio.sleep(1)
            # === НОВОЕ СОСТОЯНИЕ ДЛЯ ЭКРАНА ОТКЛЮЧЕНИЯ ===
        elif app_state == "DISCONNECTED_SCREEN":
            # Запоминаем время начала показа экрана
            start_time = time.time()
            
            # Крутим цикл ровно 2 секунды, чтобы Pygame не зависал
            while time.time() - start_time < 2.0:
                # Обязательно обрабатываем события, иначе окно "крашнется"
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()
                        sys.exit()

                screen.fill(COLOR_BG)
                
                # Причина отключения
                msg_text = small_font.render(connection_info.get("disconnect_reason", "Игра окончена!"), True, (220, 20, 60))
                screen.blit(msg_text, (SCREEN_WIDTH // 2 - msg_text.get_width() // 2, SCREEN_HEIGHT // 2 - 20))
                
                # Текст возврата
                return_text = small_font.render("Возврат в меню...", True, COLOR_TEXT)
                screen.blit(return_text, (SCREEN_WIDTH // 2 - return_text.get_width() // 2, SCREEN_HEIGHT // 2 + 20))
                
                pygame.display.flip()
                await asyncio.sleep(0.016) # Пауза в 1 кадр
            
            # После 2 секунд плавно возвращаемся в меню
            app_state = "MENU"

if __name__ == "__main__":
    asyncio.run(main())