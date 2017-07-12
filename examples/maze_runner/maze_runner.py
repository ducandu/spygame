"""
 -------------------------------------------------------------------------
 spygame - maze_runner.py
 
 a simple maze-runner demo

 all you need to run this example are the files in:
    data/
    images/
    from www.github.com/sven1977/spygame/tree/master/examples/maze_runner

 created: 2017/06/11 in PyCharm
 (c) 2017 Sven - ducandu GmbH
 -------------------------------------------------------------------------
"""

import spygame as spyg


class MyAgent(spyg.Sprite):
    def __init__(self, x, y):
        super().__init__(x, y, sprite_sheet=spyg.SpriteSheet("data/erik.tsx"), tile=0)

        # some custom settings
        self.handles_own_collisions = True  # our agent handles its own collisions (instead of letting the Stage do it for us)
        # add a HumanPlayerBrain for keyboard input handling
        self.cmp_brain = self.add_component(spyg.SimpleHumanBrain("brain", ["up", "down", "left", "right"]))
        # add a physics component to physics handling (here we use: simple 2D top-down view and controls)
        self.cmp_physics = self.add_component(spyg.TopDownPhysics("physics"))

    # plain spyg.Sprite objects do not implement the `tick` function, so nothing ever happens with them
    # - we need to implement it here to make sure our components (brain and physics) are ticked as well
    def tick(self, game_loop):
        self.cmp_brain.tick(game_loop)
        self.cmp_physics.tick(game_loop)


if __name__ == "__main__":
    # create a spyg.Game object
    game = spyg.Game(screens_and_levels=[
        # the only level
        {
            "class": spyg.Level, "name": "MAZE", "id": 1, # <- this will read the data/maze.tmx file for the level's layout and setup data
        },

        # add more of your levels here
        # { ... },

    ], title="The Maze Runner - An A-maze-ing Game :)")

    # that's it, play one of the levels -> this will enter an endless game loop
    game.levels_by_name["MAZE"].play()
