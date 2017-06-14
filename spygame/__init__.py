"""
 -------------------------------------------------------------------------
 spygame (pygame based 2D game engine for the openAI gym)

 created: 2017/04/04 in PyCharm
 (c) 2017 Sven Mika - ducandu GmbH
 -------------------------------------------------------------------------
"""

from abc import ABCMeta, abstractmethod
import xml.etree.ElementTree
import pygame
import os.path
from itertools import chain
from typing import List, Union, Tuple
import types
import pytmx
import sys
import math
import re


# some debug flags that we can set to switch on debug rendering, collision handling, etc..
DEBUG_NONE = 0x0  # no debugging
DEBUG_ALL = 0xffff  # full debugging
# will not render TiledTileLayers that are marked as 'do_render'==true in the tmx files
DEBUG_DONT_RENDER_TILED_TILE_LAYERS = 0x1
# will render all collision tiles (those layers that have a type) with a square frame and - when being considered - filled green
DEBUG_RENDER_COLLISION_TILES = 0x2
DEBUG_RENDER_COLLISION_TILES_COLOR_DEFAULT = pygame.Color("red")
DEBUG_RENDER_COLLISION_TILES_COLOR_OTHER = pygame.Color("cyan")
# render the tiles currently under consideration for colliding with a sprite
DEBUG_RENDER_ACTIVE_COLLISION_TILES = 0x4
DEBUG_RENDER_ACTIVE_COLLISION_TILES_COLOR = pygame.Color("green")
# will render all Sprites (even those without an image (e.g. when blinking) with a rectangular frame representing the Sprite's .rect property
DEBUG_RENDER_SPRITES_RECTS = 0x8
DEBUG_RENDER_SPRITES_RECTS_COLOR = pygame.Color("orange")
# will render every Sprite before the Sprite's tick method was called
DEBUG_RENDER_SPRITES_BEFORE_EACH_TICK = 0x10
DEBUG_RENDER_SPRITES_AFTER_EACH_TICK = 0x20
# will render every Sprite before the Sprite's collision detection algo runs
DEBUG_RENDER_SPRITES_BEFORE_COLLISION_DETECTION = 0x40

# by default, no debugging (you can set this through a Game's c'tor using the debug_flags kwarg)
DEBUG_FLAGS = DEBUG_NONE


class EventObject(object):
    """
    Corresponds to evented class in Quintus/html5
    - NOTE: these are not pygame events!
    """

    def __init__(self):
        # - listeners keeps a list of callbacks indexed by event name for quick lookup
        # - a listener is an array of 2 elements: 0=target, 1=callback
        self.listeners = {}  # keys=event names
        # stores all valid event names; that way, we can check validity of event when subscribers subscribe to some event
        self.valid_events = set()

    def register_event(self, *events: str):
        for event in events:
            self.valid_events.add(event)

    def unregister_event(self, event: str):
        self.valid_events.remove(event)

    def unregister_events(self):
        self.valid_events.clear()

    def check_event(self, event: str):
        # make sure the event is valid (registered)
        assert event in self.valid_events, "ERROR: event {} not valid in this EventObject ({}), has not been registered!".format(event, type(self).__name__)

    def on_event(self, event: Union[str, List[str]], target=None, callback=None, register=False):
        """
        Binds a callback to an event on this object. If you provide a
        `target` object, that object will add this event to it's list of
        binds, allowing it to automatically remove it when it is destroyed.

        Args:
            event (str): The event name (e.g. tick, got_hit, etc..)
            target (object): The target object on which to call the callback (defaults to self if not given)
            callback (callable): The (bound!) method to call on target
            register (bool): whether we should register this event at the same time

        Returns:

        """

        if register:
            self.register_event(event)
        else:
            self.check_event(event)  # checks whether it's already registered

        # more than one event given
        if isinstance(event, list):
            for i in range(len(event)):
                self.on_event(event[i], target, callback)
            return

        # handle the case where there is no target provided, swapping the target and callback parameters
        if not callback:
            callback = target
            target = None

        # if there's still no callback, default to the event name
        if not callback:
            callback = event

        # handle case for callback that is a string, this will pull the callback from the target object or from this object
        if isinstance(callback, str):
            callback = getattr(target or self, callback)

        # listener is an array of 2 elements: 0=target, 1=callback
        if event not in self.listeners:
            self.listeners[event] = []
        self.listeners[event].append([target or self, callback])

        # with a provided target, the events bound to the target, so we can erase these events if the target no longer exists
        if target:
            if not hasattr(target, "binds"):
                target.event_binds = []
            target.event_binds.append([self, event, callback])

    # TODO: good debugging: warn if a registered event doesn't get triggered for a long time?
    def trigger_event(self, event, *params):
        """
        triggers an event, passing in some optional additional data about the event
        Args:
            event (str): the event's name
            params (*): the params to be passed to the handler methods as *args

        Returns:

        """
        self.check_event(event)

        # make sure there are any listeners for this specific event, if not, early out
        if event in self.listeners:
            # call each listener in the context of either the target passed into `on_event` ([0]) or the object itself
            for listener in self.listeners[event]:
                listener[1](*params)

    def off_event(self, event, target=None, callback=None, unregister=False):
        """
        unbinds an event
        - can be called with 1, 2, or 3 parameters, each of which unbinds a more specific listener

        Args:
            event ():
            target ():
            callback ():
            unregister (bool): whether we should unregister this event as well

        Returns:

        """
        if unregister:
            self.unregister_event(event)
        else:
            self.check_event(event)

        # without a target, remove all the listeners
        if not target:
            if hasattr(self, "listeners") and event in self.listeners:
                del self.listeners[event]
        else:
            # if the callback is a string, find a method of the same name on the target
            if isinstance(callback, str) and hasattr(target, callback):
                callback = getattr(target, callback)
            if hasattr(self, "listeners") and event in self.listeners:
                l = self.listeners[event]
                # loop from the end to the beginning, which allows us to remove elements without having to affect the loop
                for i in range(len(l) - 1, -1, -1):
                    if l[i][0] is target:
                        if not callback or callback is l[i][1]:
                            l.pop(i)

    def debind_events(self):
        """
        called to remove any listeners from this object
        - e.g. when this object is destroyed you'll want all the event listeners to be removed from this object

        Returns:

        """
        if hasattr(self, "event_binds"):
            for source, event, _ in self.event_binds:
                source.off_event(event, self)


# can handle events as well as
class State(EventObject):
    def __init__(self):
        super().__init__()
        self.dict = {}

    # sets a value in our dict and triggers a changed event
    def set(self, key, value, trigger_event=False):
        # trigger an event that the value changed
        if trigger_event:
            old = self.dict[key] if key in self.dict else None
            self.trigger_event("changed." + key, value, old)
        # set to new value
        self.dict[key] = value

    # retrieve a value from the dict
    def get(self, key):
        if key not in self.dict:
            raise (Exception, "ERROR: key {} not in dict!".format(key))
        return self.dict[key]

    # decrease value by amount
    def dec(self, key, amount: int = 1):
        self.dict[key] -= amount

    # increase value by amount
    def inc(self, key, amount: int = 1):
        self.dict[key] += amount


class KeyboardInputs(EventObject):
    def __init__(self, key_list=None):
        super().__init__()

        # stores the keys that we would like to be registered as important
        # - key: pygame keyboard code (e.g. pygame.K_ESCAPE, pygame.K_UP, etc..)
        # - value: True if currently pressed, False otherwise
        # - needs to be ticked in order to yield up-to-date information (this will be done by a GameLoop playing a Screen)
        self.keyboard_registry = {}
        self.descriptions = {}
        self.desc_to_key = {}  # for reverse mapping from description (e.g. 'up') to int (e.g. pygame.K_UP)

        if key_list is None:
            key_list = ["up", "down", "left", "right"]
        self.update_keys(key_list)

    def update_keys(self, new_key_list: Union[List, None] = None):
        """
        populates our registry and other dicts with the new key-list given (may be an empty list)

        :param list new_key_list: the new key list, where each item is the lower-case pygame keycode without the leading "K_" e.g. "up" for pygame.K_UP
                                  - use None for clearing out the registry (no keys assigned)
        """
        self.unregister_events()
        self.keyboard_registry.clear()
        self.descriptions.clear()
        self.desc_to_key.clear()
        if new_key_list:
            for desc in new_key_list:
                key = getattr(pygame, "K_" + desc.upper())
                self.keyboard_registry[key] = False
                self.descriptions[key] = desc
                self.desc_to_key[desc] = key
                # signal that we might trigger the following events:
                self.register_event("key_down." + desc, "key_up." + desc)

    def tick(self):
        """
        pulls all keyboard events from the event queue and processes them according to our keyboard_registry/descriptions
        - triggers events for all registered keys like: 'key_down.[desc]' (when  pressed) and 'key_up.[desc]' (when released),
          where desc is the lowercase string after 'pygame.K_'... (e.g. 'down', 'up', etc..)
        """
        events = pygame.event.get([pygame.KEYDOWN, pygame.KEYUP])
        for e in events:
            # a key was pressed that we are interested in -> set to True or False
            if e.key in self.keyboard_registry:
                if e.type == pygame.KEYDOWN:
                    self.keyboard_registry[e.key] = True
                    self.trigger_event("key_down." + self.descriptions[e.key])
                else:
                    self.keyboard_registry[e.key] = False
                    self.trigger_event("key_up." + self.descriptions[e.key])


class GameObject(EventObject):
    """
    Inherits from Sprite, but also adds capability to add Components
    """

    # stores all GameObjects by a unique int ID
    id_to_obj = {}
    next_id = 0

    def __init__(self):
        super().__init__()

        self.components = {}  # dict of added components by component's name
        self.is_destroyed = False

        self.id = GameObject.next_id
        GameObject.id_to_obj[self.id] = self
        GameObject.next_id += 1

    def add_component(self, component):
        """
        Adds a component object to this game Entity -> calls the component's added method
        Args:
            component (Component): component to be added to GameObject under game_obj.components[component.name]

        Returns:
            component (Component): for chaining
        """

        component.game_object = self
        assert component.name not in self.components, "ERROR: component with name {} already exists in Entity!".format(component.name)
        self.components[component.name] = component
        component.added()
        return component

    def remove_component(self, component):
        assert component.name in self.components, "ERROR: component with name {} does no exist in Entity!".format(component.name)
        # call the removed handler (if implemented)
        component.removed()
        # only then erase the component from the GameObject
        del self.components[component.name]

    def destroy(self):
        """
        Destroys the object by calling debind and removing the object from it's parent
        - will trigger a destroyed event callback
        Returns:

        """
        # we are already dead -> return
        if self.is_destroyed:
            return

        # debind events where we are the target
        self.debind_events()

        self.is_destroyed = True

        # tell everyone we are done
        self.trigger_event("destroyed")

        # remove ourselves from the id_to_obj dict
        del GameObject.id_to_obj[self.id]

    # a tick (coming from the containing Stage); may do something or not
    def tick(self, game_loop):
        pass


class SpriteSheet(object):
    """
    loads a spritesheet from a tsx file and assigns frames to each sprite (Surface) in the sheet
    """

    def __init__(self, file, store_flips: Union[dict, None] = None):
        try:
            tree = xml.etree.ElementTree.parse(file)
        except:
            raise ("ERROR: could not open xml file: {}".format(file))

        elem = tree.getroot()
        props = elem.attrib
        self.name = props["name"]
        self.tw = int(props["tilewidth"])
        self.th = int(props["tileheight"])
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


class Sprite(GameObject, pygame.sprite.Sprite):
    """
    adds a SpriteSheet to the object and inherits from pygame.sprite.Sprite, so a Sprite has an image and a position via rect
    """

    # dict of Sprite types (by name) to bitmappable-int (1, 2, 4, 8, 16, etc..)
    # - this can be used to determine which Sprites collide with which other Sprites
    types = {
        "none"          : 0x0,
        "default"       : 0x1,
        "default_ground": 0x2,
        "default_wall"  : 0x4,
        "particle"      : 0x8,
        "friendly"      : 0x10,
        "enemy"         : 0x20,
        "character"     : 0x40,
        "ui"            : 0x80,
        "all"           : 0x100,
    }
    next_type = 0x200

    @staticmethod
    def get_type(type) -> int:
        """
        returns the bitmap code for an already existing Sprite type or for a new type (the code will be created then)
        - types are usually used for collision masks
        Args:
            type (str): the type, whose code should be returned

        Returns: int

        """
        if type not in Sprite.types:
            Sprite.types[type] = Sprite.next_type
            Sprite.next_type *= 2
        return Sprite.types[type]

    # TODO: make Sprite accept an image file as well (png will be loaded and simply set as image)
    def __init__(self, x: int, y: int, sheet_or_wh_or_file: Union[SpriteSheet, str, Tuple[int], None] = None):
        pygame.sprite.Sprite.__init__(self)
        GameObject.__init__(self)

        # all sprites need to have a position
        # - but support Sprites without SpriteSheets:
        # -- some Rect without image
        if isinstance(sheet_or_wh_or_file, tuple):
            self.spritesheet = None
            self.image = None  # pygame.Surface((sheet_or_wh_or_file[0], sheet_or_wh_or_file[1]))
            # self.image.fill(pygame.Color(0, 0, 0, 255))  # all transparent image
            self.rect = pygame.Rect(x, y, sheet_or_wh_or_file[0], sheet_or_wh_or_file[1])
        # -- with SpriteSheet
        elif isinstance(sheet_or_wh_or_file, SpriteSheet):
            self.spritesheet = sheet_or_wh_or_file
            self.image = sheet_or_wh_or_file.tiles[0]
            self.rect = pygame.Rect(x, y, self.spritesheet.tw, self.spritesheet.th)
        # an image file -> fixed image -> store as Surface in self.image
        elif isinstance(sheet_or_wh_or_file, str):
            self.spritesheet = None
            self.image = pygame.image.load(sheet_or_wh_or_file)
            self.rect = self.image.get_rect()
        # -- tiny-size rect (no image)
        else:
            self.spritesheet = None
            self.image = None  # pygame.Surface((0, 0))
            self.rect = pygame.Rect(x, y, 1, 1)

        # GameObject specific stuff
        self.type = Sprite.get_type("default")  # specifies the type of the GameObject (can be used e.g. for collision detection)
        self.handles_own_collisions = False  # set to True if this object takes care of its own collision handling
        self.collision_mask = Sprite.get_type("default")  # set the bits here that we would like to collide with (all other types will be ignored)

        self.stage = None  # the current Stage this Sprite is in
        self.sprite_groups = []  # the current Groups that this Sprite belongs to
        self.flip = {"x": False, "y": False}  # 'x': flip in x direction, 'y': flip in y direction, False: don't flip

        self.register_event("added_to_stage")  # allow any Stage to trigger this event using this Sprite

    def move(self, x, y, precheck=False):
        """
        moves us by x/y pixels
        OBSOLETE: - if precheck is set to True: pre-checks the planned move via call to stage.locate and only moves entity as far as possible

        :param int x: the amount in pixels to move in x-direction
        :param int y: the amount in pixels to move in y-direction
        :param bool precheck: ???
        """

        #if precheck:
        #    testcol = self.stage.locate(p.x+x, p.y+y, Q._SPRITE_DEFAULT, p.w, p.h);
        #    if ((!testcol) || (testcol.tileprops && testcol.tileprops['liquid'])) {
        #        return True
        #
        #    return False

        self.rect.x += x
        self.rect.y += y

        # TODO: move the obj_to_follow into collide of stage (stage knows its borders best, then we don't need to define xmax/xmin, etc.. anymore)
        # TODO: maybe we could even build a default collision-frame around every stage when inserting the collision layer
        """
        if sprite.rect.x < self.x_min:
            sprite.rect.x = self.x_min
            self.vx = 0
        elif sprite.rect.x > self.x_max:
            sprite.rect.x = self.x_max
            self.vx = 0
        if sprite.rect.y < self.y_min:
            sprite.rect.y = self.y_min
            self.vy = 0
        elif sprite.rect.y > self.y_max:
            sprite.rect.y = self.y_max
            self.vy = 0
        """

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
        if self.image:
            display.surface.blit(self.image, (self.rect.x + display.offsets[0], self.rect.y + display.offsets[1]))
        if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_RECTS:
            pygame.draw.rect(display.surface, DEBUG_RENDER_SPRITES_RECTS_COLOR, pygame.Rect((self.rect.x, self.rect.y), (self.rect.w, self.rect.h)), 1)


