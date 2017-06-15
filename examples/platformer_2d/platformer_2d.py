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


class Viking(spyg.AnimatedSprite, metaclass=ABCMeta):
    """
    a generic Viking class
    """
    def __init__(self, x: int, y: int, spritesheet: spyg.SpriteSheet, animation_setup: dict):
        """
        :param int x: the start x position
        :param int y: the start y position
        :param spyg.SpriteSheet spritesheet: the SpriteSheet object (tsx file) to use for this Viking
        :param dict animation_setup: a dictionary to be passed to spyg.Animation.register_settings and
                stored under the SpriteSheet.name in the animations registry
        """
        super().__init__(x, y, spritesheet, animation_setup)

        self.handles_own_collisions = True
        self.type = spyg.Sprite.get_type("friendly")

        self.is_active_character = False  # more than one Viking can exist in the level
        self.life_points = 3
        self.ladder_frame = 0
        self.unhealthy_fall_speed = 420
        self.unhealthy_fall_speed_on_slopes = 450  # on slopes, vikings can fall a little harder without hurting themselves

        # add components to this Viking
        # loop time line:
        # - pre-tick: Brain (needs animation comp to check e.g., which commands are disabled), Physics (movement + collision resolution)
        # - tick: chose animation to play
        # - post-tick: Animation
        self.register_event("pre_tick", "post_tick", "collision")
        self.cmp_brain = self.add_component(spyg.Brain("brain", ["up", "down", "left", "right", "action1", "action2"]))
        self.cmp_physics = self.add_component(spyg.PlatformerPhysics("physics"))
        self.cmp_physics.squeeze_speed = 0.5

        # subscribe/register to some events
        self.on_event("bump.bottom", self, "land", register=True)
        self.register_event("bump.top", "bump.left", "bump.right")
        self.on_event("squeezed.top", self, "get_squeezed", register=True)
        self.on_event("hit.liquid_ground", self, "hit_liquid_ground", register=True)  # player stepped into liquid ground
        self.on_event("hit.particle", self, "hit_particle", register=True)  # player hits a particle
        self.on_event("die", register=True)  # some animations trigger 'die' when done

        # initialize the 'getting bored'-timer
        self.standing_around_since = 0
        self.next_bored_seq = int(random.random() * 10) + 5  # play the next 'bored'-sequence after this amount of seconds

    # makes this Viking the currently active player
    def activate(self):
        if not self.is_active_character:
            self.is_active_character = True
        return self

    # makes this Viking currently inactive
    def deactivate(self):
        if self.is_active_character:
            self.is_active_character = False
        return self

    # sequence of this Sprite's tick-flow:
    # - tick gets called by the Stage
    # - pre_tick is triggered by this tick
    # -- pre_tick calls tick of the Components (Animation, Brain (maps keyboard input to controls), Physics)
    # -- Physics Component tick method runs:
    # --- determines x/y speeds and moves according to s = v*dt
    # --- runs collision detection against all layers
    # --- if a layer detects a collision, it is postprocessed (e.g. slopes)
    # --- then event "collision" is triggered on this Sprite
    # --- Physics Component listens for this event and handles the collision by solving for wall-bumps and slopes
    def tick(self, game_loop):
        dt = game_loop.dt

        #print("tick dt={}".format(dt))

        # tell our subscribers (e.g. Components) that we are ticking
        self.trigger_event("pre_tick", game_loop)

        #print("vy after pre_tick: {}".format(self.components["physics"].vy))

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
            pass

        # not moving in x direction
        else:
            if self.cmp_animation.animation == 'stand':
                self.standing_around_since += dt
            else:
                self.standing_around_since = 0

            # not moving in x-direction, but trying -> push
            if self.cmp_brain.commands["left"] != self.cmp_brain.commands["right"]:  # xor
                self.play_animation("push")
            # out of breath from running?
            elif self.check_out_of_breath and self.check_out_of_breath():
                pass
            # getting bored?
            elif self.check_bored_timer():
                pass
            # just stand
            elif self.allow_play_stand():
                self.play_animation("stand")

        self.trigger_event("post_tick", game_loop)

        return

    @abstractmethod
    def check_actions(self):
        pass

    def check_on_ladder(self, dt) -> bool:
        if self.cmp_physics.on_ladder <= 0:
            return False

        anim = self.components["animation"]
        anim.animation = False  # do anim manually when on ladder
        anim.flags = 0

        character_bot = self.rect.y + self.rect.height - 4

        # we are alomst at the top -> put end-of-ladder frame
        if character_bot <= self.cmp_physics.which_ladder.rect.topy:
            self.ladder_frame = 63
            # we crossed the "frame-jump" barrier -> y-jump player to cover the sprite frame y-shift between ladder top position and ladder 2nd-to-top position
            if self.on_ladder > self.cmp_physics.which_ladder.rect.topy:
                self.rect.y -= 5
        # we are reaching the top -> put one-before-end-of-ladder frame
        elif character_bot <= self.cmp_physics.which_ladder.yalmosttop:
            self.ladder_frame = 64
            if self.cmp_physics.on_ladder:
                if self.cmp_physics.on_ladder <= self.cmp_physics.which_ladder.rect.topy:
                    self.rect.y += 5
        # we are in middle of ladder -> alternate climbing frames
        else:
            self.ladder_frame += self.cmp_physics.vy * dt * -0.16
            if self.ladder_frame >= 69:
                self.ladder_frame = 65
            elif self.ladder_frame < 65:
                self.ladder_frame = 68.999

        # update on_ladder (serves as y-pos memory for previous y-position so we can detect a crossing of the "frame-jump"-barrier)
        self.cmp_physics.on_ladder = character_bot
        anim.frame = int(self.ladder_frame)  # normalize to whole frame number

        return True

    # function is called when sprite lands on floor
    def land(self, col):
        # if impact was big -> bump head/beDizzy
        if col.impact > self.unhealthy_fall_speed:
            self.play_animation("be_dizzy", 1)

    # quicksand or water
    def hit_liquid_ground(self, what):
        if what == "quicksand":
            self.play_animation("sink_in_quicksand", 1)
        elif what == "water":
            self.play_animation("sink_in_water", 1)
        self.cmp_physics.vy = 2

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
        self.trigger("dead", self)
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
            self.next_bored_seq = int(random.random() * 10) + 5
            self.play_animation(random.choice(["be_bored1", "be_bored2"]))
            return True
        return False

    # check, whether it's ok to play 'stand' animation
    def allow_play_stand(self):
        anim_setup = spyg.Animation.get_settings(self.spritesheet.name, self.cmp_animation.animation)
        return not (anim_setup["flags"] & spyg.Animation.ANIM_PROHIBITS_STAND)


