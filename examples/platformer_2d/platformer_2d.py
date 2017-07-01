"""
 -------------------------------------------------------------------------
 spygame - platformer_2d.py

 a 2D platformer demo (all graphics are (c) Blizzard Entertainment Inc)

 all you need to run this example are the files in:
    data/
    images/
    from www.github.com/sven1977/spygame/tree/master/examples/platformer_2d

 created: 2017/06/12 in PyCharm
 (c) 2017 Sven - ducandu GmbH
 -------------------------------------------------------------------------
"""

import spygame as spyg

import random
from abc import ABCMeta, abstractmethod

import pygame
import pygame.font

import functools
import math


class KeyLock(spyg.Sprite):
    def __init__(self, x, y, color="yellow"):
        super().__init__(x, y, image_file="images/generic.png", image_section=(2*16, 1*16, 16, 16))
        self.color = color
        # make sure we get stored as items-that-we-are-touching-right-now inside some physics component (in order to unlock iff using key and touching )
        self.type = spyg.Sprite.get_type("touch")
        # don't collide with anything
        self.collision_mask = 0
        self.render_order = 10

    def unlocked(self):
        """
        will execute once a Viking is touching this KeyLock and using the matching Key Item
        """
        pass


class Viking(spyg.AnimatedSprite, metaclass=ABCMeta):
    """
    a generic Viking class
    """
    def __init__(self, x, y, spritesheet, animation_setup):
        """
        :param int x: the start x position
        :param int y: the start y position
        :param spyg.SpriteSheet spritesheet: the SpriteSheet object (tsx file) to use for this Viking
        :param dict animation_setup: a dictionary to be passed to spyg.Animation.register_settings and
                stored under the SpriteSheet.name in the animations registry
        :param spyg.HumanPlayerBrain brain: a custom spyg.HumanPlayerBrain to use for this Viking
        """
        super().__init__(x, y, spritesheet, animation_setup, width_height=(24, 32))

        self.type = spyg.Sprite.get_type("friendly")
        self.collision_mask |= spyg.Sprite.get_type("default,one_way_platform,particle")

        self.life_points = 3
        self.ladder_frame = 0
        self.ladder_frame_bend = 63  # the frame number in the SpriteSheet where the character just bends down to start climbing
        self.ladder_frame_start_climb = 64  # the frame number in the SpriteSheet where the character is between bending down and climbing
        self.ladder_frames = [65, 66, 67, 68]  # the frame numbers in the SpriteSheet that describe the climbing movement
        self.unhealthy_fall_speed = 420
        self.unhealthy_fall_speed_on_slopes = 450  # on slopes, vikings can fall a little harder without hurting themselves

        # add components to this Viking
        # loop time line:
        # - pre-tick: HumanPlayerBrain (needs animation comp to check e.g., which commands are paralyzed), Physics (movement + collision resolution)
        # - tick: chose animation to play
        # - post-tick: Animation
        self.register_event("pre_brain", "pre_physics", "post_physics", "collision", "pre_animation", "post_animation")

        # add our Components
        self.cmp_brain = self.add_component(spyg.HumanPlayerBrain("brain", ["up", "down", "left", "right"]))  # type: spyg.HumanPlayerBrain

        phys = spyg.PlatformerPhysics("physics")
        phys.squeeze_speed = 0.5
        self.cmp_physics = self.add_component(phys)  # type: spyg.PlatformerPhysics

        # subscribe/register to some events
        self.on_event("bump.bottom", self, "land")
        self.on_event("squeezed.top", self, "get_squeezed")
        self.on_event("hit.liquid_ground", self, "hit_liquid_ground")  # player stepped into liquid ground
        self.on_event("hit.particle", self, "hit_particle")  # player hits a particle
        self.on_event("die", register=True)  # some animations trigger 'die' when done
        self.register_event("dead")

        # initialize the 'getting bored'-timer
        self.standing_around_since = 0
        self.next_bored_seq = int(random.random() * 10) + 5  # play the next 'bored'-sequence after this amount of seconds

    # makes this Viking the currently active player
    def activate(self):
        self.cmp_brain.activate()

    # makes this Viking currently inactive
    def deactivate(self):
        self.cmp_brain.deactivate()

    # sequence of this Sprite's tick-flow:
    # - tick gets called by the Stage
    # - pre_brain is triggered
    # - HumanPlayerBrain is ticked
    # - pre_physics is triggered
    # - PlatformerPhysocs is ticked
    # -- determines x/y speeds and moves according to s = v*dt
    # -- runs collision detection against all layers
    # -- event "collision" is triggered on this Sprite if collisions are found
    # --- Physics Component listens for this event and handles the collision by solving for wall-bumps and slopes
    # - post_physics is triggered
    # - next animation to play is determined (play_animation is called)
    # - pre_animation is triggered
    # - Animation is ticked (now, the played animation will actually be blitted)
    # - post_animation is triggered
    def tick(self, game_loop):
        dt = game_loop.dt

        # pre-brain event
        self.trigger_event("pre_brain", game_loop)

        # brain
        self.cmp_brain.tick(game_loop)

        # pre physics
        self.trigger_event("pre_physics", game_loop)

        # physics
        self.cmp_physics.tick(game_loop)

        # post physics
        self.trigger_event("post_physics", game_loop)

        # player is currently standing on ladder (locked into ladder)
        if self.check_on_ladder(dt):
            pass

        # jumping/falling
        elif self.check_in_air():
            pass

        # special capabilities can go here: e.g. hit with sword or shoot arrows
        elif self.check_actions():
            pass

        # moving in x direction
        elif self.cmp_physics.vx != 0:
            self.check_running()

        # not moving in x direction
        else:
            if self.cmp_animation.animation == "stand" or self.cmp_animation.animation == "stand_shield_down":
                self.standing_around_since += dt
            else:
                self.standing_around_since = 0

            # not moving in x-direction, but trying -> push
            if self.cmp_brain.commands["left"] != self.cmp_brain.commands["right"]:  # xor
                self.play_animation("push")
            # out of breath from running?
            elif hasattr(self, "check_out_of_breath") and self.check_out_of_breath():
                pass
            # getting bored?
            elif self.check_bored_timer():
                pass
            # just stand (if allowed)
            elif self.allow_play_stand():
                pass

        # pre animation
        self.trigger_event("pre_animation", game_loop)

        # animation
        self.cmp_animation.tick(game_loop)

        # post animation
        self.trigger_event("post_animation", game_loop)

        return

    @abstractmethod
    def check_actions(self):
        pass

    def check_on_ladder(self, dt):
        """
        returns True if we are currently locked into a ladder, False otherwise
        - if we are locked into a ladder also set the current SpriteSheet frame manually (via animation.frame and animation.animation=None)

        :param float dt: the time passed since the last tick
        :return: whether we are locked into a ladder or not
        :rtype: bool
        """
        anim = self.components["animation"]

        # we are not locked into a ladder -> early out
        if self.cmp_physics.on_ladder is None:
            # if our animation is still set to climb -> play default animation
            if anim.animation == "climb":
                self.play_animation(spyg.Animation.get_settings(self.spritesheet.name, "default"))
            return False

        self.play_animation("climb")  # set to climb (is_manual == True; set frame manually when on ladder)

        # we are almost at the top (last n pixels) -> put end-of-ladder frame
        delta = self.rect.bottom - self.cmp_physics.touched_ladder.rect.top
        if delta <= 4:
            self.ladder_frame = self.ladder_frame_bend
        # we are reaching the top -> put one-before-end-of-ladder frame
        elif delta <= 12:
            self.ladder_frame = self.ladder_frame_start_climb
        # we are in middle of ladder -> alternate climbing frames
        else:
            self.ladder_frame += self.cmp_physics.vy * dt * -0.12
            if self.ladder_frame >= self.ladder_frames[-1] + 1:
                self.ladder_frame = self.ladder_frames[0]
            elif self.ladder_frame < self.ladder_frames[0]:
                self.ladder_frame = self.ladder_frames[-1] + 0.999

        anim.frame = int(self.ladder_frame)  # floor to whole frame number

        return True

    # function is called when sprite lands on floor
    def land(self, col):
        # if impact was big -> bump head/beDizzy
        if col.impact > self.unhealthy_fall_speed:
            self.play_animation("be_dizzy", 1)

    # quicksand or water
    def hit_liquid_ground(self, what):
        self.play_animation("sink_in_" + what)

    # hit a flying particle (shot, arrow, etc..)
    def hit_particle(self, col):
        # sliding away from arrow
        # TODO: if we set the speed here, it will be overwritten (to 0) by step func in gamePhysics component
        # we need to have something like an external force that will be applied on top of the player's/scorpion's own movements
        # p.vx = 100*(col.normalX > 0 ? 1 : -1);
        # p.gravityX = -2*(col.normalX > 0 ? 1 : -1);
        self.play_animation("get_hurt", 1)

    # called when this object gets squeezed from top by a heavy object
    def get_squeezed(self, squeezer):
        self.play_animation("get_squeezed", 1)
        # update collision points (top point should be 1px lower than bottom point of squeezer)
        # TODO: don't have p.points in spygame ??
        # dy = (squeezer.rect.y + squeezer.rect.centery) - (self.y + p.points[0][1]) + 1
        # Q._changePoints(this, 0, dy)

    # die function (take this Viking out of the game)
    def die(self):
        self.destroy()

    # player is running (called if x-speed != 0)
    def check_running(self):
        if self.cmp_brain.commands["left"] != self.cmp_brain.commands["right"]:  # xor
            if self.cmp_physics.at_wall:
                self.play_animation("push")
            else:
                self.play_animation("run")

    # check whether we are in the air
    def check_in_air(self):
        # we are sinking in water/quicksand
        if self.cmp_animation.animation == "sink_in_quicksand" or self.cmp_animation.animation == "sink_in_water":
            return False
        # falling too fast
        elif self.cmp_physics.vy > self.unhealthy_fall_speed:
            self.play_animation("fall")
            return True
        # TODO: use something like docking_state to determine whether we are falling or not
        elif self.cmp_physics.vy != 0:
        #elif not self.docking_state[0]:
            self.play_animation("jump")
            return True
        return False

    # check, whether player is getting bored (to play bored sequence)
    def check_bored_timer(self):
        if self.standing_around_since > self.next_bored_seq:
            self.standing_around_since = 0
            self.next_bored_seq = int(random.random() * 5) + 5
            self.play_animation(random.choice(["be_bored1", "be_bored2"]))
            return True
        return False

    # check, whether it's ok to play 'stand' animation
    def allow_play_stand(self):
        anim_setup = spyg.Animation.get_settings(self.spritesheet.name, self.cmp_animation.animation)
        if anim_setup and not (anim_setup["flags"] & spyg.Animation.get_flag("block_stand")):
            # TODO: fix this depedency on knowing that some children will be defining `which_stand` method
            self.play_animation(self.which_stand() if hasattr(self, "which_stand") else "stand")