class Repeater(Sprite):
    """
    a background 2D repeater that scrolls slower than the viewport
    """
    def __init__(self, x, y, image_file, **kwargs):
        super().__init__(x, y, image_file)
        self.vx = 1
        self.vy = 1
        self.repeat_x = kwargs.get("repeat_x", True)
        self.repeat_y = kwargs.get("repeat_y", True)
        self.repeat_w = kwargs.get("repeat_w", self.rect.width)
        self.repeat_h = kwargs.get("repeat_h", self.rect.height)
        self.type = 0  # ??

    def render(self, display):
        view_x = display.offsets[0]
        view_y = display.offsets[1]
        offset_x = self.rect.centerx + view_x * self.vx
        offset_y = self.rect.centery + view_y * self.vy
        cur_x = 0
        cur_y = 0
        start_x = 0

        if self.repeat_x:
            cur_x = math.floor(-offset_x % self.repeat_w)
            if cur_x > 0:
                cur_x -= self.repeat_w
        else:
            cur_x = self.rect.centerx - view_x
        if self.repeat_y:
            cur_y = math.floor(-offset_y % self.repeat_h)
            if cur_y > 0:
                cur_y -= self.repeat_h
        else:
            cur_y = self.rect.centery - view_y

        start_x = cur_x
        scale = 1.0
        while cur_y < self.stage.screen.height / scale:
            cur_x = start_x
            while cur_x < self.stage.screen.width / scale:
                display.surface.blit(self.image, dest=(math.floor(cur_x + view_x), math.floor(cur_y + view_y)))
                cur_x += self.repeat_w
                if not self.repeat_x:
                    break

            cur_y += self.repeat_h
            if not self.repeat_y:
                break


class AnimatedSprite(Sprite):
    """
    adds an Animation component to each instance

    :param int x: the initial x position of the Sprite
    :param int y: the initial y position of the Sprite
    :param SpriteSheet spritesheet: the SpriteSheet object to use for this Sprite
    :param dict animation_setup: the dictionary with the animation setup data to be sent to Animation.register_settings (the name of the registry record will
            be spritesheet.name)
    """

    def __init__(self, x: int, y: int, spritesheet, animation_setup: dict):
        super().__init__(x, y, spritesheet)  # assign the image/rect for the Sprite
        self.register_event("post_tick")
        self.cmp_animation = self.add_component(Animation("animation"))

        Animation.register_settings(spritesheet.name, animation_setup, register_events_on=self)
        # play the default animation
        self.play_animation(animation_setup["default"])


class Display(object):
    instantiated = False

    """
    a simple wrapper class for a pygame.display/pygame.Surface object representing the pygame display
    - also stores offset information
    """

    def __init__(self, width: int = 600, height: int = 400, title="Spygame Rocks!"):
        assert not Display.instantiated, "ERROR: can only create one {} object!".format(type(self).__name__)
        Display.instantiated = True

        pygame.display.set_caption(title)
        self.surface = pygame.display.set_mode((width, height))
        self.offsets = [0, 0]

    def change_offsets(self, x, y):
        self.offsets[0] = x
        self.offsets[1] = y

    def change_dims(self, width, height):
        pygame.display.set_mode((width, height))
        assert self.surface is pygame.display.get_surface(), "ERROR: self.display is not same object as pygame.display.get_surface() anymore!"

    def debug_refresh(self):
        """
        force-refreshes the display (only for debug purposes)
        Returns:

        """
        pygame.display.flip()
        pygame.event.get([])  # we seem to have to do this


class GameLoop(object):
    """
    Class that represents the GameLoop
    - has play and pause functions: play stats the tick/callback loop
    - has clock for ticking (keeps track of self.dt each tick), handles max-fps rate
    - handles keyboard input registrations via its KeyboardInputs object
    - needs a callback to know what to do each tick. Does the keyboard_inputs.tick, then calls callback with self as only argument
    """

    # static loop object (the currently active GameLoop gets stored here)
    active_loop = None

    @staticmethod
    def play_a_loop(**kwargs):
        """
        factory: plays a given GameLoop object or creates a new one using the given **kwargs options

        :param any kwargs:
                force_loop (bool): whether to play regardless of whether we still have some active loop running
                callback (callable): the GameLoop's callback loop function
                keyboard_inputs (KeyboardInputs): the GameLoop's KeyboardInputs object
                display (Display): the Display object to render everything on
                max_fps (int): the max frames per second to loop through
                screen_obj (Screen): alternatively, a Screen can be given, from which we will extract `display`, `max_fps` and `keyboard_inputs`
                game_loop (Union[str,GameLoop]): the GameLoop to use (instead of creating a new one); "new" or [empty] for new one
                dont_play (bool): whether - after creating the GameLoop - it should be `play`ed. Can be used for openAI gym purposes, where we just `step`,
                                  not `tick`
        :return: the created/played GameLoop object or None
        :rtype: Union[GameLoop, None]
        """

        defaults(kwargs, {"force_loop": False, "screen_obj": None, "keyboard_inputs": None, "display": None, "max_fps": None,
                          "game_loop" : "new", "dont_play": False})

        # - if there's no other loop active, run the default stageGameLoop
        # - or: there is an active loop, but we force overwrite it
        if GameLoop.active_loop is None or ("force_loop" in kwargs and kwargs["force_loop"]):
            # generate a new loop (and play)
            if kwargs["game_loop"] == "new":
                keyboard_inputs = None
                # set keyboard inputs directly
                if kwargs["keyboard_inputs"]:
                    keyboard_inputs = kwargs["keyboard_inputs"]
                # or through the screen_obj
                elif kwargs["screen_obj"]:
                    keyboard_inputs = kwargs["screen_obj"].keyboard_inputs

                display = None
                # set display directly
                if kwargs["display"]:
                    display = kwargs["display"]
                # or through the screen_obj
                elif kwargs["screen_obj"]:
                    display = kwargs["screen_obj"].display

                max_fps = 60
                # set display directly
                if kwargs["max_fps"]:
                    max_fps = kwargs["max_fps"]
                # or through the screen_obj
                elif kwargs["screen_obj"]:
                    max_fps = kwargs["screen_obj"].max_fps

                loop = GameLoop(Stage.stage_default_game_loop_callback, display=display,
                                keyboard_inputs=keyboard_inputs, max_fps=max_fps)
                if not kwargs["dont_play"]:
                    loop.play()
                return loop

            # just play an already existing loop
            elif isinstance(kwargs["game_loop"], GameLoop):
                kwargs["game_loop"].play()
                return kwargs["game_loop"]

            # do nothing
            return None

    def __init__(self, callback: callable, display: Display, keyboard_inputs: KeyboardInputs = None, max_fps=60):
        """

        Args:
            callback (callable): The callback function used for looping
            keyboard_inputs (KeyboardInputs): The keyboard input registry to use
            max_fps (float): the maximum frame rate per second to allow when ticking. fps can be slower, but never faster
        """
        self.is_paused = True  # True -> Game loop will be paused (no frames, no ticks)
        self.callback = callback  # gets called each tick with this GameLoop instance as the first parameter (can then extract dt as `game_loop.dt`)
        self.timer = pygame.time.Clock()  # our tick object
        self.frame = 0  # global frame counter
        self.dt = 0.0  # time since last tick was executed
        # registers those keyboard inputs to capture each tick (up/right/down/left as default if none given)
        # - keyboard inputs can be changed during the loop via self.keyboard_input.update_keys([new key list])
        self.keyboard_inputs = keyboard_inputs or KeyboardInputs(None)
        self.display = display
        self.max_fps = max_fps

    def pause(self):
        self.is_paused = True
        GameLoop.active_loop = None

    def play(self, max_fps=None):
        # pause the current loop
        if GameLoop.active_loop:
            GameLoop.active_loop.pause()
        GameLoop.active_loop = self
        self.is_paused = False
        while not self.is_paused:
            self.tick(max_fps)

    def tick(self, max_fps=None):
        if not max_fps:
            max_fps = self.max_fps

        # move the clock and store the dt (since last frame) in sec
        self.dt = self.timer.tick(max_fps) / 1000

        # default global events?
        events = pygame.event.get(pygame.QUIT)  # TODO: add more here?
        for e in events:
            if e.type == pygame.QUIT:
                raise (SystemExit, "QUIT")

        # collect keyboard events
        self.keyboard_inputs.tick()

        # call the callback with self (for references to important game parameters)
        self.callback(self)

        # increase global frame counter
        self.frame += 1

    def step(self, action):
        """
        executes one action on the game
        - the action gets translated into a keyboard sequence first, then is played
        :param action:
        :type action:
        :return:
        :rtype:
        """
        # default global events?
        events = pygame.event.get(pygame.QUIT)  # TODO: add more here?
        for e in events:
            if e.type == pygame.QUIT:
                raise (SystemExit, "QUIT")

        # collect keyboard events
        self.keyboard_inputs.tick()

        # call the callback with self (for references to important game parameters)
        self.callback(self)

        # increase global frame counter
        self.frame += 1


# OBSOLETE: got rid of Scenes altogether. They seemed to make things overly complicated.
#class Scene(object):
#    """
#    A Scene class that allows a 'scene-func' to be run when the Scene is staged (on one of the Stages of the Game)
#    """
#
#    # stores all scenes of the game by name
#    scenes_registry = {}
#
#    @staticmethod
#    def register_scene(name: str, scene_or_func=None, options=None):
#        if not scene_or_func:
#            scene_or_func = Scene.default_scene_func_from_pytmx
#        if not options:
#            options = {}

#        # we have to create the scene from the scene_func
#        if callable(scene_or_func):
#            scene = Scene(scene_or_func, options)
#        # we are given the Scene
#        else:
#            scene = scene_or_func
#        Scene.scenes_registry[name] = scene
#        return scene

#    @staticmethod
#    def get_scene(name: str):
#        if name not in Scene.scenes_registry:
#            return None
#        return Scene.scenes_registry[name]

#    # helper function for setting up a scene on a stage
#    # reads a tmx file and creates a scene from it
#    @staticmethod
#    def default_scene_func_from_pytmx(stage):
#        # mandatory options: tmx (the tmx object)
#        if "tmx_obj" not in stage.options:
#            return
#        tmx_obj = stage.options["tmx_obj"]
#        for layer in tmx_obj.layers:
#            stage.add_tiled_layer(layer, tmx_obj)

#    def __init__(self, scene_func, options=None):
#        """

#        Args:
#            scene_func (callable): the function to be executed when the Scene is staged
#            options (None,iterable): the options to pass on to the Stage when staging this Scene
#        """
#        self.scene_func = scene_func  # will take Stage object as only(!) parameter (options can be retrieved from stage.options)
#        self.options = options or {}  # options for the Scene; will be merged with Stage's options when staging the Scene


