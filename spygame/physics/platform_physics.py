class PlatformerPhysics(ControlledPhysicsComponent):
    """
    Defines "The Lost Vikings"-like game physics.
    Supports: Running over sloped tiles, jumping, ladders, moving platforms and elevators, pushable heavy rocks, one-way-platforms
    To be addable to any character (player or enemy) or thing (e.g. a pushable rock)
    """

    # used repeatedly (recycle) for collision detection information being passed between the CollisionAlgorithm object and the physics Copmonents
    # collision_objects = (PlatformerCollision(), PlatformerCollision())

    @staticmethod
    def get_highest_tile(tiles, direction, start_abs, end_abs):
        """
        Returns the `highest` tile in a list (row or column) of sloped, full-collision or empty tiles.

        :param list tiles: the list of tiles to check
        :param str direction: the direction in which the list of tiles is arranged (x=row of tiles or y=column of tiles)
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
        self.type_before_ladder = None
        self.is_pushable = False  # set to True if a collision with the entity causes the entity to move a little
        self.is_heavy = False  # set to True if this object should squeeze other objects that are below it and cannot move away
        # set to a value > 0 to define the squeezeSpeed at which this object gets squeezed by heavy objects (objects with is_heavy == True)
        self.squeeze_speed = 0
        self.push_back_list = []  # a list of push back x-forces that will be applied (if populated) frame by frame on our GameObject
        # if an up-slope (e.g. 20°) does not reach it full-tiled right neighbor, would a sprite treat this as stairs and still climb up the full-tile
        self.allow_stairs_climb = True

        # self.touching = 0  # bitmap with those bits set that the entity is currently touching (colliding with)
        self.at_exit = False
        self.at_wall = False
        self.is_sinking_til = None  # a y-pos at which point the GameObject will stop sinking into a LiquidBody
        self.on_ladder = None  # None if GameObject is not locked into a ladder; Ladder obj if obj is currently locked into a ladder (in climbing position)
        self.touched_ladder = None  # holds the ladder Sprite, if player is currently touching a Ladder (not locked in!), otherwise: None
        self.climb_frame_value = 0  # int([climb_frame_value]) determines the frame to use to display climbing position

        self.game_obj_cmp_dockable = None  # type: Dockable; the GameObject's Dockable component (that we will add to the GameObject ourselves)

    def added(self):
        super().added()

        obj = self.game_object

        # add the Dockable Component to our GameObject (we need it this for us to work properly)
        self.game_obj_cmp_dockable = obj.add_component(Dockable("dockable"))

        # add some bit-flags to the collision mask of our GameObject
        obj.collision_mask |= Sprite.get_type("default,ladder,liquid")

        # register events that we may trigger directly on the game_object
        obj.register_event("hit.particle", "hit.liquid", "squeezed.top", "bump.top", "bump.bottom", "bump.left", "bump.right")

    def lock_ladder(self):
        """
        Locks the GameObject into a ladder.
        Makes sure that there is nothing in the x-way (to move to the center of the ladder if standing a little bit aside). Otherwise, will not lock.
        """
        obj = self.game_object

        # test x-direction after corrective x-move to center of ladder (if there is something, don't lock)
        #obj.stage.locate()

        self.on_ladder = self.touched_ladder
        # switch off gravity
        self.gravity = False
        # lock obj to center of ladder (touched_ladder is always set to the one we are touching right now)
        obj.rect.centerx = self.touched_ladder.rect.centerx
        self.vx = 0  # stop x-movement
        # undock all objects currently docked to us (if any)
        self.game_obj_cmp_dockable.undock_all_docked_objects()
        # store the type before it locked to the ladder and remove the dockable/one-way-platform types (if set)
        self.type_before_ladder = obj.type
        obj.type &= ~Sprite.get_type("one_way_platform,dockable")

    def unlock_ladder(self):
        """
        Frees the GameObject from a ladder - if it is currently on a ladder.
        """
        if self.on_ladder:
            self.on_ladder = None
            self.gravity = True
            # restores the type we had before we locked into the ladder
            self.game_object.type = self.type_before_ladder

    def push_back(self, sequence):
        """
        Pushes the GameObject in x direction for some number of frames (e.g. when being hit by an arrow). The force of the push is given as
        x-acceleration value being added to the already calculated normal physics acceleration values. E.g. the character's brain wants to go left:
        ax is then the running acceleration plus the value of the first item in the sequence. The sequence's first item is then removed.

        :param list sequence: a list of additive x-accelerations that will be applied (on top of the regular physics) to the GameObject frame by frame
         until the list is empty
        """
        self.push_back_list = sequence

    def tick(self, game_loop):
        """
        Needs to be called by the GameObject at some point during the GameObject's `tick` method.
        Determines x/y-speeds and moves the GameObject.

        :param GameLoop game_loop: the currently playing GameLoop object
        """
        dt = game_loop.dt
        ax = self.push_back_list.pop(0) if len(self.push_back_list) > 0 else 0
        obj = self.game_object
        dockable = obj.components["dockable"]

        #print("dt={} x={} vx={}".format(dt, obj.rect.x, self.vx))

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
                    ax += -(self.run_acceleration or 999000000000)  # accelerate left
                    obj.flip['x'] = True  # mirror other_sprite

                    # user is pressing left or right -> leave on_ladder state
                    self.unlock_ladder()
                # user presses both keys (left and right) -> just stop
                else:
                    self.vx = 0

            # only right is pressed
            elif self.game_obj_cmp_brain.commands["right"]:
                if self.stops_abruptly_on_direction_change and self.vx < 0:
                    self.vx = 0  # stop first if still walking in other direction
                ax += self.run_acceleration or 999000000000  # accelerate right
                obj.flip['x'] = False

                # user is pressing left or right -> leave on_ladder state
                self.unlock_ladder()
            # stop immediately (vx=0; don't accelerate negatively)
            else:
                # ax = 0; // already initalized to 0
                self.vx = 0

            # determine y speed
            # -----------------
            if self.on_ladder:
                self.vy = 0
            # user is pressing 'up' (ladder?)
            if self.game_obj_cmp_brain.commands.get("up", False):
                # obj is currently locked into a ladder
                if self.on_ladder:
                    # reached the top of the ladder -> lock out of ladder
                    if obj.rect.bottom <= self.touched_ladder.rect.top:
                        self.unlock_ladder()
                    else:
                        self.vy = -self.climb_speed
                # player locks into ladder
                elif self.touched_ladder and self.touched_ladder.rect.bottom >= obj.rect.bottom > self.touched_ladder.rect.top:
                    self.lock_ladder()
            # user is pressing only 'down' (ladder?)
            elif self.game_obj_cmp_brain.commands.get("down", False):
                if self.on_ladder:
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
                jump = self.game_obj_cmp_brain.commands.get("jump", False)
                if not jump:
                    self.disable_jump = False
                else:
                    if (self.on_ladder or dockable.is_docked()) and not self.disable_jump:
                        self.unlock_ladder()
                        self.vy = -self.jump_speed
                        dockable.undock()
                    self.disable_jump = True
        # entity has no steering unit (x-speed = 0)
        else:
            self.vx = 0

        # TODO: check the entity's magnitude of vx and vy,
        # reduce the max dt_step if necessary to prevent skipping through objects.
        dt_step = dt
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

            # do we have to stop sinking?
            if self.is_sinking_til and obj.rect.y >= self.is_sinking_til:
                self.vy = 0.0

            # reset all touch flags before doing all the collision analysis
            if self.vx != 0.0 or self.vy != 0.0:
                # self.slope_up_down = 0
                if self.on_ladder is None:
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

                #print("dt={} sx={} vx={}".format(dt, sx, self.vx))

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
        # TODO: non-default layers (touch?)
        # for layer in stage.tiled_tile_layers.values():
        #    if not layer.type & Sprite.get_type("default") and sprite.collision_mask & layer.type:
        #        layer.collide(sprite, direction, direction_veloc, original_pos)

    def collide_with_collision_layer(self, sprite, layer, direction, direction_veloc, original_pos):
        """
        Collides a Sprite with a collision TiledTileLayer (type==default) and solves all detected collisions.
        Supports slopes of all shapes (given y = mx + b parameterized).
        Certain restrictions apply for the tiled landscape for this algorithm to work:
        - no upside-down slopes allowed (slopes on the ceiling)
        - TODO: what other restrictions?

        :param Sprite sprite: the Sprite to test for collisions against a TiledTileLayer
        :param TiledTileLayer layer: the TiledTileLayer object in which to look for collision tiles (full of sloped)
        :param str direction: `x` or `y` direction in which the sprite is currently moving before this test
        :param float direction_veloc: the velocity in the given direction (could be negative or positive)
        :param Tuple[int,int] original_pos: the position of the sprite before the move that caused this collision test to be executed
        """
        # determine the tile boundaries (which tiles does the sprite overlap with?)
        tile_start_x, tile_end_x, tile_start_y, tile_end_y = layer.get_overlapping_tiles(sprite)

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
                                col = AABBCollision.collide(sprite, tile_sprite, None, "y", 0.1, original_pos)
                            # neighbor slope not high enough AND stairs option disabled -> 1) bump up sprite on slope 2) solve x-collision against full tile
                            else:
                                # make sure the sprite is bumped up on the neighbor up-slope (this may already be done by the xy-pull if vx is not too high)
                                if sprite.components["dockable"].is_docked():
                                    sprite.move(0.0, -(sprite.rect.bottom - (neighbor.rect.bottom - neighbor_border_y)))
                                # no stairs -> bump against full tile from the side
                                col = AABBCollision.collide(sprite, tile_sprite, None, direction, direction_veloc, original_pos)
                        # normal full-tile x-collision w/o neighbor slope
                        else:
                            col = AABBCollision.collide(sprite, tile_sprite, None, direction, direction_veloc, original_pos)

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
                        col = AABBCollision.collide(sprite, tile_sprite, None, direction, direction_veloc, original_pos)
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
                    col = AABBCollision.collide(sprite, highest_tile, None, direction, direction_veloc, original_pos)
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
        Gets called (via event trigger 'collision' (setup when this component is added to our GameObject)) when a collision is detected (e.g. by a layer).

        :param Collision col: the collision object of the detected collision (the first sprite in that Collision object must be our GameObject)
        """
        obj = self.game_object
        assert obj is col.sprite1, "ERROR: game_object ({}) of physics component is not identical with passed in col.sprite1 ({})!".format(obj, col.sprite1)
        dockable = obj.components["dockable"]

        assert hasattr(col, "sprite2"), "ERROR: no sprite2 in col-object!"
        other_obj = col.sprite2
        other_obj_physics = other_obj.components.get("physics", None)

        # getting hit by a particle (Arrow, ScorpionShot, Fireball, etc..)
        if other_obj.type & Sprite.get_type("particle"):
            # obj is not heavy -> push back from getting hit by that particle
            if not self.is_heavy:
                obj.trigger_event("hit.particle", col)
                push_direction = col.normal_x if col.normal_x != 0 else math.copysign(1.0, getattr(other_obj, "vx", 0.0))
                if push_direction != 0.0:
                    self.push_back([500 * push_direction] * 5)
            return

        # colliding with a one-way-platform: can only collide when coming from the top
        # -> test early out here
        if other_obj.type & Sprite.get_type("one_way_platform"):
            # other object is a ladder as well
            if other_obj.type & Sprite.get_type("ladder"):
                # set touched_ladder to the ladder
                self.touched_ladder = other_obj
                # we are locked into a ladder
                if self.on_ladder:
                    return
            # we are x-colliding with the one-way-platform OR y-colliding in up direction OR y-colliding in down direction but not(!)
            # with the top of the one-way-platform -> ignore collision and return
            if col.direction == "x" or col.direction_veloc < 0 or (col.original_pos[1] + obj.rect.height) > other_obj.rect.top:
                return

        # TODO: get rid of this:
        # a collision layer
        if isinstance(other_obj, TileSprite):
            tile_props = other_obj.tile_props
            type_ = tile_props.get("type")
            # colliding with an exit
            if type_ == "exit":
                self.at_exit = True
                obj.stage.screen.trigger_event("reached_exit", obj)  # let the level know
                return
        # a liquid body
        elif isinstance(other_obj, LiquidBody):
            # just on first collision: pull up a little again, then slowly sink in (no more gravity)
            obj.collision_mask = 0
            obj.rect.y += col.separate[1]
            self.is_sinking_til = other_obj.rect.top
            self.vy = 0.01
            self.gravity = False
            obj.trigger_event("hit.liquid", other_obj.description)
            return

        # normal collision
        col.impact = 0.0

        impact_x = abs(self.vx)
        impact_y = abs(self.vy)

        # move away from the collision (back to where we were before)
        x_orig = obj.rect.x
        y_orig = obj.rect.y
        obj.move(col.separate[0], col.separate[1])

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
                    obj.move(None, y_orig - col.separate[1] * (other_obj_physics.squeeze_speed / self.vy), absolute=True)
                # otherwise, just undo the y-separation
                else:
                    obj.move(0.0, -col.separate[1])

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
        Pushes a pushable other GameObject (assuming that this other object also has a PlatformerPhysics Component).

        :param pusher: the Sprite that's actively pushing against the other GameObject
        :param col: the Collision object (that caused the push) returned by the collision detector method
        """

        pushee = col.sprite2  # the object being pushed
        orig_x = pushee.rect.x
        pushee_phys = pushee.components["physics"]
        # calculate the amount to move in x-direction based on vx_max and the collision-separation
        move_x = - col.separate[0] * abs(pushee_phys.vx_max / col.direction_veloc)
        # adjust x-speed based on vx_max
        self.vx = math.copysign(pushee_phys.vx_max, col.direction_veloc)

        # first move rock, then do a x-collision detection of the rock, then fix that collision (if any) -> only then move the pusher
        pushee.move(move_x, 0)
        # TODO: be careful not to overwrite the col object that's currently still being used by this method's caller
        # right now it's being overridden by the below call -> it's not a problem yet because this collision object is only used further via the normal_x
        # property, which should stay the same
        self.collide_in_one_direction(pushee, "x", self.vx, (orig_x, pushee.rect.y))
        # re-align pusher with edge of pushee
        if self.vx < 0:
            x_delta = pushee.rect.right - pusher.rect.left
        else:
            x_delta = pushee.rect.left - pusher.rect.right
        # and we are done
        pusher.move(x_delta, 0)