# define player: Baleog
class Baleog(Viking):
    def __init__(self, x: int, y: int, spritesheet: spyg.SpriteSheet):
        super().__init__(x, y, spritesheet, {
            "default"          : "stand",  # the default animation to play
            "stand"            : {"frames": [0], "loop": False, "flags": spyg.Animation.ANIM_PROHIBITS_STAND},
            "be_bored1"        : {"frames": [1, 2, 2, 1, 1, 3, 4, 3, 4, 5, 6, 5, 6, 7, 8, 7, 8, 3, 4, 3, 4], "rate": 1 / 3, "loop": False, "next": "stand",
                                  "flags" : spyg.Animation.ANIM_PROHIBITS_STAND},
            "be_bored2"        : {"frames": [1, 2, 2, 1, 1, 7, 8, 7, 8, 2, 2, 1, 2, 2, 1], "rate": 1 / 3, "loop": False, "next": "stand",
                                  "flags" : spyg.Animation.ANIM_PROHIBITS_STAND},
            "run"              : {"frames": [9, 10, 11, 12, 13, 14, 15, 16], "rate": 1 / 8},
            "push"             : {"frames": [54, 55, 56, 57], "rate": 1 / 4},
            "jump"             : {"frames": [36, 37], "rate": 1 / 6},
            "fall"             : {"frames"     : [38], "loop": False, "flags": spyg.Animation.ANIM_DISABLES_CONTROL,
                                  "keys_status": {"left": -1, "right": -1, "up": -1}},
            "be_dizzy"         : {"frames": [39, 40, 41, 40, 41, 42, 42, 43], "rate": 1 / 3, "loop": False, "next": "stand",
                                  "flags" : (spyg.Animation.ANIM_DISABLES_CONTROL | spyg.Animation.ANIM_PROHIBITS_STAND)},
            "get_hurt"         : {"frames": [72], "rate": 1 / 2, "next": 'stand',
                                  "flags" : (spyg.Animation.ANIM_DISABLES_CONTROL | spyg.Animation.ANIM_PROHIBITS_STAND)},
            "get_squeezed"     : {"frames": [122, 123, 124, 124, 125, 125, 125, 125], "rate": 1 / 3, "loop": False, "trigger": "die",
                                  "flags" : (spyg.Animation.ANIM_DISABLES_CONTROL | spyg.Animation.ANIM_PROHIBITS_STAND)},
            "sink_in_quicksand": {"frames": [120, 121, 121, 120, 120, 121, 121, 120], "rate": 1 / 2, "loop": False, "trigger": "die",
                                  "flags" : (spyg.Animation.ANIM_DISABLES_CONTROL | spyg.Animation.ANIM_PROHIBITS_STAND)},
            "sink_in_water"    : {"frames": [90, 91, 92, 93, 91, 92, 93], "rate": 1 / 2, "loop": False, "trigger": "die",
                                  "flags" : (spyg.Animation.ANIM_PROHIBITS_STAND | spyg.Animation.ANIM_DISABLES_CONTROL)},
            "burn"             : {"frames": [126, 127, 128, 129, 130, 131, 132, 133], "rate": 1 / 4, "loop": False, "trigger": "die",
                                  "flags" : (spyg.Animation.ANIM_DISABLES_CONTROL | spyg.Animation.ANIM_PROHIBITS_STAND)},
            # disables control, except for action1 (which is pressed down)
            "swing_sword1"     : {"frames": [18, 19, 20, 21], "rate": 1 / 4, "loop": False, "next": 'stand',
                                  "flags" : (spyg.Animation.ANIM_DISABLES_CONTROL | spyg.Animation.ANIM_SWING_SWORD), "keys_status": {"space": 1}},
            # disables control, except for action1 (which is pressed down)
            "swing_sword2"     : {"frames": [22, 23, 24, 25], "rate": 1 / 4, "loop": False, "next": 'stand',
                                  "flags" : (spyg.Animation.ANIM_DISABLES_CONTROL | spyg.Animation.ANIM_SWING_SWORD), "keys_status": {"space": 1}},
            "draw_bow"         : {"frames": [27, 27, 28, 29, 30, 31], "rate": 1 / 5, "loop": False, "next": 'holdBow',
                                  "flags" : (spyg.Animation.ANIM_DISABLES_CONTROL | spyg.Animation.ANIM_BOW), "keys_status": {"d": 1}},
            "hold_bow"         : {"frames"     : [31], "loop": False, "flags": (spyg.Animation.ANIM_DISABLES_CONTROL | spyg.Animation.ANIM_BOW),
                                  "keys_status": {"d": -1}},
            "release_bow"      : {"frames": [33, 32, 33, 32, 33, 32, 0], "rate": 1 / 6, "loop": False, "next": "stand",
                                  "flags" : (spyg.Animation.ANIM_PROHIBITS_STAND | spyg.Animation.ANIM_BOW)},
        })

        self.components["physics"].can_jump = False
        self.disabled_sword = False

    def check_actions(self):
        # sword or arrow?
        if self.check_hit_with_sword() or self.check_shoot_with_arrow():
            return True
        return False

    # hit with sword
    # - returns true if player is currently hitting with sword
    def check_hit_with_sword(self):
        anim_flags = self.components["animation"].flags
        brain = self.components["brain"]
        # action1 is pressed AND user's sword is replenished (had released space) AND anim is currently not swinging sword
        if brain.commands["sword"] and not self.disable_sword and not (anim_flags & spyg.Animation.ANIM_SWING_SWORD):
            self.disabled_sword = True
            self.play_animation(random.choice(["swing_sword1", "swing_sword2"]))
            return True
        # re-enable sword? (space key needs to be released between two sword strikes)
        elif not brain.commands["sword"]:  # TODO: what about touch screens?
            self.disabled_sword = False

        return anim_flags & spyg.Animation.ANIM_SWING_SWORD

    # shoot arrow
    # - returns true if player is doing something with arrow right now
    # - false otherwise
    def check_shoot_with_arrow(self):
        anim = self.components["animation"]
        anim_flags = anim.flags
        brain = self.components["brain"]
        if brain.commands["arrow"] and not (anim_flags & spyg.Animation.ANIM_BOW):
            self.play_animation("draw_bow")
            return True
        elif not brain.commands["arrow"] and anim.animation == "hold_bow":
            self.play_animation("release_bow")
            self.stage.add_sprite(Arrow(self))
            return True
        return brain.commands["arrow"] and (anim_flags & spyg.Animation.ANIM_BOW)


