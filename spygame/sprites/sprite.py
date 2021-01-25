import pygame

from spygame.game_object import GameObject
from spygame.sprites.sprite_sheet import SpriteSheet


class Sprite(GameObject, pygame.sprite.Sprite):
    """
    A Sprite can be added to a Stage; has a type and a collision mask for collision detection with other Sprites or TiledTileLayers also on the Stage.
    Sprite objects inherit from pygame.sprite.Sprite, so a Sprite has an image and a position/collision rect via rect property (pygame.rect).
    Each Sprite can have either a static image or hold a SpriteSheet object from which it can pull images for animation purposes; either way, the `image`
    property holds the current image.
    The image rect (property `image_rect`) can be different from the collision rect (property `rect`); usually one would want the collision rect to be
    a little smaller than the actual image.
    """

    # dict of Sprite types (by name) to bitmappable-int (1, 2, 4, 8, 16, etc..)
    # - this can be used to determine which Sprites collide with which other Sprites
    types = {
        "none":             0x0,  # e.g. background Sprites (e.g. waterfalls)
        "dockable":         0x1,  # if other objects would like to dock to this Sprite
        "default":          0x2,  # e.g. collision layers (should normally also be dockable)
        "one_way_platform": 0x4,  # objects can only collide with this Sprite when coming from the top (also no x-collisions) (should normally also be dockable)
        "particle":         0x8,  # e.g. an arrow/shot/etc..
        "friendly":         0x10,
        "enemy":            0x20,
        "all":              0xffff,
    }
    next_type = 0x200

    @staticmethod
    def get_type(types_):
        """
        Returns the bitmap code for an already existing Sprite type or for a new type (the code will be created then).
        Types are usually used for collision masks.

        :param str types_: the type(s) (comma-separated), whose code(s) should be returned
        :return: the type as an int; if many types are given, returns a bitmask with all those bits set that represent the given types
        :rtype: int
        """
        ret = 0
        for type_ in types_.split(","):
            if type_ not in Sprite.types:
                Sprite.types[type_] = Sprite.next_type
                Sprite.next_type *= 2
            ret |= Sprite.types[type_]
        return ret

    def __init__(self, x, y, **kwargs):
        """
        :param int x: the initial x position of this Sprite
        :param int y: the initial y position of this Sprite
        :param any **kwargs:
         - sprite_sheet: a ready SpriteSheet object to use (set initial image to first frame in the SpriteSheet)
         - image_file: use image_file (str) as a file name for a static image
         - image_section (Tuple[int,int,int,int]): offset-x, offset-y, width, height defining a rect to use only a subsection of the given static image
         - width_height (Tuple[int,int]): the dimensions of the collision rect; if not given, we'll try to derive the collision rect from
           the given image/spritesheet
         - image_rect: a pygame.Rect defining the x/y offset and width/height of the Sprite's image with respect to the Sprite's rect (collision)
           e.g. if the image is 32x32 but the collision rect should only be 16x32 (slim), the width_height kwarg should be (16, 32) and the image_rect kwarg
           should be pygame.Rect(-8, 0, 32, 32)
        """
        pygame.sprite.Sprite.__init__(self)
        GameObject.__init__(self)

        # can be set to the number of ticks to ignore by the containing stage depending on whether this Sprite is within the Stage's viewable borders
        self.ignore_after_n_ticks = 1  # >0: not to be ignored; <=0: ignore this sprite for one tick

        # determine the image of this Sprite, its collision rect, and its image-offset-rect (where with respect to the collision rect do we draw the image?)
        # - with SpriteSheet
        if "sprite_sheet" in kwargs:
            sheet = kwargs["sprite_sheet"]
            assert isinstance(sheet, SpriteSheet), "ERROR: in Sprite's ctor: kwargs[`sprite_sheet`] must be of type `SpriteSheet`!"
            self.spritesheet = sheet
            # TODO: make it possible to create a Sprite from more than one tile (e.g. for a platform/elevator). Either in x-direction or y-direction or both
            self.image = sheet.tiles[kwargs.get("tile", 0)]
            width_height = kwargs.get("width_height", (self.spritesheet.tw, self.spritesheet.th))
            self.rect = pygame.Rect(x, y, width_height[0], width_height[1])  # collision rect
            self.image_rect = kwargs.get("image_rect", pygame.Rect(width_height[0] / 2 - self.spritesheet.tw / 2,
                                                                   width_height[1] / 2 - self.spritesheet.th / 2,
                                                                   self.spritesheet.tw, self.spritesheet.th))
            self.do_render = True
        # - an image file -> fixed image -> store as Surface in self.image
        elif "image_file" in kwargs:
            image = kwargs["image_file"]
            assert isinstance(image, str), "ERROR: in Sprite's ctor: kwargs[`image_file`] must be of type str!"
            self.spritesheet = None
            source = pygame.image.load(image)
            if "image_section" in kwargs:
                sec = kwargs["image_section"]
                assert isinstance(sec, tuple) and len(sec) == 4,\
                    "ERROR: in Sprite's ctor: kwargs[`image_section`] must be of type tuple and of len 4 (offset-x, offset-y, width, height)!"
                self.image = pygame.Surface((sec[2], sec[3]))
                self.image.blit(source, dest=(0, 0), area=pygame.Rect(*sec))
            else:
                self.image = source
            self.image_rect = self.image.get_rect()
            width_height = kwargs.get("width_height", (self.image_rect.width, self.image_rect.height))
            self.rect = pygame.Rect(x, y, width_height[0], width_height[1])  # collision
            # fix image x/y (would be 0,0 otherwise)
            self.image_rect = kwargs.get("image_rect", pygame.Rect(width_height[0] / 2 - self.image_rect.width / 2,
                                                                   width_height[1] / 2 - self.image_rect.height / 2,
                                                                   self.image_rect.width, self.image_rect.height))
            self.do_render = True
        # - empty image plus a collision rect of some size
        elif "width_height" in kwargs:
            width_height = kwargs["width_height"]
            assert isinstance(width_height, tuple) and len(width_height) == 2,\
                "ERROR: in Sprite's ctor: kwargs[`width_height`] must be of type tuple and of len 2!"
            self.spritesheet = None
            self.image = None
            self.rect = pygame.Rect(x, y, width_height[0], width_height[1])
            self.image_rect = pygame.Rect(0, 0, width_height[0], width_height[1])
            self.do_render = True if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_RECTS else False
        # - tiny-size rect (no image)
        else:
            self.spritesheet = None
            self.image = None
            self.rect = pygame.Rect(x, y, 1, 1)
            self.image_rect = pygame.Rect(0, 0, 1, 1)
            self.do_render = True if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_RECTS else False

        # GameObject specific stuff
        self.type = Sprite.get_type("default")  # specifies the type of the Sprite (can be used e.g. for collision detection)
        self.handles_own_collisions = False  # set to True if this object takes care of its own collision handling
        self.collision_mask = Sprite.get_type("default")  # set the bits here that we would like to collide with (all other types will be ignored)

        self.stage = None  # the current Stage this Sprite is in
        self.sprite_groups = []  # the current Groups that this Sprite belongs to
        self.do_render = kwargs.get("do_render", self.do_render)  # we may overwrite this
        self.render_order = kwargs.get("render_order", 50)  # the higher this number the later this Sprite will be rendered in the Stage's render function
        self.flip = {"x": False, "y": False}  # 'x': flip in x direction, 'y': flip in y direction, False: don't flip

        # our min/max positions (might be adjusted to more accurate values once placed onto a Stage)
        self.x_min = "auto"  # by default, make x-position be limited automatically by Stage/Level borders
        self.x_max = "auto"
        self.y_min = None  # by default, make y-positions not limited
        self.y_max = None

        self.on_event("added_to_stage", self, "added_to_stage", register=True)  # allow any Stage to trigger this event using this Sprite

    def added_to_stage(self, stage):
        """
        adjusts our max positions based on the stage's level's dimensions - only if it's a Level (not a simple Screen)

        :param Stage stage: the Stage we were added to
        """
        # TODO: make this independent on Level or simple Screen (even a Screen should have dimensions)
        if isinstance(stage.screen, Level):
            if self.x_min == "auto":
                self.x_min = 0
            if self.x_max == "auto":
                self.x_max = stage.screen.width - self.rect.width
            if self.y_min == "auto":
                self.y_min = 0
            if self.y_max == "auto":
                self.y_max = stage.screen.height - self.rect.height

    def move(self, x, y, absolute=False):
        """
        Moves us by x/y pixels (or to x,y if absolute=True).

        :param Union[int,None] x: the amount in pixels to move in x-direction
        :param Union[int,None] y: the amount in pixels to move in y-direction
        :param bool absolute: whether x and y are given as absolute coordinates (default: False): in this case x/y=None means do not move in this dimension
        """
        # absolute coordinates given
        if absolute:
            if x is not None:
                self.rect.x = x
            if y is not None:
                self.rect.y = y
        # do a minimum of 1 pix (if larger 0.0)
        else:
            if 0 < x < 1:
                x = 1
            self.rect.x += x
            if 0 < y < 1:
                y = 1
            self.rect.y += y

        # then we do the boundary checking
        if self.x_max is not None and self.rect.x > self.x_max:
            self.rect.x = self.x_max
        elif self.x_min is not None and self.rect.x < self.x_min:
            self.rect.x = self.x_min

        if self.y_max is not None and self.rect.y > self.y_max:
            self.rect.y = self.y_max
        elif self.y_min is not None and self.rect.y < self.y_min:
            self.rect.y = self.y_min

    # @override(GameObject)
    def destroy(self):
        super().destroy()

        # if we are on a stage -> remove us from that stage
        if self.stage:
            self.stage.remove_sprite(self)

        # remove us from all our pygame.sprite.Groups
        for sprite_group in self.sprite_groups:
            sprite_group.remove(self)

    def render(self, display):
        """
        Paints the Sprite with its current image onto the given Display object.

        :param Display display: the Display object to render on (Display has a pygame.Surface, on which we blit our image)
        """
        if self.image:
            #print("render at x={}".format(self.rect.x + self.image_rect.x - display.offsets[0]))
            display.surface.blit(self.image, (self.rect.x + self.image_rect.x - display.offsets[0], self.rect.y + self.image_rect.y - display.offsets[1]))
        if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_RECTS:
            pygame.draw.rect(display.surface, DEBUG_RENDER_SPRITES_RECTS_COLOR,
                             pygame.Rect((self.rect.x - display.offsets[0], self.rect.y - display.offsets[1]),
                                         (self.rect.w, self.rect.h)), 1)