# define player: Baleog the Fierce
class Baleog(Viking):
    def __init__(self, x, y):
        super().__init__(x, y, spyg.SpriteSheet("data/baleog.tsx"), {
            "default":           "stand",  # the default animation to play
            "stand":             {"frames": [0], "loop": False, "flags": spyg.Animation.get_flag("block_stand"), "priority": 0},
            "be_bored1":         {"frames": [1, 2, 2, 1, 1, 3, 4, 3, 4, 5, 6, 5, 6, 7, 8, 7, 8, 3, 4, 3, 4], "rate": 1 / 3, "loop": False, "next": "stand"},
            "be_bored2":         {"frames": [1, 2, 2, 1, 1, 7, 8, 7, 8, 2, 2, 1, 2, 2, 1], "rate": 1 / 3, "loop": False, "next": "stand"},
            "climb":             {"flags":  spyg.Animation.get_flag("manual")},
            "run":               {"frames": [9, 10, 11, 12, 13, 14, 15, 16], "rate": 1 / 8},
            "push":              {"frames": [54, 55, 56, 57], "rate": 1 / 4},
            "jump":              {"frames": [36, 37], "rate": 1 / 6},
            "fall":              {"frames": [38], "loop": False, "flags": spyg.Animation.get_flag("paralyzes"),
                                  "properties": {"paralyzes_exceptions": {"left", "right", "up"}}},
            "be_dizzy":          {"frames": [39, 40, 41, 40, 41, 42, 42, 43], "rate": 1 / 3, "loop": False, "next": "stand",
                                  "flags":  spyg.Animation.get_flag("paralyzes,block_stand")},
            "get_hurt":          {"frames": [72], "rate": 1 / 2, "next": "stand",
                                  "flags":  spyg.Animation.get_flag("paralyzes,block_stand")},
            "get_squeezed":      {"frames": [122, 123, 124, 124, 125, 125, 125, 125], "rate": 1 / 3, "loop": False, "trigger": "die",
                                  "flags":  spyg.Animation.get_flag("paralyzes,block_stand")},
            "sink_in_quicksand": {"frames": [120, 121, 121, 120, 120, 121, 121, 120], "rate": 1 / 2, "loop": False, "trigger": "die",
                                  "priority": 100,
                                  "flags":  spyg.Animation.get_flag("paralyzes")},
            "sink_in_water":     {"frames": [90, 91, 92, 93, 91, 92, 93], "rate": 1 / 2, "loop": False, "trigger": "die",
                                  "priority": 100,
                                  "flags":  spyg.Animation.get_flag("paralyzes")},
            "burn":              {"frames": [126, 127, 128, 129, 130, 131, 132, 133], "rate": 1 / 4, "loop": False, "trigger": "die",
                                  "flags":  spyg.Animation.get_flag("paralyzes,block_stand")},
            # disables control, except for action1 (which is pressed down)
            "swing_sword1":      {"frames": [18, 19, 20, 21], "rate": 1 / 4, "loop": False, "next": "stand",
                                  "flags":  spyg.Animation.get_flag("paralyzes")},
            # disables control, except for action1 (which is pressed down)
            "swing_sword2":      {"frames": [22, 23, 24, 25], "rate": 1 / 4, "loop": False, "next": "stand",
                                  "flags":  spyg.Animation.get_flag("paralyzes")},
            "draw_bow":          {"frames": [27, 27, 28, 29, 30, 31], "rate": 1 / 5, "loop": False, "next": "hold_bow",
                                  "priority": 1,
                                  "flags": spyg.Animation.get_flag("paralyzes"), "properties": {"paralyzes_exceptions": {"d"}}},
            "hold_bow":          {"frames": [31], "loop": False, "priority": 2,
                                  "flags": spyg.Animation.get_flag("paralyzes"), "properties": {"paralyzes_exceptions": {"d"}},
                                  },
            "release_bow":       {"frames": [33, 32, 33, 32, 33, 32, 0], "rate": 1 / 6, "loop": False, "next": "stand",
                                  "priority": 3,
                                  "flags":  spyg.Animation.get_flag("block_stand,paralyzes")},
        })

        # add non-standard actions to our Brain
        self.cmp_brain.add_translations([
            ("space", "swing_sword", spyg.KeyboardBrainTranslation.DOWN_ONE_TICK | spyg.KeyboardBrainTranslation.BLOCK_REPEAT_UNTIL_ANIM_COMPLETE,
             None, {"swing_sword1", "swing_sword2"}),  # sword
            ("d", "draw_bow", spyg.KeyboardBrainTranslation.UP_ONE_TICK | spyg.KeyboardBrainTranslation.BLOCK_OTHER_CMD_UNTIL_ANIM_COMPLETE,
             "release_bow", "draw_bow"),  # bow (anim draw_bow has to be complete)
        ])

        # parametrize our physics
        self.components["physics"].can_jump = False

    def check_actions(self):
        # sword or arrow?
        if self.check_hit_with_sword() or self.check_shoot_with_arrow():
            return True
        return False

    def check_hit_with_sword(self):
        """
        :return: True if player is currently hitting with sword
        :rtype: bool
        """
        brain = self.components["brain"]
        if brain.commands["swing_sword"]:
            self.play_animation(random.choice(["swing_sword1", "swing_sword2"]))
            return True

        return self.cmp_animation.animation[:11] == "swing_sword"

    def check_shoot_with_arrow(self):
        """
        :return: True if player is doing something with arrow right now
        :rtype: bool
        """
        brain = self.components["brain"]
        if brain.commands["draw_bow"]:
            print("getting `draw_bow` command: playing draw_bow\n")
            self.play_animation("draw_bow")
            return True
        elif brain.commands["release_bow"]:
            print("getting `release_bow` command: playing release_bow and shooting\n")
            self.play_animation("release_bow")
            self.stage.add_sprite(Arrow(self), "arrows")
            return True
        return False