class Stage(GameObject):
    """
    A Stage is a container class for Sprites (GameObjects) divided in groups
    - each group has a name
    - Sprites within a Stage can collide with each other
    """

    # list of all Stages
    max_stages = 10
    stages = [None for x in range(max_stages)]
    active_stage = 0  # the currently ticked/rendered Stage

    # the default game loop callback to use if none given when staging a Scene
    # - clamps dt
    # - ticks all stages
    # - renders all stages
    # - updates the pygame.display
    @staticmethod
    def stage_default_game_loop_callback(game_loop: GameLoop):
        # clamp dt
        if game_loop.dt < 0:
            game_loop.dt = 1.0 / 60
        elif game_loop.dt > 1.0 / 15:
            game_loop.dt = 1.0 / 15

        # tick all Stages
        for i, stage in enumerate(Stage.stages):
            Stage.active_stage = i
            if stage:
                stage.tick(game_loop)

        # render all Stages and refresh the pygame.display
        Stage.render_stages(game_loop.display, refresh_after_render=True)

        Stage.active_stage = 0

    @staticmethod
    def render_stages(display: Display, refresh_after_render: bool = False):
        """
        loops through all Stages and renders all of them
        Args:
            display (Display): Display object on which to render
            refresh_after_render (bool): do we refresh the pygame.display after all Stages have been called with `render`?

        Returns:
        """
        # black out display (really necessary? I think so)
        display.surface.fill(pygame.Color("#000000"))
        # call render on all Stages
        for i, stage in enumerate(Stage.stages):
            Stage.active_stage = i
            if stage:
                stage.render(display)
        # for debugging purposes
        if refresh_after_render:
            pygame.display.flip()

    @staticmethod
    def clear_stage(idx: int):
        if Stage.stages[idx]:
            Stage.stages[idx].destroy()
            Stage.stages[idx] = None

    @staticmethod
    def clear_stages():
        for i in range(len(Stage.stages)):
            Stage.clear_stage(i)

    @staticmethod
    def get_stage(idx=Union[int, None]):
        if idx is None:
            idx = Stage.active_stage
        return Stage.stages[idx]

    @staticmethod
    def stage_screen(screen, screen_func=None, stage_idx=None, options=None):
        """
        supported options are (if not given, we take some of them from given Screen object, instead):
        - stage_idx (int): sets the stage index to use (0-9)
        - stage_class (class): sets the class (must be a Stage class) to be used when creating the new Stage
        - force_loop (bool): if set to True and we currently have a GameLoop running, stop the current GameLoop and replace it with a new one, which has
                                to be given via the "game_loop" option (as GameLoop object, or as string "new" for a default GameLoop)
        - keyboard_inputs (KeyboardInputs): the KeyboardInputs object to use for the new GameLoop
        - display (Display): the Display to use for the new GameLoop
        - components (List[Component]): a list of Component objects to add to the new Stage (e.g. a Viewport)

        :param Screen screen: the Screen object to set up on a certain stage
        :param callable screen_func: the function to use to set up the Stage (before playing it)
        :param int stage_idx: the Stage index to use (0=default Stage)
        :param dict options: options to be used when instantiating the Stage
        :return: the new Stage object
        :rtype: Stage
        """
        if options is None:
            options = {}

        defaults(options, {"stage_class": Stage})

        # figure out which stage to use
        stage_idx = stage_idx if stage_idx is not None else (options["stage_idx"] if "stage_idx" in options else 0)

        # clean up an existing stage if necessary
        Stage.clear_stage(stage_idx)

        # create a new Stage and make this this the active stage
        stage = Stage.stages[stage_idx] = options["stage_class"](screen, options)
        Stage.active_stage = stage_idx

        # setup the Stage via the screen_fun (passing it the newly created Stage)
        if not screen_func:
            screen_func = screen.screen_func

        screen_func(stage)
        Stage.active_stage = 0

        # finally return the stage to the user for use if needed
        return stage

    def __init__(self, screen, options=None):
        super().__init__()
        self.screen = screen  # the screen object associated with this Stage
        self.tiled_layers = {}  # pytmx.pytmx.TiledLayer (TiledTileLayer or TiledObjectGroup) by name
        self.tiled_layers_to_render = []  # list of all layers by name (TiledTileLayers AND TiledObjectGroups) in the order in which they have to be rendered
        self.tiled_layers_to_collide = []  # list of all layers that collide (mask is not 0) by name (TiledTileLayers)

        # dict of pygame.sprite.Group objects (by name) that contain Sprites (each TiledObjectGroup results in one Group)
        # - the name of the group is always the name of the TiledObjectLayer in the tmx file
        self.sprite_groups = {}
        self.sprites = []  # a plain list of all Sprites in this Stage

        # self.index = {}  # used for search methods
        self.remove_list = []  # sprites to be removed from the Stage (only remove when Stage gets ticked)
        self.options = options or {}

        self.is_paused = False
        self.is_hidden = False

        # register events that we will trigger
        self.register_event("destroyed",
                            "added_to_stage", "removed_from_stage",  # Sprites added/removed to/from us
                            "pre_ticks", "pre_collisions",  # before we tick all Sprites, before we analyse all Sprites for collisions
                            "post_tick",  # after we ticked all Sprites
                            "pre_render", "post_render"  # before/after we render all our layers
                            )

        # add Components to this Stage
        if "components" in self.options:
            for comp in self.options["components"]:
                self.add_component(comp)

        # make sure our destroyed method is called when the stage is destroyed
        self.on_event("destroyed")

    def destroyed(self):
        self.invoke("debind_events")
        self.trigger_event("destroyed")

    #OBSOLETE:
    # executes our Scene by calling the Scene's function with self as only parameter
    #def load_scene(self):
    #    if self.scene:
    #        self.scene.scene_func(self)

    # TODO: loadAssets?

    # calls the callback function for each sprite, each time passing it the sprite and params
    def for_each(self, callback: callable, params=None):  # quintus: `each`
        if not params:
            params = []
        for sprite in self.sprites:
            callback(sprite, *params)

    # calls a function on all of the GameObjects on this Stage
    def invoke(self, func_name: str, params=None):
        if not params:
            params = []
        for sprite in self.sprites:
            if hasattr(sprite, func_name):
                func = getattr(sprite, func_name)
                if callable(func):
                    func(*params)

    # returns the first GameObject in this Stage that - when passed to the detector function with params - returns True
    def detect(self, detector: callable, params=None):
        if not params:
            params = []
        for sprite in self.sprites:
            if detector(sprite, *params):
                return sprite

    def add_tiled_layer(self, pytmx_layer: pytmx.pytmx.TiledElement, pytmx_tiled_map: pytmx.pytmx.TiledMap):
        assert pytmx_layer.name not in self.tiled_layers, "ERROR: pytmx_layer with name {} already exists!".format(pytmx_layer.name)

        # make a spygame.TmxLayer
        if isinstance(pytmx_layer, pytmx.pytmx.TiledObjectGroup):
            # TODO: what if we have many objects in the layer that should have different render_order? (e.g. a Repeater)
            # try once more with another object layer (but there was a bug in pytmx)
            l = TiledObjectGroup(pytmx_layer, pytmx_tiled_map)
        elif isinstance(pytmx_layer, pytmx.pytmx.TiledTileLayer):
            # use default collision objects if not given
            if "tile_layer_physics_collisions" not in self.options:
                self.options["tile_layer_physics_collisions"] = (Collision(), Collision())
            assert "tile_layer_physics_collision_detector" in self.options, \
                "ERROR: a TiledTileLayer needs a physics collision detector given in the Stage's option: `tile_layer_physics_collision_detector`!"
            assert "tile_layer_physics_collision_postprocessor" in self.options, \
                "ERROR: a TiledTileLayer needs a physics collision handler given in the Stage's option: `tile_layer_physics_collision_postprocessor`!"
            l = TiledTileLayer(pytmx_layer, pytmx_tiled_map, self.options["tile_layer_physics_collisions"],
                               self.options["tile_layer_physics_collision_detector"], self.options["tile_layer_physics_collision_postprocessor"])
            # put the pytmx_layer into one of the collision groups (normal or touch)?
            # - this is useful for our solve_collisions method
            if l.type != Sprite.get_type("none"):
                self.tiled_layers_to_collide.append(l)
        else:
            raise Exception("ERROR: pytmx_layer of type {} cannot be added to Stage. Needs to be pytmx.pytmx.TiledTileLayer or pytmx.pytmx.TiledObjectGroup!".
                            format(type(pytmx_layer).__name__))

        self.tiled_layers[l.name] = l
        if l.do_render:
            self.tiled_layers_to_render.append(l)
            self.tiled_layers_to_render.sort(key=lambda x: x.render_order)

        # if layer is a TiledObjectGroup -> add the (already existing) sprite-group to this stage under the name of the layer
        if isinstance(l, TiledObjectGroup):
            assert l.name not in self.sprite_groups, \
                "ERROR: trying to add a TiledObjectGroup to a Stage, but the Stage already has a spritegroup with the name of that layer ({})". \
                    format(l.name)
            self.sprite_groups[l.name] = l.sprite_group
            for sprite in l.sprite_group.sprites():
                self.add_sprite(sprite, l.name)

    # TODO: Sprite or GameObject??
    def add_sprite(self, sprite: Sprite, group_name: str):
        """
        adds a new sprite to an existing or a new Group
            :param GameObject sprite: the GameObject to be added
            :param str group_name: the name of the group to which the GameObject should be added (group will not be created if it doesn't exist yet)
            :return: the Sprite that was added
        """
        # if the group doesn't exist yet, create it
        if group_name not in self.sprite_groups:
            self.sprite_groups[group_name] = pygame.sprite.Group()
        sprite.stage = self  # set the Stage of this GameObject
        self.sprite_groups[group_name].add(sprite)
        self.sprites.append(sprite)
        sprite.sprite_groups.append(self.sprite_groups[group_name])

        # trigger two events, one on the Stage with the object as target and one on the object with the Stage as target
        self.trigger_event("added_to_stage", sprite)
        sprite.trigger_event("added_to_stage", self)

        return sprite

    def remove_sprite(self, sprite: Sprite):
        self.remove_list.append(sprite)

    def force_remove_sprite(self, sprite: Sprite):
        # try to remove from sprites list (if it's still in there)
        try:
            self.sprites.remove(sprite)
        except ValueError:
            return

        # destroy the object
        sprite.destroy()
        self.trigger_event("removed_from_stage", sprite)

    def pause(self):
        self.is_paused = True

    def unpause(self):
        self.is_paused = False

    def solve_collisions(self):
        """
        look for the objects layer and do each object against the main collision layer
        - some objects in the objects layer do their own collision -> skip those here (e.g. ladder climbing objects)
        - after the main collision layer, do each object against each other
        """
        # collide each object with all collidable layers (matching collision mask of object)
        for sprite in self.sprites:
            # if this game_object completely handles its own collisions within its tick -> ignore it
            if not sprite.handles_own_collisions and sprite.collision_mask > 0:
                # collide with all matching tile layers
                for tile_layer in self.tiled_layers_to_collide:
                    # only collide, if the type of the layer matches one of the object's bits in the mask
                    # TODO: do we have to match the layer's collision mask as well? (layers currently don't have a collision mask)
                    if sprite.collision_mask & tile_layer.type:
                        col = tile_layer.collide(sprite)
                        if col:
                            sprite.trigger_event("collision", col)

        # collide all objects with all other game-objects
        exhaustive = self.sprites.copy()
        for sprite in self.sprites:
            exhaustive.remove(sprite)
            # if this game_object completely handles its own collisions within its tick -> ignore it
            if not sprite.handles_own_collisions and sprite.collision_mask > 0:
                for sprite2 in exhaustive:
                    col = SATCollision.collide(sprite, sprite2)
                    if col:
                        # TODO: do we have to trigger the reversed collision as well?
                        sprite.trigger_event("collision", col)

    def tick(self, game_loop):
        """
        gets called each frame by the GameLoop
        - calls update on all its Sprites (through 'updateSprites')

        :param GameLoop game_loop: the GameLoop object that's currently running (and ticking all Stages)
        """

        if self.is_paused:
            return False

        # do the ticking of all objects
        self.trigger_event("pre_ticks", game_loop)
        for sprite in self.sprites:
            if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_BEFORE_EACH_TICK:
                sprite.render(game_loop.display)
                game_loop.display.debug_refresh()
            sprite.tick(game_loop)
            if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_AFTER_EACH_TICK:
                sprite.render(game_loop.display)
                game_loop.display.debug_refresh()

        # do the collision resolution
        self.trigger_event("pre_collisions", game_loop)
        self.solve_collisions()

        # garbage collect destroyed GameObjects
        for sprite in self.remove_list:
            self.force_remove_sprite(sprite)
        self.remove_list.clear()

        self.trigger_event("post_tick", game_loop)

    def hide(self):
        """
        hides the Stage
        """
        self.is_hidden = True

    def show(self):
        """
        unhides the Stage
        """
        self.is_hidden = False

    def stop(self):
        """
        stops playing the Stage (stops calling `tick` on all GameObjects)
        """
        self.hide()
        self.pause()

    def start(self):
        """
        starts running the Stage (and calling all GameObject's `tick` method)
        """
        self.show()
        self.unpause()

    def render(self, display: Display):
        """
        gets called each frame by the GameLoop (after 'tick' is called on all Stages)
        - renders all GameObjects

        :param Display display: the Display object to render on
        """
        if self.is_hidden:
            return False

        self.trigger_event("pre_render", display)
        for layer in self.tiled_layers_to_render:
            layer.render(display)
        self.trigger_event("post_render", display)


class TmxLayer(object, metaclass=ABCMeta):
    """
    a wrapper class for the pytmx TiledObject class that can either represent a TiledTileLayer or a TiledObjectGroup
    - needs to implement render and stores some spygame specific properties such as collision, render, etc.

    :param pytmx.pytmx.TiledElement tmx_layer_obj: the underlying pytmx TiledTileLayer
    :param pytmx.pytmx.TiledMap tmx_tiled_map: the underlying pytmx TiledMap object (representing the tmx file)
    """

    def __init__(self, tmx_layer_obj, tmx_tiled_map):
        self.pytmx_layer = tmx_layer_obj
        self.pytmx_tiled_map = tmx_tiled_map
        self.name = tmx_layer_obj.name
        properties = tmx_layer_obj.properties
        defaults(properties, {"do_render": "true", "render_order": 0})
        self.properties = properties
        self.do_render = (properties["do_render"] == "true")
        self.render_order = int(properties["render_order"])

    @abstractmethod
    def render(self, display: Display):
        pass


