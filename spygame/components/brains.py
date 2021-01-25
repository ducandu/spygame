from abc import ABCMeta, abstractmethod

from spygame.components.component import Component


class Brain(Component, metaclass=ABCMeta):
    """
    A generic Brain class that has a command dict for other classes to be able to look up what the brain currently wants.
    Also has a main-switch to activate/deactivate the Brain.
    Should implement `tick` method and set self.commands each tick.
    """
    def __init__(self, name="brain", commands=None):
        super().__init__(name)

        self.is_active = True  # main switch: if False, we don't do anything
        if not commands:
            commands = []
        self.commands = {command: False for command in commands}  # the commands coming from the brain (e.g. `jump`, `sword`, `attack`, etc..)

    def reset(self):
        """
        Sets all commands to False.
        """
        for key in self.commands:
            self.commands[key] = False

    def activate(self):
        """
        Makes this Brain active: we will react to the GameLoop's keyboard events.
        """
        self.is_active = True

    def deactivate(self):
        """
        Makes this Brain inactive: we will not(!) react to the GameLoop's keyboard events (no exceptions).
        """
        self.is_active = False
        self.reset()  # set all commands to False

    @abstractmethod
    def tick(self, game_loop):
        """
        Needs to be called by the GameObject at some point during the GameObject's `tick` method.

        :param GameLoop game_loop: the currently playing GameLoop object
        """
        pass


class SimpleHumanBrain(Brain):
    """
    looks for keys that match our stored commands and sets these commands to True if the key is pressed, False otherwise
    """
    def added(self):
        pass

    def tick(self, game_loop):
        """
        Needs to be called by the GameObject at some point during the GameObject's `tick` method.
        Translates all keys from the GameLoops's KeyboardInputs object into our command dict.

        :param GameLoop game_loop: the currently playing GameLoop object
        """

        # main switch is set to OFF
        if not self.is_active:
            return

        # first reset everything to False
        self.reset()

        # current animation does not block: normal commands possible
        for key_code, is_pressed in game_loop.keyboard_inputs.keyboard_registry.items():
            # look up the str description of the key
            desc = game_loop.keyboard_inputs.descriptions[key_code]
            # look up the key-to-command translation rules
            self.commands[desc] = is_pressed

class AnimationLinkedBrain(Brain, metaclass=ABCMeta):
    """
    A Brain that is linked to an Animation component and can thus subscribe to events triggered by that Component.
    """
    def __init__(self, name="brain", commands=None):
        super().__init__(name, commands)
        self.game_obj_cmp_anim = None  # our GameObject's Animation Component (if any); needed for animation flags

    def added(self):
        # search for an Animation component of our game_object
        self.game_obj_cmp_anim = self.game_object.components.get("animation")
        assert isinstance(self.game_obj_cmp_anim, Animation),\
            "ERROR: {} needs its GameObject to also have a Component called `animation` that's of type Animation!".format(type(self).__name__)


