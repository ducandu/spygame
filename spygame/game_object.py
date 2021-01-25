from spygame.event_object import EventObject


class GameObject(EventObject):
    """
    A GameObject adds the capability to add one or more Component objects to the GameObject
    (e.g. animation, physics, etc..).
    Component objects are stored by their name in the GameObject.components dict.
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

        # register events that need to trigger (later)
        self.register_event("destroyed")

    def add_component(self, component):
        """
        Adds a component object to this GameObject -> calls the component's added method.

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
        Removes the given component from this GameObject.

        :param Component component: the Component object to be removed
        """
        assert component.name in self.components, "ERROR: component with name {} does no exist in Entity!".format(component.name)
        # call the removed handler (if implemented)
        component.removed()
        # only then erase the component from the GameObject
        del self.components[component.name]

    def destroy(self):
        """
        Destroys the GameObject by calling debind and removing the object from it's parent.
        Will trigger a `destroyed` event (callback).
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
        A tick (coming from the GameObject containing Stage).
        Override this if you want your GameObject to do something each frame.

        :param GameLoop game_loop: the GameLoop that's currently playing
        """
        pass