class TiledTileLayer(TmxLayer):
    """
    a wrapper class for pytmx.pytmx.TiledTileLayer, which represents a 'normal' tile layer in a tmx file
    - reads in all tiles' images into one Surface object so we can render the entire layer at once
    - implements `render`
    """

    def __init__(self, pytmx_layer, pytmx_tiled_map, collision_objects, collision_detector, collision_postprocessor):
        """
        :param pytmx.pytmx.TiledTileLayer pytmx_layer: the underlying pytmx TiledTileLayer
        :param pytmx.pytmx.TiledMap pytmx_tiled_map: the underlying pytmx TiledMap object (representing the tmx file)
        :param callable collision_detector: the function to use for detecting collisions (e.g. spyg.SATCollision/spyg.AABBCollision/etc..)
        :param callable collision_postprocessor: the function to use to handle collisions (once detected by the collision_detector)
        """
        super().__init__(pytmx_layer, pytmx_tiled_map)

        self.type_str = self.properties.get("type", "none")
        self.type = 0

        self.props_by_pos = {}  # stores the properties of each tile by position tuple (x, y)
        # an object representing a single tile from this layer to pass to a collision function
        self.tile_sprite = TileSprite(self, pytmx_tiled_map, pygame.Rect((0, 0), (self.pytmx_tiled_map.tilewidth, self.pytmx_tiled_map.tileheight)))
        # store our tuple of two Collision objects for passing into the collision handler
        assert isinstance(collision_objects, tuple) and len(collision_objects) == 2 and \
               isinstance(collision_objects[0], Collision) and isinstance(collision_objects[1], Collision), \
            "ERROR: parameter collision_objects needs to be a tuple of two Collision objects!"
        self.collision_objects = collision_objects
        self.collision_detector = collision_detector
        self.collision_postprocessor = collision_postprocessor

        # get collision mask of this layer from self.collision property
        types_ = self.type_str.split(",")
        for t in types_:
            self.type |= Sprite.get_type(t)

        # update do_render indicator depending on some debug settings
        self.do_render = (self.do_render and not (DEBUG_FLAGS & DEBUG_DONT_RENDER_TILED_TILE_LAYERS)) or \
                         (self.type != Sprite.get_type("none") and (DEBUG_FLAGS & DEBUG_RENDER_COLLISION_TILES))
        # put this layer in one single Sprite that we can then blit on the display (with 'area=' to avoid drawing the entire layer each time)
        self.pygame_sprite = None

        # we are rendering this layer, need to get entire image into this structure
        if self.do_render:
            surf = pygame.Surface((self.pytmx_layer.width * self.pytmx_tiled_map.tilewidth, self.pytmx_layer.height * self.pytmx_tiled_map.tileheight),
                                  flags=pygame.SRCALPHA)
            # rendered collision layer
            if self.type != Sprite.get_type("none") and (DEBUG_FLAGS & DEBUG_RENDER_COLLISION_TILES):
                # red for normal collisions, light-blue for touch collisions
                color = DEBUG_RENDER_COLLISION_TILES_COLOR_DEFAULT if self.type & Sprite.get_type("default") else DEBUG_RENDER_COLLISION_TILES_COLOR_OTHER
                for (x, y, image), (_, _, gid) in zip(self.pytmx_layer.tiles(), self.pytmx_layer.iter_data()):
                    surf.blit(image.convert_alpha(), (x * self.pytmx_tiled_map.tilewidth, y * self.pytmx_tiled_map.tileheight))
                    tile_props = self.pytmx_tiled_map.get_tile_properties_by_gid(gid) or {}
                    # normal collision tiles
                    if not tile_props.get("no_collision"):
                        pygame.draw.rect(surf, color, pygame.Rect((x * self.pytmx_tiled_map.tilewidth, y * self.pytmx_tiled_map.tileheight),
                                                                  (self.pytmx_tiled_map.tilewidth, self.pytmx_tiled_map.tileheight)), 1)
            # "normal" layer (and no debug rendering)
            else:
                for x, y, image in self.pytmx_layer.tiles():
                    surf.blit(image.convert_alpha(), (x * self.pytmx_tiled_map.tilewidth, y * self.pytmx_tiled_map.tileheight))

            pygame_sprite = pygame.sprite.Sprite()
            pygame_sprite.image = surf
            pygame_sprite.rect = surf.get_rect()
            self.pygame_sprite = pygame_sprite

        # this is a collision layer, need to store each non-empty tile's (gid > 0) properties
        if self.type != Sprite.get_type("none"):
            # loop through each tile and store tile props by x/y tuple in our dict
            for x, y, gid in self.pytmx_layer.iter_data():
                # skip empty tiles (gid==0)
                if gid == 0:
                    continue
                tile_props = self.pytmx_tiled_map.get_tile_properties_by_gid(gid) or {}
                # go through dict and translate data types into proper python types ("true" -> bool, 0.0 -> float, etc..)
                for key, value in tile_props.items():
                    # bool
                    if value == "true" or value == "false":
                        value = (value == "true")
                    # int
                    elif re.fullmatch('\d+', str(value)):
                        value = int(value)
                    # float (or string)
                    else:
                        try:
                            value = float(value)
                        except (ValueError, TypeError):  # string/list/etc..
                            pass
                    # assign correct typed value
                    tile_props[key] = value

                # directly translate possible tile types (for collision) into the correct bitmask
                types_ = tile_props.get("type")
                # type of this tile has not been translated into bitmap yet
                if isinstance(types_, str):
                    tile_props["type"] = 0
                    for t in types_.split(","):
                        tile_props["type"] |= Sprite.get_type(t)
                self.props_by_pos[(x, y)] = tile_props

    def render(self, display: Display):
        """
        blits a part of our Sprite's image onto the Display's Surface using the Display's offset attributes

        :param Display display: the Display object to render on
        """
        assert self.do_render, "ERROR: TiledTileLayer.render() called but self.do_render is False!"
        assert not isinstance(self.pygame_sprite, Sprite), "ERROR: TiledTileLayer.render() called but self.pygame_sprite is not a Sprite!"
        r = pygame.Rect(self.pygame_sprite.rect)  # make a clone so we don't change the original Rect
        # apply the display offsets (camera)
        r.x += display.offsets[0]
        r.y += display.offsets[1]
        # TODO: we shouldn't have to do this each render, just once (display size does not change)
        r.width = display.surface.get_width()
        r.height = display.surface.get_height()
        display.surface.blit(self.pygame_sprite.image, dest=(0, 0), area=r)

    def collide(self, sprite: Sprite, direction='x', direction_veloc=1.0):
        """
        solves collisions between this tile layer and any Sprite (depends on the velocity of the Sprite)

        :param Sprite sprite: the Sprite to test
        :param str direction: the direction in which to check for collision ('x' or 'y')
        :param float direction_veloc: the velocity of the Sprite in the given direction (can be negative)
        :return: a Collision object with all details of the collision between the Sprite and this layer (None if there is no collision)
        :rtype: Union[None, Collision]
        """
        # determine the tile steps (left/right up/down)
        direction_x = 1
        direction_y = 1
        if direction == 'x':
            direction_x = int(math.copysign(1.0, direction_veloc))
        else:
            direction_y = int(math.copysign(1.0, direction_veloc))

        tile_start_x = sprite.rect.left // self.pytmx_tiled_map.tilewidth
        tile_end_x = sprite.rect.right // self.pytmx_tiled_map.tilewidth
        tile_start_y = sprite.rect.top // self.pytmx_tiled_map.tileheight
        tile_end_y = sprite.rect.bottom // self.pytmx_tiled_map.tileheight

        if DEBUG_FLAGS & DEBUG_RENDER_ACTIVE_COLLISION_TILES:
            for tile_y in range(tile_start_y, tile_end_y + 1):
                for tile_x in range(tile_start_x, tile_end_x + 1):
                    pygame.draw.rect(GameLoop.active_loop.display.surface, DEBUG_RENDER_ACTIVE_COLLISION_TILES_COLOR,
                                     pygame.Rect((tile_x * self.pytmx_tiled_map.tilewidth, tile_y * self.pytmx_tiled_map.tileheight),
                                                 (self.pytmx_tiled_map.tilewidth, self.pytmx_tiled_map.tileheight)), 1)
            GameLoop.active_loop.display.debug_refresh()

        if direction_x < 0:
            tmp = tile_end_x
            tile_end_x = tile_start_x
            tile_start_x = tmp
        if direction_y < 0:
            tmp = tile_end_y
            tile_end_y = tile_start_y
            tile_start_y = tmp

        # - slope handling takes place here
        #   - slope-handling: pick that tile for the collision that has to deal with shifting the y-pos of the character up
        #     (which means, if we find a collision with a slope-2-offset-1-tile and the character is already touching the next tile with its right-x-corner, we pick the next tile (if it's also a slope 2, etc...)
        # - pick the first collision and return it
        # - make sure each tile is only checked once for collisions (use tileFlags hash to tag tiles as "already processed")
        # - the order of the tiles we loop through is bottom-up and in direction of characters running direction (objp.vx)
        for tile_y in range(tile_start_y, tile_end_y + direction_y, direction_y):
            for tile_x in range(tile_start_x, tile_end_x + direction_x, direction_x):
                tile_xy = (tile_x, tile_y)

                tile_props = self.props_by_pos.get(tile_xy)

                # empty tile OR no_collision property of this tile is set to 'true' -> skip
                if tile_props is None or tile_props.get("no_collision"):
                    continue

                # set up our TileSprite (a Sprite that represents a single tile) for the collision detector
                self.tile_sprite.tile_x = tile_x
                self.tile_sprite.tile_y = tile_y
                self.tile_sprite.rect.x = tile_x * self.pytmx_tiled_map.tilewidth
                self.tile_sprite.rect.y = tile_y * self.pytmx_tiled_map.tileheight
                self.tile_sprite.tile_props = tile_props

                # check the actual collision with our collision detector
                col = self.collision_detector(sprite, self.tile_sprite, self.collision_objects, direction=direction, direction_veloc=direction_veloc)

                # we got a new collision with this tile -> post-process collision and - if still ok - return
                if col and col.is_collided and col.magnitude > 0:
                    # post-process the collision depending on the given Physics engine's post-processor (e.g. to deal with slopes)
                    col = self.collision_postprocessor(col)
                    # collision is still ok (after post-processing) -> trigger collision event on Sprite
                    if col.is_collided:
                        sprite.trigger_event("collision", col)
                        # return after the first tile collided with Sprite
                        return col
                    else:
                        # keep looking for other tiles that might collide
                        continue

        return None  # no collision


class TileSprite(Sprite):
    """
    class used by TiledTileLayer objects to have a means of representing single tiles in terms of Sprite objects
    (used for collision detector function)
    """
    def __init__(self, layer: TiledTileLayer, pytmx_tiled_map: pytmx.pytmx.TiledMap, rect: Union[pygame.Rect, None] = None):
        """
        :param TiledTileLayer layer: the TiledTileLayer object to which this tile belongs
        :param pytmx.pytmx.TiledMap pytmx_tiled_map: the tmx tiled-map object to which this tile belongs
                                                     (useful to have to look up certain map-side properties, e.g. tilewidth/height)
        :param Union[pygame.Rect, None] rect: the pygame.Rect representing the position and size of the tile
        """
        self.tiled_tile_layer = layer
        self.pytmx_tiled_map = pytmx_tiled_map
        self.tile_w = self.pytmx_tiled_map.tilewidth  # the width of the tile that was hit
        self.tile_h = self.pytmx_tiled_map.tileheight  # the height of the tile that was hit
        super().__init__(0, 0, (self.tile_w, self.tile_h))
        self.tile_x = 0  # the x position in the layer of the tile that was hit
        self.tile_y = 0  # the y position in the layer of the tile that was hit
        self.tile = 0  # the ID of the tile in the layer
        self.tile_props = {}  # the properties dict of the tile that was hit


class TiledObjectGroup(TmxLayer):
    """
    a wrapper class for the pytmx.TiledObjectGroup class, which represents an object layer in a tmx file
    - generates all GameObjects specified in the layer (a.g. the agent, enemies, etc..)
    - implements `render` by looping through all GameObjects and rendering their Sprites one by one
    """

    def __init__(self, pytmx_layer: pytmx.pytmx.TiledObjectGroup, pytmx_tiled_map: pytmx.pytmx.TiledMap):
        super().__init__(pytmx_layer, pytmx_tiled_map)

        # create the sprite group for this layer (all GameObjects will be added to this group)
        self.sprite_group = pygame.sprite.Group()

        # add each object from the layer converted into a GameObject to this Stage under group: group.name
        for obj in self.pytmx_layer:
            obj_props = obj.properties

            # if the (Sprite) class of the object is given, construct it here using its c'tor
            # - classes are given as strings: e.g. sypg.Sprite, vikings.Viking, Agent (Agent class would be in __main__ module)
            if "sprite_class" in obj_props:
                match_obj = re.fullmatch('^((.+)\.)?(\w+)$', obj_props["sprite_class"])
                assert match_obj, "ERROR: class property in pytmx.pytmx.TiledObjectGroup does not match pattern!"
                _, module_, class_ = match_obj.groups(default="__main__")  # if no module given, assume a class defined in __main__

                sheet_or_image = None
                if "tsx" in obj_props:
                    sheet_or_image = SpriteSheet("data/" + obj_props["tsx"] + ".tsx")
                elif "image_file" in obj_props:
                    sheet_or_image = "images/" + obj_props["image_file"] + ".png"

                # generate the Sprite
                sprite = getattr(sys.modules[module_], class_)(obj.x, obj.y, sheet_or_image)
                self.sprite_group.add(sprite)

    def render(self, display):
        # loop through each Sprite in the group and blit it to the Display's Surface
        for sprite in self.sprite_group.sprites():
            sprite.render(display)
            # display.surface.blit(sprite.image, dest=(sprite.rect.x + display.offsets[0], sprite.rect.y + display.offsets[1]))


class Collision(object):
    """
    a simple feature object that stores collision properties for collisions between two objects
    or between an object and a TiledTileLayer
    """

    def __init__(self):
        self.sprite1 = None  # hook into the first Sprite participating in this collision
        self.sprite2 = None  # hook into the second Sprite participating in this collision (this could be a TileSprite)
        self.is_collided = True  # True if a collision happened (usually True)
        self.distance = 0  # how much do we have to move sprite1 to separate the two Sprites? (always negative)
        self.magnitude = 0  # abs(distance)
        self.normal_x = 0.0  # x-component of the collision normal
        self.normal_y = 0.0  # y-component of the collision normal
        self.separate = [0, 0]  # (distance * normal_x, distance * normal_y)
        self.direction = None  # None, 'x' or 'y' (direction in which we measure the collision; the other direction is ignored)
        self.direction_veloc = 0  # velocity direction component (e.g. direction=='x' veloc==5 -> moving right, veloc==-10.4 -> moving left)


class PlatformerCollision(Collision):
    """
    a collision object that can be used by PlatformerPhysics to handle Collisions
    """

    def __init__(self):
        super().__init__()
        self.impact = 0.0  # the impulse of the collision on some mass (used for pushing heavy objects)
        self.slope = False  # whether this is a collision with a sloped TileSprite of a TiledTileLayer
                            # (will also be False if obj1 collides with the Tile's rect, but obj1 is still in air (slope))
        self.slope_y_pull = 0  # amount of y that Sprite has to move up (negative) or down (positive) because of the slope
        self.slope_up_down = 0  # 0=no slope, -1=down slope, 1 = up slope


class Component(GameObject, metaclass=ABCMeta):
    """
    a Component can be added to and removed from other GameObjects
    - use `extend` to make a Component's method be callable directly from the owning GameObject

    :param str name: the name of the component (the name can be used to retrieve any GameObject's components via the [GameObject].components dict)
    """

    def __init__(self, name):
        super().__init__()
        self.name = name
        self.game_object = None  # to be set by Entity when this component gets added

    @abstractmethod
    def added(self):
        """
        gets called when the component is added to a GameObject
        """
        pass

    def removed(self):
        """
        gets called when the component is removed from a GameObject
        """
        pass

    def extend(self, method):
        """
        extends the given method (has to take self as 1st param) onto the GameObject, so that this method can be called
        directly from the GameObject

        :param callable method: method, which to make callable from within the owning GameObject
        """
        assert self.game_object, "ERROR: need self.game_object in order to extend the method to that GameObject!"
        # use the MethodType function to bind the play_animation function to only this object (not any other instances of the GameObject's class)
        # - the extended method will take two self's (0=Component, 1=GameObject), thus selfs should be called 'comp' and 'game_object' OR 'self' and 'game_object'
        setattr(self.game_object, method.__name__, types.MethodType(method, self.game_object))


class Brain(Component):
    """
    a brain class that handles agent control (via the GameLoop´s keyboard registry)
    - sets self.commands each tick depending on keyboard input
    """

    def __init__(self, name: str, commands: Union[list, None]):
        super().__init__(name)
        if commands is None:
            commands = []
        self.commands = {command: False for command in commands}
        self.game_obj_cmp_anim = None  # our GameObject's Animation Component (if any); needed for animation flags
        self.animation_flags = 0  # a copy of the GameObject's current Animation flags (store copy here for performance reasons)

    def reset(self):
        """
        sets all commands to False (makes this Brain inactive)
        """
        for key in self.commands:
            self.commands[key] = False

    def added(self):
        # call our own tick method when event "pre_tick" is triggered on our GameObject
        self.game_object.on_event("pre_tick", self, "tick", register=True)
        # search for an Animation component
        self.game_obj_cmp_anim = self.game_object.components.get("animation")

    # for now, just translate keyboard_inputs from GameLoop object into our commands
    def tick(self, game_loop: GameLoop):
        # update current animation flags
        if self.game_obj_cmp_anim:
            self.animation_flags = self.game_obj_cmp_anim.flags
        # current animation does not block: normal commands possible
        if not (self.animation_flags & Animation.ANIM_DISABLES_CONTROL):
            for (key, value), desc in zip(game_loop.keyboard_inputs.keyboard_registry.items(), game_loop.keyboard_inputs.descriptions.values()):
                self.commands[desc] = value
        # all commands are blocked right now -> set everything to False
        else:
            self.reset()


