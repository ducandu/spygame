"""
 -------------------------------------------------------------------------
 spygame - platformer_2d.py

 a 2D platformer demo (all graphics are (c) Blizzard Entertainment Inc)

 all you need to run this example are the files in:
    data/
    images/
    from www.github.com/sven1977/spygame/tree/master/examples/platformer_2d

 created: 2017/06/12 in PyCharm
 (c) 2017 Sven Mika - ducandu GmbH
 -------------------------------------------------------------------------
"""

import spygame as spyg
import spygame.examples.vikings as vik


# main program
if __name__ == "__main__":

    level = "LLM0"  # make this match your tmx file (tmx-file's name in all upper case and without the .tmx extension)

    # create a spyg.Game object
    game = spyg.Game(screens_and_levels=[
        # a level definition
        {
            "class": vik.VikingLevel, "name": level, "id": 1,
        },

        # add more of your levels here
        # { ... },

        ], width=1200, height=380,
        # debug_flags=(spyg.DEBUG_DONT_RENDER_TILED_TILE_LAYERS | spyg.DEBUG_RENDER_COLLISION_TILES | spyg.DEBUG_RENDER_SPRITES_RECTS | spyg.DEBUG_RENDER_ACTIVE_COLLISION_TILES))
        title="The Lost Vikings - Return of the Heroes :)")  #, debug_flags=(spyg.DEBUG_DONT_RENDER_TILED_TILE_LAYERS | spyg.DEBUG_RENDER_COLLISION_TILES))

    # that's it, play one of the levels -> this will enter an endless game loop
    game.levels_by_name[level].play()
