import spygame as spyg
import spygame.examples.vikings as vik

if __name__ == "__main__":
    # create a spyg.Game object
    game = spyg.Game(screens_and_levels=[
        # the only level
        {
            "class": vik.VikingLevel, "name": "TUTORIAL", "id": 1,
        },

        # add more of your levels here
        # { ... },

    ], width=200, height=200, title="Erik's Trip to Egypt")  # , debug_flags=spyg.DEBUG_DONT_RENDER_TILED_TILE_LAYERS| spyg.DEBUG_RENDER_COLLISION_TILES | spyg.DEBUG_RENDER_SPRITES_RECTS)

    game.levels_by_name["TUTORIAL"].play()

