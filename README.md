# spygame
## 2D game engine based on Pygame and level-tmx files

### Get the code
* Git the [spygame](www.github.com/sven1977/spygame) code or do a `pip install spygame`

### Get started
* write a simple game against the engine:

```python
import spygame as spyg


class MyAgent(spyg.Sprite):
    def __init__(self, x, y, spritesheet):
        super().__init__(x, y, spritesheet)

        # some custom settings
        self.handles_own_collisions = True  # our agent handles its own collisions (instead of letting the Stage do it for us)
        # add a Brain for keyboard input handling
        self.cmp_brain = self.add_component(spyg.Brain("brain", ["up", "down", "left", "right"]))
        # add a physics component to physics handling (here we use: simple 2D top-down view and controls)
        self.cmp_physics = self.add_component(spyg.TopDownPhysics("physics"))

    # plain spyg.Sprite objects do not implement the `tick` function, so nothing ever happens with them
    # - we need to implement it here to add the pre-tick event (this will trigger the brain and physics components to act)
    def tick(self, game_loop):
        # tell our subscribers (e.g. Components) that we are ticking
        self.trigger_event("pre_tick", game_loop)


# create a spyg.Game object
game = spyg.Game(screens_and_levels=[
    # the only level
    {
        "class": spyg.Level, "name": "MAZE", "id": 1,
    },

    # add more of your levels here
    # { ... },

], title="The Maze Runner - An A-maze-ing Game :)")

# that's it, play one of the levels -> this will enter an endless game loop
game.levels_by_name["MAZE"].play()
```

All you need in order to run this game is the above code in a directory, and the additional subdirectories data/ and images/, which can
be found [here](www.github.com/sven1977/spygame/tree/master/examples/maze_runner). These directories contain the necessary SpriteSheets,
level background images and level setup (collision layers, background images, position and class of the player, etc..).

This should give you a level like:
![Vikings Sample](https://raw.githubusercontent.com/sven1977/spygame/master/examples/maze_runner/screen1.png)
in which you can control the Agent via the four arrow keys (up, down, left, right).

If you would like to create more complex levels (or entire Games with many Screens and Levels), read the spygame documentation, in which we'll
create a full-blown 2D platformer Level.

