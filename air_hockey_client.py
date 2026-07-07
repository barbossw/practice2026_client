import asyncio
import websockets
import json
import pygame
import sys

# Server Constants Map & Screen Dimensions
# X: -200 to 200 (width = 400)
# Y: -300 to 300 (height = 600)
WIDTH = 400
HEIGHT = 600
FPS = 60
PLAYER_RADIUS = 50
PUCK_RADIUS = 20

# Colors for a simple, clean design
WHITE = (245, 245, 245)
BLACK = (40, 40, 40)
RED = (235, 87, 87)
BLUE = (45, 156, 219)
GREEN = (39, 174, 96)
LINE_COLOR = (200, 200, 200)

# Global Game State (Defaults)
game_state = {
    "puck": {"first": 0, "second": 0},
    "player1": {"first": 0, "second": -150},
    "player2": {"first": 0, "second": 150},
    "score": {"first": 0, "second": 0}
}

def to_screen(x, y):
    # Maps Server coordinates to PyGame screen coordinates
    # Server: (0,0) is center, Y increases upwards
    # Screen: (0,0) is top-left, Y increases downwards
    return int(x + 200), int(300 - y)

def to_server(x, y):
    # Maps PyGame screen coordinates back to Server coordinates
    return float(x - 200), float(300 - y)

async def receive_data(ws):
    global game_state
    try:
        async for message in ws:
            try:
                data = json.loads(message)
                if data.get("type") == "GameState":
                    state_data = data.get("data", {})
                    # Update local state with server truth
                    if "puck" in state_data:
                        game_state["puck"] = state_data["puck"]["position"]
                    if "player1" in state_data:
                        game_state["player1"] = state_data["player1"]["position"]
                    if "player2" in state_data:
                        game_state["player2"] = state_data["player2"]["position"]
                    if "score" in state_data:
                        game_state["score"] = state_data["score"]
            except json.JSONDecodeError:
                pass
    except websockets.exceptions.ConnectionClosed:
        print("Connection closed by server.")
    except Exception as e:
        print(f"Error receiving data: {e}")

async def main(server_uri="ws://localhost:8000/ws_connect"):
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Air Hockey - Client")
    
    font = pygame.font.SysFont("Arial", 48, bold=True)
    small_font = pygame.font.SysFont("Arial", 16)

    ws = None
    try:
        print(f"Connecting to {server_uri}...")
        ws = await websockets.connect(server_uri)
        # Run receiver in the background
        asyncio.create_task(receive_data(ws))
        print("Connected!")
    except Exception as e:
        print(f"Could not connect to server: {e}")
        print("Running in offline/render-only mode.")

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # Input Handling
        mx, my = pygame.mouse.get_pos()
        
        # Constrain mouse strictly to the user's (bottom) half of the field
        # The user's center point cannot cross the middle line
        if my < HEIGHT // 2 + PLAYER_RADIUS:
            my = HEIGHT // 2 + PLAYER_RADIUS
            
        sx, sy = to_server(mx, my)

        # Transmit latest position to the server
        if ws and ws.open:
            try:
                await ws.send(json.dumps({
                    "position": {"x": sx, "y": sy}
                }))
            except:
                pass

        # === Rendering ===
        screen.fill(WHITE)
        
        # Draw Table features (center line, center circle)
        pygame.draw.line(screen, LINE_COLOR, (0, HEIGHT//2), (WIDTH, HEIGHT//2), 4)
        pygame.draw.circle(screen, LINE_COLOR, (WIDTH//2, HEIGHT//2), 60, 4)
        
        # Draw Goals (-100 to 100 in server X)
        g_left, _ = to_screen(-100, 0)
        g_right, _ = to_screen(100, 0)
        pygame.draw.rect(screen, GREEN, (g_left, 0, g_right - g_left, 15)) # Opponent Goal
        pygame.draw.rect(screen, GREEN, (g_left, HEIGHT-15, g_right - g_left, 15)) # User Goal
        
        # Fetch up-to-date positions
        p1_pos = to_screen(game_state["player1"]["first"], game_state["player1"]["second"])
        p2_pos = to_screen(game_state["player2"]["first"], game_state["player2"]["second"])
        puck_pos = to_screen(game_state["puck"]["first"], game_state["puck"]["second"])
        
        # Draw Player 1 (User - Blue)
        pygame.draw.circle(screen, BLUE, p1_pos, PLAYER_RADIUS)
        pygame.draw.circle(screen, WHITE, p1_pos, PLAYER_RADIUS - 15, 3)
        
        # Draw Player 2 (Opponent - Red)
        pygame.draw.circle(screen, RED, p2_pos, PLAYER_RADIUS)
        pygame.draw.circle(screen, WHITE, p2_pos, PLAYER_RADIUS - 15, 3)
        
        # Draw Puck (Black)
        pygame.draw.circle(screen, BLACK, puck_pos, PUCK_RADIUS)
        pygame.draw.circle(screen, WHITE, puck_pos, PUCK_RADIUS - 8, 2)
        
        # Draw Score Overlay
        score_p1 = game_state['score']['first']
        score_p2 = game_state['score']['second']
        
        # Orient the score nicely: Opponent (top) - User (bottom)
        score_text = font.render(f"{score_p2}   -   {score_p1}", True, LINE_COLOR)
        screen.blit(score_text, (WIDTH//2 - score_text.get_width()//2, HEIGHT//2 - score_text.get_height()//2))
        
        if not ws or not ws.open:
            warn_text = small_font.render("Connecting/Offline", True, RED)
            screen.blit(warn_text, (5, 5))

        pygame.display.flip()
        
        # Allow asyncio to process incoming packets and wait for the next frame
        await asyncio.sleep(1 / FPS)

    if ws:
        await ws.close()
    pygame.quit()
    sys.exit()

if __name__ == '__main__':
    # Ensure Windows uses a compatible event loop if applicable
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
