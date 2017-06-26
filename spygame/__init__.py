"""
 -------------------------------------------------------------------------
 spygame (pygame based 2D game engine for the openAI gym)
 -------------------------------------------------------------------------

 created: 2017/04/04 in PyCharm
 (c) 2017 Sven Mika - ducandu GmbH
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
import numpy as np
import functools


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
DEBUG_RENDER_ACTIVE_COLLISION_TILES_COLOR_GREYED_OUT = pygame.Color("grey")
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
    an EventObject introduces event handling and most objects that occur in spygame games will inherit from this class
    - NOTE: spygame events are not(!) pygame events
    - EventObject can 'have' some events, which are simple strings (the names of the events, e.g. 'hit', 'jump', 'collided', etc..)
    - EventObject can trigger any event by their name
    - if an EventObject wants to trigger an event, this event must have been registered with the EventObject beforehand (will raise exception otherwise)
    -
    """
    def __init__(self):
        # - listeners keeps a list of callbacks indexed by event name for quick lookup
        # - a listener is an array of 2 elements: 0=target, 1=callback
        self.listeners = {}  # keys=event names; values=list of 2 elements (0=target object, 1=callback method)
        # stores all valid event names; that way, we can check validity of event when subscribers subscribe to some event
        self.valid_events = set()

    def register_event(self, *events):
        """
        registers a possible event (str) with this object; only registered events are allowed to be triggered later

        :param str events: the event (or events) that should be registered
        """
        for event in events:
            self.valid_events.add(event)

    def unregister_event(self, *events):
        """
        removes one or more events from this EventObject's event registry; unregistered events are no longer allowed to be triggered

        :param str events: the event(s) that should be removed from the registry
        """
        self.valid_events.remove(event)

    def unregister_events(self):
        """
        unregisters all events from this GameObject (see 'unregister_event')
        """
        self.valid_events.clear()

    def check_event(self, event: str):
        """
        checks whether the given event is in this EventObject's registry (raises exception if not)

        :param str event: the event to be checked
        """
        # make sure the event is valid (registered)
        if event not in self.valid_events:
            raise Exception("ERROR: event '{}' not valid in this EventObject ({}); event has not been registered!".format(event, type(self).__name__))

    def on_event(self, event, target=None, callback=None, register=False):
        """
        binds a callback to an event on this EventObject
        - if you provide a `target` object, that object will add this event to it's list of binds, allowing it to automatically remove it when
        it is destroyed.
        - from here on, if the event gets triggered, the callback will be called on the target object
        - note: only previously registered events may be triggered (we can register the event here by setting register=True)

        :param Union[str,List[str]] event: the name of the event to be bound to the callback (e.g. tick, got_hit, etc..)
        :param target (EventObject): The target object on which to call the callback (defaults to self if not given)
        :param callable callback: the bound method to call on target if the event gets triggered
        :param bool register: whether we should register this event right now (only registered events are allowed to be triggered later)
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
        triggers an event and specifies the parameters to be passed to the bound event handlers (callbacks) as \*params

        :param str event: the name of the event that should be triggered; note: this event name will have to be registered with the EventObject
            in order for the trigger to succeed
        :param any params: the parameters to be passed to the handler methods as \*args
        """
        self.check_event(event)

        # make sure there are any listeners for this specific event, if not, early out
        if event in self.listeners:
            # call each listener in the context of either the target passed into `on_event` ([0]) or the object itself
            for listener in self.listeners[event]:
                listener[1](*params)

    def off_event(self, event, target=None, callback=None, unregister=False):
        """
        unbinds an event from a target/callback
        - can be called with 1, 2, or 3 parameters, each of which unbinds a more specific listener

        :param str event: the name of the event to unbind from the callback
        :param EventObject target: the target EventObject to unbind this event from (callback would be a member of this target)
        :param callable callback: the callback to unbind the event from
        :param bool unregister: whether we should unregister this event as well
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
    """
    a class to handle keyboard inputs by the user playing the spygame game
    - a KeyboardInput object is passed to the GameLoop c'tor, so that the GameLoop can `tick` the KeyboardInput object each frame
    - single keys to watch out for can be registered via the `update_keys` method (not registered keys will be ignored)
    - the tick method collects all keydown/keyup pygame events and stores the currently registered keys in the `keyboard_registry` as True (currently pressed)
    or False (currently not pressed)
    - all keys are described by their pygame names (without the leading `K_`), e.g. pygame.K_UP=`up`, pygame.K_ESCAPE=`escape`, etc..
    """
    def __init__(self, key_list=None):
        super().__init__()

        # stores the keys that we would like to be registered as important
        # - key: pygame keyboard code (e.g. pygame.K_ESCAPE, pygame.K_UP, etc..)
        # - value: True if currently pressed, False otherwise
        # - needs to be ticked in order to yield up-to-date information (this will be done by a GameLoop playing a Screen)
        self.keyboard_registry = {}
        self.descriptions = {}
        #OBSOLETE: self.desc_to_key = {}  # for reverse mapping from description (e.g. 'up') to int (e.g. pygame.K_UP)

        if key_list is None:
            key_list = ["up", "down", "left", "right"]
        self.update_keys(key_list)

    def update_keys(self, new_key_list=None):
        """
        populates our registry and other dicts with the new key-list given (may be an empty list)

        :param Union[List,None] new_key_list: the new key list, where each item is the lower-case pygame keycode without the leading
            `K_` e.g. `up` for pygame.K_UP; use None for clearing out the registry (no keys assigned)
        """
        self.unregister_events()
        self.keyboard_registry.clear()
        self.descriptions.clear()
        #OBSOLETE: self.desc_to_key.clear()
        if new_key_list:
            for desc in new_key_list:
                key = getattr(pygame, "K_" + (desc.upper() if len(desc) > 1 else desc))
                self.keyboard_registry[key] = False
                self.descriptions[key] = desc
                #OBSOLETE: self.desc_to_key[desc] = key
                # signal that we might trigger the following events:
                self.register_event("key_down." + desc, "key_up." + desc)

    def tick(self):
        """
        pulls all keyboard events from the event queue and processes them according to our keyboard_registry/descriptions
        - triggers events for all registered keys like: 'key_down.[desc]' (when  pressed) and 'key_up.[desc]' (when released),
        where desc is the lowercase string after `pygame.K_`... (e.g. 'down', 'up', etc..)
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
    a GameObject adds the capability to add one or more Component objects to the GameObject
    (e.g. animation, physics, etc..)
    - Component objects are stored by their name in the GameObject.components dict
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
        Adds a component object to this GameObject -> calls the component's added method

        :param Component component: component to be added to GameObject under game_obj.components[component.name]
        :return: the same Component for chaining
        :rtype: Component
        """

        component.game_object = self
        assert component.name not in self.components, "ERROR: component with name {} already exists in Entity!".format(component.name)
        self.components[component.name] = component
        component.added()
        return component

    def remove_component(self, component):
        """
        removes the given component from this GameObject

        :param Component component: the Component object to be removed
        """
        assert component.name in self.components, "ERROR: component with name {} does no exist in Entity!".format(component.name)
        # call the removed handler (if implemented)
        component.removed()
        # only then erase the component from the GameObject
        del self.components[component.name]

    def destroy(self):
        """
        Destroys the GameObject by calling debind and removing the object from it's parent
        - will trigger a `destroyed` event (callback)
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

    def tick(self, game_loop):
        """
        a tick (coming from the GameObject containing Stage); override this if you want your GameObject to do something each frame
        :param GameLoop game_loop: the GameLoop that's currently playing
        """
        pass