# define player: Erik the Swift
class Erik(Viking):
    def __init__(self, x, y):
        super().__init__(x, y, spyg.SpriteSheet("data/erik.tsx"), {
            "default":           "stand",  # the default animation to play
            "stand":             {"frames": [0], "loop": False, "flags": spyg.Animation.get_flag("block_stand")},
            "be_bored1":         {"frames": [1], "rate": 1 / 2, "next": "stand", "flags": spyg.Animation.get_flag("block_stand")},
            "be_bored2":         {"frames": [61, 2, 3, 4, 3, 4, 3, 4], "rate": 1 / 3, "next": 'stand',
                                  "flags":  spyg.Animation.get_flag("block_stand")},
            "climb":             {"flags":  spyg.Animation.get_flag("manual")},
            "run":               {"frames": [5, 6, 7, 8, 9, 10, 11, 12], "rate": 1 / 8},
            "out_of_breath":     {"frames": [13, 14, 15, 13, 14, 15], "rate": 1 / 4, "next": 'stand',
                                  "flags":  spyg.Animation.get_flag("block_stand")},
            "push":              {"frames": [54, 55, 56, 57], "rate": 1 / 4},
            "jump_up":           {"frames": [16], "loop": False},
            "jump_peak":         {"frames": [17], "loop": False},
            "jump_down":         {"frames": [18, 19], "rate": 1 / 3},
            "fall":              {"frames": [81], "loop": False, "flags": spyg.Animation.get_flag("paralyzes"),
                                  "properties": {"paralyzes_exceptions": {"left", "right", "up"}}},
            "be_dizzy":          {"frames": [36, 37, 38, 39, 40, 38, 39, 40, 41, 42, 43], "rate": 1 / 3, "loop": False, "next": 'stand',
                                  "flags":  spyg.Animation.get_flag("paralyzes,block_stand")},
            "get_hurt":          {"frames": [72], "rate": 1 / 2, "next": 'stand',
                                  "flags":  spyg.Animation.get_flag("paralyzes,block_stand")},
            "get_squeezed":      {"frames": [126, 127, 128, 128, 129, 129, 129, 129], "rate": 1 / 4, "loop": False, "trigger": 'die',
                                  "flags":  (spyg.Animation.get_flag("paralyzes,block_stand"))},
            "sink_in_quicksand": {"frames": [108, 109, 110, 108, 109, 110, 108, 109], "loop": False, "rate": 1 / 2, "trigger": 'die',
                                  "priority": 100,
                                  "flags":  spyg.Animation.get_flag("paralyzes")},
            "sink_in_water":     {"frames": [90, 91, 92, 93, 91, 92, 93], "loop": False, "rate": 1 / 2, "trigger": 'die',
                                  "priority": 100,
                                  "flags":  spyg.Animation.get_flag("paralyzes")},
            "burn":              {"frames": [117, 118, 119, 120, 121, 122, 123, 124], "rate": 1 / 4, "loop": False, "trigger": 'die',
                                  "flags":  spyg.Animation.get_flag("paralyzes")},
        })

        # add non-standard actions to our Brain
        self.cmp_brain.add_translations([
            ("space", "jump"),
            #("d", "cmd_smash_wall", spyg.KeyboardBrainTranslation.),
            #TODO: smash walls("d", "smash", ),
        ])

        # edit physics a little
        phys = self.components["physics"]
        phys.run_acceleration = 450
        phys.can_jump = True
        phys.vx_max = 175
        phys.stops_abruptly_on_direction_change = False

        self.ran_fast = False  # flag: if True, play outOfBreath sequence
        self.vx_out_of_breath = 120  # speed after which to play outOfBreath sequence
        self.vx_smash_wall = 150  # minimum speed at which we can initiate smash sequence with 'D'

    # Erik has no special actions
    def check_actions(self):
        return False

    def check_running(self):
        phys = self.components["physics"]
        brain = self.components["brain"]
        if brain.commands["left"] != brain.commands["right"]:  # xor
            if phys.at_wall:
                self.play_animation("push")
                self.ran_fast = True
            else:
                self.play_animation("run")
            if abs(phys.vx) > self.vx_out_of_breath:
                self.ran_fast = True

    # check whether we are in the air
    def check_in_air(self) -> bool:
        anim = self.components["animation"]
        phys = self.components["physics"]
        # we are sinking in water/quicksand
        if anim.animation == "sink_in_quicksand" or anim.animation == "sink_in_water":
            return False
        # falling too fast
        elif phys.vy > self.unhealthy_fall_speed:
            self.play_animation("fall")
            return True
        # Erik jumps
        elif phys.vy != 0:
            if abs(phys.vy) < 60:
                self.play_animation("jump_peak")
            elif phys.vy < 0:
                self.play_animation("jump_up")
            elif phys.vy > 0:
                self.play_animation("jump_down")
            return True
        return False

    # overwrite bored functionality: Erik blinks eyes more often than he does his other crazy stuff
    def check_bored_timer(self):
        if self.standing_around_since > self.next_bored_seq:
            self.standing_around_since = 0
            self.next_bored_seq = int(random.random() * 5) + 5
            self.play_animation(random.choice(["be_bored1", "be_bored1"]))
            return True
        return False

    # check whether we should play the out of breath sequence
    def check_out_of_breath(self):
        anim = self.components["animation"]
        if anim.animation == "run" and self.ran_fast:
            self.play_animation("out_of_breath")
            self.ran_fast = False
        return False


