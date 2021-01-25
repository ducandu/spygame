# --------------------------------------------------------------
#
# spygame (pygame based 2D game engine)
#
# created: 2017/04/04 in PyCharm
# (c) 2017-2021 Sven Mika - ducandu GmbH
#
# --------------------------------------------------------------

from abc import ABCMeta, abstractmethod
import xml.etree.ElementTree
import pygame
import os.path
from itertools import chain
from typing import Union
import pytmx
import sys
import math
import re
import numpy as np
import functools

VERSION_ = '0.1'
RELEASE_ = '0.1a9'

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



# can handle events as well as
class State(EventObject):
    """
    A simple state class that serves as a dict with settable and gettable key/value pairs.
    Setting a new value will trigger "changed"+key events.
    """
    def __init__(self):
        super().__init__()
        self.dict = {}

    # sets a value in our dict and triggers a changed event
    def set(self, key, value, trigger_event=False):
        # trigger an event that the value changed
        if trigger_event:
            old = self.dict[key] if key in self.dict else None
            self.trigger_event("changed." + key, value)
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
    A class to handle keyboard inputs by the user playing the spygame game.
    A KeyboardInput object is passed to the GameLoop c'tor, so that the GameLoop can `tick` the KeyboardInput object each frame.
    Single keys to watch out for can be registered via the `update_keys` method (not registered keys will be ignored).
    The tick method collects all keydown/keyup pygame events and stores the currently registered keys in the `keyboard_registry` as True (currently pressed)
    or False (currently not pressed).
    All keys are described by their pygame names (without the leading `K_`), e.g. pygame.K_UP=`up`, pygame.K_ESCAPE=`escape`, etc..
    """
    def __init__(self, key_list=None):
        """
        :param Union[list,None] key_list: the list of keys to be added right away to our keyboard_registry dict
        """
        super().__init__()

        # stores the keys that we would like to be registered as important
        # - key: pygame keyboard code (e.g. pygame.K_ESCAPE, pygame.K_UP, etc..)
        # - value: True if currently pressed, False otherwise
        # - needs to be ticked in order to yield up-to-date information (this will be done by a GameLoop playing a Screen)
        self.keyboard_registry = {}
        self.descriptions = {}

        if key_list is None:
            key_list = ["up", "down", "left", "right"]
        self.update_keys(key_list)

    def update_keys(self, new_key_list=None):
        """
        Populates our registry and other dicts with the new key-list given (may be an empty list).

        :param Union[List,None] new_key_list: the new key list, where each item is the lower-case pygame keycode without the leading
            `K_` e.g. `up` for pygame.K_UP; use None for clearing out the registry (no keys assigned)
        """
        self.unregister_all_events()
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
        Pulls all keyboard events from the event queue and processes them according to our keyboard_registry/descriptions.
        Triggers events for all registered keys like: 'key_down.[desc]' (when  pressed) and 'key_up.[desc]' (when released),
        where desc is the lowercase string after `pygame.K_`... (e.g. 'down', 'up', etc..).
        """
        events = pygame.event.get([pygame.KEYDOWN, pygame.KEYUP])
        for e in events:
            # a key was pressed that we are interested in -> set to True or False
            if getattr(e, 'key', None) in self.keyboard_registry:
                if e.type == pygame.KEYDOWN:
                    self.keyboard_registry[e.key] = True
                    self.trigger_event("key_down." + self.descriptions[e.key])
                else:
                    self.keyboard_registry[e.key] = False
                    self.trigger_event("key_up." + self.descriptions[e.key])







class Autobuild(object):
    """
    Mix-in class to force x, y, width, height structure of ctors. All Autobuild instances (objects that are built automatically by a TiledTileLayer with
    the property autobuild_objects=true) will have to abide to this ctor parameter structure.
    """
    def __init__(self, x, y, w, h, tile_w, tile_h):
        """
        :param int x: the x position of the Autobuild in tile units
        :param int y: the y position of the Autobuild in tile units
        :param int w: the width of the Autobuild in tile units
        :param int h: the height of the Autobuild in tile units
        :param int tile_w: the tile width of the layer
        :param int tile_h: the tile height of the layer
        """
        self.x_in_tiles = x
        self.y_in_tiles = y
        self.w_in_tiles = w
        self.h_in_tiles = h
        self.tile_w = tile_w
        self.tile_h = tile_h


class Ladder(Sprite, Autobuild):
    """
    A Ladder object that actors can climb on.
    One-way-platform type: one cannot fall through the top of the ladder but does not collide with the rest (e.g. from below) of the ladder.
    A Ladder object does not have an image and is thus not(!) being rendered; the image of the ladder has to be integrated into a rendered TiledTileLayer.
    TiledTileLayers have the possibility to generate Ladder objects automatically from those tiles that are flagged with the type='ladder' property. In that
    case, the TiledTileLayer property 'build_ladders' (bool) has to be set to true.
    """
    def __init__(self, x, y, w, h, tile_w, tile_h):
        """
        :param int x: the x position of the Ladder in tile units
        :param int y: the y position of the Ladder in tile units
        :param int w: the width of the Ladder in tile units
        :param int h: the height of the Ladder in tile units
        :param int tile_w: the tile width of the layer
        :param int tile_h: the tile height of the layer
        """
        Autobuild.__init__(self, x, y, w, h, tile_w, tile_h)
        # transform values here to make collision with ladder to only trigger when player is relatively close to the x-center of the ladder
        # - make this a 2px wide vertical axis in the center of the ladder
        x_px = self.x_in_tiles * self.tile_w + int(self.w_in_tiles * self.tile_w/2) - 1
        y_px = self.y_in_tiles * self.tile_h

        # call the Sprite ctor (now everything is in px)
        Sprite.__init__(self, x_px, y_px, width_height=(2, self.h_in_tiles * self.tile_h))

        # collision types
        self.type = Sprite.get_type("ladder,dockable,one_way_platform")
        self.collision_mask = 0  # do not do any collisions


class LiquidBody(Sprite, Autobuild):
    """
    A LiquidBody object (quicksand, water, etc..) that an actor will sink into and die. The AIBrain of enemies will avoid stepping into such an object.
    """
    def __init__(self, x, y, w, h, tile_w, tile_h, description="quicksand"):
        """
        :param int x: the x position of the Ladder in tile units
        :param int y: the y position of the Ladder in tile units
        :param int w: the width of the Ladder in tile units
        :param int h: the height of the Ladder in tile units
        :param int tile_w: the tile width of the layer
        :param int tile_h: the tile height of the layer
        """
        Autobuild.__init__(self, x, y, w, h, tile_w, tile_h)
        # make the liquid object a little lower than the actual tiles (especially at the top assuming that the top is done with tiles only showing
        # the very shallow surface of the liquid body)
        x_px = self.x_in_tiles * self.tile_w
        y_px = self.y_in_tiles * self.tile_h + int(self.tile_h * 0.9)

        # call the Sprite ctor (now everything is in px)
        Sprite.__init__(self, x_px, y_px, width_height=(self.w_in_tiles * self.tile_w, self.h_in_tiles * self.tile_h - int(self.tile_h * 0.9)))

        # can be used to distinguish between different types of liquids (water, quicksand, lava, etc..)
        self.description = description

        # collision types
        self.type = Sprite.get_type("liquid")
        self.collision_mask = 0  # do not do any collisions


class AnimatedSprite(Sprite):
    """
    Adds an Animation component to each Sprite instance.
    AnimatedSprites need a SpriteSheet (no static images or no-render allowed).

    :param int x: the initial x position of the Sprite
    :param int y: the initial y position of the Sprite
    :param SpriteSheet spritesheet: the SpriteSheet object to use for this Sprite
    :param dict animation_setup: the dictionary with the animation setup data to be sent to Animation.register_settings (the name of the registry record will
            be kwargs["anim_settings_name"] OR spritesheet.name)
    """

    def __init__(self, x, y, sprite_sheet, animation_setup, **kwargs):
        """
        :param int x: the initial x position of the AnimatedSprite
        :param int y: the initial y position of the AnimatedSprite
        :param SpriteSheet sprite_sheet: the SpriteSheet to use for animations
        :param dict animation_setup: a dictionary with all the different animation name and their settings (animation speed, frames to use, etc..)
        """
        assert isinstance(sprite_sheet, SpriteSheet), "ERROR: AnimatedSprite needs a SpriteSheet in its c'tor!"

        super().__init__(x, y, sprite_sheet=sprite_sheet, **kwargs)
        self.cmp_animation = self.add_component(Animation("animation"))

        self.anim_settings_name = kwargs.get("anim_settings_name", None) or sprite_sheet.name
        Animation.register_settings(self.anim_settings_name, animation_setup, register_events_on=self)
        # play the default animation (now that we have added the Animation Component, we can call play_animation on ourselves)
        self.play_animation(animation_setup["default"])