class HumanPlayerBrain(AnimationLinkedBrain):
    """
    An AnimationLinkedBrain that handles agent control (via the GameLoop´s keyboard registry).
    Supports special keyboard->command translations (e.g. key down -> command A for one tick; key up -> command B for one tick).
    """
    def __init__(self, name="brain", key_brain_translations=None):
        """
        :param str name: the name of this component
        :param Union[list,None] key_brain_translations: list of KeyboardBrainTranslation objects or None
        """
        super().__init__(name)

        # stores the values of the keyboard_inputs in the previous tick (to catch changes in the keyboard state)
        self.keyboard_prev = {}

        # build our key_brain_translation dict to translate key inputs into commands
        if key_brain_translations is None:
            key_brain_translations = []

        self.key_brain_translations = {}
        self.add_translations(key_brain_translations)

        self.animation_prev = None

        self.is_paralyzed = False  # is this brain paralyzed? (e.g. when agent is dizzy)
        self.paralyzes_exceptions = None  # keys that are still ok to be handled, even if paralyzed

    def added(self):
        super().added()
        # subscribe to anim.ends events
        self.game_obj_cmp_anim.on_event("anim.ends", self, "anim_ends", register=True)

    def anim_ends(self, anim, anim_new):
        pass

    def add_translations(self, key_brain_translations):
        """
        Adds a single or more KeyboardBrainTranslation object to our dict.

        :param Union[KeyboardBrainTranslation,str,dict,tuple] key_brain_translations: the keyboard-to-command translation to be added to this Brain
         (can be represented in different ways; see code)
        """
        # list: re-call this method one-by-one
        if isinstance(key_brain_translations, list):
            for trans in key_brain_translations:
                self.add_translations(trans)
        # str: key = command
        elif isinstance(key_brain_translations, str):
            self.add_translations(KeyboardBrainTranslation(key_brain_translations, key_brain_translations))
        # tuple: pass as positional args into c'tor (key,cmd,flags,other_cmd,anim_to_be_completed)
        elif isinstance(key_brain_translations, tuple):
            self.add_translations(KeyboardBrainTranslation(*key_brain_translations))
        # dict: pass as kwargs into c'tor
        elif isinstance(key_brain_translations, dict):
            self.add_translations(KeyboardBrainTranslation(**key_brain_translations))
        # KeyboardBrainTranslation: take as is and store
        elif isinstance(key_brain_translations, KeyboardBrainTranslation):
            assert key_brain_translations.key not in self.key_brain_translations, "ERROR: key {} already in key_brain_translations dict!". \
                format(key_brain_translations.key)
            self.key_brain_translations[key_brain_translations.key] = key_brain_translations
            self.keyboard_prev[key_brain_translations.key] = False  # create the entry for the key (for faster lookup later without [dict].get())
            self.commands[key_brain_translations.command] = False
            if key_brain_translations.other_command:
                self.commands[key_brain_translations.other_command] = False
        # not supported type
        else:
            raise Exception("ERROR: key_brain_translations parameter has wrong type; needs to be str, KeyboardBrainTranslation, tuple, or dict!")

    def remove_translation(self, key):
        """
        Adds a single KeyboardBrainTranslation object to our dict.

        :param str key: the key (str) to be removed from our key-to-command translation dict
        """
        self.key_brain_translations.pop(key, None)

    #def enable_translation(self, key):
    #    trans = self.key_brain_translations.get(key)
    #    if trans:
    #        trans.is_disabled = False

    #def disable_translation(self, key):
    #    trans = self.key_brain_translations.get(key)
    #    if trans:
    #        trans.is_disabled = True

    def tick(self, game_loop: GameLoop):
        """
        Needs to be called by the GameObject at some point during the GameObject's `tick` method.
        Translates all keys from the GameLoops's KeyboardInputs object into our command dict.

        :param GameLoop game_loop: the currently playing GameLoop object
        """

        # main switch is set to OFF
        if not self.is_active:
            return

        # support for `paralyzes` flag and `paralyzes_exceptions` is built into this class
        self.is_paralyzed = bool(self.game_obj_cmp_anim.flags & Animation.get_flag("paralyzes"))
        self.paralyzes_exceptions = self.game_obj_cmp_anim.properties.get("paralyzes_exceptions")

        # first reset everything to False
        self.reset()

        # current animation does not block: normal commands possible
        for key_code, is_pressed in game_loop.keyboard_inputs.keyboard_registry.items():
            # look up the str description of the key
            desc = game_loop.keyboard_inputs.descriptions[key_code]
            # look up the key-to-command translation rules
            trans = self.key_brain_translations.get(desc)  # type: KeyboardBrainTranslation
            # not a known key to this Brain OR this translation is (temporarily) disabled
            if not trans or trans.is_disabled or (self.is_paralyzed and (not self.paralyzes_exceptions or desc not in self.paralyzes_exceptions)):
                continue
            # normal translation
            if trans.flags == trans.NORMAL:
                self.commands[trans.command] = is_pressed
            # key is currently down
            elif is_pressed:
                # if we don't repeat the command -> check whether this press is new and only then set the command
                if trans.flags & trans.DOWN_ONE_TICK:
                    # key was previously up -> new press
                    if self.keyboard_prev[desc] is False:
                        # check for condition on the current anim (don't set command if a certain anim is currently playing)
                        if (trans.flags & trans.BLOCK_REPEAT_UNTIL_ANIM_COMPLETE) == 0 or \
                                self.game_obj_cmp_anim.animation not in trans.animation_to_complete:
                            self.commands[trans.command] = True
                # NORMAL: down -> leave command=True
                else:
                    self.commands[trans.command] = True
            # key is currently up
            else:
                # we fire a single-tick other_command if the key has just been released
                if trans.flags & trans.UP_ONE_TICK and self.keyboard_prev[desc] is True:
                    # we have an anim condition on other_command
                    if trans.flags & trans.BLOCK_OTHER_CMD_UNTIL_ANIM_COMPLETE:
                        if trans.state_other_command & trans.STATE_FULLY_CHARGED:
                            # fire command and reset all state flags
                            self.commands[trans.other_command] = True
                            trans.state_other_command = 0
                        # set the STATE_CMD_RECEIVED flag and wait for the charging to be complete
                        elif trans.state_other_command & trans.STATE_CHARGING:
                            trans.state_other_command |= trans.STATE_CMD_RECEIVED
                    # no anim condition
                    else:
                        self.commands[trans.other_command] = True
                # if we are waiting for other_command to be charged -> check whether we have to keep the main command active (until charging is done)
                elif trans.flags & trans.BLOCK_OTHER_CMD_UNTIL_ANIM_COMPLETE and trans.state_other_command & trans.STATE_CHARGING:
                    self.commands[trans.command] = True

            # check for other command dependency on animation and start charging (or reset state)
            if trans.flags & trans.BLOCK_OTHER_CMD_UNTIL_ANIM_COMPLETE:
                # we are currently charging (playing the animation)
                if self.game_obj_cmp_anim.animation in trans.animation_to_complete:
                    trans.state_other_command |= trans.STATE_CHARGING
                    trans.state_other_command &= ~trans.STATE_FULLY_CHARGED
                # we are just done with the animation -> set to fully charged
                elif self.animation_prev in trans.animation_to_complete:
                    # if we have already got the command -> fire it now
                    if trans.state_other_command & trans.STATE_CMD_RECEIVED:
                        self.commands[trans.command] = False
                        self.commands[trans.other_command] = True
                        trans.state_other_command = 0
                    # otherwise, update the charging state and keep waiting for the key to be released
                    else:
                        trans.state_other_command |= trans.STATE_FULLY_CHARGED
                        trans.state_other_command &= ~trans.STATE_CHARGING

            # update keyboard_prev dict
            self.keyboard_prev[desc] = is_pressed
            # store previous animation
            self.animation_prev = self.game_obj_cmp_anim.animation


