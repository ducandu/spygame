from spygame.sprites.sprite import Sprite
from spygame.physics.platform_physics import PlatformPhysics

class MovableRock(Sprite):
    def __init__(self, x, y, **kwargs):
        if not kwargs.get("image_file"):
            kwargs["image_file"] = "images/movable_rock.png"
        super().__init__(x, y, **kwargs)

        self.type = Sprite.get_type("default,dockable")
        self.collision_mask = Sprite.get_type("default,friendly,enemy,particle")

        # add Physics (and thus Dockable) components to this Rock
        # - pre-tick: Physics (movement + collision resolution)
        #self.register_event("collision")

        phys = PlatformerPhysics("physics")
        phys.is_pushable = True  # rock can be pushed by an agent
        phys.vx_max = 10  # max move speed (when pushed): this should be very slow
        phys.is_heavy = True  # rock makes Stage's viewport rock if it hits ground AND squeezes agents :(
        self.cmp_physics = self.add_component(phys)

        # subscribe/register to some events
        self.on_event("bump.bottom", self, "land", register=True)
        self.register_event("bump.top", "bump.left", "bump.right", "hit.liquid")

    def tick(self, game_loop):
        # let our physics component handle all movements
        self.cmp_physics.tick(game_loop)

    def land(self, *args):
        self.stage.shake_viewport(1, 10)