# define player: Erik the Swift
class Erik(Viking):
    def __init__(self, x: int, y: int, spritesheet: spyg.SpriteSheet):
        super().__init__(x, y, spritesheet, {
            "default"          : "stand",  # the default animation to play
            "stand"            : {"frames": [0], "loop": False, "flags": spyg.Animation.ANIM_PROHIBITS_STAND},
            "be_bored1"        : {"frames": [1], "rate": 1 / 2, "next": 'stand', "flags": spyg.Animation.ANIM_PROHIBITS_STAND},
            "be_bored2"        : {"frames": [61, 2, 3, 4, 3, 4, 3, 4], "rate": 1 / 3, "next": 'stand',
                                  "flags" : spyg.Animation.ANIM_PROHIBITS_STAND},
            "run"              : {"frames": [5, 6, 7, 8, 9, 10, 11, 12], "rate": 1 / 8},
            "out_of_breath"    : {"frames": [13, 14, 15, 13, 14, 15], "rate": 1 / 4, "next": 'stand',
                                  "flags" : spyg.Animation.ANIM_PROHIBITS_STAND},
            "push"             : {"frames": [54, 55, 56, 57], "rate": 1 / 4},
            "jump_up"          : {"frames": [16], "loop": False},
            "jump_peak"        : {"frames": [17], "loop": False},
            "jump_down"        : {"frames": [18, 19], "rate": 1 / 3},
            "fall"             : {"frames"     : [81], "loop": False, "flags": spyg.Animation.ANIM_DISABLES_CONTROL,
                                  "keys_status": {"left": -1, "right": -1, "up": -1}},
            "be_dizzy"         : {"frames": [36, 37, 38, 39, 40, 38, 39, 40, 41, 42, 43], "rate": 1 / 3, "loop": False, "next": 'stand',
                                  "flags" : (spyg.Animation.ANIM_DISABLES_CONTROL | spyg.Animation.ANIM_PROHIBITS_STAND)},
            "get_hurt"         : {"frames": [72], "rate": 1 / 2, "next": 'stand',
                                  "flags" : (spyg.Animation.ANIM_DISABLES_CONTROL | spyg.Animation.ANIM_PROHIBITS_STAND)},
            "get_squeezed"     : {"frames": [126, 127, 128, 128, 129, 129, 129, 129], "rate": 1 / 4, "loop": False, "trigger": 'die',
                                  "flags" : (spyg.Animation.ANIM_DISABLES_CONTROL | spyg.Animation.ANIM_PROHIBITS_STAND)},
            "sink_in_quicksand": {"frames": [108, 109, 110, 108, 109, 110, 108, 109], "loop": False, "rate": 1 / 2, "trigger": 'die',
                                  "flags" : (spyg.Animation.ANIM_PROHIBITS_STAND | spyg.Animation.ANIM_DISABLES_CONTROL)},
            "sink_in_water"    : {"frames": [90, 91, 92, 93, 91, 92, 93], "loop": False, "rate": 1 / 2, "trigger": 'die',
                                  "flags" : (spyg.Animation.ANIM_PROHIBITS_STAND | spyg.Animation.ANIM_DISABLES_CONTROL)},
            "burn"             : {"frames": [117, 118, 119, 120, 121, 122, 123, 124], "rate": 1 / 4, "loop": False, "trigger": 'die',
                                  "flags" : spyg.Animation.ANIM_DISABLES_CONTROL},
        })

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
            "tile_layer_physics_collisions": (spyg.PlatformerCollision(), spyg.PlatformerCollision()),
            "tile_layer_physics_collision_postprocessor": spyg.PlatformerPhysics.tile_layer_physics_collision_postprocessor,
            "components": [spyg.Viewport(self.display)]
        })

        # find all Vikings in the Stage and store them for us
        for sprite in stage.sprites:
            if isinstance(sprite, Viking):
                self.vikings.append(sprite)

        # handle characters deaths
        for i, viking in enumerate(self.vikings):
            viking.on_event("die", self, "viking_died")

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
        self.keyboard_inputs.on_event("key_down.ctrl", self, "next_active_viking", register=True)
        # activate stage's escape menu
        self.keyboard_inputs.on_event("key_down.esc", self, "escape_menu", register=True)

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
                        self.active_viking_changed([i, i])

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
    def active_viking_changed(self, new_viking_idx, old_viking_idx):
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
            stage.follow_object_with_viewport(vikings[new_viking_idx])
            # make the new Viking blink for a while
            vikings[new_viking_idx].blink_animation(15, 1.5)  # 15/s for 1.5s
        # no one is active anymore -> switch 'em all off
        else:
            for viking in vikings:
                viking.deactivate()