# define player: Olaf the ???
class Olaf(Viking):
    def __init__(self, x, y):
        super().__init__(x, y, spyg.SpriteSheet("data/olaf.tsx"), {
            "default":              "stand_shield_down",  # the default animation to play
            "stand_shield_down":    {"frames": [0], "loop": False},
            "stand_shield_up":      {"frames": [14], "loop": False},
            "be_bored":             {"frames": [1, 2, 3, 2, 3, 2, 3, 4, 4, 3, 1], "rate": 1 / 3, "next": self.which_stand, "flags": spyg.Animation.get_flag("block_stand")},
            "climb":                {"flags":  spyg.Animation.get_flag("manual")},
            "run_shield_down":      {"frames": [5, 6, 7, 9, 10, 11, 12, 13], "rate": 1 / 8},
            "run_shield_up":        {"frames": [15, 16, 17, 18, 19, 20, 21, 22], "rate": 1 / 8},
            "push":                 {"frames": [33, 34, 36, 37], "rate": 1 / 4},
            "sail_shield_down":     {"frames": [52, 53], "rate": 1 / 6},
            "sail_shield_up":       {"frames": [24, 25], "rate": 1 / 4},
            "sail_shield_up_steer": {"frames": [27, 28], "rate": 1 / 4},
            "fall":                 {"frames": [54, 54, 90], "rate": 1, "loop": False, "flags": spyg.Animation.get_flag("paralyzes"),
                                     "properties": {"paralyzes_exceptions": {"left", "right", "up"}}},
            "be_dizzy":             {"frames": [29, 30, 31, 32], "rate": 1 / 2, "loop": False, "next": self.which_stand,
                                     "flags":  spyg.Animation.get_flag("paralyzes,block_stand")},
            "get_hurt":             {"frames": [38], "rate": 1 / 2, "next": self.which_stand,
                                     "flags":  spyg.Animation.get_flag("paralyzes,block_stand")},
            "get_squeezed":         {"frames": [117, 118, 119, 119, 120, 120, 120, 120], "rate": 1 / 4, "loop": False, "trigger": "die",
                                     "flags":  spyg.Animation.get_flag("paralyzes,block_stand")},
            "sink_in_quicksand":    {"frames": [102, 103, 102, 103, 102, 103, 102, 103], "loop": False, "rate": 1 / 2, "trigger": "die",
                                     "priority": 100,
                                     "flags":  spyg.Animation.get_flag("paralyzes")},
            "sink_in_water":        {"frames": [63, 64, 65, 66, 66, 67], "loop": False, "rate": 1 / 2, "trigger": "die",
                                     "priority": 100,
                                     "flags":  spyg.Animation.get_flag("paralyzes")},
            "burn":                 {"frames": [108, 109, 110, 111, 112, 113, 114, 115], "rate": 1 / 4, "loop": False, "trigger": "die",
                                     "flags":  spyg.Animation.get_flag("paralyzes")},
        })

        # add non-standard actions to our Brain
        self.cmp_brain.add_translations([
            ("space", "switch_shield", spyg.KeyboardBrainTranslation.DOWN_ONE_TICK),  # shield up/down
            # TODO: careful: if two keys write to the same command, the second key will always overwrite the first one
            # ("d", "switch_shield", spyg.KeyboardBrainTranslation.DOWN_ONE_TICK),  # shield up/down
        ])

        phys = self.cmp_physics
        phys.run_acceleration = 100
        phys.vx_max = 140
        self.max_fall_speed_shield_down = phys.max_fall_speed
        self.max_fall_speed_shield_up = phys.max_fall_speed / 10

        self.ladder_frame_bend = 39
        self.ladder_frame_start_climb = 40
        self.ladder_frames = [41, 42, 43, 45]

        self.is_shield_up = False  # whether Olaf has his shield currently up or down

        # sneak shield handling into the parent's tick function
        self.on_event("pre_physics", self, "check_switch_shield")

    def check_switch_shield(self, game_loop):
        # we are getting a switch shield command -> first switch the position of our shield
        if self.cmp_brain.commands["switch_shield"]:
            self.is_shield_up = (self.is_shield_up is False)  # toggle
            # change our physics properties based on shield state
            # - one-way-feature to Olaf (things can stand on top of him)
            # - fall-speed
            phys = self.cmp_physics
            if self.is_shield_up:
                phys.max_fall_speed = self.max_fall_speed_shield_up
                self.type |= spyg.Sprite.get_type("dockable,one_way_platform")
            else:
                phys.max_fall_speed = self.max_fall_speed_shield_down
                self.type &= ~(spyg.Sprite.get_type("dockable,one_way_platform"))

    def which_stand(self):
        return "stand_shield_up" if self.is_shield_up else "stand_shield_down"

    # Olaf has no special actions
    def check_actions(self):
        return False

    # check whether we are in the air
    def check_in_air(self):
        # we are sinking in water/quicksand
        if self.cmp_animation.animation == "sink_in_quicksand" or self.cmp_animation.animation == "sink_in_water":
            return False
        # falling too fast
        elif self.cmp_physics.vy > self.unhealthy_fall_speed:
            self.play_animation("fall")
            return True
        # TODO: use something like docking_state to determine whether we are falling or not
        elif self.cmp_physics.vy != 0:
        #elif not self.docking_state[0]:
            if self.is_shield_up:
                # we are steering
                if self.cmp_brain.commands["right"] or self.cmp_brain.commands["left"]:
                    self.play_animation("sail_shield_up_steer")
                # we are just sailing
                else:
                    self.play_animation("sail_shield_up")
            else:
                self.play_animation("sail_shield_down")
            return True
        return False

    def check_bored_timer(self):
        if self.standing_around_since > self.next_bored_seq:
            self.standing_around_since = 0
            self.next_bored_seq = int(random.random() * 5) + 5
            self.play_animation("be_bored")
            return True
        return False

    def check_running(self):
        phys = self.components["physics"]
        brain = self.components["brain"]
        if brain.commands["left"] != brain.commands["right"]:  # xor
            if phys.at_wall:
                self.play_animation("push")
            else:
                self.play_animation("run_shield_up" if self.is_shield_up else "run_shield_down")