class AIBrain(AnimationLinkedBrain):
    """
    An AnimationLinkedBrain that can handle simple left/right logic for 2D platformer monsters.
    The brain will take care of avoiding cliffs, but other than that always just walk from left to right and back.
    Overwrite this to implement more complex behaviors in the tick method.
    """
    def __init__(self, name="brain", commands=None):
        if not commands:
            commands = ["left", "right"]
        super().__init__(name, commands)
        self.flipped = False  # if True: character is turning left

    def added(self):
        super().added()

        # simple behavior: change our direction if we run into a wall
        self.game_object.on_event("bump.right", self, "bumped", register=True)
        self.game_object.on_event("bump.left", self, "bumped", register=True)

    def tick(self, game_loop):
        """
        Needs to be called by the GameObject at some point during the GameObject's `tick` method.

        :param GameLoop game_loop: the currently playing GameLoop object
        """
        obj = self.game_object

        self.reset()

        if self.game_obj_cmp_anim and self.game_obj_cmp_anim.flags & Animation.get_flag("paralyzes"):
            return

        # look for edges ahead -> then change direction if one is detected
        # - makes sure an enemy character does not fall off a cliff
        if (not (game_loop.frame % 3) and self.check_cliff_ahead()) or obj.rect.x <= 0 or obj.rect.x >= obj.x_max:
            self.toggle_direction()

        self.commands["left" if self.flipped else "right"] = True

    def bumped(self, col):
        self.toggle_direction()

    def toggle_direction(self):
        """
        Changes the current direction (left to right or vice-versa)
        """
        self.flipped = self.flipped is False

    def check_cliff_ahead(self):
        """
        Checks whether there is a cliff ahead (returns true if yes).
        """
        obj = self.game_object
        tile_w = obj.stage.screen.tmx_obj.tilewidth
        tile_h = obj.stage.screen.tmx_obj.tileheight
        # check below character (c=character sprite, _=locateObject (a stripe with x=x width=w-6 and height=3))
        # ccc    -> walking direction
        # ccc
        #  _
        w = max(tile_w * 1.5, obj.rect.width - 6)
        col = obj.stage.locate((obj.rect.right - tile_w - w) if self.flipped else (obj.rect.left + tile_w),
                               obj.rect.bottom - tile_h * 0.5,
                               w,
                               tile_h * 1.75,
                               Sprite.get_type("default"))
        if not col or isinstance(col.sprite2, LiquidBody):
            return True
        return False

    # checks whether an enemy is in sight
    def check_enemy_ahead(self):
        pass