class Animation(Component):
    # static animation-properties registry
    # - stores single animation records (these are NOT Animation objects, but simple dicts representing settings for single animation sequences)
    animation_settings = {}

    # some flags
    # TODO: make these less Viking-dependent (implement similar 'type'-registry as for Sprites' collisions)
    ANIM_NONE = 0x0
    ANIM_SWING_SWORD = 0x1
    ANIM_DISABLES_CONTROL = 0x2
    ANIM_PROHIBITS_STAND = 0x4  # anims that should never be overwritten by 'stand'(even though player might not x - move)
    ANIM_BOW = 0x8

    @staticmethod
    def register_settings(settings_name, settings, register_events_on=None):
        # we do not have this name registered yet
        if settings_name not in Animation.animation_settings:
            assert "default" in settings, "ERROR: no entry `default` in animation-settings. Each settings block needs a default animation name."
            for anim in settings:
                if anim != "default":
                    defaults(settings[anim], {
                        "rate"         : 1 / 3,  # the rate with which to play this animation in 1/s
                        "frames"       : [0, 1],  # the frames to play from our spritesheet (starts with 0)
                        "priority"     : -1,  # which priority to use for next if next is given
                        "flags"        : Animation.ANIM_NONE,
                        # flags bitmap that determines the behavior of the animation (e.g. block controls during animation play, etc..)
                        "loop"         : True,  # whether to loop the animation when done
                        "next"         : None,  # which animation to play next
                        "next_priority": -1,  # which priority to use for next if next is given
                        "trigger"      : None,  # which events to trigger on the game_object that plays this animation
                        "trigger_data" : None,  # data to pass to the event handler if trigger is given
                        "keys_status"  : {},  # ??? can override DISABLE_MOVEMENT setting only for certain keys
                    })
            Animation.animation_settings[settings_name] = settings

        if isinstance(register_events_on, EventObject):
            l = list(chain.from_iterable(("anim." + anim, "anim_loop." + anim, "anim_end." + anim) for anim in settings))
            register_events_on.register_event(*l)

    @staticmethod
    def get_settings(spritesheet_name, anim_setting):
        if spritesheet_name not in Animation.animation_settings or anim_setting not in Animation.animation_settings[spritesheet_name]:
            return None
        return Animation.animation_settings[spritesheet_name][anim_setting]

    def __init__(self, name: str):
        super().__init__(name)
        self.animation = None  # str: if set to something, we are playing this animation
        self.rate = 1 / 3  # default rate in s
        self.has_changed = False
        self.priority = -1  # animation priority (takes the value of the highest priority animation that wants to be played simultaneously)
        self.frame = 0  # the current frame in the animation 'frames' list
        self.time = 0  # the current time after starting the animation in s
        self.flags = 0
        self.keys_status = {}
        self.blink_rate = 3.0
        self.blink_duration = 0
        self.blink_time = 0
        self.is_hidden = False  # True: half the time we are blinking

    def added(self):
        # make sure our GameObject is actually a Sprite
        assert isinstance(self.game_object, Sprite), "ERROR: Component Animation can only be added to a Sprite object!"

        # call our own tick method when event "post_tick" is triggered on our GameObject
        self.game_object.on_event("post_tick", self, self.tick)
        # tell our GameObject that we might trigger some "anim..." events on it
        self.game_object.register_event("anim", "anim_frame", "anim_loop", "anim_end")

        # extend some methods directly onto the GameObject
        self.extend(self.play_animation)
        self.extend(self.blink_animation)

    def tick(self, game_loop):
        """
        gets called when the GameObject triggers a "pre_tick" event

        :param GameLoop game_loop: the GameLoop that's currently playing
        """
        obj = self.game_object

        # blink stuff?
        if self.blink_duration > 0:
            self.blink_time += game_loop.dt
            # blinking stops
            if self.blink_time >= self.blink_duration:
                self.blink_duration = 0
                self.is_hidden = False
            else:
                frame = int(self.blink_time * self.blink_rate)
                self.is_hidden = True if frame % 2 == 0 else False

        # animation stuff?
        if self.animation:
            anim_settings = Animation.get_settings(obj.spritesheet.name, self.animation)
            rate = anim_settings["rate"] or self.rate
            stepped = 0
            self.time += game_loop.dt
            if self.has_changed:
                self.has_changed = False
            else:
                self.time += game_loop.dt
                if self.time > rate:
                    stepped = self.time // rate
                    self.time -= stepped * rate
                    self.frame += stepped
            # we are changing frames
            if stepped > 0:
                # there are no more frames
                if self.frame >= len(anim_settings["frames"]):
                    # this animation ends
                    if anim_settings["loop"] is False or anim_settings["next"]:
                        self.frame = len(anim_settings["frames"]) - 1
                        obj.trigger_event("anim_end")
                        obj.trigger_event("anim_end." + self.animation)
                        self.priority = -1
                        if anim_settings["trigger"]:
                            obj.trigger_event(anim_settings["trigger"], anim_settings["trigger_data"])
                        if anim_settings["next"]:
                            self.play_animation(obj, anim_settings["next"], anim_settings["next_priority"])
                        return
                    # this animation loops
                    else:
                        obj.trigger_event("anim_loop")
                        obj.trigger_event("anim_loop." + self.animation)
                        self.frame %= len(anim_settings["frames"])

                obj.trigger_event("anim_frame")

            # assign the correct image to the `image` field of the GameObject (already correctly x/y-flipped)
            # hidden: no image
            if self.is_hidden:
                obj.image = None
            # visible: some image
            else:
                tiles_dict = obj.spritesheet.tiles  # no flipping
                if obj.flip["x"]:
                    if obj.flip["y"]:
                        tiles_dict = obj.spritesheet.tiles_flipped_xy
                    else:
                        tiles_dict = obj.spritesheet.tiles_flipped_x
                elif obj.flip["y"]:
                    tiles_dict = obj.spritesheet.tiles_flipped_y
                obj.image = tiles_dict[anim_settings["frames"][int(self.frame)]]

    def play_animation(comp, game_object, name, priority=0):
        """
        plays an animation on our GameObject

        :param GameObject game_object: the GameObject on which to play the animation; the animation has to be setup via register_settings with the name
          of the SpriteSheet of the GameObject
        :param str name: the name of the animation to play
        :param int priority: the priority with which to play this animation (if this method is called multiple times, it will pick the higher one)
        """
        if name and name != comp.animation and priority >= comp.priority:
            comp.animation = name
            comp.has_changed = True
            comp.time = 0
            comp.frame = 0  # start each animation from 0
            comp.priority = priority

            # look up animation in list
            anim_settings = Animation.get_settings(game_object.spritesheet.name, comp.animation)
            # set flags to sprite's properties
            comp.flags = anim_settings["flags"]
            comp.keys_status = anim_settings["keys_status"]

            game_object.trigger_event("anim")
            game_object.trigger_event("anim." + comp.animation)

    def blink_animation(comp, game_object, rate=3.0, duration=3.0):
        """
        blinks the GameObject with the given parameters

        :param GameObject game_object: our GameObject to which blinking is applied
        :param float rate: the rate with which to blink (in 1/s)
        :param float duration: the duration of the blinking (in s); after the duration, the blinking stops
        """
        comp.blink_rate = rate
        comp.blink_duration = duration
        comp.blink_time = 0


class Dockable(Component):
    """
    a dockable component allows for other Sprites to dock to this Component's GameObject
    - other Sprites that are docked to us will be moved along with us
    """

    DEFINITELY_DOCKED = 0x1  # this object is definitely docked to something right now
    DEFINITELY_NOT_DOCKED = 0x2  # this object is definitely not docked to something right now
    TO_BE_DETERMINED = 0x4  # the docking state of this object is currently being determined
    PREVIOUSLY_DOCKED = 0x8  # if set, the object was docked to something in the previous frame

    def __init__(self, name):
        """
        :param str name: the name of the Component
        """
        super().__init__(name)
        self.docked_sprites = {}  # dictionary that holds all Sprites (key=GameObject's id) currently docked to this one
        # holds the objects that we stand on and stood on previously:
        # slot 0=current state; slot 1=previous state (sometimes we need the previous state since the current state gets reset to 0 every step)
        self.docking_state = 0
        self.docked_to = None  # the reference to the object that we are currently docked to

    def added(self):
        # make sure our GameObject is a Sprite
        assert isinstance(self.game_object, Sprite), "ERROR: game_object of Component Dockable must be of type Sprite (not {})!". \
            format(type(self.game_object).__name__)
        # extend our GameObject with move
        self.extend(self.move)

    def move(self, sprite, x, y, precheck=False):
        """
        this will 'overwrite' the normal Sprite's `move` method by Component's extend
        - if precheck is set to True: pre-checks the planned move via call to stage.locate and only moves entity as far as possible

        :param Sprite sprite: the GameObject that this Component belongs to (the Sprite to move around)
        :param int x: the amount in pixels to move in x-direction
        :param int y: the amount in pixels to move in y-direction
        :param bool precheck: ???
        """

        #if precheck:
        #    testcol = self.stage.locate(p.x+x, p.y+y, Q._SPRITE_DEFAULT, p.w, p.h);
        #    if ((!testcol) || (testcol.tileprops && testcol.tileprops['liquid'])) {
        #        return True
        #
        #    return False

        # do a minimum of 1 pix (if larger 0.0)
        if x > 0 and x < 1:
            x = 1
        sprite.rect.x += x
        if y > 0 and y < 1:
            y = 1
        sprite.rect.y += y

        # TODO: move the obj_to_follow into collide of stage (stage knows its borders best, then we don't need to define xmax/xmin, etc.. anymore)
        # TODO: maybe we could even build a default collision-frame around every stage when inserting the collision layer
        """
        if sprite.rect.x < self.x_min:
            sprite.rect.x = self.x_min
            self.vx = 0
        elif sprite.rect.x > self.x_max:
            sprite.rect.x = self.x_max
            self.vx = 0
        if sprite.rect.y < self.y_min:
            sprite.rect.y = self.y_min
            self.vy = 0
        elif sprite.rect.y > self.y_max:
            sprite.rect.y = self.y_max
            self.vy = 0
        """
        # move all our docked Sprites along with us
        for docked_sprite in self.docked_sprites:
            docked_sprite.move(x, y)

    def dock_to(self, mother_ship):
        """
        a sprite lands on an elevator -> couple the elevator to the sprite so that when the elevator moves, the sprite moves along with it
        - only possible to dock to "default" objects

        :param Sprite mother_ship: the Sprite to dock to (Sprite needs to have a dockable component)
        """
        prev = self.is_docked()
        obj = self.game_object
        if mother_ship.type & Sprite.get_type("default"):
            self.docking_state = Dockable.DEFINITELY_DOCKED
            if prev:
                self.docking_state |= Dockable.PREVIOUSLY_DOCKED
            self.docked_to = mother_ship
            if hasattr(mother_ship, "docked_objects"):
                mother_ship.docked_objects[obj.id] = self

    def undock(self):
        """
        undocks itself from the mothership
        """
        obj = self.game_object
        prev = self.is_docked()
        self.docking_state = Dockable.DEFINITELY_NOT_DOCKED
        if prev:
            self.docking_state |= Dockable.PREVIOUSLY_DOCKED
        # remove docked obj from mothership docked-obj-list
        if self.docked_to and "dockable" in self.docked_to.components:
            del prev.components["dockable"].docked_sprites[obj.id]
            self.docked_to = None

    def to_determine(self):
        """
        changes our docking state to be undetermined (saves the current state as PREVIOUS flag)
        """
        prev = self.is_docked()
        self.docking_state = Dockable.TO_BE_DETERMINED
        if prev:
            self.docking_state |= Dockable.PREVIOUSLY_DOCKED

    def is_docked(self):
        """
        returns True if the current state is definitely docked OR (to-be-determined AND previous state was docked)

        :return: most-likely docking state
        :rtype: bool
        """
        return self.docking_state & Dockable.DEFINITELY_DOCKED or \
               (self.docking_state & Dockable.TO_BE_DETERMINED and self.docking_state & Dockable.PREVIOUSLY_DOCKED)


class PhysicsComponent(Component, metaclass=ABCMeta):
    """
    defines an abstract generic physics component that can be added to agents (or enemies) to behave in the world
    - GameObject's that own this Comonent may have a Brain component as well in order to steer behavior of the agent in `tick`
    - needs to override `tick` and `collision`
    """

    def __init__(self, name: str):
        super().__init__(name)
        self.game_obj_cmp_brain = None  # the GameObject's Brain component (used by Physics for steering and action control within `tick` method)

    # probably needs to be extended further by child classes
    def added(self):
        obj = self.game_object

        obj.on_event("pre_tick", self, "tick")  # run this component's tick function after GameObject's one (so we can react to the GameObject's move)
        obj.on_event("collision", self, "collision")  # handle collisions

        self.game_obj_cmp_brain = self.game_object.components.get("brain", None)
        # if there is a 'brain' component in the GameObject it has to be of type Brain
        if self.game_obj_cmp_brain:
            assert isinstance(self.game_obj_cmp_brain, Brain), "ERROR: GameObject's `brain` Component is not of type Brain!"

    # may determine x/y-speeds and movements of the GameObject (gravity, etc..)
    @abstractmethod
    def tick(self, game_loop: GameLoop):
        pass

    @abstractmethod
    def collision(self, col: Collision):
        """
        this is the resolver for a Collision that happened between two Sprites under this PhysicsComponent

        :param Collision col: the Collision object describing the collision that already happened between two sprites
        """
        pass

    @staticmethod
    def tile_layer_physics_collision_postprocessor(col: Collision) -> Union[None, Collision, Tuple[Collision]]:
        """
        determines what a Layer should do once it detects a collision via its `collide` method
        Args:
            col (Collision): the collision object detected by the Layer
        Returns: col (Collision)
        """
        # by default, just set collided to True and return the collision as is
        # - specific Physics behavior will have to be implemented by the different physics Components
        col.is_collided = True

        return col


class TopDownPhysics(PhysicsComponent):
    """
    defines "top-down-2D"-step physics (agent can move in any of the 4 directions using any step-size (smooth walking))
    - to be addable to any character (player or enemy)
    """

    def __init__(self, name: str):
        super().__init__(name)
        # velocities/physics stuff
        self.vx = 0
        self.vy = 0
        self.run_acceleration = 300  # running acceleration
        self.v_max = 150  # max run-speed
        self.stops_abruptly_on_direction_change = True  # Vikings stop abruptly when running in one direction, then the other direction is pressed

        # environment stuff (TODO: where to get Level dimensions from?)
        self.x_min = 0  # the minimum/maximum allowed positions
        self.y_min = 0
        self.x_max = 9000
        self.y_max = 9000

        self.touching = 0  # bitmap with those bits set that the entity is currently touching (colliding with)
        # TODO: what does at_exit mean in terms of an MDP/RL-setting?
        self.at_exit = False

        self.game_obj_cmp_brain = None  # the GameObject's Brain component (used by Physics for steering and action control)

    def added(self):
        obj = self.game_object
        self.x_max -= obj.rect.width
        self.y_max -= obj.rect.height

        obj.on_event("pre_tick", self, "tick", register=True)  # run this component's tick function after GameObject's one (so we can react to the GameObject's move)
        obj.on_event("collision", self, "collision", register=True)  # handle collisions
        obj.register_event("bump.top", "bump.bottom", "bump.left", "bump.right")  # we will trigger these as well -> register them

        self.game_obj_cmp_brain = self.game_object.components.get("brain", None)
        assert not self.game_obj_cmp_brain or isinstance(self.game_obj_cmp_brain, Brain), "ERROR: GameObject's `brain` Component is not of type Brain!"

    # determines x/y-speeds and moves the GameObject
    def tick(self, game_loop: GameLoop):
        dt = game_loop.dt
        dt_step = dt
        ax = 0
        ay = 0
        obj = self.game_object
        stage = obj.stage

        # entity has a brain component
        if self.game_obj_cmp_brain:
            # determine x speed
            # -----------------
            # user is trying to move left or right (or both?)
            if self.game_obj_cmp_brain.commands["left"]:
                # only left is pressed
                if not self.game_obj_cmp_brain.commands["right"]:
                    if self.stops_abruptly_on_direction_change and self.vx > 0:
                        self.vx = 0  # stop first if still walking in other direction
                    ax = -self.run_acceleration  # accelerate left
                    obj.flip['x'] = True  # mirror sprite
                # user presses both keys (left and right) -> just stop
                else:
                    self.vx = 0
            # only right is pressed
            elif self.game_obj_cmp_brain.commands["right"]:
                if self.stops_abruptly_on_direction_change and self.vx < 0:
                    self.vx = 0  # stop first if still walking in other direction
                ax = self.run_acceleration  # accelerate right
                obj.flip['x'] = False
            # stop immediately (vx=0; don't accelerate negatively)
            else:
                self.vx = 0

            # determine y speed
            # -----------------
            # user is trying to move up or down (or both?)
            if self.game_obj_cmp_brain.commands["up"]:
                # only up is pressed
                if not self.game_obj_cmp_brain.commands["down"]:
                    if self.stops_abruptly_on_direction_change and self.vy > 0:
                        self.vy = 0  # stop first if still walking in other direction
                    ay = -self.run_acceleration  # accelerate up
                # user presses both keys (up and down) -> just stop
                else:
                    self.vy = 0
            # only down is pressed
            elif self.game_obj_cmp_brain.commands["down"]:
                if self.stops_abruptly_on_direction_change and self.vy < 0:
                    self.vy = 0  # stop first if still walking in other direction
                ay = self.run_acceleration  # accelerate down
            # stop immediately (vy=0; don't accelerate negatively)
            else:
                self.vy = 0

        # entity has no steering unit (speed = 0)
        else:
            self.vx = 0
            self.vy = 0

        # TODO: check the entity's magnitude of vx and vy,
        # reduce the max dt_step if necessary to prevent skipping through objects.
        while dt_step > 0:
            dt = min(1 / 30, dt_step)

            # update x/y-velocity based on acceleration
            self.vx += ax * dt
            if abs(self.vx) > self.v_max:
                self.vx = -self.v_max if self.vx < 0 else self.v_max
            self.vy += ay * dt
            if abs(self.vy) > self.v_max:
                self.vy = -self.v_max if self.vy < 0 else self.v_max

            # reset all touch flags before doing all the collision analysis
            self.at_exit = False

            # first move in x-direction and solve x-collisions
            if self.vx != 0.0:
                obj.move(self.vx * dt, 0.0)
                if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_BEFORE_COLLISION_DETECTION:
                    obj.render(game_loop.display)
                    game_loop.display.debug_refresh()

                # then do the normal collision layer(s)
                for layer in stage.tiled_layers_to_collide:
                    if layer.type & Sprite.get_type("default"):
                        layer.collide(obj, 'x', self.vx)

            # then move in y-direction and solve y-collisions
            if self.vy != 0.0:
                obj.move(0.0, self.vy * dt)
                if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_BEFORE_COLLISION_DETECTION:
                    obj.render(game_loop.display)
                    game_loop.display.debug_refresh()

                # then do the normal collision layer(s)
                for layer in stage.tiled_layers_to_collide:
                    if layer.type & Sprite.get_type("default"):
                        layer.collide(obj, 'y', self.vy)

            dt_step -= dt

    def collision(self, col: Collision):
        obj = self.game_object
        assert obj is col.sprite1, "ERROR: game_object ({}) of physics component is not identical with passed in col.sprite1 ({})!".format(obj, col.sprite1)

        assert hasattr(col, "sprite2"), "ERROR: no sprite2 in col-object!"
        other_obj = col.sprite2

        # collided with a tile (from a layer)
        if isinstance(other_obj, TileSprite):
            tile_props = other_obj.tile_props
            # colliding with an exit
            # TODO: what does exit mean? in a RL setting? end of episode?
            if tile_props.get("exit"):
                self.at_exit = True
                obj.stage.options["screen_obj"].trigger_event("reached_exit", obj)  # let the level know
                return

        # move away from the collision (back to where we were before)
        obj.rect.x -= col.separate[0]
        obj.rect.y -= col.separate[1]

        # bottom collision
        if col.normal_y < -0.3:
            if self.vy > 0:
                self.vy = 0
            obj.trigger_event("bump.bottom", col)

        # top collision
        if col.normal_y > 0.3:
            if self.vy < 0:
                self.vy = 0
            obj.trigger_event("bump.top", col)

        # left/right collisions
        if abs(col.normal_x) > 0.3:
            # we hit a fixed wall
            if self.vx * col.normal_x < 0:  # if normalX < 0 -> vx is > 0 -> set to 0; if normalX > 0 -> vx is < 0 -> set to 0
                self.vx = 0
                obj.trigger_event("bump." + ("right" if col.normal_x < 0 else "left"), col)