class SpriteSheet(object):
    """
    represents a spritesheet loaded from a tsx file
    - stores each single image (as pygame.Surface) in the sheet by its position
    - allows for already doing flip transformations (x/y and/or both axes) so we save time during the game
    - stores single tile properties in tile_props_by_id dict (only for those tiles that actually have custom properties defined in the tsx file)
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


class Sprite(GameObject, pygame.sprite.Sprite):
    """
    a Sprite can be added to a Stage; has a type and a collision mask for collision detection with other Sprites or TiledTileLayers also on the Stage
    - Sprite objects inherit from pygame.sprite.Sprite, so a Sprite has an image and a position via rect
    - each Sprite can have either a static image or hold a SpriteSheet object from which it can pull images for animation purposes; either way, the image
    property is set that way
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
    def get_type(types):
        """
        returns the bitmap code for an already existing Sprite type or for a new type (the code will be created then)
        - types are usually used for collision masks

        :param str types: the type(s) (comma-separated), whose code(s) should be returned
        :return: the type as an int; if many types are given, returns a bitmask with all those bits set that represent the given types
        :rtype: int
        """
        ret = 0
        for type_ in types.split(","):
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
        - image_section: a tuple with 4 values: offset-x, offset-y, width, height defining a rect to use only a subsection of the given static image
        - width_height: Tuple[int,int] -> empty image (no rendering) with a rect of the given width/height
        """
        pygame.sprite.Sprite.__init__(self)
        GameObject.__init__(self)

        self.do_render = True

        # with SpriteSheet
        if "sprite_sheet" in kwargs:
            sheet = kwargs["sprite_sheet"]
            assert isinstance(sheet, SpriteSheet), "ERROR: in Sprite's ctor: kwargs[`sprite_sheet`] must be of type `SpriteSheet`!"
            self.spritesheet = sheet
            # TODO: make it possible to create a Sprite from more than one tile (e.g. for a platform/elevator). Either in x-direction or y-direction or both
            self.image = sheet.tiles[0]
            self.rect = pygame.Rect(x, y, self.spritesheet.tw, self.spritesheet.th)
        # an image file -> fixed image -> store as Surface in self.image
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
                self.image.blit(source, area=pygame.Rect(*sec))
            else:
                self.image = source
            self.rect = self.image.get_rect()
            # fix x/y (would be 0,0 otherwise)
            self.rect.x = x
            self.rect.y = y
        # empty image of some size
        elif "width_height" in kwargs:
            width_height = kwargs["width_height"]
            assert isinstance(width_height, tuple) and len(width_height) == 2,\
                "ERROR: in Sprite's ctor: kwargs[`width_height`] must be of type tuple and of len 2!"
            self.spritesheet = None
            self.image = None
            self.rect = pygame.Rect(x, y, width_height[0], width_height[1])
            self.do_render = True if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_RECTS else False
        # tiny-size rect (no image)
        else:
            self.spritesheet = None
            self.image = None
            self.rect = pygame.Rect(x, y, 1, 1)
            self.do_render = True if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_RECTS else False

        # GameObject specific stuff
        self.type = Sprite.get_type("default")  # specifies the type of the GameObject (can be used e.g. for collision detection)
        self.handles_own_collisions = False  # set to True if this object takes care of its own collision handling
        self.collision_mask = Sprite.get_type("default")  # set the bits here that we would like to collide with (all other types will be ignored)

        self.stage = None  # the current Stage this Sprite is in
        self.sprite_groups = []  # the current Groups that this Sprite belongs to
        self.render_order = 50  # the higher this number the later this Sprite will be rendered in the Stage's render function
        self.flip = {"x": False, "y": False}  # 'x': flip in x direction, 'y': flip in y direction, False: don't flip

        self.register_event("added_to_stage")  # allow any Stage to trigger this event using this Sprite

    def move(self, x, y, precheck=False, absolute=False):
        """
        moves us by x/y pixels
        OBSOLETE: - if precheck is set to True: pre-checks the planned move via call to stage.locate and only moves entity as far as possible

        :param Union[int,None] x: the amount in pixels to move in x-direction
        :param Union[int,None] y: the amount in pixels to move in y-direction
        :param bool precheck: ???
        :param bool absolute: whether x and y are given as absolute coordinates (default: False): in this case x/y=None means do not move in this dimension
        """

        #if precheck:
        #    testcol = self.stage.locate(p.x+x, p.y+y, Q._SPRITE_DEFAULT, p.w, p.h);
        #    if ((!testcol) || (testcol.tileprops && testcol.tileprops['liquid'])) {
        #        return True
        #
        #    return False

        if not absolute:
            self.rect.x += x
            self.rect.y += y
        else:
            if x is not None:
                self.rect.x = x
            if y is not None:
                self.rect.y = y

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
        """
        paints the Sprite with its current image onto the given Display object

        :param Display display: the Display object to render on (Display has a pygame.Surface, on which we blit our image)
        """
        if self.image:
            display.surface.blit(self.image, (self.rect.x - display.offsets[0], self.rect.y - display.offsets[1]))
        if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_RECTS:
            pygame.draw.rect(display.surface, DEBUG_RENDER_SPRITES_RECTS_COLOR, \
                             pygame.Rect((self.rect.x - display.offsets[0], self.rect.y - display.offsets[1]), (self.rect.w, self.rect.h)), 1)


class Repeater(Sprite):
    """
    a background 2D repeater that scrolls slower than the Viewport
    """
    def __init__(self, x, y, image_file, **kwargs):
        super().__init__(x, y, image_file)
        self.vx = kwargs.get("vx", 1.0)
        self.vy = kwargs.get("vy", 1.0)
        self.repeat_x = kwargs.get("repeat_x", True)
        self.repeat_y = kwargs.get("repeat_y", True)
        self.repeat_w = kwargs.get("repeat_w", self.rect.width)
        self.repeat_h = kwargs.get("repeat_h", self.rect.height)
        # don't collide with anything
        self.type = Sprite.get_type("none")
        self.collision_mask = 0

    # @override(Sprite)
    def render(self, display):
        # debug rendering (no backgrounds) -> early out
        if DEBUG_FLAGS & DEBUG_DONT_RENDER_TILED_TILE_LAYERS:
            return
        view_x = display.offsets[0]
        view_y = display.offsets[1]
        offset_x = self.rect.x + view_x * self.vx
        offset_y = self.rect.y + view_y * self.vy
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


class Ladder(Sprite):
    """
    a Ladder object that actors can climb on
    - one-way-platform type: one cannot fall through the top of the ladder but does not collide with the rest (e.g. from below) of the ladder
    - a Ladder object does not have an image and is thus not(!) being rendered; the image of the ladder has to be integrated into a TiledTileLayer
    - TiledTileLayers have the possibility to generate lists of Ladder objects from those tiles that are flagged with the type='ladder' property
    """
    def __init__(self, x, y, width=32, height=80):
        """
        :param int x: the x position of the Ladder
        :param int y: the y position of the Ladder
        :param int width: the width of the Ladder in pixels (not tiles!)
        :param int height: the height of the Ladder in pixels (not tiles!)
        """
        # transform values here to make collision with ladder to only trigger when player is relatively close to the x-center of the ladder
        # - make this a 2px wide vertical axis in the center of the ladder
        x = x + int(width/2) - 1
        width = 2

        #OBSOLETE: we should dock to the ladder instead
        # - also make ladder stick out a few px on the top to solve:
        # [block]_ladder_[block] problems when standing on [block] and trying to go down <- that ladder
        # height += 1
        # y -= 1

        super().__init__(x, y, (width, height))

        # collision types
        self.type = Sprite.get_type("ladder,one_way_platform")
        self.collision_mask = 0  # do not do any collisions

        # important to be able to start the 'top-of-ladder' animation sequence for agents that climb up the ladder
        self.almost_top = self.rect.top + 12


class AnimatedSprite(Sprite):
    """
    adds an Animation component to each Sprite instance
    - AnimatedSprites need a SpriteSheet (no static images or no-render allowed)

    :param int x: the initial x position of the Sprite
    :param int y: the initial y position of the Sprite
    :param SpriteSheet spritesheet: the SpriteSheet object to use for this Sprite
    :param dict animation_setup: the dictionary with the animation setup data to be sent to Animation.register_settings (the name of the registry record will
            be spritesheet.name)
    """

    def __init__(self, x, y, sprite_sheet, animation_setup):
        """
        :param int x: the initial x position of the AnimatedSprite
        :param int y: the initial y position of the AnimatedSprite
        :param SpriteSheet sprite_sheet: the SpriteSheet to use for animations
        :param dict animation_setup: a dictionary with all the different animation name and their settings (animation speed, frames to use, etc..)
        """
        assert isinstance(sprite_sheet, SpriteSheet), "ERROR: AnimatedSprite needs a SpriteSheet in its c'tor!"

        super().__init__(x, y, sprite_sheet=sprite_sheet)  # assign the image/rect for the Sprite
        self.register_event("post_tick")
        self.cmp_animation = self.add_component(Animation("animation"))

        Animation.register_settings(sprite_sheet.name, animation_setup, register_events_on=self)
        # play the default animation (now that we have added the Animation Component, we can call play_animation on ourselves)
        self.play_animation(animation_setup["default"])


class Display(object):
    """
    a simple wrapper class for a pygame.display/pygame.Surface object representing the pygame display
    - also stores offset information for Viewport focusing (if Viewport is smaller that the Level, which is usually the case)
    """

    instantiated = False

    def __init__(self, width=600, height=400, title="Spygame Rocks!"):
        """
        :param int width: the width of the Display
        :param int height: the height of the Display
        :param str title: the caption to use on the pygame display
        """
        assert not Display.instantiated, "ERROR: can only create one {} object!".format(type(self).__name__)
        Display.instantiated = True

        pygame.display.set_caption(title)
        self.surface = pygame.display.set_mode((width, height))
        self.offsets = [0, 0]

    def change_dims(self, width, height):
        """
        changes the Display's size dynamically (during the game)
        :param int width: the new width to use
        :param int height: the new height to use
        """
        pygame.display.set_mode((width, height))
        assert self.surface is pygame.display.get_surface(), "ERROR: self.display is not same object as pygame.display.get_surface() anymore!"

    def debug_refresh(self):
        """
        force-refreshes the display (used only for debug purposes)
        """
        pygame.display.flip()
        pygame.event.get([])  # we seem to have to do this


class GameLoop(object):
    """
    class that represents the GameLoop
    - has play and pause functions: play starts the tick/callback loop
    - has clock for ticking (keeps track of self.dt each tick), handles and abides to max-fps rate setting
    - handles keyboard input registrations via its KeyboardInputs object
    - needs a callback to know what to do each tick. Does the keyboard_inputs.tick, then calls callback with self as only argument
    """

    # static loop object (the currently active GameLoop gets stored here)
    active_loop = None

    @staticmethod
    def play_a_loop(**kwargs):
        """
        factory: plays a given GameLoop object or creates a new one using the given \*\*kwargs options

        :param any kwargs:
                force_loop (bool): whether to play regardless of whether we still have some active loop running
                callback (callable): the GameLoop's callback loop function
                keyboard_inputs (KeyboardInputs): the GameLoop's KeyboardInputs object
                display (Display): the Display object to render everything on
                max_fps (int): the max frames per second to loop through
                screen_obj (Screen): alternatively, a Screen can be given, from which we will extract `display`, `max_fps` and `keyboard_inputs`
                game_loop (Union[str,GameLoop]): the GameLoop to use (instead of creating a new one); "new" or [empty] for new one
                dont_play (bool): whether - after creating the GameLoop - it should be `play`ed. Can be used for openAI gym purposes, where we just `step`, not `tick`
        :return: the created/played GameLoop object or None
        :rtype: Union[GameLoop,None]
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

    def __init__(self, callback, display, keyboard_inputs=None, max_fps=60):
        """
        :param callable callback: the callback function to call each time we `tick` (after collecting keyboard events)
        :param Display display: the Display object associated with the loop
        :param KeyboardInputs keyboard_inputs: the KeyboardInputs object to use for collecting keyboard information each tick (we simply call the
        KeyboardInputs' `tick` method during our own `tick` method)
        :param int max_fps: the maximum frame rate per second to allow when ticking. fps can be slower, but never faster
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
        """
        pauses this GameLoop
        """
        self.is_paused = True
        GameLoop.active_loop = None

    def play(self, max_fps=None):
        """
        plays this GameLoop (after pausing the currently running GameLoop, if any)
        """
        # pause the current loop
        if GameLoop.active_loop:
            GameLoop.active_loop.pause()
        GameLoop.active_loop = self
        self.is_paused = False
        # tick as long as we are not paused
        while not self.is_paused:
            self.tick(max_fps)

    def tick(self, max_fps=None):
        """
        called each frame of the GameLoop
        - collects keyboard events
        - calls the GameLoop's `callback`
        - keeps a frame counter

        :param int max_fps: the maximum allowed number of frames per second (usually 60)
        """
        if not max_fps:
            max_fps = self.max_fps

        # move the clock and store the dt (since last frame) in sec
        self.dt = self.timer.tick(max_fps) / 1000

        # default global events?
        events = pygame.event.get(pygame.QUIT)  # TODO: add more here?
        for e in events:
            if e.type == pygame.QUIT:
                raise Exception(SystemExit, "QUIT")

        # collect keyboard events
        self.keyboard_inputs.tick()

        # call the callback with self (for references to important game parameters)
        self.callback(self)

        # increase global frame counter
        self.frame += 1

    def step(self, action):
        """
        (!)for reinforcement learning only(!) WIP:
        executes one action on the game
        - the action gets translated into a keyboard sequence first, then is played

        :param str action: the action to execute on the MDP
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