class Display(object):
    """
    A simple wrapper class for a pygame.display/pygame.Surface object representing the pygame display.
    Also stores offset information for Viewport focusing (if Viewport is smaller that the Level, which is usually the case).
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
        self.width = width
        self.height = height
        self.surface = pygame.display.set_mode((width, height))
        self.offsets = [0, 0]

    def change_dims(self, width, height):
        """
        Changes the Display's size dynamically (during the game).

        :param int width: the new width to use
        :param int height: the new height to use
        """
        self.width = width
        self.height = height
        pygame.display.set_mode((width, height))
        assert self.surface is pygame.display.get_surface(), "ERROR: self.display is not same object as pygame.display.get_surface() anymore!"

    def debug_refresh(self):
        """
        Force-refreshes the display (used only for debug purposes).
        """
        pygame.display.flip()
        pygame.event.get([])  # we seem to have to do this


class GameLoop(object):
    """
    Class that represents the GameLoop.
    Has play and pause functions: play starts the tick/callback loop.
    Has clock for ticking (keeps track of self.dt each tick), handles and abides to max-fps rate setting.
    Handles keyboard input registrations via its KeyboardInputs object.
    Needs a callback to know what to do each tick.
    Tick method does keyboard_inputs.tick, then calls the given callback with self as only argument.
    """

    # static loop object (the currently active GameLoop gets stored here)
    active_loop = None

    @staticmethod
    def play_a_loop(**kwargs):
        """
        Factory: plays a given GameLoop object or creates a new one using the given \*\*kwargs options.

        :param any kwargs:
                - force_loop (bool): whether to play regardless of whether we still have some active loop running
                - callback (callable): the GameLoop's callback loop function
                - keyboard_inputs (KeyboardInputs): the GameLoop's KeyboardInputs object
                - display (Display): the Display object to render everything on
                - max_fps (int): the max frames per second to loop through
                - screen_obj (Screen): alternatively, a Screen can be given, from which we will extract `display`, `max_fps` and `keyboard_inputs`
                - game_loop (Union[str,GameLoop]): the GameLoop to use (instead of creating a new one); "new" or [empty] for new one
                - dont_play (bool): whether - after creating the GameLoop - it should be played. Can be used for openAI gym purposes, where we just step,
                  not tick
        :return: the created/played GameLoop object or None
        :rtype: Union[GameLoop,None]
        """

        defaults(kwargs, {
            "force_loop": False,
            "screen_obj": None,
            "keyboard_inputs": None,
            "display": None,
            "max_fps": None,
            "game_loop": "new",
            "dont_play": False,
        })

        # - if there's no other loop active, run the default stageGameLoop
        # - or: there is an active loop, but we force overwrite it
        if GameLoop.active_loop is None or kwargs["force_loop"]:
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
                # set max_fps directly
                if kwargs["max_fps"]:
                    max_fps = kwargs["max_fps"]
                # or through the screen_obj
                elif kwargs["screen_obj"]:
                    max_fps = kwargs["screen_obj"].max_fps

                # Create a new GameLoop object.
                loop = GameLoop(Stage.stage_default_game_loop_callback, display=display,
                                keyboard_inputs=keyboard_inputs, max_fps=max_fps)
                # And play it, if necessary.
                if not kwargs["dont_play"]:
                    loop.play()
                return loop

            # Play an already existing loop.
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
        Pauses this GameLoop.
        """
        self.is_paused = True
        GameLoop.active_loop = None

    def play(self, max_fps=None):
        """
        Plays this GameLoop (after pausing the currently running GameLoop, if any).
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
        Called each frame of the GameLoop.
        Collects keyboard events.
        Calls the GameLoop's `callback`.
        Keeps a frame counter.

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
        Executes one action on the game.
        The action gets translated into a keyboard sequence first, then is played.

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
    A Stage is a container class for Sprites sorted by pygame.sprite.Groups and TiledTileLayers.
    Sprites within a Stage can collide with each other or with the TiledTileLayers in the Stage.
    Sprites and TiledTileLayers that are to be rendered are stored sorted by their render_order property (lowest renders first).
    """

    # list of all Stages
    max_stages = 10
    stages = [None for x in range(max_stages)]
    active_stage = 0  # the currently ticked/rendered Stage
    locate_obj = Sprite(0, 0, width_height=(0, 0))  # used to do test collisions on a Stage

    @staticmethod
    def stage_default_game_loop_callback(game_loop: GameLoop):
        """
        The default game loop callback to use if none is given when staging a Scene.
        Order: Clamps dt (to avoid extreme values), ticks all stages, renders all stages, updates the pygame.display

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
        Loops through all Stages and renders all of them.

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
        Clears one of the Stage objects by index.

        :param int idx: the index of the Stage to clear (index==slot in static Stage.stages list)
        """
        if Stage.stages[idx]:
            Stage.stages[idx].destroy()
            Stage.stages[idx] = None

    @staticmethod
    def clear_stages():
        """
        Clears all our Stage objects.
        """
        for i in range(len(Stage.stages)):
            Stage.clear_stage(i)

    @staticmethod
    def get_stage(idx=0):
        """
        Returns the Stage at the given index (returns None if none found).

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
        Supported options are (if not given, we take some of them from given Screen object, instead):
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
        """
        :param Screen screen: the Stage's Screen object (a Screen determines which elements (layers and sprites) go on the Stage)
        :param dict options: the options ruling the behavior of this Stage. options can be:
         components (list): a list of components to add to this Stage during construction (usually, a Viewport gets added)
         tile_sprite_handler (callable): a method taking a TiledTileLayer and returning an ndarray (tile-x/y position) of TileSprite objects (None if tile is
          empty)
         physics_collision_detector (callable): a method to use to detect a possible collision between two Sprites (defaults to AABBCollision.collide)
         tick_sprites_in_range_only (bool): if set to True (default), we will not tick those Sprite objects that are currently outside a) our Viewport
          component or b) outside the display
        """
        super().__init__()
        self.screen = screen  # the screen object associated with this Stage
        self.tiled_tile_layers = {}  # TiledLayer objects by name
        self.tiled_object_groups = {}  # TiledObjectGroup objects by name
        self.to_render = []  # list of all layers and sprites by name (TiledTileLayers AND Sprites) in the order in which they have to be rendered

        # dict of pygame.sprite.Group objects (by name) that contain Sprites (each TiledObjectGroup results in one Group)
        # - the name of the group is always the name of the TiledObjectGroup in the tmx file
        self.sprite_groups = {}
        self.sprites = []  # a plain list of all Sprites in this Stage

        self.remove_list = []  # sprites to be removed from the Stage (only remove when Stage gets ticked)

        defaults(options, {"physics_collision_detector": AABBCollision.collide, "tick_sprites_in_range_only": True, "tick_sprites_n_more_frames": 500})
        self.options = options

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
        self.cmp_viewport = None  # type: Union[Viewport,None]
        if "components" in self.options:
            for comp in self.options["components"]:
                assert isinstance(comp, Component), "ERROR: one of the given components in Stage's c'tor (options['components']) is not of type Component!"
                self.add_component(comp)
                if comp.name == "viewport":
                    self.cmp_viewport = comp

        # store the viewable range Rect
        self.respect_viewable_range = self.cmp_viewport and self.options["tick_sprites_in_range_only"]
        self.viewable_rect = pygame.Rect(0, 0, self.screen.display.width, self.screen.display.height)

        # make sure our destroyed method is called when the stage is destroyed
        self.on_event("destroyed")

    def destroyed(self):
        self.invoke("debind_events")

    def for_each(self, callback, params=None):
        """
        Calls the given callback function for each sprite, each time passing it the sprite itself and \*params.

        :param callable callback: the callback to call for each sprite in the Stage
        :param any params: the params to pass as second/third/etc.. parameter to the callback
        """
        if not params:
            params = []
        for sprite in self.sprites:
            callback(sprite, *params)

    def invoke(self, func_name, params=None):
        """
        Calls a function on all of the GameObjects on this Stage.

        :param str func_name: the function name to call on all our GameObjects using getattr
        :param Union[list,None] params: the \*args passed to that function
        """
        if not params:
            params = []
        for sprite in self.sprites:
            func = getattr(sprite, func_name, None)
            if callable(func):
                func(*params)

    def detect(self, detector, params=None):
        """
        Returns the first GameObject in this Stage that - when passed to the detector function with params - returns True.

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
        Returns the first Collision found by colliding the given measurements (Rect) against this Stage's objects.
        Starts with all TiledTileLayer objects, then all other Sprites.

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
        obj.rect.y = y
        obj.rect.width = w
        obj.rect.height = h
        obj.type = type_
        obj.collision_mask = collision_mask

        if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_RECTS:
            pygame.draw.rect(self.screen.display.surface, DEBUG_RENDER_SPRITES_RECTS_COLOR,
                             pygame.Rect((obj.rect.x - self.screen.display.offsets[0], obj.rect.y - self.screen.display.offsets[1]),
                                         (obj.rect.w, obj.rect.h)), 1)
            GameLoop.active_loop.display.debug_refresh()

        # collide with all matching tile layers
        for tiled_tile_layer in self.tiled_tile_layers.values():
            if obj.collision_mask & tiled_tile_layer.type:
                col = tiled_tile_layer.collide_simple_with_sprite(obj, self.options["physics_collision_detector"])
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
        Adds a pytmx.TiledElement to the Stage with all its tiles or objects.
        The TiledElement could either be converted into a TiledTileLayer or a TiledObjectGroup (these objects are generated in this function based on the
        pytmx equivalent being passed in).

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
            assert "tile_sprite_handler" in self.options, \
                "ERROR: a TiledTileLayer needs a tile_sprite_handler callable to generate all TileSprite objects in the layer!"
            l = TiledTileLayer(pytmx_layer, pytmx_tiled_map, self.options["tile_sprite_handler"])
            self.add_tiled_tile_layer(l)

        else:
            raise Exception("ERROR: pytmx_layer of type {} cannot be added to Stage. Needs to be pytmx.pytmx.TiledTileLayer or pytmx.pytmx.TiledObjectGroup!".
                            format(type(pytmx_layer).__name__))

    def add_tiled_object_group(self, tiled_object_group):
        """
        Adds a TiledObjectGroup (all it's objects as single Sprites) to this Stage.

        :param TiledObjectGroup tiled_object_group:
        """
        # add the layer to our tiled_layers list
        self.tiled_object_groups[tiled_object_group.name] = tiled_object_group

        # add the (already created) sprite-group to this stage under the name of the layer
        assert tiled_object_group.name not in self.sprite_groups, \
            "ERROR: trying to add a TiledObjectGroup to a Stage, but the Stage already has a sprite_group with the name of that layer ({})". \
                format(tiled_object_group.name)
        self.sprite_groups[tiled_object_group.name] = tiled_object_group.sprite_group

        # add each single sprite of the group to the Stage
        for sprite in tiled_object_group.sprite_group.sprites():
            self.add_sprite(sprite, tiled_object_group.name)

    def add_tiled_tile_layer(self, tiled_tile_layer):
        """
        Adds a TiledTileLayer to this Stage.
        Puts it in the ordered to_render list, in the tiled_layers list.

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

        # capture ladders and other autobuild structures?
        if tiled_tile_layer.properties.get("autobuild_objects") == "true":
            objects = tiled_tile_layer.capture_autobuilds()
            for obj in objects:
                self.add_sprite(obj, "autobuilds")

    def add_sprite(self, sprite, group_name):
        """
        Adds a new single Sprite to an existing or a new pygame.sprite.Group.

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
        Removes a Sprite from this Stage by putting it in the remove_list for later removal.

        :param Sprite sprite: the Sprite to be removed from the Stage
        """
        self.remove_list.append(sprite)

    def force_remove_sprite(self, sprite: Sprite):
        """
        Force-removes the given Sprite immediately (without putting it in the remove_list first).

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
        Pauses playing the Stage.
        """
        self.is_paused = True

    def unpause(self):
        """
        Unpauses playing the Stage.
        """
        self.is_paused = False

    def tick(self, game_loop):
        """
        Gets called each frame by the GameLoop.
        Calls the tick method on all its Sprites (but only if the sprite is within the viewport).

        :param GameLoop game_loop: the GameLoop object that's currently running (and ticking all Stages)
        """

        if self.is_paused:
            return False

        # do the ticking of all Sprite objects
        self.trigger_event("pre_ticks", game_loop)

        # only tick sprites that are within our viewport
        if self.respect_viewable_range:
            self.viewable_rect.x = self.cmp_viewport.x
            self.viewable_rect.y = self.cmp_viewport.y
            for sprite in self.sprites:
                if sprite.rect.bottom > self.viewable_rect.top and sprite.rect.top < self.viewable_rect.bottom and \
                                sprite.rect.left < self.viewable_rect.right and sprite.rect.right > self.viewable_rect.left:
                    sprite.ignore_after_n_ticks = self.options["tick_sprites_n_more_frames"]  # reset to max
                    self.tick_sprite(sprite, game_loop)
                else:
                    sprite.ignore_after_n_ticks -= 1  # if reaches 0 -> ignore
                    if sprite.ignore_after_n_ticks > 0:
                        self.tick_sprite(sprite, game_loop)
        else:
            for sprite in self.sprites:
                sprite.ignore_after_n_ticks = self.options["tick_sprites_n_more_frames"]  # always reset to max
                self.tick_sprite(sprite, game_loop)

        # do the collision resolution
        self.trigger_event("pre_collisions", game_loop)
        self.solve_collisions()

        # garbage collect destroyed GameObjects
        for sprite in self.remove_list:
            self.force_remove_sprite(sprite)
        self.remove_list.clear()

        self.trigger_event("post_tick", game_loop)

    @staticmethod
    def tick_sprite(sprite, game_loop):
        """
        ticks one single sprite
        :param Sprite sprite: the Sprite object to tick
        :param GameLoop game_loop: the GameLoop object that's currently playing
        """
        if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_BEFORE_EACH_TICK:
            sprite.render(game_loop.display)
            game_loop.display.debug_refresh()
        sprite.tick(game_loop)
        if DEBUG_FLAGS & DEBUG_RENDER_SPRITES_AFTER_EACH_TICK:
            sprite.render(game_loop.display)
            game_loop.display.debug_refresh()

    def solve_collisions(self):
        """
        Look for the objects layer and do each object against the main collision layer.
        Some objects in the objects layer do their own collision -> skip those here (e.g. ladder climbing objects).
        After the main collision layer, do each object against each other.
        """
        # collide each object with all collidable layers (matching collision mask of object)
        for sprite in self.sprites:
            # not ignored (one-tick) and if this game_object completely handles its own collisions within its tick -> ignore it
            if sprite.ignore_after_n_ticks > 0 and not sprite.handles_own_collisions and sprite.collision_mask > 0:
                # collide with all matching tile layers
                for tiled_tile_layer in self.tiled_tile_layers.values():
                    # only collide, if one of the types of the layer matches one of the bits in the Sprite's collision_mask
                    if sprite.collision_mask & tiled_tile_layer.type:
                        col = tiled_tile_layer.collide_simple_with_sprite(sprite, self.options["physics_collision_detector"])
                        if col:
                            sprite.trigger_event("collision", col)

        # collide all Sprites with all other Sprites (both ways!)
        # - only check if sprite1's collision_matrix matches sprite2's type
        for sprite in self.sprites:
            # not ignored (one-tick) and if this Sprite completely handles its own collisions within its tick -> ignore it
            if sprite.ignore_after_n_ticks > 0 and not sprite.handles_own_collisions and sprite.collision_mask > 0:
                for sprite2 in self.sprites:
                    if sprite is not sprite2 and sprite2.collision_mask > 0 and sprite.collision_mask & sprite2.type and sprite2.collision_mask & sprite.type:
                        direction, v = self.estimate_sprite_direction(sprite)
                        col = self.options["physics_collision_detector"](sprite, sprite2, direction=direction, direction_veloc=v)
                        if col:
                            # trigger "collision" for sprite1
                            sprite.trigger_event("collision", col)
                            ## but only for sprite2 if it does NOT handle its own collisions
                            #if not sprite2.handles_own_collisions:
                            sprite2.trigger_event("collision", col.invert())

    @staticmethod
    def estimate_sprite_direction(sprite):
        """
        tries to return an accurate tuple of direction (x/y) and direction_veloc
        - if sprite directly has vx and vy, use these
        - if sprite has a physics component: use vx and vy from that Component
        - else: pretend vx and vy are 0.0
        then return the direction whose veloc component is highest plus that highest veloc

        :param Sprite sprite: the Sprite to estimate
        :return: tuple of direction (x/y) and direction_veloc
        :rtype: Tuple[str,float]
        """
        phys = sprite.components.get("physics", None)
        # sprite has a physics component with vx/vy
        if phys and hasattr(phys, "vx") and hasattr(phys, "vy"):
            vx = phys.vx
            vy = phys.vy
        # sprite has a vx/vy (meaning handles its own physics)
        elif hasattr(sprite, "vx") and hasattr(sprite, "vy"):
            vx = sprite.vx
            vy = sprite.vy
        else:
            vx = 0.0
            vy = 0.0

        if abs(vx) > abs(vy):
            return "x", vx
        else:
            return "y", vy

    def hide(self):
        """
        Hides the Stage.
        """
        self.is_hidden = True

    def show(self):
        """
        Unhides the Stage.
        """
        self.is_hidden = False

    def stop(self):
        """
        Stops playing the Stage (stops calling `tick` on all GameObjects).
        """
        self.hide()
        self.pause()

    def start(self):
        """
        Starts running the Stage (and calling all GameObject's `tick` method).
        """
        self.show()
        self.unpause()

    def render(self, display):
        """
        Gets called each frame by the GameLoop (after 'tick' is called on all Stages).
        Renders all its layers (ordered by 'render_order' property of the TiledTileLayer in the tmx file).
        TODO: renders Sprites that are not part of any layer.

        :param Display display: the Display object to render on
        """
        if self.is_hidden:
            return False

        self.trigger_event("pre_render", display)
        # loop through the sorted to_render list and render all TiledTileLayer and Sprite objects in this list
        for layer_or_sprite in self.to_render:
            if getattr(layer_or_sprite, "ignore_after_n_ticks", 1) <= 0:
                continue
            layer_or_sprite.render(display)
        self.trigger_event("post_render", display)


class TmxLayer(object, metaclass=ABCMeta):
    """
    A wrapper class for the pytmx TiledObject class that can either represent a TiledTileLayer or a TiledObjectGroup.
    Needs to implement render and stores some spygame specific properties such as collision, render, etc.

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
    A wrapper class for pytmx.pytmx.TiledTileLayer, which represents a 'normal' tile layer in a tmx file.
    Reads in all tiles' images into one Surface object so we can render the entire layer at once.
    Implements `render`.
    """

    def __init__(self, pytmx_layer, pytmx_tiled_map, tile_sprite_handler):
        """
        :param pytmx.pytmx.TiledTileLayer pytmx_layer: the underlying pytmx TiledTileLayer
        :param pytmx.pytmx.TiledMap pytmx_tiled_map: the underlying pytmx TiledMap object (representing the tmx file)
        :param callable tile_sprite_handler: the callable that returns an ndarray, populated with TileSprite objects for storage in this layer
        """
        super().__init__(pytmx_layer, pytmx_tiled_map)

        self.type_str = self.properties.get("type", "none")
        self.type = 0
        # get type mask of this layer from `type` property
        for t in self.type_str.split(","):
            self.type |= Sprite.get_type(t)

        # an ndarray holding all single tiles (by x/y position) from this layer
        # non-existing tiles are not(!) stored in this ndarray and return None at the respective x/y position
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
        Builds the image (pygame.Surface) for this tile layer based on all found tiles in the layer.
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

    def render(self, display):
        """
        Blits a part of our Sprite's image onto the Display's Surface using the Display's offset attributes.

        :param Display display: the Display object to render on
        """
        assert self.do_render, "ERROR: TiledTileLayer.render() called but self.do_render is False!"
        assert not isinstance(self.pygame_sprite, Sprite), "ERROR: TiledTileLayer.render() called but self.pygame_sprite is not a Sprite!"
        r = pygame.Rect(self.pygame_sprite.rect)  # make a clone so we don't change the original Rect
        # apply the display offsets (camera)
        r.x += display.offsets[0]
        r.y += display.offsets[1]
        r.width = display.width
        r.height = display.height
        display.surface.blit(self.pygame_sprite.image, dest=(0, 0), area=r)

    def capture_autobuilds(self):
        """
        Captures all autobuild objects in this layer and returns them in a list of objects.
        Once an autobuild tile is found: searches neighboring tiles (starting to move right and down) for the same property and thus measures the object's
        width and height (in tiles).

        :return: list of generated autobuild objects
        :rtype: List[object]
        """
        objects = []
        # loop through each tile and look for ladder type property
        for y in range(self.pytmx_layer.height):
            for x in range(self.pytmx_layer.width):
                tile_sprite = self.tile_sprites[(x, y)]  # type: TileSprite
                if not tile_sprite:
                    continue
                props = tile_sprite.tile_props
                # we hit the upper left corner of an autobuild object -> spread out to find more neighboring similar tiles
                ctor = props.get("autobuild_class", False)
                if ctor:
                    assert isinstance(ctor, type), "ERROR: translation of tile ({},{}) property `autobuild_class` did not yield a defined class!".format(x, y)
                    tile_left = self.tile_sprites[(x-1, y)]  # type: TileSprite
                    tile_top = self.tile_sprites[(x, y-1)]  # type: TileSprite
                    if tile_left and tile_left.tile_props.get("autobuild_class") == ctor or \
                            tile_top and tile_top.tile_props.get("autobuild_class") == ctor:
                        continue
                    # measure width and height
                    w = 1
                    h = 1
                    x2 = x+1
                    while True and x2 < self.pytmx_layer.width:
                        ts = self.tile_sprites[(x2, y)]
                        if not (ts and ts.tile_props.get("autobuild_class") == ctor):
                            break
                        w += 1
                        x2 += 1

                    y2 = y+1
                    while True and y2 < self.pytmx_layer.height:
                        ts = self.tile_sprites[(x, y2)]
                        if not (ts and ts.tile_props.get("autobuild_class") == ctor):
                            break
                        h += 1
                        y2 += 1

                    # insert new object (all autobuild objects need to accept x, y, w, h in their constructors)
                    objects.append(ctor(x, y, w, h, self.pytmx_tiled_map.tilewidth, self.pytmx_tiled_map.tileheight, **props.get("autobuild_kwargs", {})))
        return objects

    def get_overlapping_tiles(self, sprite):
        """
        Returns the tile boundaries (which tiles does the sprite overlap with?).

        :param Sprite sprite: the sprite to test against
        :return: a tuple of (start-x. end-x, start-y, end-y) tile-coordinates to consider as overlapping with the given Sprite
        :rtype: tuple
        """
        tile_start_x = min(max(0, sprite.rect.left // self.pytmx_tiled_map.tilewidth), self.pytmx_tiled_map.width - 1)
        tile_end_x = max(0, min(self.pytmx_tiled_map.width - 1, (sprite.rect.right - 1) // self.pytmx_tiled_map.tilewidth))
        tile_start_y = min(max(0, sprite.rect.top // self.pytmx_tiled_map.tileheight), self.pytmx_tiled_map.height - 1)
        tile_end_y = max(0, min(self.pytmx_tiled_map.height - 1, (sprite.rect.bottom - 1) // self.pytmx_tiled_map.tileheight))
        return tile_start_x, tile_end_x, tile_start_y, tile_end_y

    def collide_simple_with_sprite(self, sprite, collision_detector):
        """
        Collides a Sprite (that only obeys simple physics rules) with a TiledTileLayer and solves all detected collisions.
        The Sprite needs to have the properties vx and vy, which are interpreted as the Sprite's velocity.
        Ignores slopes.

        :param Sprite sprite: the Sprite to test for collisions against a TiledTileLayer
        :param callable collision_detector: the collision detector method to use (this is set in the Sprite's Stage's options)
        """
        tile_start_x, tile_end_x, tile_start_y, tile_end_y = self.get_overlapping_tiles(sprite)

        xy, v = Stage.estimate_sprite_direction(sprite)

        # very simple algo: look through tile list (in no particular order) and return first tile that collides
        # None if no colliding tile found
        for tile_x in range(tile_start_x, tile_end_x + 1):
            for tile_y in range(tile_start_y, tile_end_y + 1):
                tile_sprite = self.tile_sprites[tile_x, tile_y]
                if not tile_sprite:
                    continue
                col = collision_detector(sprite, tile_sprite, collision_objects=None,
                                         direction=xy, direction_veloc=v, original_pos=(sprite.rect.x, sprite.rect.y))
                if col:
                    return col
        return None


class TileSprite(Sprite):
    """
    Class used by TiledTileLayer objects to have a means of representing single tiles in terms of Sprite objects
    (used for collision detector function).
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
        # add the `dockable` type to all tiles
        self.type |= Sprite.get_type("dockable")


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
        self.max_y = max(self.get_y(0), self.get_y(self.rect.width))  # store our highest y-value (height of this tile)

    def get_y(self, x):
        """
        Calculates the y value (in normal cartesian y-direction (positive values on up axis)) for a given x-value.

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
        Applies a so-called xy-pull on a Sprite object moving in x-direction in this sloped tile.
        An xy-pull is a change in the y-coordinate because of the x-movement (sliding up/down a slope while moving left/right).

        :param Sprite sprite: the Sprite object that's moving on the slope
        """
        if self.slope == 0 or not self.slope:
            return
        # the local x value for the Sprite on the tile's internal x-axis (0=left edge of tile)
        x_local = max(0, (sprite.rect.left if self.slope < 0 else sprite.rect.right) - self.rect.left)
        # the absolute y-position that we will force the sprite into
        y = self.rect.bottom - self.get_y(x_local) - sprite.rect.height
        sprite.move(None, y, True)


class TiledObjectGroup(TmxLayer):
    """
    A wrapper class for the pytmx.TiledObjectGroup class, which represents an object layer in a tmx file.
    Generates all GameObjects specified in the layer (a.g. the agent, enemies, etc..).
    Implements `render` by looping through all GameObjects and rendering their Sprites one by one.
    """

    def __init__(self, pytmx_layer: pytmx.pytmx.TiledObjectGroup, pytmx_tiled_map: pytmx.pytmx.TiledMap):
        super().__init__(pytmx_layer, pytmx_tiled_map)

        # create the sprite group for this layer (all GameObjects will be added to this group)
        self.sprite_group = pygame.sprite.Group()

        # construct each object from the layer (as a Sprite) and add them to the sprite_group of this layer
        for obj in self.pytmx_layer:
            # allow objects in the tmx file to be 'switched-off' by making them invisible
            if not obj.visible:
                continue

            obj_props = obj.properties

            # if the (Sprite) class of the object is given, construct it here using its c'tor
            # - classes are given as strings: e.g. sypg.Sprite, vikings.Viking, Agent (Agent class would be in __main__ module)
            # - first look in the tile's properties for the 'class' field, only then try the 'type' field directly of the object (manually given by designer)
            class_global = obj_props.pop("class", None) or obj.type
            if class_global:
                ctor = convert_type(class_global, force_class=True)
                assert isinstance(ctor, type), "ERROR: python class `{}` for object in object-layer `{}` not defined!".\
                    format(class_global, self.pytmx_layer.name)

                # get other kwargs for the Sprite's c'tor
                kwargs = get_kwargs_from_obj_props(obj_props)

                # generate the Sprite
                sprite = ctor(obj.x, obj.y, **kwargs)
                ## add the do_render and render_order to the new instance
                #sprite.do_render = (obj_props.get("do_render", "true") == "true")  # the default for objects is true
                #if sprite.do_render:
                #    sprite.render_order = int(obj_props.get("render_order", 50))  # the default for objects is 50
                self.sprite_group.add(sprite)


class Collision(object):
    """
    A simple feature object that stores collision properties for collisions between two objects or between an object and a TiledTileLayer.
    """

    def __init__(self):
        self.sprite1 = None  # hook into the first Sprite participating in this collision
        self.sprite2 = None  # hook into the second Sprite participating in this collision (this could be a TileSprite)
        self.is_collided = True  # True if a collision happened (usually True)
        self.distance = 0  # how much do we have to move sprite1 to separate the two Sprites? (always negative)
        self.magnitude = 0  # abs(distance)
        self.impact = 0.0  # NOT SURE: the impulse of the collision on some mass (used for pushing heavy objects)
        self.normal_x = 0.0  # x-component of the collision normal
        self.normal_y = 0.0  # y-component of the collision normal
        self.separate = [0, 0]  # (-distance * normal_x, -distance * normal_y) how much to we have to change x/y values for rect to separate the two sprites
        self.direction = None  # None, 'x' or 'y' (direction in which we measure the collision; the other direction is ignored)
        self.direction_veloc = 0  # velocity direction component (e.g. direction=='x' veloc==5 -> moving right, veloc==-10.4 -> moving left)
        self.original_pos = [0, 0]  # the original x/y-position of sprite1 before the move that lead to the collision happened

    def invert(self):
        """
        Inverts this Collision in place to yield the Collision for the case that the two Sprites are switched.
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
        return self


## OBSOLETE CLASS
#class PlatformerCollision(Collision):
#    """
#    A collision object that can be used by PlatformerPhysics to handle Collisions.
#    """
#
#    def __init__(self):
#        super().__init__()
#        self.impact = 0.0  # the impulse of the collision on some mass (used for pushing heavy objects)

#        # OBSOLETE: these should all be no longer needed
#        # self.slope = False  # whether this is a collision with a sloped TileSprite of a TiledTileLayer
                            # (will also be False if obj1 collides with the Tile's rect, but obj1 is still in air (slope))
#        # self.slope_y_pull = 0  # amount of y that Sprite has to move up (negative) or down (positive) because of the collision (with a slope)
#        #self.slope_up_down = 0  # 0=no slope, -1=down slope, 1 = up slope




class KeyboardBrainTranslation(object):
    """
    A class to represent a relationship between a pressed key and a command (or two commands)
    The normal relationship is: [some key]: when pressed -> [command] is True; when not pressed -> [command] is False
    But other, more complex relationships are supported as well.
    """
    # key-to-command flags
    NORMAL = 0x0  # normal: when key down -> command is True (this is essentially: DOWN_LEAVE_UP_LEAVE)
    DOWN_ONE_TICK = 0x1  # when key down -> command is True for only one tick (after that, key needs to be released to fire another command)
    # DOWN_LEAVE = 0x2  # when key down -> command is x (and stays x as long as key is down)
    UP_ONE_TICK = 0x2  # when key up -> command is y for one frame

    # can only execute command if an animation is currently not playing or just completed (e.g. swinging sword)
    BLOCK_REPEAT_UNTIL_ANIM_COMPLETE = 0x4
    # when key down -> command is x (and stays x); when key gets released -> command is y for one frame (BUT only after a certain animation has been completed)
    BLOCK_OTHER_CMD_UNTIL_ANIM_COMPLETE = 0x8

    # some flags needed to describe the state for the DOWN_LEAVE_UP_ONE_TICK_WAIT_FOR_ANIM type of key-command-translation
    STATE_NONE = 0x0
    STATE_CHARGING = 0x1  # we are currently charging after key-down (when fully charged, we are ready to execute upon other_command)
    STATE_FULLY_CHARGED = 0x2  # if set, we are fully charged and we will execute other_command as soon as the key is released
    STATE_CMD_RECEIVED = 0x4  # if set, the key for the other_command has already been released, but we are still waiting for the charging to be complete

    def __init__(self, key, command, flags=0, other_command=None, animation_to_complete=None):
        """
        :param str key: the key's description, e.g. `up` for K_UP
        :param str command: the `main` command's description; can be any string e.g. `fire`, `jump`
        :param int flags: keyboard-command behavior flags
        :param str other_command: a possible second command associated with the key (when key is released, e.g. `release_bow`)
        :param Union[list,str] animation_to_complete: animation(s) that needs to be completed in order for the other_command to be executable
        """

        self.key = key
        self.command = command

        assert flags & (self.BLOCK_REPEAT_UNTIL_ANIM_COMPLETE | self.BLOCK_OTHER_CMD_UNTIL_ANIM_COMPLETE) == 0 or \
            isinstance(animation_to_complete, str) or isinstance(animation_to_complete, set), "ERROR: animation_to_complete needs to be of type str or set!"

        self.flags = flags
        self.other_command = other_command
        # this could be a set of anims (one of them has to be completed)
        self.animation_to_complete = {animation_to_complete} if isinstance(animation_to_complete, str) else animation_to_complete
        self.state_other_command = 0  # the current state for the other_command (charging, charged, cmd_received)

        self.is_disabled = False  # set to True for temporarily blocking this translation






class Dockable(Component):
    """
    A dockable component allows 1) for Sprites to dock to a so-called "mother_ship" and b) for Sprites to become "mother_ships" themselves (other Sprites can
    dock to this Sprite). Sprites that are docked to our mother_ship (this Component's Sprite) will be moved along with it when they stand on top.
    """

    DEFINITELY_DOCKED = 0x1  # this object is definitely docked to something right now
    DEFINITELY_NOT_DOCKED = 0x2  # this object is definitely not docked to something right now
    TO_BE_DETERMINED = 0x4  # the docking state of this object is currently being determined
    PREVIOUSLY_DOCKED = 0x8  # if set, the object was docked to something in the previous frame

    def __init__(self, name="dockable"):
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

    def move(self, sprite, x, y, absolute=False):
        """
        This will 'overwrite' the normal Sprite's `move` method by Component's extend.

        :param Sprite sprite: the GameObject that this Component belongs to (the Sprite to move around)
        :param Union[int,None] x: the amount in pixels to move in x-direction
        :param Union[int,None] y: the amount in pixels to move in y-direction
        :param bool absolute: whether x and y are given as absolute coordinates (default: False): in this case x/y=None means do not move in this dimension
        """
        orig_x = sprite.rect.x
        orig_y = sprite.rect.y

        # first call the original Sprite's move method
        sprite._super_move(x, y, absolute)

        # move all our docked Sprites along with us
        if not absolute:
            for docked_sprite in self.docked_sprites:
                docked_sprite.move(x, y, absolute=False)
        else:
            # translate into relative movement: we don't want the docked components to move to the given mothership's absolute values
            x_move = x - orig_x if x is not None else 0
            y_move = y - orig_y if y is not None else 0
            for docked_sprite in self.docked_sprites:
                docked_sprite.move(x_move, y_move)

    def dock_to(self, mother_ship):
        """
        A sprite lands on an elevator -> couple the elevator to the sprite so that when the elevator moves, the sprite moves along with it.
        Only possible to dock to `dockable`-type objects.

        :param Sprite mother_ship: the Sprite to dock to (Sprite needs to have a dockable component)
        """
        prev = self.is_docked()
        obj = self.game_object
        # can only dock to dockable-type objects
        if mother_ship.type & Sprite.get_type("dockable"):
            self.docking_state = Dockable.DEFINITELY_DOCKED
            if prev:
                self.docking_state |= Dockable.PREVIOUSLY_DOCKED
            self.docked_to = mother_ship
            # add docked obj to mothership docked-obj-list (if present)
            if "dockable" in mother_ship.components:
                #print("adding {} (id {}) to mothership {}".format(type(obj).__name__, obj.id, type(self.docked_to).__name__))
                mother_ship.components["dockable"].docked_sprites.add(obj)

    def undock(self):
        """
        Undocks itself from the mothership.
        """
        obj = self.game_object
        prev = self.is_docked()
        self.docking_state = Dockable.DEFINITELY_NOT_DOCKED
        if prev:
            self.docking_state |= Dockable.PREVIOUSLY_DOCKED
        # remove docked obj from mothership docked-obj-list (if present)
        if self.docked_to and "dockable" in self.docked_to.components:
            #print("removing {} (id {}) from mothership {}".format(type(obj).__name__, obj.id, type(self.docked_to).__name__))
            self.docked_to.components["dockable"].docked_sprites.discard(obj)
        self.docked_to = None

    def undock_all_docked_objects(self):
        """
        undocks all objects currently docked to this object
        """
        l = list(self.docked_sprites)
        for obj in l:
            if "dockable" in obj.components:
                obj.components["dockable"].undock()

    def to_determine(self):
        """
        Changes our docking state to be undetermined (saves the current state as PREVIOUS flag).
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


class Elevator(Sprite):
    """
    A simple elevator/moving platform class.
    Can either go in x or in y direction, with a configurable speed and in between settable coordinate values.
    Has a Dockable Component to be able to carry characters standing on top of it.
    Is of type one_way_platform so one can jump on the Elevator also from below it.
    """
    def __init__(self, x, y, direction="y", initial_veloc=50, max_pos=500, min_pos=0):
        super().__init__(x, y, image_file="images/elevator.png")
        self.direction = direction
        self.vx = initial_veloc if direction == "x" else 0.0
        self.vy = initial_veloc if direction == "y" else 0.0
        self.max_pos = max_pos
        self.min_pos = min_pos

        # add Dockable component (so that objects can stand on the elevator and move along with it)
        self.cmp_dockable = self.add_component(Dockable("dockable"))  # type: Dockable

        # adjust the type
        self.type |= Sprite.get_type("dockable,one_way_platform")
        self.collision_mask = 0  # don't do any collisions for this elevator (only other Sprites vs Elevator)

    def tick(self, game_loop):
        """
        Moving elevator up and down OR left and right.
        """
        dt = game_loop.dt

        self.move(self.vx * dt, self.vy * dt)
        if self.direction == "x":
            if self.rect.x < self.min_pos:
                self.vx = abs(self.vx)
                self.move(self.min_pos, None, absolute=True)
            elif self.rect.x > self.max_pos:
                self.vx = -abs(self.vx)
                self.move(self.max_pos, None, absolute=True)
        else:
            if self.rect.y < self.min_pos:
                self.vy = abs(self.vy)
                self.move(None, self.min_pos, absolute=True)
            elif self.rect.y > self.max_pos:
                self.vy = -abs(self.vy)
                self.move(None, self.max_pos, absolute=True)


class PhysicsComponent(Component, metaclass=ABCMeta):
    """
    Defines an abstract generic physics component that can be added to agents (or enemies) to behave in the world.
    GameObject's that own this Comonent may have a Brain component as well in order to steer behavior of the agent in `tick`.
    Needs to override `tick` and `collision`.
    """

    @staticmethod
    def tile_sprite_handler(tile_sprite_class, layer):
        """
        Populates the tile_sprites dict of a TiledTileLayer with tile_sprite_class (e.g. TileSprite or SlopedTileSprite) objects.

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
            # also keep autobuild kwargs in a separate dict
            look_for_autobuild = (True if tile_props.get("autobuild_class") else False)
            autobuild_kwargs = {}
            for key, value in tile_props.items():
                value = convert_type(value)
                # a special autobuild kwarg (for the autobuild c'tor)
                if look_for_autobuild and key[:2] == "P_":
                    autobuild_kwargs[key[2:]] = value
                else:
                    tile_props[key] = value

            if look_for_autobuild:
                tile_props["autobuild_kwargs"] = autobuild_kwargs

            ret[x, y] = tile_sprite_class(layer, layer.pytmx_tiled_map, gid, tile_props,
                                          pygame.Rect(x * layer.pytmx_tiled_map.tilewidth, y * layer.pytmx_tiled_map.tileheight,
                                                      layer.pytmx_tiled_map.tilewidth, layer.pytmx_tiled_map.tileheight))
        return ret

    # probably needs to be extended further by child classes
    def added(self):
        obj = self.game_object
        # handle collisions
        obj.on_event("collision", self, "collision", register=True)
        # flag the GameObject as "handles collisions itself"
        self.game_object.handles_own_collisions = True

    # may determine x/y-speeds and movements of the GameObject (gravity, etc..)
    @abstractmethod
    def tick(self, game_loop: GameLoop):
        """
        Needs to be called by the GameObject at some point during the GameObject's `tick` method.

        :param GameLoop game_loop: the currently playing GameLoop object
        """
        pass

    @abstractmethod
    def collision(self, col):
        """
        This is the resolver for a Collision that happened between two Sprites under this PhysicsComponent.

        :param Collision col: the Collision object describing the collision that already happened between two sprites
        """
        pass


class ControlledPhysicsComponent(PhysicsComponent, metaclass=ABCMeta):
    """
    When added to a GameObject, checks for an existing Brain Component and creates a property (self.game_obj_cmp_brain) for easy access.
    """
    def __init__(self, name="physics"):
        super().__init__(name)
        self.game_obj_cmp_brain = None  # the GameObject's HumanPlayerBrain component (used by Physics for steering and action control within `tick` method)

    def added(self):
        super().added()
        self.game_obj_cmp_brain = self.game_object.components.get("brain", None)
        # if there is a Component named `brain` in the GameObject it has to be of type Brain
        assert not self.game_obj_cmp_brain or isinstance(self.game_obj_cmp_brain, Brain),\
            "ERROR: {}'s `brain` Component is not of type Brain!".format(type(self.game_object).__name__)


class TopDownPhysics(ControlledPhysicsComponent):
    """
    Defines "top-down-2D"-step physics (agent can move in any of the 4 directions using any step-size (smooth walking)).
    To be addable to any character (player or enemy).
    """
    def __init__(self, name="physics"):
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
    def tick(self, game_loop):
        """
        Needs to be called by the GameObject at some point during the GameObject's `tick` method.

        :param GameLoop game_loop: the currently playing GameLoop object
        """
        dt = game_loop.dt
        # accelerations
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
                    obj.flip["x"] = True  # mirror sprite
                # user presses both keys (left and right) -> just stop
                else:
                    self.vx = 0
            # only right is pressed
            elif self.game_obj_cmp_brain.commands["right"]:
                if self.stops_abruptly_on_direction_change and self.vx < 0:
                    self.vx = 0  # stop first if still walking in other direction
                ax = self.run_acceleration  # accelerate right
                obj.flip["x"] = False
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
        dt_step = dt
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
            orig_pos = (obj.rect.x, obj.rect.y)
            if self.vx != 0.0:
                obj.move(self.vx * dt, 0.0)
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

            dt_step -= dt

    def collide_in_one_direction(self, sprite, direction, direction_veloc, original_pos):
        """
        Detects and solves all possible collisions between our GameObject and all Stage's objects (layers and Sprites) in one direction (x or y).

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

    def collide_with_collision_layer(self, sprite, layer, direction, direction_veloc, original_pos):
        """
        Collides a Sprite with a collision TiledTileLayer (type==default) and solves all detected collisions.

        :param Sprite sprite: the Sprite to test for collisions against a TiledTileLayer
        :param TiledTileLayer layer: the TiledTileLayer object in which to look for collision tiles (full of sloped)
        :param str direction: `x` or `y` direction in which the sprite is currently moving before this test
        :param float direction_veloc: the velocity in the given direction (could be negative or positive)
        :param Tuple[int,int] original_pos: the position of the sprite before the move that caused this collision test to be executed
        """
        # determine the tile boundaries (which tiles does the sprite overlap with?)
        tile_start_x, tile_end_x, tile_start_y, tile_end_y = layer.get_overlapping_tiles(sprite)

        # if sprite is moving in +/-x-direction:
        # 1) move in columns from left to right (right to left) to look for tiles
        if direction == 'x':
            direction_x = int(math.copysign(1.0, direction_veloc))
            for tile_x in range(tile_start_x if direction_x > 0 else tile_end_x, (tile_end_x if direction_x > 0 else tile_start_x) + direction_x, direction_x):
                for tile_y in range(tile_start_y, tile_end_y + 1):  # y-order doesn't matter
                    tile_sprite = layer.tile_sprites[tile_x, tile_y]
                    if tile_sprite:
                        col = AABBCollision.collide(sprite, tile_sprite, None, direction, direction_veloc, original_pos)
                        if col:
                            sprite.trigger_event("collision", col)
                            return
        else:
            direction_y = int(math.copysign(1.0, direction_veloc))
            for tile_y in range(tile_start_y if direction_y > 0 else tile_end_y, (tile_end_y if direction_y > 0 else tile_start_y) + direction_y, direction_y):
                for tile_x in range(tile_start_x, tile_end_x + 1):  # x-order doesn't matter
                    tile_sprite = layer.tile_sprites[tile_x, tile_y]
                    if tile_sprite:
                        col = AABBCollision.collide(sprite, tile_sprite, None, direction, direction_veloc, original_pos)
                        if col:
                            sprite.trigger_event("collision", col)
                            return

    def collision(self, col):
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

        # solve collision
        obj.move(col.separate[0], col.separate[1])

        # top/bottom collisions
        if abs(col.normal_y) > 0.3:
            if self.vy * col.normal_y < 0:  # if normal_y < 0 -> vy is > 0 -> set to 0; if normal_x > 0 -> vy is < 0 -> set to 0
                self.vy = 0
            obj.trigger_event("bump." + ("bottom" if col.normal_y < 0 else "top"), col)

        # left/right collisions
        if abs(col.normal_x) > 0.3:
            if self.vx * col.normal_x < 0:  # if normal_y < 0 -> vx is > 0 -> set to 0; if normal_y > 0 -> vx is < 0 -> set to 0
                self.vx = 0
                obj.trigger_event("bump." + ("right" if col.normal_x < 0 else "left"), col)



class Viewport(Component):
    """
    A viewport is a component that can be added to a Stage to help that Stage render the scene depending on scrolling/obj_to_follow certain GameObjects
    - any GameObject with offset_x/y fields is supported, the Viewport will set these offsets to the Viewports x/y values
    before each render call
    """
    def __init__(self, display):
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
        assert isinstance(self.game_object, Stage), "ERROR: Viewport Component can only be added to a Stage, but game_objects is of type {}!".\
            format(type(self.game_object).__name__)
        self.game_object.on_event("pre_render", self, "pre_render")

        self.extend(self.follow_object_with_viewport)
        self.extend(self.unfollow_object_with_viewport)
        self.extend(self.center_on_xy_with_viewport)
        self.extend(self.move_to_xy_with_viewport)
        self.extend(self.shake_viewport)

    # EXTENSION methods (take self as well as GameObject as first two params)
    def follow_object_with_viewport(self, stage, obj_to_follow, directions=None, bounding_box=None, max_speed=float("inf")):
        """
        Makes the viewport follow a GameObject (obj_to_follow).

        :param GameObject stage: our game_object (the Stage) that has `self` as component
        :param GameObject obj_to_follow: the GameObject that we should follow
        :param dict directions: dict with 'x' and 'y' set to either True or False depending on whether we follow only in x direction or y or both
        :param dict bounding_box: should contain min_x, max_x, min_y, max_y so we know the boundaries of the camera
        :param float max_speed: the max speed of the camera
        """
        stage.off_event("post_tick", self, "follow")
        if not directions:
            directions = {"x": True, "y": True}

        # this should be the level dimensions to avoid over-scrolling by the camera
        # - if we don't have a Level (just a Screen), use the display's size
        if not bounding_box:  # get a default bounding box
            # TODO: this is very specific to us having always a Stage (with options['screen_obj']) as our owning stage
            w = self.game_object.screen.width if hasattr(self.game_object.screen, "width") else self.display.surface.get_width()
            h = self.game_object.screen.height if hasattr(self.game_object.screen, "height") else self.display.surface.get_height()
            bounding_box = {"min_x": 0, "min_y": 0, "max_x": w, "max_y": h}

        self.directions = directions
        self.obj_to_follow = obj_to_follow
        self.bounding_box = bounding_box
        self.max_speed = max_speed
        stage.on_event("post_tick", self, "follow")
        self.follow(first=(False if max_speed > 0.0 else True))  # start following

    def unfollow_object_with_viewport(self, stage):
        """
        Stops following.

        :param GameObject stage: our game_object (the Stage) that has `self` as component
        """
        stage.off_event("post_tick", self, "follow")
        self.obj_to_follow = None

    def center_on_xy_with_viewport(self, stage, x, y):
        """
        Centers the Viewport on a given x/y position (so that the x/y position is in the center of the screen afterwards).

        :param GameObject stage: our game_object (the Stage) that has `self` as component
        :param int x: the x position to center on
        :param int y: the y position to center on
        """
        self.center_on(x, y)

    def move_to_xy_with_viewport(self, stage, x, y):
        """
        Moves the Viewport to the given x/y position (top-left corner, not center(!)).

        :param GameObject stage: our game_object (the Stage) that has `self` as Component
        :param int x: the x position to move to
        :param int y: the y position to move to
        """
        self.move_to(x, y)

    def shake_viewport(self, stage, time=3, frequency=5):
        """
        Shakes the Viewport object for the given time and with the given frequency.

        :param GameObject stage: our game_object (the Stage) that has `self` as Component
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
        Helper method to follow our self.obj_to_follow (should not be called by the API user).
        Called when the Stage triggers Event 'post_tick' (passes GameLoop into it which is not used).

        :param GameLoop game_loop: the GameLoop that's currently playing
        :param bool first: whether this is the very first call to this function (if so, do a hard center on, otherwise a soft-center-on)
        """
        follow_x = self.directions["x"](self.obj_to_follow) if callable(self.directions["x"]) else self.directions["x"]
        follow_y = self.directions["y"](self.obj_to_follow) if callable(self.directions["y"]) else self.directions["y"]

        func = self.center_on if first else self.soft_center_on
        func(self.obj_to_follow.rect.centerx if follow_x else None, self.obj_to_follow.rect.centery if follow_y else None)

    def soft_center_on(self, x=None, y=None):
        """
        Soft-centers on a given x/y position respecting the Viewport's max_speed property (unlike center_on).

        :param Union[int,None] x: the x position to center on (None if we should ignore the x position)
        :param Union[int,None] y: the y position to center on (None if we should ignore the y position)
        """
        if x:
            dx = (x - self.display.width / 2 / self.scale - self.x) / 3  # //, this.followMaxSpeed);
            if abs(dx) > self.max_speed:
                dx = math.copysign(self.max_speed, dx)

            if self.bounding_box:
                if (self.x + dx) < self.bounding_box["min_x"]:
                    self.x = self.bounding_box["min_x"] / self.scale
                elif self.x + dx > (self.bounding_box["max_x"] - self.display.width) / self.scale:
                    self.x = (self.bounding_box["max_x"] - self.display.width) / self.scale
                else:
                    self.x += dx
            else:
                self.x += dx

        if y:
            dy = (y - self.display.height / 2 / self.scale - self.y) / 3
            if abs(dy) > self.max_speed:
                dy = math.copysign(self.max_speed, dy)
            if self.bounding_box:
                if self.y + dy < self.bounding_box["min_y"]:
                    self.y = self.bounding_box["min_y"] / self.scale
                elif self.y + dy > (self.bounding_box["max_y"] - self.display.height) / self.scale:
                    self.y = (self.bounding_box["max_y"] - self.display.height) / self.scale
                else:
                    self.y += dy
            else:
                self.y += dy

    def center_on(self, x=None, y=None):
        """
        Centers on a given x/y position without(!) respecting the Viewport's max_speed property (unlike soft_center_on).

        :param Union[int,None] x: the x position to center on (None if we should ignore the x position)
        :param Union[int,None] y: the y position to center on (None if we should ignore the y position)
        """
        if x:
            self.x = x - self.display.width / 2 / self.scale
        if y:
            self.y = y - self.display.height / 2 / self.scale

    def move_to(self, x=None, y=None):
        """
        Moves the Viewport to a given x/y position (top-left corner, not centering) without(!) respecting the Viewport's max_speed property.

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
        Sets the offset property of the given Display so that it matches our (previously) calculated x/y values.

        :param Display display: the Display, whose offset we will change here
        """
        self.display.offsets[0] = self.x
        self.display.offsets[1] = self.y


class Screen(EventObject, metaclass=ABCMeta):
    """
    A Screen object has a play and a done method that need to be implemented.
    The play method stages the Screen on a Stage.
    The done method can do some cleanup.
    """
    def __init__(self, name: str = "start", **kwargs):
        super().__init__()
        self.name = name
        self.id = kwargs.get("id", 0)  # type: int

        # handle keyboard inputs
        self.keyboard_inputs = kwargs.get("keyboard_inputs", KeyboardInputs([]))  # type: KeyboardInputs
        # our Display object
        self.display = kwargs.get("display", None)  # type: Display
        self.max_fps = kwargs.get("max_fps", 60)  # type: float

    @abstractmethod
    def play(self):
        pass

    @abstractmethod
    def done(self):
        pass


class SimpleScreen(Screen):
    """
    A simple Screen that has support for labels and sprites (static images) shown on the screen.
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
        Defines this screen's Stage setup.
        Stage functions are used to setup a Stage (before playing it).

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
        Plays the Screen.
        """

        # start screen (will overwrite the old 0-stage (=main-stage))
        # - also, will give our keyboard-input setup to the new GameLoop object
        Stage.stage_screen(self, SimpleScreen.screen_func, stage_idx=0)

    def done(self):
        print("we're done!")


class Level(Screen, metaclass=ABCMeta):
    """
    A Level class adds tmx file support to the Screen.
    TiledTileLayers (background, collision, foreground, etc..) as well as single Sprite objects can be defined in the tmx file.
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
        Sets up the Stage by adding all layers (one-by-one) from the tmx file to the Stage.

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
        Start level (stage the scene; will overwrite the old 0-stage (=main-stage)).
        The options-object below will be also stored in [Stage object].options.
        Child Level classes only need to do these three things: a) stage a screen, b) register some possible events, c) play a new game loop.
        """
        Stage.stage_screen(self, None, stage_idx=0, options={
            "tile_sprite_handler": functools.partial(PhysicsComponent.tile_sprite_handler, TileSprite),
            #"components": [Viewport(self.display)]
        })

        # activate level triggers
        self.on_event("agent_reached_exit", self, "done", register=True)
        # play a new GameLoop giving it some options
        GameLoop.play_a_loop(screen_obj=self)

    def done(self):
        Stage.get_stage().stop()

        # switch off keyboard
        self.keyboard_inputs.update_keys([])  # empty list -> no more keys


class Game(object):
    """
    An object that serves as a container for Screen and Level objects.
    Manages displaying the screens (start screen, menus, etc..) and playable levels of the game.
    Also keeps a Display object (and determines its size), which is used for rendering and displaying the game.
    """

    instantiated = False

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

    def get_next_level(self, level):
        """
        returns the next level (if exists) as object; None if no next level

        :param Level level: the Level, whose next Level we would like to get
        :return: the next Level after level; None if no next Level exists
        :rtype: Union[Level,None]
        """
        try:
            next_ = self.levels[(level if isinstance(level, int) else level.id) + 1]
        except IndexError:
            next_ = None
        return next_

    def level_mastered(self, level):
        """
        a level has been successfully finished -> play next one

        :param Level level: the Level object that has been mastered
        """
        next_ = self.get_next_level(level)
        if next_:
            next_.play()
        else:
            print("All done!! Congrats!!")
            self.level_aborted(level)

    def level_lost(self, level):
        """
        a level has been lost

        :param Level level: the Level object in which the loss happened
        """
        print("Game Over!")
        self.level_aborted(level)

    def level_aborted(self, level):
        """
        aborts the level and tries to play the "start" screen

        :param Level level: the Level object that has been aborted
        """
        Stage.clear_stages()
        screen = self.screens_by_name.get("start")
        if screen:
            screen.play()
        else:
            quit()


class CollisionAlgorithm(object):
    """
    A static class that is used to store a collision algorithm.
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
    A simple axis-aligned bounding-box collision mechanism which only works on Pygame rects.
    """

    @staticmethod
    def collide(sprite1, sprite2, collision_objects=None, direction='x', direction_veloc=0.0, original_pos=None):
        # TODO: actually, we only need one collision object as we should always only resolve one object at a time

        # TODO: utilize direction veloc information to only return the smallest separation collision

        # direction must be given AND direction_veloc must not be 0.0
        #assert direction == "x" or direction == "y", "ERROR: in AABB collision between {} and {}: direction needs to be either 'x' or 'y'!". \
        #    format(type(sprite1).__name__, type(sprite2).__name__)
        #assert direction_veloc != 0.0, "ERROR in AABB collision between {} and {}: direction_veloc must not be 0.0!".\
        #    format(type(sprite1).__name__, type(sprite2).__name__)

        # use default CollisionObjects?
        if not collision_objects:
            collision_objects = AABBCollision.default_collision_objects

        ret = AABBCollision.try_collide(sprite1, sprite2, collision_objects[0], direction, direction_veloc)
        if not ret:
            return None

        if not ret.is_collided:
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
            if direction == "x":
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

        if not ret.is_collided:
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
    Adds all key/value pairs from defaults_dict into dictionary, but only if dictionary doesn't have the key defined yet.

    :param dict dictionary: the target dictionary
    :param dict defaults_dict: the source (default) dictionary to take the keys from (only if they are not defined in dictionary
    """
    for key, value in defaults_dict.items():
        if key not in dictionary:  # overwrite only if key is missing
            dictionary[key] = value


