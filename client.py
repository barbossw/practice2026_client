import pygame
import asyncio
import websockets
from websockets.protocol import State
import json
import sys
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
                    print("Успешное подключение! Ожидание второго игрока...")
                    app_state = "PLAYING"
                    
                    game_state = {
                        "player1": {"position": {"first": 0.0, "second": -200.0}},
                        "player2": {"position": {"first": 0.0, "second": 200.0}},
                        "puck": {"position": {"first": 0.0, "second": 0.0}},
                        "score": {"first": 0, "second": 0}
                    }
                    is_dragging = False

                    # ---------------------------------------------------------
                    # ФОНОВАЯ ЗАДАЧА ДЛЯ ЧТЕНИЯ ДАННЫХ
                    # Она работает параллельно и больше не тормозит отрисовку
                    # ---------------------------------------------------------
                    async def receive_messages():
                        try:
                            async for message in websocket:
                                data = json.loads(message)
                                if data.get("type") == "GameState":
                                    game_state.update(data["data"])
                                elif data.get("type") == "Message":
                                    print(f"Сообщение: {data.get('data')}")
                        except websockets.exceptions.ConnectionClosed:
                            print("Соединение разорвано. Возврат в меню.")
                            
                    # Запускаем чтение в фоне
                    receive_task = asyncio.create_task(receive_messages())

                    # Основной игровой цикл
                    while app_state == "PLAYING":
                        # Проверяем, не закрылось ли соединение в фоновой задаче
                        if receive_task.done():
                            app_state = "MENU"
                            break

                        # 1. Обработка событий Pygame
                        for event in pygame.event.get():
                            if event.type == pygame.QUIT:
                                receive_task.cancel()
                                pygame.quit()
                                sys.exit()
                            
                            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                                mouse_x, mouse_y = event.pos
                                p1_pos = game_state["player1"]["position"]
                                p1_screen_x, p1_screen_y = to_screen_coords(p1_pos["first"], p1_pos["second"])
                                
                                distance = math.hypot(mouse_x - p1_screen_x, mouse_y - p1_screen_y)
                                if distance <= PLAYER_RADIUS:
                                    is_dragging = True

                            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                                is_dragging = False

                        # 2. Логика отправки координат (теперь не тормозит)
                        try:
                            if is_dragging:
                                mouse_x, mouse_y = pygame.mouse.get_pos()
                                if mouse_y < SCREEN_HEIGHT // 2:
                                    mouse_y = SCREEN_HEIGHT // 2

                                server_x, server_y = to_server_coords(mouse_x, mouse_y)
                                payload = {"position": {"x": server_x, "y": server_y}}
                            else:
                                p1_pos = game_state["player1"]["position"]
                                payload = {"position": {"x": p1_pos["first"], "y": p1_pos["second"]}}

                            if websocket.state == State.OPEN:
                                await websocket.send(json.dumps(payload))
                                
                        except websockets.exceptions.ConnectionClosed:
                            app_state = "MENU"
                            break

                        # 3. Отрисовка
                        screen.fill(COLOR_BG)
                        pygame.draw.line(screen, COLOR_LINE, (0, SCREEN_HEIGHT // 2), (SCREEN_WIDTH, SCREEN_HEIGHT // 2), 3)

                        p1_pos = game_state["player1"]["position"]
                        p2_pos = game_state["player2"]["position"]
                        puck_pos = game_state["puck"]["position"]
                        score = game_state["score"]

                        # Player 1
                        p1_x, p1_y = to_screen_coords(p1_pos["first"], p1_pos["second"])
                        outline_width = 0 if is_dragging else 3
                        pygame.draw.circle(screen, COLOR_PLAYER1, (p1_x, p1_y), PLAYER_RADIUS)
                        pygame.draw.circle(screen, (0, 0, 139), (p1_x, p1_y), PLAYER_RADIUS, outline_width)

                        # Player 2
                        p2_x, p2_y = to_screen_coords(p2_pos["first"], p2_pos["second"])
                        pygame.draw.circle(screen, COLOR_PLAYER2, (p2_x, p2_y), PLAYER_RADIUS)

                        # Puck
                        puck_x, puck_y = to_screen_coords(puck_pos["first"], puck_pos["second"])
                        pygame.draw.circle(screen, COLOR_PUCK, (puck_x, puck_y), PUCK_RADIUS)

                        # Score
                        score_text = font.render(f"{score['first']} - {score['second']}", True, COLOR_TEXT)
                        screen.blit(score_text, (SCREEN_WIDTH // 2 - score_text.get_width() // 2, 20))

                        pygame.display.flip()
                        
                        # Даем event loop время на обработку фоновой задачи (пауза ~60 FPS)
                        await asyncio.sleep(1/FPS)

                    # Отменяем фоновую задачу при выходе из игры
                    receive_task.cancel()

            except ConnectionRefusedError:
                print("Не удалось подключиться к серверу.")
                app_state = "MENU"
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Ошибка: {e}")
                app_state = "MENU"

if __name__ == "__main__":
    asyncio.run(main())