class Stage(GameObject):
    """
    A Stage is a container class for Sprites sorted by pygame.sprite.Groups and TiledTileLayers
    - Sprites within a Stage can collide with each other or with the TiledTileLayers in the Stage
    - Sprites and TiledTileLayers that are to be rendered are stored sorted by their render_order property (lowest renders first)
    -
    """

    # list of all Stages
    max_stages = 10
    stages = [None for x in range(max_stages)]
    active_stage = 0  # the currently ticked/rendered Stage
    locate_obj = Sprite(0, 0, width_height=(0, 0))  # used to do test collisions on a Stage

    @staticmethod
    def stage_default_game_loop_callback(game_loop: GameLoop):
        """
        the default game loop callback to use if none given when staging a Scene
        - clamps dt
        - ticks all stages
        - renders all stages
        - updates the pygame.display

        :param GameLoop game_loop: the currently playing (active) GameLoop
        """
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
    def render_stages(display, refresh_after_render=False):
        """
        loops through all Stages and renders all of them

        :param Display display: Display object on which to render
        :param bool refresh_after_render: do we refresh the pygame.display after all Stages have been called with `render`?
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
    def clear_stage(idx):
        """
        clears one of the Stage objects by index

        :param int idx: the index of the Stage to clear (index==slot in static Stage.stages list)
        """
        if Stage.stages[idx]:
            Stage.stages[idx].destroy()
            Stage.stages[idx] = None

    @staticmethod
    def clear_stages():
        """
        clears all our Stage objects
        """
        for i in range(len(Stage.stages)):
            Stage.clear_stage(i)

    @staticmethod
    def get_stage(idx=0):
        """
        returns the Stage at the given index (returns None if none found)

        :param Union[int,None] idx: the index of the Stage to return (0=default Stage)
        :return: the Stage object at the given index or None if there is no Stage at that index
        :rtype: Union[Stage,None]
        """
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
        self.tiled_tile_layers = {}  # TiledLayer objects by name
        self.tiled_object_groups = {}  # TiledObjectGroup objects by name
        self.to_render = []  # list of all layers and sprites by name (TiledTileLayers AND Sprites) in the order in which they have to be rendered

        # dict of pygame.sprite.Group objects (by name) that contain Sprites (each TiledObjectGroup results in one Group)
        # - the name of the group is always the name of the TiledObjectGroup in the tmx file
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

        # add Components to this Stage (given in options)
        if "components" in self.options:
            for comp in self.options["components"]:
                assert isinstance(comp, Component), "ERROR: one of the given components in Stage's c'tor (options['components']) is not of type Component!"
                self.add_component(comp)

        # make sure our destroyed method is called when the stage is destroyed
        self.on_event("destroyed")

    def destroyed(self):
        self.invoke("debind_events")
        self.trigger_event("destroyed")

    # calls the callback function for each sprite, each time passing it the sprite and params
    def for_each(self, callback: callable, params=None):  # quintus: `each`
        if not params:
            params = []
        for sprite in self.sprites:
            callback(sprite, *params)

    def invoke(self, func_name, params=None):
        """
        calls a function on all of the GameObjects on this Stage

        :param str func_name: the function name to call on all our GameObjects using getattr
        :param Union[list,None] params: the *args passed to that function
        """
        if not params:
            params = []
        for sprite in self.sprites:
            func = getattr(sprite, func_name, None)
            if callable(func):
                func(*params)

    def detect(self, detector, params=None):
        """
        returns the first GameObject in this Stage that - when passed to the detector function with params - returns True

        :param callable detector: a function that returns a bool
        :param list params: the list of positional args that are passed to the detector
        :return: the first GameObject in this Stage that - when passed to the detector function with params - returns True
        :rtype: Union[Sprite,None]
        """
        if not params:
            params = []
        for sprite in self.sprites:
            if detector(sprite, *params):
                return sprite

    def locate(self, x, y, w=1, h=1, type_=Sprite.get_type("default"), collision_mask=Sprite.get_type("default")):
        """
        returns the first Collision found by colliding the given measurements (Rect) against this Stage's objects
        - starts with all TiledTileLayer objects, then all other Sprites

        :param int x: the x-coordinate of the Rect to check
        :param int y: the y-coordinate of the Rect to check
        :param int w: the width of the Rect to check
        :param int h: the height of the Rect to check
        :param int type_: the type of the Rect (has to match collision_mask of Stage's objects)
        :param int collision_mask: the collision mask of the Rect (only layers and Sprites that match this mask are checked)
        :return: the first Collision encountered
        :rtype: Union[Collision,None]
        """
        obj = self.locate_obj
        obj.rect.x = x
        obj.y = y
        obj.width = w
        obj.height = h
        obj.type = type_
        obj.collision_mask = collision_mask

        # collide with all matching tile layers
        for tile_layer in self.tiled_layers.values():
            if obj.collision_mask & tile_layer.type:
                col = tile_layer.collide(obj)
                # don't solve -> just return
                if col:
                    return col

        # collide with all Sprites (only if both collision masks match each others types)
        for sprite in self.sprites:
            if obj.collision_mask & sprite.type and sprite.collision_mask & obj.type:
                col = self.options["physics_collision_detector"](obj, sprite)
                if col:
                    return col
        # nothing found
        return None

    def add_tiled_layer(self, pytmx_layer, pytmx_tiled_map):
        """
        adds a pytmx.TiledElement to the Stage with all its tiles or objects
        - the TiledElement could either be converted into a TiledTileLayer or a TiledObjectGroup (these objects are generated in this function based on the
        pytmx equivalent being passed in)

        :param pytmx.pytmx.TiledElement pytmx_layer: the original pytmx object to derive our TiledTileLayer or TileObjectGroup from
        :param pytmx.pytmx.TiledMap pytmx_tiled_map: the original pytmx TiledMap object (the tmx file) to which this layer belongs
        """
        # a TiledObjectGroup ("Object Layer" in the tmx file)
        if isinstance(pytmx_layer, pytmx.pytmx.TiledObjectGroup):
            assert pytmx_layer.name not in self.tiled_object_groups, "ERROR: TiledObjectGroup with name {} already exists in Stage!".format(pytmx_layer.name)
            l = TiledObjectGroup(pytmx_layer, pytmx_tiled_map)
            self.add_tiled_object_group(l)

        # a TiledTileLayer ("Tile Layer" in the tmx file)
        elif isinstance(pytmx_layer, pytmx.pytmx.TiledTileLayer):
            assert pytmx_layer.name not in self.tiled_tile_layers, "ERROR: TiledTileLayer with name {} already exists in Stage!".format(pytmx_layer.name)
            # use default collision objects if not given
            #if "tile_sprite_handler" not in self.options:
            #    self.options["tile_layer_physics_collisions"] = (Collision(), Collision())
            assert "tile_sprite_handler" in self.options, \
                "ERROR: a TiledTileLayer needs a tile_sprite_handler callable to generate all TileSprite objects in the layer!"
            #assert "physics_collision_detector" in self.options, \
            #    "ERROR: a TiledTileLayer needs a physics collision detector given in the Stage's option as `physics_collision_detector`!"
            #assert "tile_layer_physics_collision_postprocessor" in self.options, \
            #    "ERROR: a TiledTileLayer needs a physics collision handler given in the Stage's option: `tile_layer_physics_collision_postprocessor`!"
            l = TiledTileLayer(pytmx_layer, pytmx_tiled_map, self.options["tile_sprite_handler"])
                               # self.options["tile_layer_physics_collision_tile_selector"],
                               # self.options["physics_collision_detector"], self.options["tile_layer_physics_collision_postprocessor"])
            self.add_tiled_tile_layer(l)

        else:
            raise Exception("ERROR: pytmx_layer of type {} cannot be added to Stage. Needs to be pytmx.pytmx.TiledTileLayer or pytmx.pytmx.TiledObjectGroup!".
                            format(type(pytmx_layer).__name__))

    def add_tiled_object_group(self, tiled_object_group):
        """
        adds a TiledObjectGroup (all it's objects as single Sprites) to this Stage
        :param TiledObjectGroup tiled_object_group:
        """
        # add the layer to our tiled_layers list
        self.tiled_object_groups[tiled_object_group.name] = tiled_object_group

        # add the (already created) sprite-group to this stage under the name of the layer
        assert tiled_object_group.name not in self.sprite_groups, \
            "ERROR: trying to add a TiledObjectGroup to a Stage, but the Stage already has a spritegroup with the name of that layer ({})". \
                format(tiled_object_group.name)
        self.sprite_groups[tiled_object_group.name] = tiled_object_group.sprite_group

        # add each single sprite of the group to the Stage
        for sprite in tiled_object_group.sprite_group.sprites():
            self.add_sprite(sprite, tiled_object_group.name)

    def add_tiled_tile_layer(self, tiled_tile_layer):
        """
        adds a TiledTileLayer to this Stage
        - puts it in the ordered to_render list, in the tiled_layers list

        :param TiledTileLayer tiled_tile_layer: the TiledTileLayer to add to this Stage
        """
        # put the pytmx_layer into one of the collision groups (if not type==none)?
        # - this is useful for our solve_collisions method
        #if tiled_tile_layer.type != Sprite.get_type("none"):
        #    self.tiled_layers_to_collide.append(tiled_tile_layer)

        # put only TiledTileLayers in to_render (iff do_render=true) and single Sprites (from the TiledObjectGroup) all ordered by render_order
        self.tiled_tile_layers[tiled_tile_layer.name] = tiled_tile_layer

        # add it to the to_render list and re-sort the list by render_order values (note: this list also contains single Sprites)
        if tiled_tile_layer.do_render:
            self.to_render.append(tiled_tile_layer)
            self.to_render.sort(key=lambda x: x.render_order)

        # TODO: make this ladder process more generic (maybe other object types could be built like that as well)
        # capture ladders?
        if tiled_tile_layer.properties.get("build_ladders") == "true":
            ladders = tiled_tile_layer.capture_ladders()
            for ladder in ladders:
                self.add_sprite(ladder, "ladders")

    def add_sprite(self, sprite, group_name):
        """
        adds a new single Sprite to an existing or a new pygame.sprite.Group

        :param Sprite sprite: the Sprite to be added to this Stage (the Sprite's position is defined in its rect.x/y properties)
        :param str group_name: the name of the group to which the GameObject should be added (group will not be created if it doesn't exist yet)
        :return: the Sprite that was added
        :rtype: Sprite
        """
        # if the group doesn't exist yet, create it
        if group_name not in self.sprite_groups:
            self.sprite_groups[group_name] = pygame.sprite.Group()
        sprite.stage = self  # set the Stage of this GameObject
        self.sprite_groups[group_name].add(sprite)
        self.sprites.append(sprite)
        sprite.sprite_groups.append(self.sprite_groups[group_name])

        # add each single Sprite to the sorted (by render_order) to_render list and to the "all"-sprites list
        # - note: the to_render list also contains entire TiledTileLayer objects
        if sprite.do_render:
            self.to_render.append(sprite)
            self.to_render.sort(key=lambda x: x.render_order)

        # trigger two events, one on the Stage with the object as target and one on the object with the Stage as target
        self.trigger_event("added_to_stage", sprite)
        sprite.trigger_event("added_to_stage", self)

        return sprite

    def remove_sprite(self, sprite: Sprite):
        """
        removes a Sprite from this Stage by putting it in the remove_list for later removal

        :param Sprite sprite: the Sprite to be removed from the Stage
        """
        self.remove_list.append(sprite)

    def force_remove_sprite(self, sprite: Sprite):
        """
        force-removes the given Sprite immediately (without putting it in the remove_list first)

        :param Sprite sprite: the Sprite to be removed from the Stage
        """
        try:
            self.sprites.remove(sprite)
            if sprite.do_render:
                self.to_render.remove(sprite)
        except ValueError:
            return

        # destroy the object
        sprite.destroy()
        self.trigger_event("removed_from_stage", sprite)

    def pause(self):
        """
        pauses playing the Stage
        """
        self.is_paused = True

    def unpause(self):
        """
        unpauses playing the Stage
        """
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
                for tile_layer in self.tiled_layers.values():
                    # only collide, if one of the types of the layer matches one of the bits in the Sprite's collision_mask
                    if sprite.collision_mask & tile_layer.type:
                        col = tile_layer.collide(sprite)
                        if col:
                            sprite.trigger_event("collision", col)

        # collide all Sprites with all other Sprites (both ways!)
        # - only check if sprite1's collision_matrix matches sprite2's type
        for sprite in self.sprites:
            # if this Sprite completely handles its own collisions within its tick -> ignore it
            if not sprite.handles_own_collisions and sprite.collision_mask > 0:
                for sprite2 in self.sprites:
                    if sprite is not sprite2 and not sprite2.handles_own_collisions and sprite2.collision_mask > 0 and \
                                    sprite.collision_mask & sprite2.type and sprite2.collision_mask & sprite.type:
                        col = self.options["physics_collision_detector"](sprite, sprite2)
                        if col:
                            # trigger "collision" for both Sprites
                            sprite.trigger_event("collision", col)
                            sprite2.trigger_event("collision", col.invert())

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
        - renders all its layers (ordered by 'render_order' property of the TiledTileLayer in the tmx file)
        TODO: - renders Sprites that are not part of any layer

        :param Display display: the Display object to render on
        """
        if self.is_hidden:
            return False

        self.trigger_event("pre_render", display)
        # loop through the sorted to_render list and render all TiledTileLayer and Sprite objects in this list
        for layer_or_sprite in self.to_render:
            layer_or_sprite.render(display)
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


class TiledTileLayer(TmxLayer):
    """
    a wrapper class for pytmx.pytmx.TiledTileLayer, which represents a 'normal' tile layer in a tmx file
    - reads in all tiles' images into one Surface object so we can render the entire layer at once
    - implements `render`
    """

    def __init__(self, pytmx_layer, pytmx_tiled_map, tile_sprite_handler):
        """
        :param pytmx.pytmx.TiledTileLayer pytmx_layer: the underlying pytmx TiledTileLayer
        :param pytmx.pytmx.TiledMap pytmx_tiled_map: the underlying pytmx TiledMap object (representing the tmx file)
        :param callable tile_sprite_handler: the callable that returns a readily populated TileSprite object for storage in this layer
        """
        super().__init__(pytmx_layer, pytmx_tiled_map)

        self.type_str = self.properties.get("type", "none")
        self.type = 0
        # get type mask of this layer from `type` property
        for t in self.type_str.split(","):
            self.type |= Sprite.get_type(t)

        # an ndarray holding all single tiles (by x/y position) from this layer (for passing to a collision function and easy-access information storage)
        self.tile_sprites = tile_sprite_handler(self)

        # update do_render indicator depending on some debug settings
        self.do_render = (self.properties["do_render"] == "true" and not (DEBUG_FLAGS & DEBUG_DONT_RENDER_TILED_TILE_LAYERS)) or \
                         (self.type != Sprite.get_type("none") and (DEBUG_FLAGS & DEBUG_RENDER_COLLISION_TILES))
        self.render_order = int(self.properties["render_order"])

        # put this layer in one single Sprite that we can then blit on the display (with 'area=[some rect]' to avoid drawing the entire layer each time)
        self.pygame_sprite = None
        # we are rendering this layer, need to store entire image in this structure
        if self.do_render:
            self.pygame_sprite = self.build_sprite_surface()

    def build_sprite_surface(self):
        """
        builds the image (pygame.Surface) for this tile layer based on all found tiles in the layer
        """
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
        return pygame_sprite

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

    # TODO: make ladder-capturing from background layer more generic (include waterfalls sprites, quicksand sprites, etc..)
    def capture_ladders(self):
        """
        captures all ladder objects in this layer and returns them in a list of Ladder objects
        - once a ladder tile is found: searches neighboring tiles (starting to move right and down) for the same property and thus measures the ladder width
        and height (in tiles)

        :return: list of generated Ladder objects
        :rtype: List[Ladder]
        """
        ladders = []
        # loop through each tile and look for ladder type property
        for y in range(self.pytmx_layer.height):
            for x in range(self.pytmx_layer.width):
                tile_sprite = self.tile_sprites[(x, y)]  # type: TileSprite
                if not tile_sprite:
                    continue
                props = tile_sprite.tile_props
                # we hit the upper left corner of a ladder
                if props.get("type") == "ladder":
                    tile_left = self.tile_sprites[(x-1, y)]  # type: TileSprite
                    tile_top = self.tile_sprites[(x, y-1)]  # type: TileSprite
                    if (tile_left and tile_left.tile_props.get("type") == "ladder") or (tile_top and tile_top.tile_props.get("type") == "ladder"):
                        continue
                    # measure width and height
                    w = 1
                    h = 1
                    x2 = x+1
                    while True:
                        ts = self.tile_sprites[(x2, y)]
                        if not (ts and ts.tile_props.get("type") == "ladder"):
                            break
                        w += 1
                        x2 += 1

                    y2 = y+1
                    while True:
                        ts = self.tile_sprites[(x, y2)]
                        if not (ts and ts.tile_props.get("type") == "ladder"):
                            break
                        h += 1
                        y2 += 1

                    # insert new Ladder
                    ladders.append(Ladder(x * self.pytmx_tiled_map.tilewidth, y * self.pytmx_tiled_map.tileheight,\
                                          w * self.pytmx_tiled_map.tilewidth, h * self.pytmx_tiled_map.tileheight))
        return ladders


class TileSprite(Sprite):
    """
    class used by TiledTileLayer objects to have a means of representing single tiles in terms of Sprite objects
    (used for collision detector function)
    """
    def __init__(self, layer, pytmx_tiled_map, id_, tile_props, rect):
        """
        :param TiledTileLayer layer: the TiledTileLayer object to which this tile belongs
        :param pytmx.pytmx.TiledMap pytmx_tiled_map: the tmx tiled-map object to which this tile belongs
                                                     (useful to have to look up certain map-side properties, e.g. tilewidth/height)
        :param int id_: tthe ID of the tile in the layer
        :param dict tile_props: the properties dict of this tile (values already translated into python types)
        :param Union[pygame.Rect,None] rect: the pygame.Rect representing the position and size of the tile
        """
        super().__init__(rect.x, rect.y, width_height=(rect.width, rect.height))
        self.tiled_tile_layer = layer
        self.pytmx_tiled_map = pytmx_tiled_map
        self.tile = id_
        self.tile_x = self.rect.x // self.pytmx_tiled_map.tilewidth
        self.tile_y = self.rect.y // self.pytmx_tiled_map.tileheight
        self.tile_props = tile_props


class SlopedTileSprite(TileSprite):
    """
    a TileSprite that supports storing some temporary calculations about a slope in the tile and its relation to a Sprite that's currently colliding
    with the TileSprite
    - used by the PlatformerPhysics Component when detecting and handling slope collisions
    """
    def __init__(self, layer, pytmx_tiled_map, id_, tile_props, rect):
        """
        :param TiledTileLayer layer: the TiledTileLayer object to which this tile belongs
        :param pytmx.pytmx.TiledMap pytmx_tiled_map: the tmx tiled-map object to which this tile belongs
                                                     (useful to have to look up certain map-side properties, e.g. tilewidth/height)
        :param int id_: tthe ID of the tile in the layer
        :param dict tile_props: the properties dict of this tile (values already translated into python types)
        :param Union[pygame.Rect,None] rect: the pygame.Rect representing the position and size of the tile
        """
        super().__init__(layer, pytmx_tiled_map, id_, tile_props, rect)
        # slope properties of the tile
        self.slope = tile_props.get("slope", None)  # the slope property of the tile in the tmx file (inverse steepness (1/m in y=mx+b) of the line that defines the slope)
        self.offset = tile_props.get("offset", None)  # the offset property of the tile in the tmx file (in px (b in y=mx+b))
        self.is_full = (self.slope == 0.0 and self.offset == 1.0)  # is this a full collision tile?
        self.max_x = self.pytmx_tiled_map.tilewidth
        self.max_y = max(self.get_y(0.0), self.get_y(self.rect.width))  # store our highest y-value (height of this tile)

    def get_y(self, x):
        """
        calculates the y value (in normal cartesian y-direction (positive values on up axis)) for a given x-value

        :param int x: the x-value (x=0 for left edge of tile x=tilewidth for right edge of tile)
        :return: the calculated y-value
        :rtype: int
        """
        # y = mx + b
        if self.slope is None or self.offset is None:
            return 0
        return self.slope * min(x, self.max_x) + self.offset * self.rect.height

    def sloped_xy_pull(self, sprite):
        """
        applies a so-called xy-pull on a Sprite object moving in x-direction in this sloped tile
        - an xy-pull is a change in the y-coordinate because of the x-movement (sliding up/down a slope while moving left/right)

        :param Sprite sprite: the Sprite object that's moving on the slope
        """
        if self.slope == 0:
            return
        # the local x value for the Sprite on the tile's internal x-axis (0=left edge of tile)
        x_local = max(0, (sprite.rect.left if self.slope < 0 else sprite.rect.right) - self.rect.left)
        # the absolute y-position that we will force the sprite into
        y = self.rect.bottom - self.get_y(x_local) - sprite.rect.height
        sprite.move(None, y, absolute=True)


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
            if obj.type:
                match_obj = re.fullmatch('^((.+)\.)?(\w+)$', obj.type)
                assert match_obj, "ERROR: type field ({}) of object in pytmx.pytmx.TiledObjectGroup does not match pattern!".format(obj.type)
                _, module_, class_ = match_obj.groups(default="__main__")  # if no module given, assume a class defined in __main__

                # get other kwargs for the Sprite's c'tor
                kwargs = {}
                for key, value in obj_props.items():
                    # special cases
                    # a spritesheet (filename)
                    if key == "tsx":
                        kwargs["sprite_sheet"] = SpriteSheet("data/" + value + ".tsx")
                    elif key == "img":
                        kwargs["image_file"] = "images/" + value + ".png"
                    # vanilla kwarg
                    else:
                        kwargs[key] = convert_type(value)

                # generate the Sprite
                ctor = getattr(sys.modules[module_], class_, None)
                assert ctor, "ERROR: python class `{}` for object in object-layer `{}` not defined!".format(class_, self.pytmx_layer.name)
                sprite = ctor(obj.x, obj.y, **kwargs)
                # add the do_render and render_order to the new instance
                sprite.do_render = (obj_props.get("do_render", "true") == "true")  # the default for objects is true
                if sprite.do_render:
                    sprite.render_order = int(obj_props.get("render_order", 50))  # the default for objects is 50
                self.sprite_group.add(sprite)


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
        self.separate = [0, 0]  # (-distance * normal_x, -distance * normal_y) how much to we have to change x/y values for rect to separate the two sprites
        self.direction = None  # None, 'x' or 'y' (direction in which we measure the collision; the other direction is ignored)
        self.direction_veloc = 0  # velocity direction component (e.g. direction=='x' veloc==5 -> moving right, veloc==-10.4 -> moving left)
        self.original_pos = [0, 0]  # the original x/y-position of sprite1 before the move that lead to the collision happened

    def invert(self):
        """
        inverts this Collision in place to yield the Collision for the case that the two Sprites are switched
        """
        # flip the sprites
        tmp = self.sprite1
        self.sprite1 = self.sprite2
        self.sprite2 = tmp
        # invert the normal and separate (leave distance negative, leave magnitude positive)
        self.normal_x = -self.normal_x
        self.normal_y = -self.normal_y
        self.separate = [-self.separate[0], -self.separate[1]]
        # the direction veloc
        self.direction_veloc = -self.direction_veloc


class PlatformerCollision(Collision):
    """
    a collision object that can be used by PlatformerPhysics to handle Collisions
    """

    def __init__(self):
        super().__init__()
        self.impact = 0.0  # the impulse of the collision on some mass (used for pushing heavy objects)

        # OBSOLETE: these should all be no longer needed
        # self.slope = False  # whether this is a collision with a sloped TileSprite of a TiledTileLayer
                            # (will also be False if obj1 collides with the Tile's rect, but obj1 is still in air (slope))
        # self.slope_y_pull = 0  # amount of y that Sprite has to move up (negative) or down (positive) because of the collision (with a slope)
        #self.slope_up_down = 0  # 0=no slope, -1=down slope, 1 = up slope


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


class Brain(Component, metaclass=ABCMeta):
    """
    a generic Brain class that has a command dict for other classes to be able to look up what the brain currently wants
    - also has a main-switch to activate/deactivate the Brain
    - should implement `tick` method and set self.commands each tick
    """
    def __init__(self, name, commands):
        super().__init__(name)

        self.is_active = True  # main switch: if False, we don't do anything
        self.commands = { command: False for command in commands }  # the commands coming from the brain (e.g. `jump`, `sword`, `attack`, etc..)

        self.game_obj_cmp_anim = None  # our GameObject's Animation Component (if any); needed for animation flags

    def added(self):
        # call our own tick method when event "pre_tick" is triggered on our GameObject
        self.game_object.on_event("pre_tick", self, "tick", register=True)
        # search for an Animation component
        self.game_obj_cmp_anim = self.game_object.components.get("animation")

    def reset(self):
        """
        sets all commands to False
        """
        for key in self.commands:
            self.commands[key] = False

    def activate(self):
        """
        makes this Brain active: we will react to the GameLoop's keyboard events
        """
        self.is_active = True

    def deactivate(self):
        """
        makes this Brain inactive: we will not(!) react to the GameLoop's keyboard events (no exceptions)
        """
        self.is_active = False
        self.reset()  # set all commands to False

    @abstractmethod
    def tick(self, game_loop):
        pass


class KeyboardBrainTranslation(object):
    # key-to-command flags
    NORMAL = 0x0  # normal: when key down -> command is True (this is essentially: DOWN_LEAVE_UP_LEAVE)
    DOWN_ONE_TICK = 0x1  # when key down -> command is True for only one tick (after that, key needs to be released to fire another command)
    DOWN_ONE_TICK_UP_ONE_TICK = 0x2  # when key down -> command is x for one frame; when key gets released -> command is y for one frame
    DOWN_LEAVE_UP_ONE_TICK = 0x4  # when key down -> command is x (and stays x); when key gets released -> command is y for one frame

    def __init__(self, key, command, other_command=None, flags=0):
        """
        :param str key: the key's description, e.g. `up` for K_UP
        :param str command: the `main` command's description; can be any string e.g. `fire`, `jump`
        :param str other_command: a possible second command associated with the key (when key is released, e.g. `release_bow`)
        :param int flags: keyboard-command behavior flags
        """
        self.key = key  # the
        self.command = command
        self.other_command = other_command
        self.flags = flags


class HumanPlayerBrain(Brain):
    """
    a Brain child class that handles agent control (via the GameLoop´s keyboard registry)
    - supports special keyboard->command translations (e.g. key down -> command A for one tick; key up -> command B for one tick)
    """

    def __init__(self, name, key_brain_translations):
        """
        :param str name: the name of this component
        :param Union[list,None] key_brain_translations: list of KeyboardBrainTranslation objects or None
        """
        commands = []
        # build our key_brain_translation dict to translate key inputs into commands
        if key_brain_translations is None:
            key_brain_translations = []

        self.key_brain_translations = {}
        for trans in key_brain_translations:
            if isinstance(trans, str):
                self.add_translation(KeyboardBrainTranslation(trans, trans))
                commands.append(trans)
            elif isinstance(trans, KeyboardBrainTranslation):
                self.add_translation(trans)
                commands.append(trans.command)
                if trans.other_command:
                    commands.append(trans.other_command)
            elif isinstance(trans, tuple):
                self.add_translation(KeyboardBrainTranslation(*trans))
                commands.append(trans[1])
                if trans[2]:
                    commands.append(trans[2])
            elif isinstance(trans, dict):
                self.add_translation(KeyboardBrainTranslation(**trans))
                commands.append(trans["command"])
                if "other_command" in trans:
                    commands.append(trans["other_command"])

        # now that command list is ready -> send everything to super
        super().__init__(name, commands)

        self.keyboard_prev = {}  # stores the values of the keyboard_inputs in the previous tick (to catch changes in the keyboard state)

        self.is_paralyzed = False  # is this brain paralyzed? (e.g. when agent is dizzy)
        self.paralyzed_exceptions = None  # keys that are still ok to be handled, even if paralyzed

    def add_translation(self, key_brain_translation):
        """
        adds a single KeyboardBrainTranslation object to our dict
        :param KeyboardBrainTranslation key_brain_translation: the translation to be added
        """
        assert key_brain_translation.key not in self.key_brain_translations, "ERROR: key {} already in key_brain_translations dict!".\
            format(key_brain_translation.key)
        self.key_brain_translations[key_brain_translation.key] = key_brain_translation

    def remove_translation(self, key):
        """
        adds a single KeyboardBrainTranslation object to our dict
        :param str key: the key (str) to be removed from our key-to-command translation dict
        """
        self.key_brain_translations.pop(key, None)

    # for now, just translate keyboard_inputs from GameLoop object into our commands
    def tick(self, game_loop: GameLoop):
        # main switch is set to OFF
        if not self.is_active:
            return

        # update current animation flags
        if self.game_obj_cmp_anim:
            self.is_paralyzed = bool(self.game_obj_cmp_anim.flags & Animation.ANIM_PARALYZES)
            self.paralyzed_exceptions = self.game_obj_cmp_anim.paralyzed_exceptions

        # first reset everything to False
        self.reset()

        # current animation does not block: normal commands possible
        for key_code, is_pressed in game_loop.keyboard_inputs.keyboard_registry.items():
            # look up the str description of the key
            desc = game_loop.keyboard_inputs.descriptions[key_code]
            # we are either not paralyzed, or the key is in the exception list
            if self.is_paralyzed and desc not in self.paralyzed_exceptions:
                continue
            # look up the key-to-command translation rules
            rule = self.key_brain_translations[desc]
            # normal translation
            if rule.flags == KeyboardBrainTranslation.NORMAL:
                self.commands[rule.command] = is_pressed
            # key is currently down
            elif is_pressed:
                # if we don't repeat the command -> check whether this press is new and only then set the command
                if rule.flags & (KeyboardBrainTranslation.DOWN_ONE_TICK | KeyboardBrainTranslation.DOWN_ONE_TICK_UP_ONE_TICK):
                    self.commands[rule.command] = (self.keyboard_prev[desc] is False)
                    if rule.flags & KeyboardBrainTranslation.DOWN_ONE_TICK_UP_ONE_TICK:
                        self.commands[rule.other_command] = False
                else:
                    self.commands[rule.command] = True
            # key is currently up
            else:
                # we fire a single-tick other_command if the key has just been released
                if rule.flags & KeyboardBrainTranslation.DOWN_ONE_TICK_UP_ONE_TICK:
                    self.commands[rule.other_command] = (self.keyboard_prev[desc] is True)
                else:
                    self.commands[rule.command] = False

            # update keyboard_prev dict
            self.keyboard_prev[desc] = is_pressed


class AIBrain(Brain):
    def __init__(self, name):
        super().__init__(name, ["left", "right"])
        self.flipped = False  # if True: character is turning left

    def added(self):
        super().added()

        self.game_object.on_event("bump.right", self, "toggle_direction", register=True)
        self.game_object.on_event("bump.left", self, "toggle_direction", register=True)

    def tick(self, game_loop):
        # dt = game_loop.dt
        obj = self.game_object

        self.reset()

        if self.cmp_animation and self.cmp_animation.flags & Animation.ANIM_PARALYZES:
            return

        # look for edges ahead -> then change direction if one is detected
        # - makes sure an enemy character does not fall off a cliff
        if (not (game_loop.frame % 3) and self.check_cliff_ahead()) or obj.rect.x <= 0 or obj.rect.x >= obj.cmp_physics.x_max:
            self.toggle_direction()

        self.commands["left" if self.flipped else "right"] = True

    def toggle_direction(self):
        self.flipped = False if self.flipped else True

    # checks whether there is a cliff ahead (returns true if yes)
    def check_cliff_ahead(self):
        obj = self.game_object
        tile_h = obj.stage.screen.tmx_object.tile_h
        # check below character (c=character sprite, _=locateObject (a stripe with x=x width=w-6 and height=3))
        # ccc    -> walking direction
        # ccc
        #  _
        col = obj.stage.locate(obj.rect.left if self.flipped else obj.rect.right,
                               obj.rect.bottom + tile_h * 0.75,
                               obj.rect.width - 6,
                               tile_h * 1.5,
                               Sprite.get_type("default,ladder"))
        if not col:  # or (col.tileprops and col.tileprops['liquid']):
            return True
        return False

    # checks whether an enemy is in sight
    def check_enemy_ahead(self):
        pass


class Animation(Component):
    # static animation-properties registry
    # - stores single animation records (these are NOT Animation objects, but simple dicts representing settings for single animation sequences)
    animation_settings = {}

    # some flags
    # TODO: make these less Viking-dependent (implement similar 'type'-registry as for Sprites' collisions)
    ANIM_NONE = 0x0
    ANIM_SWING_SWORD = 0x1
    ANIM_PARALYZES = 0x2
    ANIM_PROHIBITS_STAND = 0x4  # anims that should never be overwritten by 'stand'(even though player might not x - move)
    ANIM_BOW = 0x8
    # if set: this animation does not change the Sprite's image depending on time, but they have to be set manually via the
    # frame property of the Animation component (which gives the SpriteSheet's frame, not the anim_settings frame-slot)
    ANIM_SET_FRAMES_MANUALLY = 0x10


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
                        "next"         : None,  # which animation to play next (str or callable returning a str)
                        "next_priority": -1,  # which priority to use for next if next is given
                        "trigger"      : None,  # which events to trigger on the game_object that plays this animation
                        "trigger_data" : None,  # data to pass to the event handler if trigger is given
                        "paralyzed_exceptions" : set(),  # ??? can override DISABLE_MOVEMENT setting only for certain keys
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
        self.animation = None  # str: we are playing this animation; None: we are undefined -> waiting for the next anim setup
        self.rate = 1 / 3  # default rate in s
        self.has_changed = False
        self.priority = -1  # animation priority (takes the value of the highest priority animation that wants to be played simultaneously)
        self.frame = 0  # the current frame in the animation 'frames' list OR: if self.animation is None: this is the actual frame from the SpriteSheet
        self.time = 0  # the current time after starting the animation in s
        self.flags = 0
        self.paralyzed_exceptions = set()  # set of key descriptors (e.g. "up", "down") for which an animation's paralyzed-flag does not count
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
        if self.animation and not self.flags & Animation.ANIM_SET_FRAMES_MANUALLY:
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
                        # `next` could be a callable as well returning a str to use as animation setting
                        if anim_settings["next"]:
                            self.play_animation(obj, (anim_settings["next"]() if callable(anim_settings["next"]) else anim_settings["next"]),
                                                anim_settings["next_priority"])
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
            # manual animation -> frame in SpriteSheet directly set manually
            if self.flags & Animation.ANIM_SET_FRAMES_MANUALLY:
                obj.image = tiles_dict[int(self.frame)]
            # automatic animation: self.frame is the slot in the animation's frame list (not the SpriteSheet's!)
            else:
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
            # look up animation in list
            anim_settings = Animation.get_settings(game_object.spritesheet.name, name)
            assert anim_settings, "ERROR: animation-to-play (`{}`) not found in spritesheet settings `{}`!".format(name, game_object.spritesheet.name)

            comp.animation = name
            comp.has_changed = True
            comp.time = 0
            comp.frame = 0  # start each animation from 0
            comp.priority = priority

            # set flags to sprite's properties
            comp.flags = anim_settings["flags"]
            comp.paralyzed_exceptions = anim_settings["paralyzed_exceptions"]

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
        self.docked_sprites = set()  # set that holds all Sprites (by GameObject id) currently docked to this one
        # holds the objects that we stand on and stood on previously:
        # slot 0=current state; slot 1=previous state (sometimes we need the previous state since the current state gets reset to 0 every step)
        self.docking_state = 0
        self.docked_to = None  # the reference to the object that we are currently docked to

    def added(self):
        # make sure our GameObject is a Sprite
        assert isinstance(self.game_object, Sprite), "ERROR: game_object of Component Dockable must be of type Sprite (not {})!". \
            format(type(self.game_object).__name__)
        # extend our GameObject with move (thereby overriding the Sprite's move method)
        self.extend(self.move)

    def move(self, sprite, x, y, precheck=False, absolute=False):
        """
        this will 'overwrite' the normal Sprite's `move` method by Component's extend
        - if precheck is set to True: pre-checks the planned move via call to stage.locate and only moves entity as far as possible

        :param Sprite sprite: the GameObject that this Component belongs to (the Sprite to move around)
        :param Union[int,None] x: the amount in pixels to move in x-direction
        :param Union[int,None] y: the amount in pixels to move in y-direction
        :param bool precheck: ???
        :param bool absolute: whether x and y are given as absolute coordinates (default: False): in this case x/y=None means do not move in this dimension
        """

        #if precheck:
        #    testcol = self.stage.locate(p.x+x, p.y+y, Q._SPRITE_DEFAULT, p.w, p.h);
        #    if ((!testcol) || (testcol.tileprops && testcol.tileprops['liquid'])) {
        #        return True
        #
        #    return False

        orig_x = sprite.rect.x
        orig_y = sprite.rect.y

        # absolute coordinates given
        if absolute:
            if x is not None:
                sprite.rect.x = x
            if y is not None:
                sprite.rect.y = y
        # do a minimum of 1 pix (if larger 0.0)
        else:
            if 0 < x < 1:
                x = 1
            sprite.rect.x += x
            if 0 < y < 1:
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
        if not absolute:
            for docked_sprite in self.docked_sprites:
                docked_sprite.move(x, y, absolute=absolute)
        else:
            # translate into relative movement: we don't want the docked components to move to the given mothership's absolute values
            x_move = x - orig_x if x is not None else 0
            y_move = y - orig_y if y is not None else 0
            for docked_sprite in self.docked_sprites:
                docked_sprite.move(x_move, y_move)

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
        # remove docked obj from mothership docked-obj-list (if present)
        if self.docked_to and "dockable" in self.docked_to.components:
            print("removing {} (id {}) from mothership {}".format(type(obj).__name__, obj.id, type(self.docked_to).__name__))
            self.docked_to.components["dockable"].docked_sprites.discard(obj.id)
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
        :return: True if the current state is definitely docked OR (to-be-determined AND previous state was docked)
        :rtype: bool
        """
        return bool(self.docking_state & Dockable.DEFINITELY_DOCKED or
                    (self.docking_state & Dockable.TO_BE_DETERMINED and self.docking_state & Dockable.PREVIOUSLY_DOCKED))

    def state_unsure(self):
        """
        :return: True if our current docking state is not 100% sure (TO_BE_DETERMINED)
        :rtype: bool
        """
        return bool(self.docking_state & Dockable.TO_BE_DETERMINED)


class PhysicsComponent(Component, metaclass=ABCMeta):
    """
    defines an abstract generic physics component that can be added to agents (or enemies) to behave in the world
    - GameObject's that own this Comonent may have a Brain component as well in order to steer behavior of the agent in `tick`
    - needs to override `tick` and `collision`
    """

    @staticmethod
    def tile_sprite_handler(tile_sprite_class, layer):
        """
        populates the tile_sprites dict of a TiledTileLayer with tile_sprite_class (e.g. TileSprite or SlopedTileSprite) objects

        :param TiledTileLayer layer: the TiledTileLayer, whose tiles we would like to process and store (each one) in the returned np.ndarray
        :param type tile_sprite_class: the TiledSprite subclass to use for generating TileSprite objects
        :return: a 2D np.ndarray (x,y) with the created TileSprite objects for each x/y coordinate (None if there is no tile at a position)
        :rtype: np.ndarray (2D)
        """
        # set up ndarray
        ret = np.ndarray(shape=(layer.pytmx_tiled_map.width, layer.pytmx_tiled_map.height), dtype=tile_sprite_class)
        # loop through each tile and generate TileSprites
        for x, y, gid in layer.pytmx_layer.iter_data():
            # skip empty tiles (gid==0)
            if gid == 0:
                continue
            tile_props = layer.pytmx_tiled_map.get_tile_properties_by_gid(gid) or {}
            # go through dict and translate data types into proper python types ("true" -> bool, 0.0 -> float, etc..)
            for key, value in tile_props.items():
                value = convert_type(value)
                tile_props[key] = value

            ret[x,y] = tile_sprite_class(layer, layer.pytmx_tiled_map, gid, tile_props,
                                        pygame.Rect(x * layer.pytmx_tiled_map.tilewidth, y * layer.pytmx_tiled_map.tileheight,
                                                    layer.pytmx_tiled_map.tilewidth, layer.pytmx_tiled_map.tileheight))
        return ret

    # probably needs to be extended further by child classes
    def added(self):
        obj = self.game_object

        obj.on_event("pre_tick", self, "tick", register=True)  # run this component's tick function after GameObject's one (so we can react to the GameObject's move)
        obj.on_event("collision", self, "collision", register=True)  # handle collisions

        # flag the GameObject as "handles collisions itself"
        self.game_object.handles_own_collisions = True

    # may determine x/y-speeds and movements of the GameObject (gravity, etc..)
    @abstractmethod
    def tick(self, game_loop: GameLoop):
        pass

    @abstractmethod
    def collision(self, col):
        """
        this is the resolver for a Collision that happened between two Sprites under this PhysicsComponent

        :param Collision col: the Collision object describing the collision that already happened between two sprites
        """
        pass


class ControlledPhysicsComponent(PhysicsComponent, metaclass=ABCMeta):
    """
    when added to a GameObject, adds a HumanPlayerBrain Component automatically to the GameObject
    """
    def __init__(self, name):
        super().__init__(name)
        self.game_obj_cmp_brain = None  # the GameObject's HumanPlayerBrain component (used by Physics for steering and action control within `tick` method)

    def added(self):
        super().added()
        self.game_obj_cmp_brain = self.game_object.components.get("brain", None)
        # if there is a 'brain' component in the GameObject it has to be of type HumanPlayerBrain
        assert not self.game_obj_cmp_brain or isinstance(self.game_obj_cmp_brain, Brain), "ERROR: GameObject's `brain` Component is not of type Brain!"

        # run this component's tick function after GameObject's one (so we can react to the GameObject's move)
        self.game_object.on_event("pre_tick", self, "tick", register=True)


class TopDownPhysics(ControlledPhysicsComponent):
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

    def added(self):
        super().added()

        obj = self.game_object
        self.x_max -= obj.rect.width
        self.y_max -= obj.rect.height

        obj.register_event("bump.top", "bump.bottom", "bump.left", "bump.right")  # we will trigger these as well -> register them

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

                # then do the type=='default' (collision) layer(s)
                for layer in stage.tiled_tile_layers.values():
                    if layer.type & Sprite.get_type("default"):
                        layer.collide(obj, 'x', self.vx)

            # then move in y-direction and solve y-collisions
            if self.vy != 0.0:
                obj.move(0.0, self.vy * dt)
                if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_BEFORE_COLLISION_DETECTION:
                    obj.render(game_loop.display)
                    game_loop.display.debug_refresh()

                # then do the type=='default' (collision) layer(s)
                for layer in stage.tiled_tile_layers.values():
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
        obj.rect.x += col.separate[0]
        obj.rect.y += col.separate[1]

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


class PlatformerPhysics(ControlledPhysicsComponent):
    """
    defines "The Lost Vikings"-like game physics
    - to be addable to any character (player or enemy)
    """

    # used repeatedly (recycle) for collision detection information being passed between the CollisionAlgorithm object and the physics Copmonents
    collision_objects = (PlatformerCollision(), PlatformerCollision())

    @staticmethod
    def get_highest_tile(tiles, direction, start_abs, end_abs):
        """
        returns the `highest` tile in a list (row or column) of sloped, full-collision or empty tiles

        :param list tiles: the list of tiles to check
        :param str direction: the direction in which the list of tiles is arranged (`x`=row of tiles or `y`=column of tiles)
        :param int start_abs: the absolute leftmost x-value from where to check
        :param int end_abs: the absolute rightmost x-value from where to check
        :return: a tuple consisting of a) the highest SlopedTileSprite found in the list and b) the height value measured on a cartesian y-axis (positive=up)
        :rtype: Tuple[SlopedTileSprite,int]
        """
        # start with leftmost tile (measure max height for the two x points: sprite's leftmost edge and tile's right edge)
        best_tile = None  # the highest tile in this row (if not height==0.0)
        tile = tiles[0]
        if tile:
            max_y = max(tile.get_y(start_abs - tile.rect.left), tile.get_y(tile.rect.width))
            best_tile = tile
        else:
            max_y = 0

        # then do all center tiles
        for slot in range(1, len(tiles) - 1):
            tile = tiles[slot]
            max_ = tile.max_y if tile else 0
            if max_ > max_y:
                max_y = max_
                best_tile = tile

        # then do the rightmost tile (max between tiles left edge and sprite's right edge)
        tile = tiles[-1]
        max_ = max(tile.get_y(end_abs - tile.rect.left), tile.get_y(0)) if tile else 0

        if max_ > max_y:
            max_y = max_
            best_tile = tile

        # TODO: store x-in and y-pull(push) in tile props (as temporary values)
        return best_tile, max_y

    def __init__(self, name="physics"):
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
        # set to a value > 0 to define the squeezeSpeed at which this object gets squeezed by heavy objects (objects with is_heavy == True)
        self.squeeze_speed = 0
        # if an up-slope (e.g. 20°) does not reach it full-tiled right neighbor, would a sprite treat this as stairs and still climb up the full-tile
        self.allow_stairs_climb = True

        # environment stuff (TODO: where to get Level dimensions from?)
        self.x_min = 0  # the minimum/maximum allowed positions
        self.y_min = 0
        self.x_max = 9000
        self.y_max = 9000

        # self.touching = 0  # bitmap with those bits set that the entity is currently touching (colliding with)
        self.at_exit = False
        self.at_wall = False
        self.on_ladder = 0  # 0 if GameObject is not locked into a ladder; y-pos of obj, if obj is currently locked into a ladder (in climbing position)
        self.touched_ladder = None  # holds the ladder Sprite, if player is currently touching a ladder sprite, otherwise: 0
        self.climb_frame_value = 0  # int([climb_frame_value]) determines the frame to use to display climbing position

        self.game_obj_cmp_dockable = None  # type: Dockable; the GameObject's Dockable component (that we will add to the GameObject ourselves)

    def added(self):
        super().added()

        obj = self.game_object
        self.x_max -= obj.rect.width
        self.y_max -= obj.rect.height

        # add the Dockable Component to our GameObject (we need it this for us to work properly)
        self.game_obj_cmp_dockable = obj.add_component(Dockable("dockable"))

        # add default and ladder to the collision mask of our GameObject
        obj.collision_mask |= Sprite.get_type("default,ladder")

    def lock_ladder(self):
        """
        locks the GameObject into a ladder
        """
        obj = self.game_object
        self.on_ladder = obj.rect.y
        # switch off gravity
        self.gravity = False
        # lock obj to center of ladder (touched_ladder is always set to the one we are touching right now)
        obj.rect.centerx = self.touched_ladder.rect.centerx
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
                    obj.flip['x'] = True  # mirror other_sprite

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
                    if obj.rect.bottom <= self.touched_ladder.rect.top:
                        self.unlock_ladder()
                    else:
                        self.vy = -self.climb_speed
                # player locks into ladder
                elif self.touched_ladder and self.touched_ladder.rect.bottom >= obj.rect.bottom > self.touched_ladder.rect.top:
                    self.lock_ladder()
            # user is pressing only 'down' (ladder?)
            elif self.game_obj_cmp_brain.commands["down"]:
                if self.on_ladder > 0:
                    # we reached the bottom of the ladder -> lock out of ladder
                    if obj.rect.bottom >= self.touched_ladder.rect.bottom:
                        self.unlock_ladder()
                    # move down
                    else:
                        self.vy = self.climb_speed
                elif self.touched_ladder and obj.rect.bottom < self.touched_ladder.rect.bottom and dockable.is_docked():
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
            self.vx += ax * dt
            if abs(self.vx) > self.vx_max:
                self.vx = math.copysign(self.vx_max, self.vx)
            if self.gravity:
                self.vy += self.gravity_y * dt
            if abs(self.vy) > self.max_fall_speed:
                self.vy = math.copysign(self.max_fall_speed, self.vy)

            # reset all touch flags before doing all the collision analysis
            if self.vx != 0.0 or self.vy != 0.0:
                # self.slope_up_down = 0
                if self.on_ladder == 0:
                    self.touched_ladder = None
                self.at_wall = False
                self.at_exit = False
                # make docked state undetermined for now until we know more after the move + collision-detection
                dockable.to_determine()  # we still keep in memory that we have been docked before and who we were docked to

            # first move in x-direction and solve x-collisions
            orig_pos = (obj.rect.x, obj.rect.y)
            if self.vx != 0.0:
                sx = self.vx * dt
                obj.move(sx, 0.0)
                # if we were docked to a slope -> move y component according to that slope's shape independent of y-speed
                # (and then still do the normal y-movement)
                floor = dockable.docked_to
                if isinstance(floor, SlopedTileSprite) and floor.slope != 0:
                    floor.sloped_xy_pull(obj)
                if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_BEFORE_COLLISION_DETECTION:
                    obj.render(game_loop.display)
                    game_loop.display.debug_refresh()
                self.collide_in_one_direction(obj, "x", self.vx, orig_pos)

            # then move in y-direction and solve y-collisions
            if self.vy != 0.0:
                obj.move(0.0, self.vy * dt)
                if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_BEFORE_COLLISION_DETECTION:
                    obj.render(game_loop.display)
                    game_loop.display.debug_refresh()
                self.collide_in_one_direction(obj, "y", self.vy, orig_pos)
                # we are still not sure about our docked state after y-movement -> confirm undock us
                if self.game_obj_cmp_dockable.state_unsure():
                    self.game_obj_cmp_dockable.undock()

            dt_step -= dt

    def collide_in_one_direction(self, sprite, direction, direction_veloc, original_pos):
        """
        detects and solves all possible collisions between our GameObject and all Stage's objects (layers and Sprites) in one direction (x or y)

        :param Sprite sprite: the GameObject of this Component (the moving/colliding Sprite)
        :param str direction: either "x" or "y"
        :param float direction_veloc: the velocity in the given direction (x/y-component of the velocity vector)
        :param Tuple[int,int] original_pos: the position of the game_object before this collision detection execution
        """
        stage = sprite.stage

        # default layers
        if sprite.collision_mask & Sprite.get_type("default"):
            for layer in stage.tiled_tile_layers.values():
                if layer.type & Sprite.get_type("default"):
                    self.collide_with_collision_layer(sprite, layer, direction, direction_veloc, original_pos)
        # simple sprites (e.g. enemies)
        for other_sprite in stage.sprites:
            if sprite is other_sprite:
                continue
            if sprite.collision_mask & other_sprite.type:
                col = AABBCollision.collide(sprite, other_sprite, direction=direction, direction_veloc=direction_veloc, original_pos=original_pos)
                if col:
                    sprite.trigger_event("collision", col)
        # TODO: non-default layers (touch?)
        # for layer in stage.tiled_tile_layers.values():
        #    if not layer.type & Sprite.get_type("default") and sprite.collision_mask & layer.type:
        #        layer.collide(sprite, direction, direction_veloc, original_pos)

    def collide_with_collision_layer(self, sprite, layer, direction, direction_veloc, original_pos):
        """
        collides a Sprite with a collision TiledTileLayer (type==default) and solves all detected collisions
        - supports slopes of all shapes (given y = mx + b parameterized)
        - certain restrictions apply for the tiled landscape for this algorithm to work:
        -- no upside-down slopes allowed (slopes on the ceiling)
        -- TODO: what other restrictions?

        :param Sprite sprite: the Sprite to test for collisions against a TiledTileLayer
        :param TiledTileLayer layer: the TiledTileLayer object in which to look for collision tiles (full of sloped)
        :param str direction: `x` or `y` direction in which the sprite is currently moving before this test
        :param float direction_veloc: the velocity in the given direction (could be negative or positive)
        :param Tuple[int,int] original_pos: the position of the sprite before the move that caused this collision test to be executed
        """
        # determine the tile boundaries (which tiles does the sprite overlap with?)
        tile_start_x = max(0, sprite.rect.left // layer.pytmx_tiled_map.tilewidth)
        tile_end_x = min(layer.pytmx_tiled_map.width - 1, (sprite.rect.right - 1) // layer.pytmx_tiled_map.tilewidth)
        tile_start_y = max(0, sprite.rect.top // layer.pytmx_tiled_map.tileheight)
        tile_end_y = min(layer.pytmx_tiled_map.height - 1, (sprite.rect.bottom - 1) // layer.pytmx_tiled_map.tileheight)

        # if sprite is moving in +/-x-direction:
        # 1) move in columns from left to right (right to left) to look for full collision tiles
        # - if the 'stairs'-option is enabled: the full collision tile must not have any tile next to it (in negative direction_veloc direction)
        # that's an up-slope (towards the full collision tile)
        # - if the 'stairs'-option is disabled: the full collision tile must not have a slope=1/-1 tile next to it that's an up slope (towards the full
        # collision tile)
        # 2) if one found, move Sprite out of it and that's it
        # 3) move again from top to bottom and in each row look for the highest slope under the Sprite
        # 4) if on e found that's not 0-height -> process that (y-pull or y-push) and return
        if direction == 'x':
            # find full collision tiles (no reaching(!) slope neighbor in negative veloc direction)
            # - non-reaching slope neighbors are slopes whose highest point would not reach the full neighbor tile (is smaller than 1.0 * tileheight)
            direction_x = int(math.copysign(1.0, direction_veloc))
            for tile_x in range(tile_start_x if direction_x > 0 else tile_end_x, (tile_end_x if direction_x > 0 else tile_start_x) + direction_x, direction_x):
                for tile_y in range(tile_start_y, tile_end_y + 1):  # y-order doesn't matter
                    tile_sprite = layer.tile_sprites[tile_x, tile_y]
                    # TODO: make this work for non-full slope==0 tiles (e.g. half tiles where top half is missing)
                    if tile_sprite and tile_sprite.is_full:
                        # is there a reaching slope in negative veloc direction? -> return the neighbor reaching slope tile instead
                        neighbor = layer.tile_sprites[(tile_x - direction_x), tile_y]
                        neighbor_border_y = neighbor.get_y(layer.pytmx_tiled_map.tilewidth if direction_x == 1 else 0) if neighbor else 0
                        # neighbor slope reaches til top of full tile OR neighbor slope-tile is at least 1px high and `stairs` option is enabled
                        # -> do a y-collision on the full tile with low vy (to avoid crash/high impact)
                        if neighbor_border_y > 0:
                            # neighbor slope reaches full tile OR stairs option enabled
                            if neighbor_border_y >= tile_sprite.offset * layer.pytmx_tiled_map.tileheight or self.allow_stairs_climb:
                                col = AABBCollision.collide(sprite, tile_sprite, self.collision_objects, "y", 0.1, original_pos)
                            # neighbor slope not high enough AND stairs option disabled -> 1) bump up sprite on slope 2) solve x-collision against full tile
                            else:
                                # make sure the sprite is bumped up on the neighbor up-slope (this may already be done by the xy-pull if vx is not too high)
                                if sprite.components["dockable"].is_docked():
                                    sprite.move(0.0, -(sprite.rect.bottom - (neighbor.rect.bottom - neighbor_border_y)))
                                # no stairs -> bump against full tile from the side
                                col = AABBCollision.collide(sprite, tile_sprite, self.collision_objects, direction, direction_veloc, original_pos)
                        # normal full-tile x-collision w/o neighbor slope
                        else:
                            col = AABBCollision.collide(sprite, tile_sprite, self.collision_objects, direction, direction_veloc, original_pos)

                        assert col, "ERROR: there must be a col returned from collision detector for tile {},{} neighbored by {},{}!".\
                            format(tile_sprite.tile_x, tile_sprite.tile_y, (neighbor.tile_x if neighbor else "none"), (neighbor.tile_y if neighbor else "none"))

                        sprite.trigger_event("collision", col)
                        return
            # keep looking below (same algo as positive y-direction (falling))

        # if sprite is moving up: only check for full collision tiles (no upside-down/ceiling slopes supported yet)
        elif direction_veloc < 0:
            for tile_y in range(tile_end_y, tile_start_y - 1, -1):
                for tile_x in range(tile_start_x, tile_end_x + 1):
                    tile_sprite = layer.tile_sprites[tile_x, tile_y]
                    if tile_sprite and tile_sprite.is_full:
                        col = AABBCollision.collide(sprite, tile_sprite, self.collision_objects, direction, direction_veloc, original_pos)
                        assert col, "ERROR: there must be a col returned from collision detector for tile {},{}!".format(tile_x, tile_y)
                        sprite.trigger_event("collision", col)
                        return
            # there was nothing above (no collision); have to return here not to go into following for-loop
            return

        # either no full tile found for x-direction search
        # OR
        # y-direction and veloc > 0:
        # move in rows from top to bottom, thereby - in each row - measuring the altitude of all tiles (slopes and full) and picking the
        # first highest tile in any row and then return after one highest tile (height >0 px) is found
        dockable = sprite.components["dockable"]
        is_docked = dockable.is_docked()

        for tile_y in range(tile_start_y, tile_end_y + 1):
            tiles_to_check = [layer.tile_sprites[tile_x, tile_y] for tile_x in range(tile_start_x, tile_end_x + 1)]
            (highest_tile, highest_height) = self.get_highest_tile(tiles_to_check, "x", sprite.rect.left, sprite.rect.right)
            # we found some high tile in this row -> process and return
            if highest_tile is not None:
                # y-direction (falling): deal with impact/docking/etc..
                if direction == "y":
                    col = AABBCollision.collide(sprite, highest_tile, self.collision_objects, direction, direction_veloc, original_pos)
                    assert col, "ERROR: there must be a col returned from collision detector (y) for tile {},{}!".format(highest_tile.tile_x, tile_y)
                    # fix our y-pull value via separate[1] (AABB does not know slopes, we have to adapt it to the slope's shape)
                    col.separate[1] = - (sprite.rect.bottom - (highest_tile.rect.bottom - highest_height))
                    # we were already docked on ground OR the y-pull is negative (up) -> real collision
                    if is_docked or col.separate[1] < 0:
                        sprite.trigger_event("collision", col)
                # x-direction and no xy-pull applied yet b/c we are looking at a different slope tile than the docked one before
                elif highest_tile is not dockable.docked_to:
                    # apply xy-pull to sprite (no collision)
                    highest_tile.sloped_xy_pull(sprite)
                    # dock to this new tile (only if we are not currently in air)
                    if is_docked:
                        dockable.dock_to(highest_tile)
                # keep docked tile the same
                elif is_docked:
                    dockable.dock_to(dockable.docked_to)

                return

    def collision(self, col):
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

        # colliding with a one-way-platform: can only collide when coming from the top
        # -> test early out here
        if other_obj.type & Sprite.get_type("one_way_platform"):
            # other object is a ladder as well
            if other_obj.type & Sprite.get_type("ladder"):
                # set touched_ladder to the ladder
                self.touched_ladder = other_obj
                # we are locked into a ladder
                if self.on_ladder > 0:
                    return
            # we are x-colliding with the one-way-platform OR y-colliding but not(!) with the top of the one-way-platform -> return
            if col.direction == "x" or (col.direction_veloc > 0 and (col.original_pos[1] + obj.rect.height) > other_obj.rect.top):
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

        # normal collision
        col.impact = 0.0

        impact_x = abs(self.vx)
        impact_y = abs(self.vy)

        # move away from the collision (back to where we were before)
        x_orig = obj.rect.x
        y_orig = obj.rect.y
        obj.rect.x += col.separate[0]
        obj.rect.y += col.separate[1]

        # bottom collision
        if col.normal_y < -0.3:
            # a heavy object hit the ground -> rock the stage
            if self.is_heavy and not dockable.is_docked() and other_obj.type & Sprite.get_type("default"):
                obj.stage.shake_viewport()

            other_obj_dockable = other_obj.components.get("dockable", None)

            # squeezing something
            if self.vy > 0 and isinstance(other_obj_physics, PlatformerPhysics) and self.is_heavy and other_obj_physics.squeeze_speed > 0 and \
                    other_obj_dockable and other_obj_dockable.is_docked():

                # adjust the collision separation to the new squeezeSpeed
                if self.vy > other_obj_physics.squeeze_speed:
                    obj.rect.y = y_orig - col.separate[1] * (other_obj_physics.squeeze_speed / self.vy)
                # otherwise, just undo the separation
                else:
                    obj.rect.y -= col.separate[1]

                self.vy = other_obj_physics.squeeze_speed
                other_obj.trigger_event("squeezed.top", obj)

            # normal bottom collision
            else:
                if self.vy > 0:
                    self.vy = 0
                col.impact = impact_y
                dockable.dock_to(other_obj)  # dock to bottom object (collision layer, MovableRock, Ladder (top), etc..)
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
        """
        pushes a pushable other GameObject (assuming that this other object also has a PlatformerPhysics Component)

        :param pusher: the Sprite that's actively pushing against the other GameObject
        :param col: the Collision object (that caused the push) returned by the collision detector method
        """

        pushee = col.sprite2  # correct? or does it need to be sprite1?
        ## what if normal_x is 1/-1 BUT: impact_x is 0 (yes, this can happen!!)
        ## for now: don't push, then
        #if col.impact > 0:

        pushee_phys = pushee.components["physics"]
        move_x = - col.separate[0] * abs(pushee_phys.vx_max / col.direction_veloc)

        # console.log("pushing Object: move_x="+move_x);
        # do a locate on the other side of the - already moved - pushable object
        # var testcol = pusher.stage.locate(pushee_p.x+move_x+(pushee_p.cx+1)*(p.flip ==   'x' ? -1 : 1), pushee_p.y, (Q._SPRITE_DEFAULT | Q._SPRITE_FRIENDLY | Q._SPRITE_ENEMY));
        # if (testcol && (! (testcol.tileprops && testcol.tileprops.slope))) {
        #	p.vx = 0; // don't move player, don't move pushable object
        # }
        # else {
        # move obj (plus all its docked objects) and move pusher along

        # TODO: if there is an obstacle on the other side of the pushee (e.g. a wall),
        # the pushee's collision detection method will trigger a collision event, in which case the pushee will
        # be moved back in which case


        # first move rock, then do a x-collision detection of the rock, then fix that collision (if any) -> only then move the pusher
        pushee.move(move_x, 0)
        pusher.move(move_x, 0)
        self.vx = math.copysign(pushee_phys.vx_max, col.direction_veloc)

        #else:
        #    self.vx = 0

    """OBSOLETE:
    @staticmethod
    def tile_layer_physics_collision_postprocessor(col):
        ""
        this postprocessor takes a detected collision and does slope checks on it
        - it them stores the results in the given PlatformerCollision object for further handling by the physics Component

        :param PlatformerCollision col: the collision object detected by the Layer
        :return: a post-processed collision object (adds slope-related calculations to the Collision object)
        :rtype: PlatformerCollision
        ""

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
        #col.slope_up_down = 0
        col.slope_y_pull = 0  # amount of y that Sprite has to move up (negative) or down (positive)

        # calculate y-pull based on pixels we are "in" the slope
        slope = tile.tile_props.get("slope", 0)  # -3, -2, -1, 1, 2, 3: negative=down, positive=up (1==45 degree slope, 3=15 degree slope)
        if slope != 0:
            offset = tile.tile_props.get("offset", 1)  # 1=first tile of the slope (when walking uphill), 2=second tile of the slope (when walking uphill), etc
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
            abs_slope = abs(slope)
            y_grounded = tile.rect.bottom - ((1 / abs_slope) * x_in + ((offset - 1) / abs_slope) * tile.tile_h)
            # print("tile.rect.bottom={} abs_slope={} x_in={} offset={} y_grounded={}".format(tile.rect.bottom, abs_slope, x_in, offset, y_grounded))
            slope_y_pull = y_grounded - sprite.rect.bottom  # can be positive (pull towards slop surface) or negative (push from inside slope to slope surface)

            # we are in the air -> only apply y-pull if the y-pull is negative (up push)
            # - otherwise -> keep falling (no collision)
            if not sprite.components["dockable"].is_docked() and slope_y_pull > 0:
                col.is_collided = False  # this will cause the detected collision (with the tile rect) to be ignored for now
            # we are on the slope (not falling or having fallen into the slope already) -> pull us up or down
            else:
                col.slope = slope
                #col.slope_up_down = math.copysign(1, slope)
                col.slope_y_pull = slope_y_pull

        return col
    """

class Viewport(Component):
    """
    A viewport is a component that can be added to a Stage to help that Stage render the scene depending on scrolling/obj_to_follow certain GameObjects
    - any GameObject with offset_x/y fields is supported, the Viewport will set these offsets to the Viewports x/y values
    before each render call
    """

    def __init__(self, display: Display):
        """
        :param Display display: the Display object associated with this Viewport
        """
        super().__init__("viewport")  # fix name to 'viewport' (only one viewport per Stage)

        self.display = display  # the pygame display (Surface) to draw on; so far we only need it to get the display's dimensions

        # top/left corner (world coordinates) of the Viewport window
        # - will be used as offset_x/y for the Display
        self.x = 0
        self.y = 0

        # parameters used for shaking the Viewport (if something heavy lands on the ground)
        self.is_shaking = False
        self.shake_y = 0  # the current shake-y-offset
        self.shake_time_total = 0
        self.shake_time_switch = 0
        self.shake_frequency = 5

        self.scale = 1.0

        self.directions = {}
        self.obj_to_follow = None
        self.max_speed = 10
        self.bounding_box = None

    def added(self):
        assert isinstance(self.game_object, Stage), "ERROR: can only add a Viewport Component to a Stage object, but GameObject is of type {}!".\
            format(type(self.game_object).__name__)
        self.game_object.on_event("pre_render", self, "pre_render")

        self.extend(self.follow_object_with_viewport)
        self.extend(self.unfollow_object_with_viewport)
        self.extend(self.center_on_xy_with_viewport)
        self.extend(self.move_to_xy_with_viewport)
        self.extend(self.shake_viewport)

    # EXTENSION methods (take self as well as GameObject as first two params)

    def follow_object_with_viewport(self, game_object, obj_to_follow, directions=None, bounding_box=None, max_speed=float("inf")):
        """
        makes the viewport follow a GameObject (obj_to_follow)

        :param GameObject game_object: our game_object (the Stage) that has `self` as component
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
            w = self.game_object.screen.width if hasattr(self.game_object.screen, "width") else self.display.surface.get_width()
            h = self.game_object.screen.height if hasattr(self.game_object.screen, "height") else self.display.surface.get_height()
            bounding_box = {"min_x": 0, "min_y": 0, "max_x": w, "max_y": h}

        self.directions = directions
        self.obj_to_follow = obj_to_follow
        self.bounding_box = bounding_box
        self.max_speed = max_speed
        game_object.on_event("post_tick", self, "follow")
        self.follow(first=(False if max_speed > 0.0 else True))  # start following

    def unfollow_object_with_viewport(self, game_object):
        """
        stops following

        :param GameObject game_object: our game_object (the Stage) that has `self` as component
        """
        game_object.off_event("post_tick", self, "follow")
        self.obj_to_follow = None

    def center_on_xy_with_viewport(self, game_object, x, y):
        """
        centers the Viewport on a given x/y position (so that the x/y position is in the center of the screen afterwards)

        :param GameObject game_object: our game_object (the Stage) that has `self` as component
        :param int x: the x position to center on
        :param int y: the y position to center on
        """
        self.center_on(x, y)

    def move_to_xy_with_viewport(self, game_object, x, y):
        """
        moves the Viewport to the given x/y position (top-left corner, not center(!))

        :param GameObject game_object: our game_object (the Stage) that has `self` as Component
        :param int x: the x position to move to
        :param int y: the y position to move to
        """
        self.move_to(x, y)

    def shake_viewport(self, game_object, time=3, frequency=5):
        """
        shakes the Viewport object for the given time and with the given frequency

        :param GameObject game_object: our game_object (the Stage) that has `self` as Component
        :param float time: the amount of time (in sec) for which the Viewport should shake
        :param floar frequency: the frequency (in up/down shakes per second) with which we should shake; higher numbers mean more rapid shaking
        """

        self.is_shaking = True
        self.shake_time_total = time
        self.shake_frequency = frequency
        self.shake_time_switch = 1 / (frequency * 2)  # after this time, we have to switch direction (2 b/c up and down)

    # END: EXTENSION METHODS

    def follow(self, game_loop=None, first=False):
        """
        helper method to follow our self.obj_to_follow (should not be called by the API user)
        - called when the Stage triggers Event 'post_tick' (passes GameLoop into it which is not used)

        :param GameLoop game_loop: the GameLoop that's currently playing
        :param bool first: whether this is the very first call to this function (if so, do a hard center on, otherwise a soft-center-on)
        """
        follow_x = self.directions["x"](self.obj_to_follow) if callable(self.directions["x"]) else  self.directions["x"]
        follow_y = self.directions["y"](self.obj_to_follow) if callable(self.directions["y"]) else  self.directions["y"]

        func = self.center_on if first else self.soft_center_on
        func(self.obj_to_follow.rect.centerx if follow_x else None, self.obj_to_follow.rect.centery if follow_y else None)

    def soft_center_on(self, x=None, y=None):
        """
        soft-centers on a given x/y position respecting the Viewport's max_speed property (unlike center_on)

        :param Union[int,None] x: the x position to center on (None if we should ignore the x position)
        :param Union[int,None] y: the y position to center on (None if we should ignore the y position)
        """
        if x:
            dx = (x - self.display.surface.get_width() / 2 / self.scale - self.x) / 3  # //, this.followMaxSpeed);
            if abs(dx) > self.max_speed:
                dx = math.copysign(self.max_speed, dx)

            if self.bounding_box:
                if (self.x + dx) < self.bounding_box["min_x"]:
                    self.x = self.bounding_box["min_x"] / self.scale
                elif self.x + dx > (self.bounding_box["max_x"] - self.display.surface.get_width()) / self.scale:
                    self.x = (self.bounding_box["max_x"] - self.display.surface.get_width()) / self.scale
                else:
                    self.x += dx
            else:
                self.x += dx

        if y:
            dy = (y - self.display.surface.get_height() / 2 / self.scale - self.y) / 3
            if abs(dy) > self.max_speed:
                dy = math.copysign(self.max_speed, dy)
            if self.bounding_box:
                if self.y + dy < self.bounding_box["min_y"]:
                    self.y = self.bounding_box["min_y"] / self.scale
                elif self.y + dy > (self.bounding_box["max_y"] - self.display.surface.get_height()) / self.scale:
                    self.y = (self.bounding_box["max_y"] - self.display.surface.get_height()) / self.scale
                else:
                    self.y += dy
            else:
                self.y += dy

    def center_on(self, x=None, y=None):
        """
        centers on a given x/y position without(!) respecting the Viewport's max_speed property (unlike soft_center_on)

        :param Union[int,None] x: the x position to center on (None if we should ignore the x position)
        :param Union[int,None] y: the y position to center on (None if we should ignore the y position)
        """
        if x:
            self.x = x - self.display.surface.get_width() / 2 / self.scale
        if y:
            self.y = y - self.display.surface.get_height() / 2 / self.scale

    def move_to(self, x=None, y=None):
        """
        moves the Viewport to a given x/y position (top-left corner, not centering) without(!) respecting the Viewport's max_speed property

        :param Union[int,None] x: the x position to move to (None if we should ignore the x position)
        :param Union[int,None] y: the y position to move to (None if we should ignore the y position)
        """
        if x:
            self.x = x
        if y:
            self.y = y
        return self.game_object  # ?? why

    def tick(self, game_loop):
        if self.is_shaking:
            dt = game_loop.dt
            self.shake_time_total -= dt
            # done shaking

    def pre_render(self, display):
        """
        sets the offset property of the given Display so that it matches our (previously) calculated x/y values

        :param Display display: the Display, whose offset we will change here
        """
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
    a simple Screen that has support for labels and sprites (static images) shown on the screen
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
        Stage.stage_screen(self, SimpleScreen.screen_func, stage=0)

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
        if not self.keyboard_inputs:
            key_list = self.tmx_obj.properties.get("keyboard_inputs", "")
            assert len(key_list) > 0, "ERROR: tmx file needs a global map property `keyboard_inputs` such as e.g. `up,down,left,right`"
            descriptions = key_list.split(",")
            self.keyboard_inputs = KeyboardInputs(descriptions)

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
                                 "physics_collision_detector": AABBCollision.collide,
                                 "tile_sprite_handler": functools.partial(PhysicsComponent.tile_sprite_handler, TileSprite)
                                 })
        for layer in stage.screen.tmx_obj.layers:
            stage.add_tiled_layer(layer, stage.screen.tmx_obj)

    def play(self):
        """
        start level (stage the scene; will overwrite the old 0-stage (=main-stage))
        - the options-object below will be also stored in [Stage object].options
        - child Level classes only need to do these three things: a) stage a screen, b) register some possible events, c) play a new game loop
        """
        Stage.stage_screen(self, self.screen_func, stage=0)
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

    def __init__(self, screens_and_levels, width=0, height=0, title="spygame Demo!", max_fps=60, debug_flags=DEBUG_NONE):
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
        self.display = Display(width, height, title)  # use widthxheight for now (default); this will be reset to the largest Level dimensions further below

        # our levels (if any) determine the size of the display
        get_w_from_levels = True if width == 0 else False
        get_h_from_levels = True if height == 0 else False

        # initialize all screens and levels
        for i, screen_or_level in enumerate(screens_and_levels):
            name = screen_or_level.pop("name", "screen{:02d}".format(i))
            id_ = screen_or_level.pop("id", 0)
            keyboard_inputs = screen_or_level.pop("keyboard_inputs", None)
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
    def collide(sprite1, sprite2, collision_objects=None, original_pos=None):
        """
        solves a simple spatial collision problem for two Sprites (that have a rect property)
        - defaults to SAT collision between two objects
        - thanks to doc's at: http://www.sevenson.com.au/actionscript/sat/
        - TODO: handle angles on objects
        - TODO: handle velocities of sprites prior to collision to calculate correct normals

        :param Sprite sprite1: sprite 1
        :param Sprite sprite2: sprite 2 (the other sprite)
        :param Union[None,Tuple[Collision]] collision_objects: the two always-recycled returnable Collision instances (aside from None); if None,
            use our default ones
        :param Union[Tuple[int],None] original_pos: the position of sprite1 before doing the move that lead to this collision-detection call
        :return: a Collision object with all details of the collision between the two Sprites (None if there is no collision)
        :rtype: Union[None,Collision]
        """
        pass