def convert_type(value, force_class=False):
    """
    Converts the given value from a string (or other) type into the most likely type.
    E.g.
    'some text' -> 'some text' (str)
    '1' -> 1 (int)
    '-51' -> -51 (int)
    '0.1' -> 0.1 (float)
    'true' -> True (bool)
    'False' -> False (bool)
    [1, 2, 3] -> [1, 2, 3] (list)
    spygame.Ladder -> <type spygame.Ladder> (a python class object; can be used as a ctor to construct objects of that class)

    :param any value: the given value to be converted to the most-likely python type
    :param bool force_class: if True, we will interpret even simple strings (starting with upper case but without any dots) as class names (e.g. Ladder)
    :return: the converted value
    :rtype: any
    """
    as_str = str(value)
    # int
    if re.fullmatch('-?\\d+', as_str):
        return int(value)
    # float
    elif re.fullmatch('-?\d+\.\d+', as_str):
        return float(value)
    # bool
    elif re.fullmatch('(true|false)', as_str, flags=re.I):
        return value in ("True", "true")
    else:
        match_obj = re.fullmatch('^((.+)\.)?([A-Z][a-zA-Z0-9]+)$', as_str)
        # a class with preceding modules (force_class does not have to be set to trigger this detection)
        if match_obj:
            _, module_, class_ = match_obj.groups(default="__main__")  # if no module given, assume a class defined in __main__
            ctor = getattr(sys.modules[module_], class_, None)
            assert isinstance(ctor, type), "ERROR: the string {}.{} does not resolve into a defined class!".format(module_, class_)
            return ctor
        # a class (no modules, but force_class is set to True)
        elif force_class:
            match_obj = re.fullmatch('^([A-Z][a-zA-Z0-9]+)$', as_str)
            if match_obj:
                (class_) = match_obj.groups()
                ctor = getattr(sys.modules["__main__"], class_, None)
                assert isinstance(ctor, type), "ERROR: the string {} does not resolve into a defined class!".format(class_)
                return ctor
        # str (or list or others)
        return value


def get_kwargs_from_obj_props(obj_props):
    """
    returns a kwargs dict retrieved from a single object's properties in a level-tmx TiledObjectGroup
    """
    kwargs = {}
    for key, value in obj_props.items():
        # special cases
        # a spritesheet (filename)
        if key == "tsx":
            kwargs["sprite_sheet"] = SpriteSheet("data/" + value + ".tsx")
        # an image_file
        elif key == "img":
            kwargs["image_file"] = "images/" + value + ".png"
        # a width/height information for the collision box
        elif key == "width_height":
            kwargs["width_height"] = tuple(map(lambda x: convert_type(x), value.split(",")))
        # vanilla kwarg
        else:
            kwargs[key] = convert_type(value)

    return kwargs