class VikingLevel(spyg.Level):
    def __init__(self, name: str = "test", **kwargs):
        super().__init__(name, **kwargs)

        # hook to the Level's Viking objects (defined in the tmx file's TiledObjectGroup)
        self.vikings = []
        self.state = spyg.State()
        self.state.register_event("changed.active_viking")

        self.register_event("mastered", "aborted", "lost", "viking_reached_exit")

    def play(self):
        # start level (stage the scene; will overwrite the old 0-stage (=main-stage))
        # - the options-object below will be also stored in [Stage object].options
        stage = spyg.Stage.stage_screen(self, None, 0, {
            "tile_sprite_handler": functools.partial(spyg.PhysicsComponent.tile_sprite_handler, spyg.SlopedTileSprite),
            "components": [spyg.Viewport(self.display)]
        })

        # find all Vikings in the Stage and store them for us
        for sprite in stage.sprites:
            if isinstance(sprite, Viking):
                self.vikings.append(sprite)

        # handle characters deaths
        for i, viking in enumerate(self.vikings):
            viking.on_event("die", functools.partial(self.viking_died, viking))

        # manage the characters in this level
        self.state.set("vikings", self.vikings)
        self.state.on_event("changed.active_viking", self, "active_viking_changed")

        self.state.set("active_viking", 0, True)  # 0=set to first Viking, True=trigger event
        # tell the Viewport of the Stage to follow the active Viking
        stage.follow_object_with_viewport(self.vikings[0])

        self.state.set("orig_num_vikings", len(self.vikings))

        # activate level triggers
        self.on_event("viking_reached_exit")

        # activate Ctrl switch vikings
        self.keyboard_inputs.on_event("key_down.rctrl", self, "next_active_viking", register=True)
        self.keyboard_inputs.on_event("key_down.lctrl", self, "next_active_viking", register=True)
        # activate stage's escape menu
        self.keyboard_inputs.on_event("key_down.escape", self, "escape_menu", register=True)

        # play a new GameLoop giving it some options
        spyg.GameLoop.play_a_loop(screen_obj=self, debug_rendering=True)

    def done(self):
        spyg.Stage.get_stage().stop()
        self.state.set("active_viking", None, True)
        # switch off keyboard
        self.keyboard_inputs.update_keys()  # empty list -> no more keys

    def escape_menu(self):
        pass

        # TODO: UI
        """def scene_func(stage):
            spyg.Stage.get_stage().pause()
            box = stage.add_sprite(new Q.UI.Container({

                x: Q.width/2,
                y: Q.height/2,
                fill: "rgba(255,255,255,0.75)"
                }));
            var label = stage.insert(new Q.UI.Text(
                { x: 0, y: -10 - 30, w: 100, align: "center", label: "Give up?", color: "black",}
                ), box);
            var yes = stage.insert(new Q.UI.Button(
                { x: 0, y: 0, fill: "#CCCCCC", label: "Yes"},
                function() { stage.options.levelObj.trigger("aborted", stage.options.levelObj); }
                ), box);
            var no = stage.insert(new Q.UI.Button(
                { x: yes.p.w + 20, y: 0, w: yes.p.w, fill: "#CCCCCC", label: "No" },
                function() { Q.clearStage(1); Q.stage(0).unpause(); }
                ), box);
            box.fit(20);

        spyg.Stage.stage_scene(spyg.Scene(scene_func), 1, { "screen_obj": self })
        """

    # handles a dead character
    def viking_died(self, dead_viking):
        # remove the guy from the Characters list
        vikings = self.state.get("vikings")
        active = self.state.get("active_viking")

        # remove the guy from vikings list
        for i, viking in enumerate(vikings):

            # found the dead guy
            if viking is dead_viking:
                vikings.pop(i)
                # no one left for the player to control -> game over, man!
                if len(vikings) == 0:
                    # TODO: UI alert("You lost!\nClearing stage 0.");
                    self.trigger_event("lost", self)

                # if viking was the active one, make next viking in list the new active one
                elif i == active:
                    # was the last one in list, make first one the active guy
                    if i == len(vikings):
                        self.state.dec("active_viking", 1)  # decrement by one: will now point to last viking in list ...
                        self.next_active_viking()  # ... will move pointer to first element in list

                    # leave active pointer where it is and call _activeCharacterChanged
                    else:
                        self.active_viking_changed(i)

                break

    # handles a character reaching the exit
    def viking_reached_exit(self, viking):
        characters = self.state.get("vikings")
        num_reached_exit = 0
        still_alive = len(characters)
        # check all characters' status (dead OR reached exit)
        for i in range(still_alive):
            # at exit
            if characters[i].components["physics"].at_exit:
                num_reached_exit += 1

        # all original characters reached the exit (level won)
        if num_reached_exit == self.state.get("orig_num_vikings"):
            # TODO UI alert("Great! You made it!");
            self.done()
            self.trigger_event("mastered", self)

        # everyone is at exit, but some guys died
        elif num_reached_exit == still_alive:
            # TODO: UI alert("Sorry, all of you have to reach the exit.");
            self.done()
            # TODO: 2) fix black screen mess when level lost or aborted
            self.trigger_event("lost", self)

    # returns the next active character (-1 if none) and moves the activeCharacter pointer to that next guy
    def next_active_viking(self):
        slot = self.state.get("active_viking")
        # TODO if typeof slot == 'undefined':
        #    return -1
        vikings = self.state.get("vikings")
        next_ = ((slot + 1) % len(vikings))
        self.state.set("active_viking", next_, True)
        return next_

    # reacts to a change in the active character to some new slot
    # - changes the viewport follow to the new guy
    def active_viking_changed(self, new_viking_idx):
        vikings = self.state.get("vikings")
        # someone is active
        if new_viking_idx is not None:
            for i in range(len(vikings)):
                if i != new_viking_idx:
                    vikings[i].deactivate()
                else:
                    vikings[i].activate()

            # make the Stage follow the new Viking
            stage = spyg.Stage.get_stage(0)  # default stage
            stage.follow_object_with_viewport(vikings[new_viking_idx], max_speed=3)
            # make the new Viking blink for a while
            vikings[new_viking_idx].blink_animation(15, 1.5)  # 15/s for 1.5s
        # no one is active anymore -> switch 'em all off
        else:
            for viking in vikings:
                viking.deactivate()