class Shot(spyg.AnimatedSprite):
    """
    // A SHOT (like the one a scorpion shoots)
    // - can be extended to do more complicated stuff
    """

    def __init__(self, offset_x: int, offset_y: int, spritesheet: spyg.SpriteSheet, animation_setup: dict, shooter: spyg.GameObject):
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.shooter = shooter
        self.flip = self.shooter.flip  # flip particle depending on shooter's flip
        self.rect.x = self.shooter.rect.x + self.offset_x * (-1 if self.flip == 'x' else 1)
        self.rect.y = self.shooter.rect.y + self.offset_y

        super().__init__(self.rect.x, self.rect.y, spritesheet, animation_setup)

        # some simple physics
        self.ax = 0
        self.ay = 0
        self.vx = 300
        self.vy = 0
        self.damage = 1
        self.hit_something = False
        self.collision_mask = spyg.Sprite.get_type("default") | spyg.Sprite.get_type("friendly")

        self.frame = 0
        self.vx = -self.vx if self.flip == 'x' else self.vx

        self.type = spyg.Sprite.get_type("particle")

        self.on_event("hit", self, "collision")
        self.on_event("collision_done")

    # simple tick function with ax and ay, speed- and pos-recalc, and collision detection
    def tick(self, game_loop):
        dt = game_loop.dt
        self.vx += self.ax * dt * (-1 if self.flip == "x" else 1)
        self.rect.x += self.vx * dt
        self.vy += self.ay * dt
        self.rect.y += self.vy * dt
        # check for collisions on this object's stage
        self.stage.solve_collisions(self)

    # we hit something
    def collision(self, col):
        # we hit our own shooter -> ignore
        if col.obj and col.obj is self.shooter:
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

    def __init__(self, shooter: spyg.GameObject):
        super().__init__(3, -3, spyg.SpriteSheet("data/arrow.tsx"), {
            "default": "fly",  # the default animation to play
            "fly"    : {"frames": [0, 1, 2, 3], "rate": 1 / 10},
        }, shooter)

        self.type = spyg.Sprite.get_type("particle") | spyg.Sprite.get_type("arrow")
        # simple physics, no extra component needed for that
        self.ax = -10
        self.ay = 40
        self.vx = 300
        self.vy = -15
        self.collision_mask = spyg.Sprite.get_type("default") | spyg.Sprite.get_type("enemy") | \
                              spyg.Sprite.get_type("friendly")