class PlatformerPhysics(PhysicsComponent):
    """
    defines "The Lost Vikings"-like game physics
    - to be addable to any character (player or enemy)
    """

    def __init__(self, name: str):
        super().__init__(name)
        self.vx = 0  # velocities
        self.vy = 0

        # physics
        self.run_acceleration = 300  # running acceleration
        self.vx_max = 150  # max run-speed
        self.max_fall_speed = 550  # maximum fall speed
        self.gravity = True  # set to False to make this guy not be subject to y-gravity (e.g. while locked into ladder)
        self.gravity_y = 9.8 * 100
        self.jump_speed = 330  # jump-power
        self.disable_jump = False  # if True: disable jumping so we don't keep jumping when action1 key keeps being pressed
        self.can_jump = True  # set to False to make this guy not be able to jump
        self.stops_abruptly_on_direction_change = True  # Vikings stop abruptly when running in one direction, then the other direction is pressed
        self.climb_speed = 70  # speed at which player can climb
        self.is_pushable = False  # set to True if a collision with the entity causes the entity to move a little
        self.is_heavy = False  # set to True if this object should squeeze other objects that are below it and cannot move away
        self.squeeze_speed = 0  # set to a value > 0 to define the squeezeSpeed at which this object gets squeezed by heavy objects
        # (objects with is_heavy == True)

        # environment stuff (TODO: where to get Level dimensions from?)
        self.x_min = 0  # the minimum/maximum allowed positions
        self.y_min = 0
        self.x_max = 9000
        self.y_max = 9000

        # self.touching = 0  # bitmap with those bits set that the entity is currently touching (colliding with)
        self.at_exit = False
        self.at_wall = False
        self.slope_up_down = 0  # 1 if on up-slope, -1 if on down-slope
        self.on_ladder = 0  # 0 if GameObject is not locked into a ladder; y-pos of obj, if obj is currently locked into a ladder (in climbing position)
        self.which_ladder = None  # holds the ladder Sprite, if player is currently touching a ladder sprite, otherwise: 0
        self.climb_frame_value = 0  # int([climb_frame_value]) determines the frame to use to display climbing position

        self.game_obj_cmp_brain = None  # the GameObject's Brain component (used by Physics for steering and action control)

    def added(self):
        obj = self.game_object
        self.x_max -= obj.rect.width
        self.y_max -= obj.rect.height

        obj.on_event("pre_tick", self, "tick")  # run this component's tick function after GameObject's one (so we can react to the GameObject's move)
        obj.on_event("collision", self, "collision")  # handle collisions

        # add the Dockable Component to our GameObject (we need it this for us to work properly)
        obj.add_component(Dockable("dockable"))

        self.game_obj_cmp_brain = self.game_object.components.get("brain")
        assert isinstance(self.game_obj_cmp_brain, Brain), "ERROR: GameObject's `brain` Component is not of type Brain!"

    def lock_ladder(self):
        """
        locks the GameObject into a ladder
        """
        obj = self.game_object
        self.on_ladder = obj.rect.y
        # switch off gravity
        self.gravity = False
        # lock obj to center of ladder (which_ladder is always set to the one we are touching right now)
        obj.rect.x = self.which_ladder.rect.x
        self.vx = 0  # stop x-movement

    def unlock_ladder(self):
        """
        frees the GameObject from a ladder
        """
        self.on_ladder = 0
        self.gravity = True

    def tick(self, game_loop: GameLoop):
        """
        determines x/y-speeds and moves the GameObject

        :param GameLoop game_loop: the GameLoop that's currently playing
        """
        dt = game_loop.dt
        dt_step = dt
        ax = 0
        obj = self.game_object
        dockable = obj.components["dockable"]
        stage = obj.stage

        # entity has a brain component
        if self.game_obj_cmp_brain:
            # determine x speed
            # -----------------
            # user is trying to move left or right (or both?)
            if self.game_obj_cmp_brain.commands["left"]:
                # only left is pressed
                if not self.game_obj_cmp_brain.commands["right"]:
                    if self.stops_abruptly_on_direction_change and self.vx > 0:
                        self.vx = 0  # stop first if still walking in other direction
                    ax = -(self.run_acceleration or 999000000000)  # accelerate left
                    obj.flip['x'] = True  # mirror sprite

                    # user is pressing left or right -> leave on_ladder state
                    if self.on_ladder > 0:
                        self.unlock_ladder()
                # user presses both keys (left and right) -> just stop
                else:
                    self.vx = 0

            # only right is pressed
            elif self.game_obj_cmp_brain.commands["right"]:
                if self.stops_abruptly_on_direction_change and self.vx < 0:
                    self.vx = 0  # stop first if still walking in other direction
                ax = self.run_acceleration or 999000000000  # accelerate right
                obj.flip['x'] = False

                # user is pressing left or right -> leave on_ladder state
                if self.on_ladder > 0:
                    self.unlock_ladder()
            # stop immediately (vx=0; don't accelerate negatively)
            else:
                # ax = 0; // already initalized to 0
                self.vx = 0

            # determine y speed
            # -----------------
            if self.on_ladder > 0:
                self.vy = 0
            # user is pressing 'up' (ladder?)
            if self.game_obj_cmp_brain.commands["up"]:
                # obj is currently on ladder
                if self.on_ladder > 0:
                    # reached the top of the ladder -> lock out of ladder
                    if obj.rect.y <= self.which_ladder.ytop - obj.rect.height / 2:
                        self.unlock_ladder()
                    else:
                        self.vy = -self.climb_speed
                # player locks into ladder
                elif (self.which_ladder and obj.rect.y <= self.which_ladder.rect.top - obj.rect.height / 2 and \
                                  obj.rect.y > self.which_ladder.rect.bottom - obj.rect.height / 2):
                    self.lock_ladder()
            # user is pressing only 'down' (ladder?)
            elif self.game_obj_cmp_brain.commands["down"]:
                if self.on_ladder > 0:
                    # we reached the bottom of the ladder -> lock out of ladder
                    if obj.rect.y >= self.which_ladder.rect.bottom - obj.rect.height / 2:
                        self.unlock_ladder()
                    # move down
                    else:
                        self.vy = self.climb_speed
                elif self.which_ladder and obj.rect.y < self.which_ladder.rect.bottom - obj.rect.height / 2 and dockable.is_docked():
                    self.lock_ladder()
            # jumping?
            elif self.can_jump:
                jump = self.game_obj_cmp_brain.commands.get("space", False)
                if not jump:
                    self.disable_jump = False
                else:
                    if (self.on_ladder > 0 or dockable.is_docked()) and not self.disable_jump:
                        if self.on_ladder > 0:
                            self.unlock_ladder()
                        self.vy = -self.jump_speed
                        dockable.undock()
                    self.disable_jump = True
        # entity has no steering unit (x-speed = 0)
        else:
            self.vx = 0

        # TODO: check the entity's magnitude of vx and vy,
        # reduce the max dt_step if necessary to prevent skipping through objects.
        while dt_step > 0:
            dt = min(1 / 30, dt_step)

            # update x/y-velocity based on acceleration
            self.vx += ax * dt  # TODO: x-gravity? + self.(p.gravityX == void 0 ? Q.gravityX : p.gravityX) * dt * p.gravity;
            if abs(self.vx) > self.vx_max:
                self.vx = -self.vx_max if self.vx < 0 else self.vx_max
            if self.gravity:
                self.vy += self.gravity_y * dt

            # if player stands on up-slope and x-speed is negative (or down-slope and x-speed is positive)
            # -> make y-speed as high as x-speed so we don't fly off the slope
            if self.slope_up_down != 0 and dockable.is_docked():
                if self.slope_up_down == 1 and self.vy < -self.vx:
                    self.vy = -self.vx
                elif self.slope_up_down == -1 and self.vy < self.vx:
                    self.vy = self.vx
            if abs(self.vy) > self.max_fall_speed:
                self.vy = -self.max_fall_speed if self.vy < 0 else self.max_fall_speed

            # reset all touch flags before doing all the collision analysis
            if self.vx != 0.0 or self.vy != 0.0:
                self.slope_up_down = 0
                if self.on_ladder == 0:
                    self.which_ladder = None
                self.at_wall = False
                self.at_exit = False
                # store previous state before becoming undetermined
                dockable.to_determine()

            # first move in x-direction and solve x-collisions
            if self.vx != 0.0:
                obj.move(self.vx * dt, 0.0)
                if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_BEFORE_COLLISION_DETECTION:
                    obj.render(game_loop.display)
                    game_loop.display.debug_refresh()

                # then do the 'default' collision layer(s)
                for layer in stage.tiled_layers_to_collide:
                    if layer.type & Sprite.get_type("default"):
                        layer.collide(obj, "x", self.vx)

            # then move in y-direction and solve y-collisions
            if self.vy != 0.0:
                obj.move(0.0, self.vy * dt)
                if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_BEFORE_COLLISION_DETECTION:
                    obj.render(game_loop.display)
                    game_loop.display.debug_refresh()

                # then do the 'default' collision layer(s)
                for layer in stage.tiled_layers_to_collide:
                    if layer.type & Sprite.get_type("default"):
                        layer.collide(obj, "y", self.vy)

            # finally: check for touch collisions first (e.g. ladders)
            for layer in stage.tiled_layers_to_collide:
                if layer.type & Sprite.get_type("touch"):
                    layer.collide(obj)
            # TODO: solve collisions with other objects

            dt_step -= dt

    def collision(self, col: PlatformerCollision):
        """
        gets called (via event trigger 'collision' (setup when this component is added to our GameObject)) when a collision is detected (e.g. by a layer)

        :param PlatformerCollision col: the collision object of the detected collision (the first sprite in that Collision object must be our GameObject)
        """
        obj = self.game_object
        assert obj is col.sprite1, "ERROR: game_object ({}) of physics component is not identical with passed in col.sprite1 ({})!".format(obj, col.sprite1)
        dockable = obj.components["dockable"]

        assert hasattr(col, "sprite2"), "ERROR: no sprite2 in col-object!"
        other_obj = col.sprite2
        other_obj_physics = other_obj.components.get("physics", None)

        # getting hit by a particle (Arrow, ScorpionShot, Fireball, etc..)
        if other_obj.type & Sprite.get_type("particle"):
            # shooter (this) is colliding with own shot -> ignore
            if obj is not other_obj.shooter:
                obj.trigger_event("hit.particle", col)
                # for particles, force the reciprocal collisions (otherwise, the character that got shot could be gone (dead) before any collisions on the
                # particle could get triggered (-> e.g. arrow will fly through a dying enemy without ever actually touching the enemy))
                other_obj.trigger_event("hit", obj)
            return

        # colliding with a ladder
        if other_obj.type & Sprite.get_type("ladder"):
            # set which_ladder to the ladder's props
            self.which_ladder = other_obj
            # if we are not locked into ladder AND on very top of the ladder, collide normally (don't fall through ladder's top)
            if (self.on_ladder > 0 or col.normal_x != 0  # don't x-collide with ladder
                    or col.normal_y > 0):  # don't collide with bottom of ladder
                return

        # a collision layer
        if isinstance(other_obj, TileSprite):
            tile_props = other_obj.tile_props
            # quicksand or water
            if tile_props.get("liquid"):
                obj.trigger_event("hit.liquid_ground", tile_props["liquid"])
                return
            # colliding with an exit
            elif tile_props.get("exit"):
                self.at_exit = True
                obj.stage.screen.trigger_event("reached_exit", obj)  # let the level know
                return
            # check for slope collision (adjust y if necessary)
            elif col.slope:
                obj.move(0, col.slope_y_pull, True)  # TODO: check top whether we can move there (there could be a block)!!)) {
                dockable.dock_to(other_obj)  # dock to collision layer (only if the pull )
                self.slope_up_down = col.slope_up_down
                # set vy to 0.0 (we are docked to the ground -> if this is x-direction: no y-moves/checks necessary anymore)
                self.vy = 0.0
                return

        # normal collision
        col.impact = 0.0

        impact_x = abs(self.vx)
        impact_y = abs(self.vy)

        # move away from the collision (back to where we were before)
        x_orig = obj.rect.x
        y_orig = obj.rect.y
        obj.rect.x -= col.separate[0]
        obj.rect.y -= col.separate[1]

        # bottom collision
        if col.normal_y < -0.3:
            # a heavy object hit the ground -> rock the stage
            if self.is_heavy and not dockable.is_docked() and other_obj.type & Sprite.get_type("default"):
                obj.stage.shake()

            other_obj_dockable = other_obj.components.get("dockable", None)

            # squeezing something
            if self.vy > 0 and isinstance(other_obj_physics, PlatformerPhysics) and self.is_heavy and other_obj_physics.squeeze_speed > 0 and \
                    other_obj_dockable and other_obj_dockable.is_docked():

                # adjust the collision separation to the new squeezeSpeed
                if self.vy > other_obj_physics.squeeze_speed:
                    obj.rect.y = y_orig + col.separate[1] * (other_obj_physics.squeeze_speed / self.vy)
                # otherwise, just undo the separation
                else:
                    obj.rect.y += col.separate[1]

                self.vy = other_obj_physics.squeeze_speed
                other_obj.trigger_event("squeezed.top", obj)

            # normal bottom collision
            else:
                if self.vy > 0:
                    self.vy = 0
                col.impact = impact_y
                dockable.dock_to(other_obj)  # dock to bottom object (collision layer or MovableRock, etc..)
                obj.trigger_event("bump.bottom", col)

        # top collision
        if col.normal_y > 0.3:
            if self.vy < 0:
                self.vy = 0
            col.impact = impact_y
            obj.trigger_event("bump.top", col)

        # left/right collisions
        if abs(col.normal_x) > 0.3:
            col.impact = impact_x
            bump_wall = False
            # we hit a pushable object -> check if it can move
            if other_obj_physics and hasattr(other_obj_physics, "is_pushable") and other_obj_physics.is_pushable and dockable.is_docked():
                self.push_an_object(obj, col)
                bump_wall = True
            # we hit a fixed wall (non-pushable)
            elif self.vx * col.normal_x < 0:  # if normalX < 0 -> p.vx is > 0 -> set to 0; if normalX > 0 -> p.vx is < 0 -> set to 0
                self.vx = 0
                bump_wall = True

            if bump_wall:
                if other_obj.type & Sprite.get_type("default"):
                    self.at_wall = True
                obj.trigger_event("bump." + ("right" if col.normal_x < 0 else "left"), col)

    def push_an_object(self, pusher, col):
        pushee = col.sprite2  # correct? or does it need to be sprite1?
        # TODO: what if normal_x is 1/-1 BUT: impact_x is 0 (yes, this can happen!!)
        # for now: don't push, then
        if col.impact > 0:
            move_x = col.separate[0] * abs(pushee.vx_max / col.impact)
            # console.log("pushing Object: move_x="+move_x);
            # do a locate on the other side of the - already moved - pushable object
            # var testcol = pusher.stage.locate(pushee_p.x+move_x+(pushee_p.cx+1)*(p.flip ==   'x' ? -1 : 1), pushee_p.y, (Q._SPRITE_DEFAULT | Q._SPRITE_FRIENDLY | Q._SPRITE_ENEMY));
            # if (testcol && (! (testcol.tileprops && testcol.tileprops.slope))) {
            #	p.vx = 0; // don't move player, don't move pushable object
            # }
            # else {
            # move obj (plus all its docked objects) and move pusher along
            pusher.move(move_x, 0)
            pushee.move(move_x, 0)
            self.vx = pushee.vx_max * (-1 if self.game_object.flip['x'] else 1)
        else:
            self.vx = 0

    @staticmethod
    def tile_layer_physics_collision_postprocessor(col):
        """
        this postprocessor takes a detected collision and does slope checks on it
        - it them stores the results in the given PlatformerCollision object for further handling by the physics Component

        :param PlatformerCollision col: the collision object detected by the Layer
        :return: a post-processed collision object (adds slope-related calculations to the Collision object)
        :rtype: PlatformerCollision
        """

        assert col.direction in ["x", "y"], "ERROR: col.direction must be either 'x' or 'y'!"

        sprite = col.sprite1  # this must have a dockable
        assert "dockable" in sprite.components and isinstance(sprite.components["dockable"], Dockable), \
            "ERROR: cannot postprocess collision without the sprite having a Dockable Component!"
        tile = col.sprite2  # this must be a TileSprite
        assert isinstance(tile, TileSprite), "ERROR: sprite2 in PlatformerCollision passed to handler must be of type TileSprite (is actually of type {})!".\
            format(type(tile).__name__)

        # check for slopes
        # approach similar to: Rodrigo Monteiro (http://higherorderfun.com/blog/2012/05/20/the-guide-to-implementing-2d-platformers/)
        # reset slope/collision flags
        col.is_collided = True
        col.slope = False
        col.slope_up_down = 0
        col.slope_y_pull = 0  # amount of y that Sprite has to move up (negative) or down (positive)

        # calculate y-pull based on pixels we are "in" the slope
        # TODO: for now: only treat 45-degree
        slope = tile.tile_props.get("slope", 0)  # -3, -2, -1, 1, 2, 3: negative=down, positive=up (1==45 degree slope, 3=15 degree slope)
        if slope != 0:
            # calculate x-amount of intrusion by the sprite into the tile (this is always positive and between 0 and tile_w)
            if col.direction == "x":
                # moving up hill
                if col.direction_veloc > 0.0 and slope > 0:
                    x_in = sprite.rect.right - tile.rect.left
                # moving up hill
                elif col.direction_veloc < 0.0 and slope < 0:
                    x_in = tile.rect.right - sprite.rect.left
                # moving down hill
                else:
                    if col.direction_veloc > 0.0:
                        x_in = tile.rect.right - sprite.rect.left
                    else:
                        x_in = sprite.rect.right - tile.rect.left
            # y-direction (we are not moving left or right) -> calc x_in depending on up or down slope
            else:
                if slope > 0:
                    x_in = sprite.rect.right - tile.rect.left
                else:
                    x_in = tile.rect.right - sprite.rect.left

            # clamp x_in to tile_w
            x_in = min(x_in, tile.tile_w)

            # the wanted y-position for the bottom of the sprite (iff we are docked to the ground)
            y_grounded = tile.rect.bottom - x_in
            slope_y_pull = y_grounded - sprite.rect.bottom

            # we are in the air -> only apply y-pull if the y-pull is negative (up push)
            # - otherwise -> keep falling (no collision)
            if not sprite.components["dockable"].is_docked() and slope_y_pull > 0:
                col.is_collided = False  # this will cause the detected collision (with the tile rect) to be ignored for now
            # we are on the slope (not falling or having fallen into the slope already) -> pull us up or down
            else:
                col.slope = slope
                col.slope_up_down = math.copysign(1, slope)
                col.slope_y_pull = y_grounded - sprite.rect.bottom

        return col


