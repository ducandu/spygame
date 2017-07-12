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

    ], title="Erik's Trip to Egypt")

    game.levels_by_name["TUTORIAL"].play()

