"""
Header Animation Module
Handles Sky, Stars, and Rain animations using Flet Canvas.
"""

import flet as ft
import flet.canvas as cv
import random
import time
import threading
from datetime import datetime

# ==================== CONSTANTS ====================

# Animation configuration
ANIMATION_STAR_COUNT = 25
ANIMATION_RAINDROP_COUNT = 40
ANIMATION_RAIN_SPEED_MIN = 3
ANIMATION_RAIN_SPEED_MAX = 8
ANIMATION_RAIN_DURATION_MIN = 300
ANIMATION_RAIN_DURATION_MAX = 420
ANIMATION_RAIN_CHANCE = 0.50
ANIMATION_RAIN_CHECK_INTERVAL = 0.15

# Colors
SKY_COLORS = {
    'sunrise': ['#1976D2', '#0097A7'],
    'day': ['#1976D2', '#0097A7'],
    'sunset': ['#1565C0', '#7B1FA2'],
    'night': ['#0D47A1', '#303F9F'],
    'rain': ['#455A64', '#546E7A'],
}

def get_time_of_day():
    """Returns current time period: 'sunrise', 'day', 'sunset', 'night'"""
    hour = datetime.now().hour
    if 5 <= hour < 8:
        return 'sunrise'
    elif 8 <= hour < 17:
        return 'day'
    elif 17 <= hour < 20:
        return 'sunset'
    else:
        return 'night'

def get_sky_colors(period):
    """Returns gradient colors for header based on time of day"""
    return SKY_COLORS.get(period, SKY_COLORS['day'])

def get_rain_colors():
    """Returns gray colors for rainy sky"""
    return SKY_COLORS['rain']


# ==================== HEADER CONTROL ====================

class HeaderAnimation(ft.Stack):
    def __init__(self, width, height, on_gradient_change=None):
        """
        Args:
            width: Width of the header
            height: Height of the header
            on_gradient_change: Callback function(colors: list) to update parent gradient
        """
        super().__init__()
        self.width = width
        self.height = height
        
        self.header_width = width
        self.header_height = height
        self.on_gradient_change = on_gradient_change
        
        self.running = False
        
        # State
        self.current_period = get_time_of_day()
        self.is_raining = False
        self.rain_start_time = 0
        
        # Objects storage
        self.stars = []     
        self.raindrops = [] 
        
        # Canvas Shapes
        self.star_shapes = []
        self.rain_shapes = []

        self.canvas = cv.Canvas(
            width=self.header_width,
            height=self.header_height,
            shapes=[],
        )
        self.controls = [self.canvas]


    def did_mount(self):
        self.running = True
        self.init_objects()
        # Start animation thread
        threading.Thread(target=self._animation_loop, daemon=True).start()
        # Start logic checker (weather/time)
        threading.Thread(target=self._logic_loop, daemon=True).start()

    def will_unmount(self):
        self.running = False

    def init_objects(self):
        """Initialize stars and rain objects based on current state"""
        # Create Stars (logic)
        self.stars = []
        self.star_shapes = []
        for _ in range(ANIMATION_STAR_COUNT):
            x = random.randint(10, self.header_width - 10)
            y = random.randint(5, self.header_height - 20)
            size = random.uniform(1.0, 2.5)
            self.stars.append({'x': x, 'y': y, 'size': size, 'opacity': random.random()})
            
            # Create Canvas Shape for star
            shape = cv.Circle(
                x=x, y=y, radius=size,
                paint=ft.Paint(color=ft.colors.with_opacity(0, ft.colors.WHITE), style=ft.PaintingStyle.FILL)
            )
            self.star_shapes.append(shape)

        # Create Raindrops (logic)
        self.raindrops = []
        self.rain_shapes = []
        for _ in range(ANIMATION_RAINDROP_COUNT):
            x = random.randint(0, self.header_width)
            y = random.randint(-self.header_height, 0)
            speed = random.uniform(ANIMATION_RAIN_SPEED_MIN, ANIMATION_RAIN_SPEED_MAX)
            length = random.uniform(10, 20)
            self.raindrops.append({'x': x, 'y': y, 'speed': speed, 'length': length})
            
            # Create Canvas Shape for rain
            shape = cv.Line(
                x1=x, y1=y, x2=x, y2=y+length,
                paint=ft.Paint(color=ft.colors.with_opacity(0, ft.colors.CYAN_200), stroke_width=1.5)
            )
            self.rain_shapes.append(shape)

        # Initial populate canvas
        self.canvas.shapes = self.star_shapes + self.rain_shapes
        self.canvas.update()

    def _logic_loop(self):
        """Handles infrequent logic: time of day change, rain start/stop"""
        while self.running:
            time.sleep(5)  # Check every 5 seconds
            
            new_period = get_time_of_day()
            
            # 1. Check Rain Logic
            if self.is_raining:
                elapsed = time.time() - self.rain_start_time
                if elapsed > ANIMATION_RAIN_DURATION_MAX or \
                   (elapsed > ANIMATION_RAIN_DURATION_MIN and random.random() < 0.2):
                    # Stop rain
                    self.is_raining = False
                    self._trigger_gradient(get_sky_colors(new_period))
            else:
                # Try to start rain
                if random.random() < (ANIMATION_RAIN_CHANCE / 12): 
                    self.is_raining = True
                    self.rain_start_time = time.time()
                    self._trigger_gradient(get_rain_colors())

            # 2. Check Time of Day Logic (if not raining)
            if not self.is_raining and new_period != self.current_period:
                self.current_period = new_period
                self._trigger_gradient(get_sky_colors(new_period))

    def _trigger_gradient(self, colors):
        """Helper to call the parent callback safely"""
        if self.on_gradient_change:
            self.on_gradient_change(colors)

    def _animation_loop(self):
        """High frequency loop for movement (60 FPS target)"""
        while self.running:
            start_time = time.time()
            
            need_update = False
            
            # --- Animate Stars ---
            if self.current_period == 'night' and not self.is_raining:
                for i, star in enumerate(self.stars):
                    if random.random() < 0.02:
                        star['opacity'] = random.uniform(0.2, 1.0)
                        self.star_shapes[i].paint.color = ft.colors.with_opacity(star['opacity'], ft.colors.WHITE)
                        need_update = True
            else:
                if self.star_shapes and self.star_shapes[0].paint.color != ft.colors.TRANSPARENT:
                    for shape in self.star_shapes:
                        shape.paint.color = ft.colors.TRANSPARENT
                    need_update = True

            # --- Animate Rain ---
            if self.is_raining:
                for i, drop in enumerate(self.raindrops):
                    drop['y'] += drop['speed']
                    
                    if drop['y'] > self.header_height:
                        drop['y'] = random.randint(-50, -10)
                        drop['x'] = random.randint(0, self.header_width)
                    
                    shape = self.rain_shapes[i]
                    shape.x1 = drop['x']
                    shape.y1 = drop['y']
                    shape.x2 = drop['x']
                    shape.y2 = drop['y'] + drop['length']
                    
                    shape.paint.color = ft.colors.with_opacity(0.6, ft.colors.CYAN_200)
                need_update = True
            else:
                if self.rain_shapes and self.rain_shapes[0].paint.color != ft.colors.TRANSPARENT:
                    for shape in self.rain_shapes:
                        shape.paint.color = ft.colors.TRANSPARENT
                    need_update = True

            if need_update:
                try:
                    self.canvas.update()
                except Exception:
                    pass

            elapsed = time.time() - start_time
            sleep_time = max(0, 0.033 - elapsed)
            time.sleep(sleep_time)