class Viewport(Component):
    """
    A viewport is a component that can be added to a Stage to help that Stage render the scene depending on scrolling/obj_to_follow certain GameObjects
    - any GameObject with offset_x/y fields is supported, the Viewport will set these offsets to the Viewports x/y values
      before each render call
    """

    def __init__(self, display: Display):
        super().__init__("viewport")  # fix name to 'viewport' (only one viewport per Stage)

        self.display = display  # the pygame display (Surface) to draw on; so far we only need it to get the display's dimensions

        # top/left corner (world coordinates) of the Viewport window
        # - will be used as offset_x/y for the Display
        self.x = 0
        self.y = 0

        # offsets used for shaking the Viewport
        self.shake_x = 0
        self.shake_y = 0

        self.scale = 1.0

        self.directions = {}
        self.obj_to_follow = None
        self.max_speed = 10
        self.bounding_box = None

    def added(self):
        self.game_object.on_event("pre_render", self, "pre_render")

        self.extend(self.follow_object_with_viewport)
        self.extend(self.unfollow_object_with_viewport)
        self.extend(self.center_on_object_with_viewport)
        self.extend(self.move_to_with_viewport)

    # EXTENSION methods (take self as well as GameObject as first two params)

    def follow_object_with_viewport(self, game_object, obj_to_follow, directions=None, bounding_box=None, max_speed=float("inf")):
        """
        makes the viewport follow a GameObject (obj_to_follow)

        :param GameObject game_object: our game_object (that has `self` as component)
        :param GameObject obj_to_follow: the GameObject that we should follow
        :param dict directions: dict with 'x' and 'y' set to either True or False depending on whether we follow only in x direction or y or both
        :param dict bounding_box: should contain min_x, max_x, min_y, max_y so we know the boundaries of the camera
        :param float max_speed: the max speed of the camera
        """
        game_object.off_event("post_tick", self, "follow")
        if not directions:
            directions = {"x": True, "y": True}

        # this should be the level dimensions to avoid over-scrolling by the camera
        # - if we don't have a Level (just a Screen), use the display's size
        if not bounding_box:  # get a default bounding box
            # TODO: this is very specific to us having always a Stage (with options['screen_obj']) as our owning game_object
            screen = self.game_object.options["screen_obj"]
            w = screen.width if hasattr(screen, "width") else self.display.surface.get_width()
            h = screen.height if hasattr(screen, "height") else self.display.surface.get_height()
            bounding_box = {"min_x": 0, "min_y": 0, "max_x": w, "max_y": h}

        self.directions = directions
        self.obj_to_follow = obj_to_follow
        self.bounding_box = bounding_box
        self.max_speed = max_speed
        game_object.on_event("post_tick", self, "follow")
        self.follow(False if max_speed > 0.0 else True)

    def unfollow_object_with_viewport(self, game_object):
        """
        stops following

        :param GameObject game_object: our game_object (that has `self` as component)
        """
        game_object.off_event("post_tick", self, "follow")
        self.obj_to_follow = None

    def center_on_object_with_viewport(self, game_object, x, y):
        self.center_on(x, y)

    def move_to_with_viewport(self, game_object, x, y):
        return self.move_to(x, y)

    # END: EXTENSION METHODS

    """shake: function() {
        setTimeout(function(vp) {vp.shakeY = 1;}, 30, this.viewport);
        setTimeout(function(vp) {vp.shakeY = -1;}, 60, this.viewport);
        setTimeout(function(vp) {vp.shakeY = 1;}, 90, this.viewport);
        setTimeout(function(vp) {vp.shakeY = -1;}, 120, this.viewport);
        setTimeout(function(vp) {vp.shakeY = 1;}, 150, this.viewport);
        setTimeout(function(vp) {vp.shakeY = -1;}, 180, this.viewport);
        setTimeout(function(vp) {vp.shakeY = 1;}, 210, this.viewport);
        setTimeout(function(vp) {vp.shakeY = 0;}, 240, this.viewport);
      },
    },
    """

    def follow(self, first: bool):
        follow_x = self.directions["x"](self.obj_to_follow) if callable(self.directions["x"]) else  self.directions["x"]
        follow_y = self.directions["y"](self.obj_to_follow) if callable(self.directions["y"]) else  self.directions["y"]

        func = self.center_on if first else self.soft_center_on
        func(self.obj_to_follow.rect.x + self.obj_to_follow.rect.width / 2 - self.offset_x if follow_x else None,
             self.obj_to_follow.rect.y + self.obj_to_follow.rect.height / 2 - self.offset_y if follow_y else None)

    def offset(self, x, y):
        self.offset_x = x
        self.offset_y = y

    def soft_center_on(self, x: Union[int, None] = None, y: Union[int, None] = None):
        if x:
            dx = (x - self.display.surface.get_width() / 2 / self.scale - self.x) / 3  # //, this.followMaxSpeed);
            if abs(dx) > self.max_speed:
                dx = math.copysign(self.max_speed, dx)

            if self.bounding_box:
                if (self.x + dx) < self.bounding_box.min_x:
                    self.x = self.bounding_box.min_x / self.scale
                elif self.x + dx > (self.bounding_box.max_x - self.display.surface.get_width()) / self.scale:
                    self.x = (self.bounding_box.max_x - self.display.surface.get_width()) / self.scale
                else:
                    self.x += dx
            else:
                self.x += dx

        if y:
            dy = (y - self.display.surface.get_height() / 2 / self.scale - self.y) / 3
            if abs(dy) > self.max_speed:
                dy = math.copysign(self.max_speed, dy)
            if self.bounding_box:
                if self.y + dy < self.bounding_box.min_y:
                    self.y = self.bounding_box.min_y / self.scale
                elif self.y + dy > (self.bounding_box.max_y - self.display.surface.get_height()) / self.scale:
                    self.y = (self.bounding_box.max_y - self.display.surface.get_height()) / self.scale
                else:
                    self.y += dy
            else:
                self.y += dy

    def center_on(self, x, y):
        if x:
            self.x = x - self.display.surface.get_width() / 2 / self.scale
        if y:
            self.y = y - self.display.surface.get_height() / 2 / self.scale

    def move_to(self, x, y):
        if x:
            self.x = x
        if y:
            self.y = y
        return self.game_object  # ?? why

    def pre_render(self, display: Display):
        # simply set the offset of our Display
        self.display.offsets[0] = self.x
        self.display.offsets[1] = self.y


class Screen(EventObject, metaclass=ABCMeta):
    """
    a screen object has a play and a done method that need to be implemented
    - the play method stages a scene
    - the done method can do some cleanup
    """

    def __init__(self, name: str = "start", **kwargs):
        super().__init__()
        self.name = name
        self.id = kwargs.get("id", 0)

        # handle keyboard inputs
        self.keyboard_inputs = kwargs.get("keyboard_inputs", KeyboardInputs([]))
        # our Display object
        self.display = kwargs.get("display", None)
        self.max_fps = kwargs.get("max_fps", 60)

    @abstractmethod
    def play(self):
        pass

    @abstractmethod
    def done(self):
        pass


class SimpleScreen(Screen):
    """
    a simple Screen that has support for labels and sprites (still images) shown on the screen
    """
    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)
        self.sprites = (kwargs["sprites"] if "sprites" in kwargs else [])
        # labels example: {x: Q.width / 2, y: 220, w: 150, label: "NEW GAME", color: "white", align: "left", weight: "900", size: 22, family: "Fixedsys"},
        self.labels = (kwargs["labels"] if "labels" in kwargs else [])
        ## TODO: audio? self.audio = kwargs["audio"] if "audio" in kwargs else []

    @staticmethod
    def screen_func(stage: Stage):
        """
        defines this screen's Stage setup
        - stage functions are used to setup a Stage (before playing it)

        :param Stage stage: the Stage to be setup
        """
        # get the Screen object (instance) from the options
        screen = stage.options["screen_obj"]

        # insert labels to screen
        for label_def in screen.labels:
            # generate new Font object
            font = pygame.font.Font(None, label_def["size"])
            surf = font.render(label_def["text"], 1, pygame.Color(label_def["color"]))
            sprite = Sprite(label_def["x"], label_def["y"], surf)
            stage.add_sprite(sprite, "labels")

        # insert objects to screen
        for game_obj in screen.game_objects:
            stage.add_sprite(game_obj, "sprites")

    def play(self):
        """
        plays the screen
        """

        # start screen (will overwrite the old 0-stage (=main-stage))
        # - also, will give our keyboard-input setup to the new GameLoop object
        Stage.stage_screen(self, SimpleScreen.screen_func, stage=0,
                                options={"components": [Viewport(self.display)]})  # <-this options-object will be stored in stage.options

    def done(self):
        print("we're done!")