class Shot(spyg.AnimatedSprite):
    """
    a shot (like the one a scorpion shoots)
    - can be extended to do more complicated stuff
    """

    def __init__(self, offset_x, offset_y, spritesheet, animation_setup, shooter):
        """
        a generic Shot object being spawned into the game usually by a Shooter object
        :param int offset_x: the x-offset with respect to the Shooter's x position
        :param int offset_y: the y-offset with respect to the Shooter's y position
        :param spyg.SpriteSheet spritesheet:
        :param dict animation_setup: the animation_setup dictionary that will be sent to the Animation component
        :param spyg.Sprite shooter: the Shooter's (Sprite) object
        """
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.shooter = shooter
        self.flip = self.shooter.flip  # flip particle depending on shooter's flip

        super().__init__(self.shooter.rect.x + self.offset_x * (-1 if self.flip["x"] else 1), self.shooter.rect.y + self.offset_y,
                         spritesheet, animation_setup)

        # some simple physics
        self.ax = 0
        self.ay = 0
        self.vx = 300
        self.vy = 0
        self.damage = 1
        self.hit_something = False

        self.type = spyg.Sprite.get_type("particle")
        self.collision_mask = spyg.Sprite.get_type("default,friendly")

        self.frame = 0
        self.vx = -self.vx if self.flip == 'x' else self.vx

        self.on_event("collision", register=True)
        self.on_event("collision_done", register=True)

    # simple tick function with ax and ay, speed- and pos-recalc, and collision detection
    def tick(self, game_loop):
        dt = game_loop.dt
        self.vx += self.ax * dt * (-1 if self.flip == "x" else 1)
        self.rect.x += self.vx * dt
        self.vy += self.ay * dt
        self.rect.y += self.vy * dt

        # tick the animation component
        self.cmp_animation.tick(game_loop)

    # we hit something
    def collision(self, col):
        # we hit our own shooter -> ignore
        if col.sprite2 is self.shooter:
            return

        self.hit_something = True
        # stop abruptly
        self.ax = 0
        self.vx = 0
        self.ay = 0
        self.vy = 0
        # play 'hit' if exists, otherwise just destroy object
        if "hit" in spyg.Animation.animation_settings[self.spritesheet.name]:
            self.play_animation("hit")
        else:
            self.collision_done()

    # we are done hitting something
    def collision_done(self):
        self.destroy()


