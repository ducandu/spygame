from spygame.components.component import Component


class Animation(Component):
    """
    A Component that takes care of setting the image property of its owning Sprite object based on so-called "animation settings".
    Animation settings are stored in a global registry under the name of the SpriteSheet object that holds the images that belong to the animation setting.
    The tick method has to be called by the Sprite's tick method in order for the Sprite's image to be changed on each tick.
    """

    # static animation-properties registry
    # - stores single animation records (these are NOT Animation objects, but simple dicts representing settings for single animation sequences)
    animation_settings = {}

    # some flags
    animation_flags = {
        "none":   0x0,
        # if set: this animation does not change the Sprite's image depending on time, but they have to be set manually via the
        # frame property of the Animation component (which gives the SpriteSheet's frame, not the anim_settings frame-slot)
        "manual": 0x1,
        "all":    0xffff,
    }
    next_flag = 0x2

    @staticmethod
    def get_flag(flags):
        """
        Returns the bitmap code for an already existing Animation flag or for a new flag (the code will be created then).
        Flags are usually used to tell a Brain Component or the character directly what effects the animation has.

        :param str flags: the flag(s) (comma-separated), whose code(s) should be returned
        :return: the flag as an int; if many flags are given, returns a bitmask with all those bits set that represent the given flags
        :rtype: int
        """
        ret = 0
        for flag in flags.split(","):
            if flag not in Animation.animation_flags:
                Animation.animation_flags[flag] = Animation.next_flag
                Animation.next_flag *= 2
            ret |= Animation.animation_flags[flag]
        return ret

    @staticmethod
    def register_settings(settings_name, settings, register_events_on=None):
        # we do not have this name registered yet
        if settings_name not in Animation.animation_settings:
            assert "default" in settings, "ERROR: no entry `default` in animation-settings. Each settings block needs a default animation name."
            for anim in settings:
                if anim != "default":
                    defaults(settings[anim], {
                        "rate":          1 / 3,  # the rate with which to play this animation in 1/s
                        "frames":        [0, 1],  # the frames to play from our spritesheet (starts with 0)
                        "priority":      0,  # which priority to use for next if next is given
                        # flags bitmap that determines the behavior of the animation (e.g. block controls during animation play, etc..)
                        "flags":         0,
                        "callbacks":     None,
                        "loop":          True,  # whether to loop the animation when done
                        "next":          None,  # which animation to play next (str or callable returning a str)
                        "next_priority": 0,  # which priority to use for next if next is given
                        "trigger":       None,  # which events to trigger on the game_object that plays this animation
                        "trigger_data":  [],  # *args data to pass to the event handler if trigger is given
                        "properties":    {},    # some custom properties of this anim
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

    def __init__(self, name):
        super().__init__(name)
        self.animation = None  # str: we are playing this animation; None: we are undefined -> waiting for the next anim setup
        self.rate = 1 / 3  # default rate in s
        self.has_changed = False
        self.priority = -1  # animation priority (takes the value of the highest priority animation that wants to be played simultaneously)
        self.frame = 0  # the current frame in the animation 'frames' list OR: if self.animation is None: this is the actual frame from the SpriteSheet
        self.time = 0  # the current time after starting the animation in s
        self.flags = 0
        self.properties = {}  # custome properties of this Animation object
        self.blink_rate = 3.0
        self.blink_duration = 0
        self.blink_time = 0
        self.is_hidden = False  # True: half the time we are blinking

    def added(self):
        # make sure our GameObject is actually a Sprite
        assert isinstance(self.game_object, Sprite), "ERROR: Component Animation can only be added to a Sprite object!"

        # tell our GameObject that we might trigger some "anim..." events on it
        self.game_object.register_event("anim.start", "anim.frame", "anim.loop", "anim.end")

        # extend some methods directly onto the GameObject
        self.extend(self.play_animation)
        self.extend(self.blink_animation)

    def tick(self, game_loop):
        """
        Needs to be called by the GameObject at some point during the GameObject's `tick` method.

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
        anim_settings = None
        if self.animation and not self.flags & Animation.get_flag("manual"):
            anim_settings = Animation.get_settings(obj.anim_settings_name, self.animation)
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
                        obj.trigger_event("anim.end", self)
                        self.priority = -1
                        if anim_settings["trigger"]:
                            obj.trigger_event(anim_settings["trigger"], *anim_settings["trigger_data"])
                        # `next` could be a callable as well returning a str to use as animation setting
                        if anim_settings["next"]:
                            #print("playing next animation {}\n".format(anim_settings["next"]))
                            self.play_animation(obj, (anim_settings["next"]() if callable(anim_settings["next"]) else anim_settings["next"]),
                                                anim_settings["next_priority"])
                        return
                    # this animation loops
                    else:
                        obj.trigger_event("anim.loop", self)
                        self.frame %= len(anim_settings["frames"])

                obj.trigger_event("anim.frame", self)

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
            if self.flags & Animation.get_flag("manual"):
                obj.image = tiles_dict[int(self.frame)]
            # automatic animation: self.frame is the slot in the animation's frame list (not the SpriteSheet's!)
            elif anim_settings:
                # TEST DEBUG
                frm = int(self.frame)
                if frm >= len(anim_settings["frames"]):
                    print("BAD: anim='{}' frm {} >= len(anim_settings[frames]) {}!\n".format(self.animation, frm, len(anim_settings["frames"])))
                tile = anim_settings["frames"][frm]
                if tile >= len(tiles_dict):
                    print("BAD: anim='{}' tile {} >= len(tiles_dict) {}!\n".format(self.animation, tile, len(tiles_dict)))
                obj.image = tiles_dict[tile]

    def play_animation(self, game_object, name, priority=0):
        """
        Plays an animation on our GameObject.

        :param GameObject game_object: the GameObject on which to play the animation; the animation has to be setup via register_settings with the name
          of the SpriteSheet of the GameObject
        :param str name: the name of the animation to play
        :param int priority: the priority with which to play this animation (if this method is called multiple times, it will pick the higher one)
        """
        if name and name != self.animation:
            # look up animation in list
            anim_settings = Animation.get_settings(game_object.anim_settings_name, name)
            assert anim_settings, "ERROR: animation-to-play (`{}`) not found in spritesheet settings `{}`!".format(name, game_object.anim_settings_name)

            priority = priority or anim_settings["priority"]
            if priority >= self.priority:
                self.animation = name
                self.has_changed = True
                self.time = 0
                self.frame = 0  # start each animation from 0
                self.priority = priority
                # set flags to sprite's properties
                self.flags = anim_settings["flags"]
                self.properties = anim_settings["properties"]

                game_object.trigger_event("anim.start", self)

    def blink_animation(self, game_object, rate=3.0, duration=3.0):
        """
        Blinks the GameObject with the given parameters.

        :param GameObject game_object: our GameObject to which blinking is applied
        :param float rate: the rate with which to blink (in 1/s)
        :param float duration: the duration of the blinking (in s); after the duration, the blinking stops
        """
        self.blink_rate = rate
        self.blink_duration = duration
        self.blink_time = 0