class Fireball(Shot):
    """
    fireball class
    """

    def __init__(self, shooter: spyg.GameObject):
        super().__init__(0, 0, spyg.SpriteSheet("data/fireball.tsx"), {
            "default": "fly",  # the default animation to play
            "fly"    : {"frames": [0, 1], "rate": 1 / 5},
            "hit"    : {"frames": [4, 5], "rate": 1 / 3, "loop": False, "trigger": "collision_done"}
        }, shooter)

        self.vx = 200
        self.type = spyg.Sprite.get_type("particle") | spyg.Sprite.get_type("fireball")
        self.collision_mask = spyg.Sprite.get_type("default") | spyg.Sprite.get_type("friendly")
        self.damage = 2  # a fireball causes more damage


class FireSpitter(spyg.GameObject):
    """
    a fire spitter can spit fireballs that kill the Vikings
    """

    def __init__(self, x, y):
        surf = pygame.Surface(1, 1)
        rect = surf.get_rect()
        rect.x = x
        rect.y = y
        super().__init__(surf, rect)

        # Q._whTileToPix(p, _TILE_SIZE); // normalize some values (width and height given in tile-units, not pixels)

        self.frequency = 1 / 3  # shooting frequency (in 1/s)
        self.last_shot_fired = 0.0  # keep track of last shot fired

    def tick(self, game_loop):
        dt = game_loop.dt
        self.last_shot_fired += dt
        # time's up -> fire shot
        if self.last_shot_fired > (1 / self.frequency):
            self.last_shot_fired = 0.0
            self.fire()

    def fire(self):
        self.stage.add_sprite(Fireball(self))


# main program
if __name__ == "__main__":
    # create a spyg.Game object
    game = spyg.Game(screens_and_levels=[
        # a level definition ("WRBC: We are back!")
        {
            "class": VikingLevel, "name": "WRBC", "id": 1,
        },

        # add more of your levels here
        # { ... },

        ], width=200,height=200,
        title="The Lost Vikings - Return of the Heroes :)", debug_flags=(spyg.DEBUG_NONE))  # spyg.DEBUG_DONT_RENDER_TILED_TILE_LAYERS | spyg.DEBUG_RENDER_COLLISION_TILES | spyg.DEBUG_RENDER_SPRITES_RECTS

    # that's it, play one of the levels -> this will enter an endless game loop
    game.levels_by_name["WRBC"].play()
