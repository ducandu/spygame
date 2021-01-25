import os
import pygame
import xml


class SpriteSheet(object):
    """
    Represents a spritesheet loaded from a tsx file.
    Stores each single image (as pygame.Surface) in the sheet by its position.
    Allows for already doing flip transformations (x/y and/or both axes) so we save time during the game.
    Stores single tile properties in tile_props_by_id dict (only for those tiles that actually have custom properties defined in the tsx file).
    """

    def __init__(self, file, store_flips=None):
        """
        :param str file: the tsx file name to be loaded into this object
        :param dict store_flips: dictionary ({"x": [True|False], "y": [True|False]}) with the flip-options; None for default (only x)
        """
        try:
            tree = xml.etree.ElementTree.parse(file)
        except:
            raise Exception("ERROR: could not open tsx(xml) file: {}".format(file))

        elem = tree.getroot()
        props = elem.attrib
        self.name = props["name"]
        self.tw = int(props["tilewidth"])
        self.th = int(props["tileheight"])
        assert "tilecount" in props, "ERROR: no `tilecount` property in properties of tsx file: `{}`!".format(file)
        self.count = int(props["tilecount"])
        self.cols = int(props["columns"])
        self.tiles = []  # the list of all Surfaces
        self.tiles_flipped_x = []  # the list of all Surfaces (flipped on x-axis)
        self.tiles_flipped_y = []  # the list of all Surfaces (flipped on y-axis)
        self.tiles_flipped_xy = []  # the list of all Surfaces (flipped on both axes)

        self.tile_props_by_id = {}  # contains tile properties set in the tmx file for each tile by tile ID

        # by default, only flip on x-axis (usually that's enough for 2D games)
        if not store_flips:
            store_flips = {"x": True, "y": False}

        for child in elem:
            # the image asset -> load and save all Surfaces
            if child.tag == "image":
                props = child.attrib
                self.w = int(props["width"])
                self.h = int(props["height"])
                image_file = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(file)), os.path.relpath(props["source"])))
                # image_file = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(file)), os.path.relpath("../images/debug.png")))
                image = pygame.image.load(image_file).convert_alpha()
                col = -1
                row = 0
                for tile in range(self.count):
                    col += 1
                    if col >= self.cols:
                        col = 0
                        row += 1
                    surf = pygame.Surface((self.tw, self.th), flags=pygame.SRCALPHA)
                    surf.blit(image, (0, 0),
                              area=pygame.Rect(col * self.tw, row * self.th, self.tw, self.th))  # blits the correct frame of the image to this new surface
                    self.tiles.append(surf)
                    # do the necessary flippings (will save time later when rendering the Sprite)
                    if store_flips["x"]:
                        surf_x_flipped = pygame.transform.flip(surf, True, False)
                        self.tiles_flipped_x.append(surf_x_flipped)
                        if store_flips["y"]:  # x and y
                            self.tiles_flipped_xy.append(pygame.transform.flip(surf_x_flipped, False, True))
                    if store_flips["y"]:
                        self.tiles_flipped_y.append(pygame.transform.flip(surf, False, True))

            # single tiles (and their properties)
            elif child.tag == "tile":
                id_ = int(child.attrib["id"])
                self.tile_props_by_id[id_] = {}  # create new dict for this tile
                for tag in child:
                    # the expected properties tag
                    if tag.tag == "properties":
                        for prop in tag:
                            val = prop.attrib["value"]
                            type_ = prop.attrib["type"] if "type" in prop.attrib else None
                            if type_:
                                if type_ == "bool":
                                    val = True if val == "true" else False
                                else:
                                    val = int(val) if type_ == "int" else float(val) if type_ == "float" else val
                            self.tile_props_by_id[id_][prop.attrib["name"]] = val
                    else:
                        raise ("ERROR: expected only <properties> tag within <tile> in tsx file {}".format(file))