class Level(Screen, metaclass=ABCMeta):
    """
    a level class
    - adds tmx file support to the Screen
    - we can get lots of information from the tmx file to build the level in the play method
    """

    def __init__(self, name: str = "test", **kwargs):
        super().__init__(name, **kwargs)

        # TODO: warn here if keyboard_inputs is given (should be given in tmx file exclusively)

        self.tmx_file = kwargs.get("tmx_file", "data/" + name.lower() + ".tmx")
        # load in the world's tmx file
        self.tmx_obj = pytmx.load_pygame(self.tmx_file)
        self.width = self.tmx_obj.width * self.tmx_obj.tilewidth
        self.height = self.tmx_obj.height * self.tmx_obj.tileheight

        self.register_event("mastered", "aborted", "lost")

        # get keyboard_inputs directly from the pytmx object
        if not self.keyboard_inputs.keyboard_registry:
            descriptions = self.tmx_obj.properties.get("keyboard_inputs", "").split(",")
            #codes_and_descriptions = []
            #for d in descriptions.split(","):
            #    pygame_code = getattr(pygame, "K_" + d.upper(), None)
            #    assert pygame_code, "ERROR: in tmx file ({}) no pygame code associated with K_{}".format(self.tmx_file, d.upper())
            #    codes_and_descriptions.append([pygame_code, d])
            self.keyboard_inputs.update_keys(descriptions)

    # populates a Stage with this Level by going through the tmx file layer by layer and adding it
    # - unlike SimpleScreen, uses only the tmx file for adding things to the Stage
    @staticmethod
    def screen_func(stage):
        """
        sets up the Stage by adding all layers (one-by-one) from the tmx file to the Stage

        :param Stage stage:
        """
        assert isinstance(stage.screen, Level), "ERROR: screen property of a Stage that uses Level.screen_func to stage a Screen must be a Level object!"

        # force add the default physics functions to the Stage's options
        defaults(stage.options, {"components": [Viewport(stage.screen.display)],
                                 "tile_layer_physics_collision_detector": AABBCollision.collide,
                                 "tile_layer_physics_collision_postprocessor": PhysicsComponent.tile_layer_physics_collision_postprocessor
                                 })
        for layer in stage.screen.tmx_obj.layers:
            stage.add_tiled_layer(layer, stage.screen.tmx_obj)

    def play(self):
        """
        start level (stage the scene; will overwrite the old 0-stage (=main-stage))
        - the options-object below will be also stored in [Stage object].options
        - child Level classes only need to do these three things: a) stage a screen, b) register some possible events, c) play a new game loop
        """
        Stage.stage_screen(self, self.screen_func, 0)
        # activate level triggers
        self.on_event("agent_reached_exit", self, "done", register=True)
        # play a new GameLoop giving it some options
        GameLoop.play_a_loop(screen_obj=self)

    def done(self):
        Stage.get_stage().stop()

        # switch off keyboard
        self.keyboard_inputs.update_keys([])  # empty list -> no more keys


class Game(object):
    instantiated = False

    """
    An object that serves as a container for Screen and Level objects
    - manages displaying the screens (start screen, menus, etc..) and playable levels of the game
    - also keeps a Display object (and determines its size), which is used for rendering and displaying the game
    """

    def __init__(self, screens_and_levels, width: int = 0, height: int = 0, title: str = "spygame Demo!", max_fps: int = 60, debug_flags=DEBUG_NONE):
        """
        :param list screens_and_levels: a list of Screen and Level definitions. Each item is a dict with
        :param int width: the width of the screen in pixels (0 for auto)
        :param int height: the height of the screen in pixels (0 for auto)
        :param str title: the title of the game (will be displayed as the game Window caption)
        :param int max_fps: the max. number of frames in one second (could be less if Game runs slow, but never more)
        :param int debug_flags: a bitmap for setting different debug flags (see global variables DEBUG_...)
        """
        assert not Game.instantiated, "ERROR: can only create one {} object!".format(type(self).__name__)
        Game.instantiated = True

        # init the pygame module (if this did not already happen)
        pygame.init()

        self.screens_by_name = {}  # holds the Screen objects by key=level-name
        self.screens = []  # list of screens
        self.levels_by_name = {}  # holds the Level objects by key=level-name
        self.levels = []  # sorted list of levels

        self.max_fps = max_fps

        # try this: set debug flags globally
        global DEBUG_FLAGS
        DEBUG_FLAGS = debug_flags

        # create the Display object for the entire game: we pass it to all levels and screen objects
        self.display = Display(600, 400, title)  # use 600x400 for now (default); this will be reset to the largest Level dimensions further below

        # our levels (if any) determine the size of the display
        get_w_from_levels = True if width == 0 else False
        get_h_from_levels = True if height == 0 else False

        # initialize all screens and levels
        for i, screen_or_level in enumerate(screens_and_levels):
            name = screen_or_level.pop("name", "screen{:02d}".format(i))
            id_ = screen_or_level.pop("id", 0)
            keyboard_inputs = screen_or_level.pop("keyboard_inputs", KeyboardInputs([]))
            max_fps = screen_or_level.pop("max_fps", self.max_fps)

            # Screen class has to be given since Screen (as a default) would be abstract
            assert "class" in screen_or_level, "ERROR: Game object needs the 'class' property for all given Screens and Levels!"
            assert issubclass(screen_or_level["class"], Screen), "ERROR: Game object needs the 'class' property to be a subclass of Screen!"
            class_ = screen_or_level["class"]
            # only distinguish between Level and "regular" Screen
            if issubclass(class_, Level):
                level = class_(name, id=id_, display=self.display, keyboard_inputs=keyboard_inputs, max_fps=max_fps, **screen_or_level)
                self.levels_by_name[name] = level
                self.levels.append(level)
                # register events
                level.on_event("mastered", self, "level_mastered")
                level.on_event("aborted", self, "level_aborted")
                level.on_event("lost", self, "level_lost")
                # store level dimensions for display
                if get_w_from_levels and level.width > width:
                    width = level.width
                if get_h_from_levels and level.height > height:
                    height = level.height
            # a Screen
            else:
                screen = class_(name, id=id_, display=self.display, keyboard_inputs=keyboard_inputs, max_fps=max_fps, **screen_or_level)
                self.screens_by_name[name] = screen
                self.screens.append(screen)

        # now that we know all Level sizes, change the dims of the pygame.display if width and/or height were Level-dependent
        if (get_w_from_levels and width > 0) or (get_h_from_levels and height > 0):
            # static method
            self.display.change_dims(width, height)

    # returns the next level (if exists) as object
    # false if no next level
    def get_next_level(self, level):
        try:
            next_ = self.levels[(level if isinstance(level, int) else level.id) + 1]
        except IndexError:
            next_ = None
        return next_

    # a level has been successfully finished
    # load/play next one
    def level_mastered(self, level):
        next_ = self.get_next_level(level)
        if not next_:
            print("All done!! Congrats!!")

    # a level has been aborted
    def level_aborted(self, level):
        Stage.clear_stages()
        self.screens_by_name["start"].play()

    # a level has been lost (all characters died)
    def level_lost(self, level):
        self.level_aborted(level)  # for now: same as aborted level


class CollisionAlgorithm(object):
    """
    a static class that is used to store a collision algorithm
    """
    # the default collision objects
    # - can be overridden via the collide method
    default_collision_objects = (Collision(), Collision())

    @staticmethod
    @abstractmethod
    def collide(sprite1, sprite2, collision_objects=None):
        """
        solves a simple spatial collision problem for two Sprites (that have a rect property)
        - defaults to SAT collision between two objects
        - thanks to doc's at: http://www.sevenson.com.au/actionscript/sat/
        - TODO: handle angles on objects
        - TODO: handle velocities of sprites prior to collision to calculate correct normals

        :param Sprite sprite1: sprite 1
        :param Sprite sprite2: sprite 2 (the other sprite)
        :param Union[None, Tuple[Collision]] collision_objects: the two always-recycled returnable Collision instances (aside from None); if None,
        use our default ones
        :return: a Collision object with all details of the collision between the two Sprites (None if there is no collision)
        :rtype: Union[None, Collision]
        """
        pass


class AABBCollision(CollisionAlgorithm):
    """
    a simple axis-aligned bounding-box collision mechanism which only works on Pygame rects
    """

    @staticmethod
    def collide(sprite1, sprite2, collision_objects=None, direction='x', direction_veloc=1.0):
        # TODO: actually, we only need one collision object as we should always only resolve one object at a time

        # TODO: utilize direction veloc information to only return the smallest separation collision

        # use default CollisionObjects?
        if not collision_objects:
            collision_objects = AABBCollision.default_collision_objects

        ret = AABBCollision.try_collide(sprite1, sprite2, collision_objects[0], direction, direction_veloc)
        if not ret:
            return None

        if ret.magnitude == 0.0:
            return None
        ret.separate[0] = ret.distance * ret.normal_x
        ret.separate[1] = ret.distance * ret.normal_y

        return ret

    @staticmethod
    def try_collide(o1, o2, collision_obj, direction, direction_veloc):
        """
        does the actual AABB collision test

        :param Sprite o1: object 1
        :param Sprite o2: object 2
        :param Collision collision_obj: the collision object to be populated
        :param str direction: the direction in which we have to measure a collision (x or y)
        :param float direction_veloc: the velocity value in the given x- or y-direction
        :return: the populated Collision object
        :rtype: Collision
        """
        assert direction == 'x' or direction == 'y', "ERROR: parameter direction needs to be either 'x' or 'y'!"

        # reset the recycled collision object
        collision_obj.is_collided = False
        collision_obj.normal_x = 0.0
        collision_obj.normal_y = 0.0
        collision_obj.magnitude = 0.0
        collision_obj.direction = direction
        collision_obj.direction_veloc = direction_veloc

        # overlap?
        if o1.rect.right > o2.rect.left and o1.rect.left < o2.rect.right and o1.rect.bottom > o2.rect.top and o1.rect.top < o2.rect.bottom:
            collision_obj.sprite1 = o1
            collision_obj.sprite2 = o2
            collision_obj.is_collided = True
            if direction == 'x':
                if direction_veloc > 0:
                    collision_obj.distance = -(o1.rect.right - o2.rect.left)
                    collision_obj.normal_x = -1.0
                elif direction_veloc < 0:
                    collision_obj.distance = -(o2.rect.right - o1.rect.left)
                    collision_obj.normal_x = 1.0
            else:
                if direction_veloc > 0:
                    collision_obj.distance = -(o1.rect.bottom - o2.rect.top)
                    collision_obj.normal_y = -1.0
                elif direction_veloc < 0:
                    collision_obj.distance = -(o2.rect.bottom - o1.rect.top)
                    collision_obj.normal_y = 1.0

            # if flip:
            #    collision_obj.distance *= -1
            #    collision_obj.normal_x *= -1
            collision_obj.magnitude = abs(collision_obj.distance)

            ## take the smaller direction (x/y)
            # dist = -(o1.rect.bottom - o2.rect.top)
            # y_magnitude = abs(dist)
            # if y_magnitude < collision_obj.magnitude:
            #    collision_obj.magnitude = y_magnitude
            #    collision_obj.distance = dist
            #    collision_obj.normal_x = 0.0
            #    collision_obj.normal_y = -1.0
            #    if flip:
            #        collision_obj.distance *= -1
            #        collision_obj.normal_y *= -1

        # collision_obj.separate = [collision_obj.distance * collision_obj.normal_x, collision_obj.distance * collision_obj.normal_y]

        return collision_obj if collision_obj.is_collided else None


# TODO: SATCollisions are WIP
class SATCollision(CollisionAlgorithm):
    normal = [0.0, 0.0]

    @staticmethod
    def collide(sprite1, sprite2, collision_objects=None):
        # use default CollisionObjects?
        if not collision_objects:
            collision_objects = SATCollision.default_collision_objects

        # do AABB first for a likely early out
        # TODO: right now, we only have pygame.Rect anyway, so these are AABBs
        if (sprite1.rect.right < sprite2.rect.left or sprite1.rect.bottom < sprite2.rect.top or
                    sprite2.rect.right < sprite1.rect.left or sprite2.rect.right < sprite1.rect.left):
            return None

        test = SATCollision.try_collide(sprite1, sprite2, collision_objects[0], False)
        if not test:
            return None

        test = SATCollision.try_collide(sprite2, sprite1, collision_objects[1], True)
        if not test:
            return None

        ret = collision_objects[1] if collision_objects[1].magnitude < collision_objects[0].magnitude else collision_objects[0]

        if ret.magnitude == 0.0:
            return None
        ret.separate[0] = ret.distance * ret.normal_x
        ret.separate[1] = ret.distance * ret.normal_y

        return ret

    @staticmethod
    def calculate_normal(points, idx):
        pt1 = points[idx]
        pt2 = points[idx + 1] if idx < len(points) - 1 else points[0]

        SATCollision.normal[0] = -(pt2[1] - pt1[1])
        SATCollision.normal[1] = pt2[0] - pt1[0]

        dist = math.sqrt(SATCollision.normal[0] ** 2 + SATCollision.normal[1] ** 2)
        if dist > 0:
            SATCollision.normal[0] /= dist
            SATCollision.normal[1] /= dist

    @staticmethod
    def dot_product_against_normal(point):
        return (SATCollision.normal[0] * point[0]) + (SATCollision.normal[1] * point[1])

    @staticmethod
    def try_collide(o1, o2, collision_obj, flip):
        shortest_dist = float("inf")
        collision_obj.is_collided = False

        # the following only works for AABBs, we will have to change that once objects start rotating or being non-rects
        p1 = [[o1.rect.x, o1.rect.y], [o1.rect.x + o1.rect.width, o1.rect.y],
              [o1.rect.x + o1.rect.width, o1.rect.y + o1.rect.height], [o1.rect.x, o1.rect.y + o1.rect.height]]

        p2 = [[o2.rect.x, o2.rect.y], [o2.rect.x + o2.rect.width, o2.rect.y],
              [o2.rect.x + o2.rect.width, o2.rect.y + o2.rect.height], [o2.rect.x, o2.rect.y + o2.rect.height]]

        # loop through all axes of sprite1
        for i in range(len(p1)):
            SATCollision.calculate_normal(p1, i)

            min1 = SATCollision.dot_product_against_normal(p1[0])
            max1 = min1

            for j in range(1, len(p1)):
                tmp = SATCollision.dot_product_against_normal(p1[j])
                if tmp < min1:
                    min1 = tmp
                if tmp > max1:
                    max1 = tmp

            min2 = SATCollision.dot_product_against_normal(p2[0])
            max2 = min2

            for j in range(1, len(p2)):
                tmp = SATCollision.dot_product_against_normal(p2[j])
                if tmp < min2:
                    min2 = tmp
                if tmp > max2:
                    max2 = tmp

            d1 = min1 - max2
            d2 = min2 - max1

            if d1 > 0 or d2 > 0:
                return None

            min_dist = (max2 - min1) * -1
            if flip:
                min_dist *= -1
            min_dist_abs = abs(min_dist)
            if min_dist_abs < shortest_dist:
                collision_obj.sprite1 = o1
                collision_obj.sprite2 = o2
                collision_obj.distance = min_dist
                collision_obj.magnitude = min_dist_abs
                collision_obj.normal_x = SATCollision.normal[0]
                collision_obj.normal_y = SATCollision.normal[1]
                if collision_obj.distance > 0:
                    collision_obj.distance *= -1
                    collision_obj.normal_x *= -1
                    collision_obj.normal_y *= -1

                collision_obj.is_collided = True
                shortest_dist = min_dist_abs

        # return the actual collision
        return collision_obj if collision_obj.is_collided else None


def defaults(dictionary, defaults_dict):
    """
    adds all key/value pairs from defaults_dict into dictionary, but only if dictionary doesn't have the key
    Args:
        dictionary (the target dictionary):
        defaults_dict (the source (default) dictionary):

    Returns:

    """
    for key, value in defaults_dict.items():
        if key not in dictionary:  # overwrite only if key is missing
            dictionary[key] = value


def extend(dictionary, extend_dict):
    """
    extends the dictionary with extend_dict, thereby overwriting existing keys
    Args:
        dictionary (the target dictionary):
        extend_dict (the source dictionary):

    Returns:

    """
    for key, value in extend_dict.items():
        dictionary[key] = value  # overwrite no matter what