class AABBCollision(CollisionAlgorithm):
    """
    a simple axis-aligned bounding-box collision mechanism which only works on Pygame rects
    """

    @staticmethod
    def collide(sprite1, sprite2, collision_objects=None, direction='x', direction_veloc=1.0, original_pos=None):
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

        # fill in some more values in the recycled Collision object before returning it
        ret.separate[0] = - ret.distance * ret.normal_x
        ret.separate[1] = - ret.distance * ret.normal_y
        if not original_pos:
            original_pos = (sprite1.rect.x, sprite1.rect.y)
        ret.original_pos = original_pos

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

            collision_obj.magnitude = abs(collision_obj.distance)

        return collision_obj if collision_obj.is_collided else None


# TODO: SATCollisions are WIP
class SATCollision(CollisionAlgorithm):
    normal = [0.0, 0.0]

    @staticmethod
    def collide(sprite1, sprite2, collision_objects=None, original_pos=None):
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

        # pick the best collision from the two
        ret = collision_objects[1] if collision_objects[1].magnitude < collision_objects[0].magnitude else collision_objects[0]

        if ret.magnitude == 0.0:
            return None

        # fill in some more values in the recycled Collision object before returning it
        ret.separate[0] = - ret.distance * ret.normal_x
        ret.separate[1] = - ret.distance * ret.normal_y
        if not original_pos:
            original_pos = (sprite1.rect.x, sprite1.rect.y)
        ret.original_pos = original_pos

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
    adds all key/value pairs from defaults_dict into dictionary, but only if dictionary doesn't have the key defined yet

    :param dict dictionary: the target dictionary
    :param dict defaults_dict: the source (default) dictionary to take the keys from (only if they are not defined in dictionary
    """
    for key, value in defaults_dict.items():
        if key not in dictionary:  # overwrite only if key is missing
            dictionary[key] = value


# OBSOLETE: use
def extend(dictionary, extend_dict):
    """
    extends the dictionary with extend_dict, thereby overwriting existing keys

    :param dict dictionary: the target dictionary
    :param dict extend_dict: the source (extension) dictionary to take the keys from (even if they are not defined in dictionary)
    """
    for key, value in extend_dict.items():
        dictionary[key] = value  # overwrite no matter what


# simple type conversion (from string input) by regular expression matching
def convert_type(value):
    as_str = str(value)
    # int
    if re.fullmatch('-?\\d+', as_str):
        return int(value)
    # float
    elif re.fullmatch('-?\d+\.\d+', as_str):
        return float(value)
    # bool
    elif re.fullmatch('(true|false)', as_str, flags=re.I):
        return bool(value)
    # str (or list or others)
    return value


