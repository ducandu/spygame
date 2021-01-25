from abc import ABCMeta, abstractmethod
import types

from spygame.game_object import GameObject


class Component(GameObject, metaclass=ABCMeta):
    """
    A Component can be added to and removed from other GameObjects.
    Use "extend" to make a Component's method be callable directly from the owning GameObject.

    :param str name: the name of the component (the name can be used to retrieve any GameObject's components via the [GameObject].components dict)
    """

    def __init__(self, name):
        super().__init__()
        self.name = name
        self.game_object = None  # to be set by Entity when this component gets added

    @abstractmethod
    def added(self):
        """
        Gets called when the component is added to a GameObject.
        """
        pass

    def removed(self):
        """
        Gets called when the component is removed from a GameObject.
        """
        pass

    def extend(self, method):
        """
        Extends the given method (has to take self as 1st param) onto the GameObject, so that this method can be called directly from the GameObject.
        The extended method will take two self's (0=Component, 1=GameObject), thus selfs should be called 'comp' and 'game_object' OR 'self' and 'game_object'

        :param callable method: method, which to make callable from within the owning GameObject
        """
        assert self.game_object, "ERROR: need self.game_object in order to extend the method to that GameObject!"

        # keep the original method under a different name (just in case it's still needed by the overwriting method)
        old = getattr(self.game_object, method.__name__, None)
        if old:
            setattr(self.game_object, "_super_" + method.__name__, old)

        # use the MethodType function to bind the given method function to only this object (not any other instances of the GameObject's class)
        setattr(self.game_object, method.__name__, types.MethodType(method, self.game_object))
