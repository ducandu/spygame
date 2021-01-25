import math

from spygame import DEBUG_FLAGS, DEBUG_DONT_RENDER_TILED_TILE_LAYERS
from spygame.sprites.sprite import Sprite

class Repeater(Sprite):
    """
    A background 2D image that scrolls slower than the Viewport (to create a pseudo 3D effect).
    """
    def __init__(self, x, y, image_file, **kwargs):
        ro = kwargs.pop("render_order", 0)  # by default, make this Sprite render first
        super().__init__(x, y, image_file=image_file, render_order=ro, **kwargs)
        self.vx = kwargs.get("vx", 1)
        self.vy = kwargs.get("vy", 1)
        self.repeat_x = kwargs.get("repeat_x", True)
        self.repeat_y = kwargs.get("repeat_y", True)
        self.repeat_w = kwargs.get("repeat_w", self.rect.width)
        self.repeat_h = kwargs.get("repeat_h", self.rect.height)
        # don't collide with anything
        self.type = Sprite.get_type("none")
        self.collision_mask = 0

    # @override(Sprite)
    def render(self, display):
        # debug rendering (no backgrounds) -> early out
        if DEBUG_FLAGS & DEBUG_DONT_RENDER_TILED_TILE_LAYERS:
            return

        self.ignore_after_n_ticks = 100  # replenish counter so that the repeater never goes out of the Viewport's scope

        view_x = display.offsets[0]
        view_y = display.offsets[1]
        offset_x = self.rect.x + view_x * self.vx
        offset_y = self.rect.y + view_y * self.vy

        if self.repeat_x:
            start_x = math.floor(-offset_x % self.repeat_w)
            if start_x > 0:
                start_x -= self.repeat_w
        else:
            start_x = self.rect.x - view_x

        if self.repeat_y:
            start_y = math.floor(-offset_y % self.repeat_h)
            if start_y > 0:
                start_y -= self.repeat_h
        else:
            start_y = self.rect.y - view_y

        scale = 1.0
        cur_y = start_y
        while cur_y < display.height / scale:
            cur_x = start_x
            while cur_x < display.width / scale:
                #display.surface.blit(self.image, dest=(math.floor(cur_x + view_x), math.floor(cur_y + view_y)))
                display.surface.blit(self.image, dest=(math.floor(cur_x), math.floor(cur_y)))
                cur_x += self.repeat_w
                if not self.repeat_x:
                    break

            cur_y += self.repeat_h
            if not self.repeat_y:
                break
