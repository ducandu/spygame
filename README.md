# spygame
## 2D game engine based on Pygame and level-tmx files

### 1) Getting started
* Git the [spygame](www.github.com/sven1977/spygame) code
* write a simple game against the engine:

```python
import spygame as spyg


class MyAgent(spyg.Sprite):
    def __init__(self, x: int, y: int, spritesheet: spyg.SpriteSheet):
        """
        Args:
            x (int): the start x position
            y (int): the start y position
            spritesheet (spyg.Spritesheet): the SpriteSheet object (tsx file) to use for this Viking
        """
        super().__init__(x, y, spritesheet, {
            "default"          : "stand",  # the default animation to play
            "stand"            : {"frames": [0], "loop": False, "flags": spyg.Animation.ANIM_PROHIBITS_STAND},
            "run"              : {"frames": [5, 6, 7, 8, 9, 10, 11, 12], "rate": 1 / 8},
        })

        self.handles_own_collisions = True
        self.type = spyg.Sprite.get_type("friendly")

        # add components to this Agent
        # loop time line:
        # - pre-tick: Brain (needs animation comp to check e.g., which commands are disabled), Physics (movement + collision resolution)
        # - tick: chose animation to play
        # - post-tick: Animation
        self.register_event("pre_tick", "post_tick", "collision")
        self.cmp_brain = self.add_component(spyg.Brain("brain", ["up", "down", "left", "right"]))
        self.cmp_physics = self.add_component(spyg.TopDownPhysics("physics"))

        # subscribe/register to some events
        self.register_event("bump.bottom", "bump.top", "bump.left", "bump.right")

    # - mainly determines agent's animation that gets played
    def tick(self, game_loop):
        dt = game_loop.dt

        # tell our subscribers (e.g. Components) that we are ticking
        self.trigger_event("pre_tick", game_loop)

        # moving in x/y direction?
        if self.cmp_physics.vx != 0 or self.cmp_physics.vy != 0:
            self.check_running()
        # not moving in any direction
        else:
            # just stand
            if self.allow_play_stand():
                self.play_animation("stand")

        self.trigger_event("post_tick", game_loop)
```