class Arrow(Shot):
    """
    arrow class
    """

    def __init__(self, shooter):
        """
        :param Sprite shooter: the shooter that shoots this Arrow object
        """
        super().__init__(16, 16, spyg.SpriteSheet("data/arrow.tsx"), {
            "default": "fly",  # the default animation to play
            "fly":     {"frames": [0, 1, 2, 3], "rate": 1 / 10},
        }, shooter)

        self.type = spyg.Sprite.get_type("arrow,particle")
        # simple physics, no extra component needed for that
        self.ax = -10
        self.ay = 40
        self.vx = 300
        self.vy = -5
        self.collision_mask = spyg.Sprite.get_type("default,enemy,friendly")


class Fireball(Shot):
    """
    fireball class
    """

    def __init__(self, shooter):
        """
        :param Sprite shooter: the shooter that shoots this FireBall object
        """
        super().__init__(0, 0, spyg.SpriteSheet("data/fireball.tsx"), {
            "default": "fly",  # the default animation to play
            "fly":     {"frames": [0, 1], "rate": 1 / 5},
            "hit":     {"frames": [2, 3], "rate": 1 / 3, "loop": False, "trigger": "collision_done"}
        }, shooter)

        self.vx = 200
        self.type = spyg.Sprite.get_type("particle,fireball")
        self.collision_mask = spyg.Sprite.get_type("default,friendly")
        self.damage = 2  # a fireball causes more damage


class FireSpitter(spyg.Sprite):
    """
    a FireSpitter can spit fireballs that kill the Vikings
    """

    def __init__(self, x, y, frequency=1/3):
        # fixed static image (a tile inside the png image)
        super().__init__(x, y, image_file="images/egpt.png", image_section=(20*16, 3*16, 16, 16))

        self.frequency = frequency  # shooting frequency (in 1/s)
        self.last_shot_fired = 0.0  # keep track of last shot fired
        self.type = spyg.Sprite.get_type("default")
        self.collision_mask = 0

    def tick(self, game_loop):
        dt = game_loop.dt
        self.last_shot_fired += dt
        # time's up -> fire shot
        if self.last_shot_fired > (1 / self.frequency):
            self.last_shot_fired = 0.0
            self.fire()

    def fire(self):
        self.stage.add_sprite(Fireball(self), "fireballs")


class MovableRock(spyg.Sprite):
    def __init__(self, x, y):
        super().__init__(x, y, image_file="images/movable_rock.png", width_height=(30, 32))

        self.type = spyg.Sprite.get_type("default")
        self.collision_mask = spyg.Sprite.get_type("default,friendly,enemy,particle")

        # add Physics (and thus Dockable) components to this Rock
        # - pre-tick: Physics (movement + collision resolution)
        #self.register_event("collision")

        phys = spyg.PlatformerPhysics("physics")
        phys.is_pushable = True  # rock can be pushed by an agent
        phys.vx_max = 10  # max move speed (when pushed): this should be very slow
        phys.is_heavy = True  # rock makes Stage's viewport rock if it hits ground AND squeezes agents :(
        self.cmp_physics = self.add_component(phys)

        # subscribe/register to some events
        self.on_event("bump.bottom", self, "land", register=True)
        self.register_event("bump.top", "bump.left", "bump.right", "hit.liquid_ground")

    def tick(self, game_loop):
        # let our physics component handle all movements
        self.cmp_physics.tick(game_loop)

    def land(self, *args):
        self.stage.shake_viewport(1, 10)


