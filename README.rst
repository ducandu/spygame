spygame - Quick Setup Instructions
==================================

.. figure:: https://raw.githubusercontent.com/sven1977/spygame/master/examples/platformer_2d/screen2.png
    :alt: The Lost Vikings - Sample spygame Level

    The Lost Vikings - Sample spygame Level - *All graphics are (c) Blizzard Entertainment Inc (The Lost Vikings)*


**IMPORTANT NOTE:** *All graphics used in this documentation and in the spygame.examples.vikings package of the spygame library were taken from the game
"The Lost Vikings" (c) 1992 by Blizzard Entertainment Inc. (formerly known as Silicon and Synapse). Please use these images (in your own projects and repos)
for demonstration purposes only and then also mention this copyright statement!*


Get the code
------------
- You may need a pygame version that matches your python version. E.g. for Windows 10 64bit + python3.6, you can download `pygame‑1.9.3‑cp36‑cp36m‑win_amd64.whl from here <http://www.lfd.uci.edu/~gohlke/pythonlibs/#pygame>`_ and then do a ``pip install [path to downloaded wheel]``
- Git the `spygame <http://github.com/sven1977/spygame>`_ code or do a ``pip install spygame``

Get started
-----------
- write a simple game against the engine:

.. code:: python

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
                "id": 1, "class": spyg.Level, "name": "MAZE", # <- this will read the data/maze.tmx file for the level's layout and setup data
            },

            # add more of your levels here
            # { ... },

        ], title="The Maze Runner - An A-maze-ing Game :)")

        # that's it, play one of the levels -> this will enter an endless game loop
        game.levels_by_name["MAZE"].play()


All you need in order to run this game is the above code in a directory, and the additional subdirectories data/ and images/, which can
be found `here <http://github.com/sven1977/spygame/tree/master/examples/maze_runner>`_. These directories contain the necessary SpriteSheets,
level background images and level setup (collision layers, background images, position and class of the player, etc..).

This should give you a level like this:

.. figure:: https://raw.githubusercontent.com/sven1977/spygame/master/examples/maze_runner/screen1.png
    :alt: The Maze Runner - An A-maze-ing Game :)

    The Maze Runner - An A-maze-ing Game :) - *All graphics are (c) Blizzard Entertainment Inc (The Lost Vikings)*

You can now control the Agent via the four arrow keys (up, down, left, right).

Next steps and Full Documentation
---------------------------------

If you would like to create more complex levels (or entire Games with many Screens and Levels), read the
`spygame documentation <https://ducandu.github.io/spygame/>`_, in which we'll create a full-blown 2D platformer Level
(sorry about spygame's documentation still being work in progress).


AI (Reinforcement Learning) with spygame
----------------------------------------

I'm currently working on making spygame available as an openAI-gym Environment type, so that reinforcement learning algorithms can run against any spygame
Level objects.


Contribute to spygame
---------------------
If you would like to contribute to the spygame library, the following items are currently open:

- add audio/sound support
- create more example games
- create more "Lost Vikings" levels
- create more physics components (apart from the existing top-down and platformer)
- create support for GUI elements (label, buttons, tick-boxes, etc..). This is an open Pygame problem and should probably be solved on the Pygame level.
- help out with integrating spygame into openAI-gym and openAI-rllab repos

.. figure:: https://raw.githubusercontent.com/sven1977/spygame/master/examples/platformer_2d/screen1.png
    :alt: Lost Vikings - Sample spygame Level

    Lost Vikings - Sample spygame Level - *All graphics are (c) Blizzard Entertainment Inc (The Lost Vikings)*


