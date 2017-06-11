"""
 -------------------------------------------------------------------------
 spygame - maze_runner.py
 
 all you need to run this example are the files in:
    data/
    images/
    from www.github.com/sven1977/spygame/tree/master/examples/maze_runner
  
 created: 2017/06/11 in PyCharm
 (c) 2017 Sven - ducandu GmbH
 -------------------------------------------------------------------------
"""

import spygame as spyg


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