class Scorpion(spyg.AnimatedSprite):
    # recyclable SpriteSheets
    sprite_sheet = None
    shot_sprite_sheet = None

    def __init__(self, x, y):
        # init our recyclable SpriteSheets
        if not self.sprite_sheet:
            self.sprite_sheet = spyg.SpriteSheet("data/scorpion.tsx")
            self.shot_sprite_sheet = spyg.SpriteSheet("data/scorpion_shot.tsx")

        super().__init__(x, y, self.sprite_sheet, {
            "default": "stand",
            "stand": {"frames": [0], "loop": False, "priority": 0},
            "get_hurt": {"frames": [0], "rate": 1/3, "loop": False, "next": "stand", "flags": spyg.Animation.get_flag("paralyzes"), "priority": 5},
            "run": {"frames": [0, 1, 2, 1], "rate": 1/4, "priority": 1},
            "shoot": {"frames": [4], "next": "stand", "rate": 1/2, "flags": spyg.Animation.get_flag("paralyzes"), "priority": 2}
        })

        self.type = spyg.Sprite.get_type("enemy")
        self.collision_mask = spyg.Sprite.get_type("default,friendly")

        self.is_mad = False  # when mad, moves with twice the speed
        self.is_mad_since = 0.0

        # add our Components
        ai_brain = spyg.AIBrain("brain")
        self.cmp_brain = self.add_component(ai_brain)  # type: spyg.AIBrain

        phys = spyg.PlatformerPhysics("physics")
        phys.run_acceleration = 0  # don't accelerate (always move at max-speed)
        self.cmp_physics = self.add_component(phys)  # type: spyg.PlatformerPhysics

        # register and setup our events
        self.on_event("hit.particle", self, "hit_particle", register=True)

    def tick(self, game_loop):
        dt = game_loop.dt

        self.cmp_brain.tick(game_loop)

        if self.is_mad_since > 0.0:
            self.is_mad_since += dt
            if self.is_mad_since > 5.0:
                self.calm_down()

        self.cmp_physics.tick(game_loop)

        # shooting
        #if self.cmp_brain.commands["fire"]:
        #    self.play_animation("shoot")
        #    shot = Shot(0, 0, spritesheet=self.shot_sprite_sheet, shooter=self, animation_setup={})
        #    shot.vx = 80
        #    shot.vy = -100
        #    shot.ay = 140
        #    self.stage.add_sprite(shot)
        # moving in x direction
        #el
        if self.cmp_physics.vx != 0:
            self.check_running()
        # not moving in x direction
        # -> play stand with low priority
        self.play_animation("stand")

        self.cmp_animation.tick(game_loop)

    # is running (called if x-speed != 0)
    def check_running(self):
        if self.cmp_brain.commands["left"] != self.cmp_brain.commands["right"] and self.cmp_animation.animation != "run":
            self.play_animation("run")

    # hit a flying particle (shot, arrow, etc..)
    def hit_particle(self, col):
        # sliding away from particle
        self.cmp_physics.vx = math.copysign(100, col.normal_x)
        self.play_animation("get_hurt", 1)
        self.get_mad()

    def get_mad(self):
        if not self.is_mad:
            self.is_mad_since = 0.0
            self.cmp_physics.vx_max *= 2
            self.is_mad = True

    def calm_down(self):
        if self.is_mad:
            self.cmp_physics.vx_max /= 2
            self.is_mad = False


class Dinosaur(spyg.AnimatedSprite):
    sprite_sheet = None

    def __init__(self, x, y):
        if not self.sprite_sheet:
            self.sprite_sheet = spyg.SpriteSheet("images/dinosaur.png")

        super().__init__(x, y, self.sprite_sheet, {
            "default": "stand",
            "stand": { "frames": [4], "loop": False, "flags": spyg.Animation.ANIM_PROHIBITS_STAND },
            "get_hurt": { "frames": [9,10], "rate": 1/2, "loop": False, "next": "stand", "flags": spyg.Animation.ANIM_PARALYZES },
            "run": { "frames": [0,1,2,3], "rate": 1/4 },
            "bite": { "frames": [4,5,6,7,8], "next": 'stand', "rate": 1/4, "flags": (spyg.Animation.ANIM_PROHIBITS_STAND | spyg.Animation.ANIM_PARALYZES) },
            "die": { "frames": [], "rate": 1/4, "trigger": "die", "flags": (spyg.Animation.ANIM_PROHIBITS_STAND | spyg.Animation.ANIM_PARALYZES) },
        })

        self.type = spyg.Sprite.get_type("enemy")
        self.collision_mask = spyg.Sprite.get_type("default,friendly")

        self.cmp_brain = self.add_component(spyg.Brain("brain", ["left", "right", "attack"]))  # type: spyg.HumanPlayerBrain
        phys = spyg.PlatformerPhysics("physics")
        phys.vx_max = 50
        phys.run_acceleration = 0
        self.cmp_physics = self.add_component(phys)  # type: spyg.PlatformerPhysics

        self.life_energy = 3  # 0 -> die
        self.is_mad_since = 0  # when mad, moves with twice the speed
        self.on_event("hit.particle", self, "hit_particle")

    def tick(self, game_loop):
        dt = game_loop.dt

        # shooting?
        if self.cmp_brain.commands["attack"]:
            self.play_animation("bite")
        # moving in x direction
        elif self.cmp_physics.vx != 0:
            self.check_running()
        # not moving in x direction
        # -> check whether we are allowed to play 'stand'
        elif not self.cmp_animation.flags & spyg.Animation.ANIM_PROHIBITS_STAND:
            self.play_animation("stand")

    # is running (called if x-speed != 0)
    def check_running(self):
        if self.cmp_brain.commands["left"] != self.cmp_brain.commands["right"] and self.cmp_animation.animation != "run":
            self.play_animation("run")

    # hit a flying particle (shot, arrow, etc..)
    def hit_particle(self, col):
        # sliding away from particle
        #p.vx = 100*(col.normalX > 0 ? 1 : -1)
        #p.ax = -2*(col.normalX > 0 ? 1 : -1)
        #TODO: implement a push in the physicsEngine
        arrow = col.sprite2
        if isinstance(arrow, Arrow) and not arrow.hit_something:
            self.life_energy -= arrow.damage
            if self.life_energy <= 0:
                self.die()
                return
            self.play_animation("get_hurt", 1)

    def die(self):
        self.play_animation("die")
        self.destroy()

# main program
if __name__ == "__main__":
    level = "EGPT"
    # create a spyg.Game object
    game = spyg.Game(screens_and_levels=[
        # a level definition ("WRBC: We are back!")
        {
            "class": VikingLevel, "name": level, "id": 1,
        },

        # add more of your levels here
        # { ... },

        ], width=400,height=250,
        # spyg.DEBUG_RENDER_SPRITES_BEFORE_COLLISION_DETECTION
        title="The Lost Vikings - Return of the Heroes :)")  #, debug_flags=(spyg.DEBUG_DONT_RENDER_TILED_TILE_LAYERS | spyg.DEBUG_RENDER_COLLISION_TILES | spyg.DEBUG_RENDER_SPRITES_RECTS | spyg.DEBUG_RENDER_ACTIVE_COLLISION_TILES))

    # that's it, play one of the levels -> this will enter an endless game loop
    game.levels_by_name[level].play()
