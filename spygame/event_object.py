class EventObject(object):
    """
    An EventObject introduces event handling and most objects that occur in spygame games will inherit from this class.
    NOTE: spygame events are not(!) pygame events.
    EventObject can 'have' some events, which are simple strings (the names of the events, e.g. 'hit', 'jump', 'collided', etc..).
    EventObject can trigger any event by their name.
    If an EventObject wants to trigger an event, this event must have been registered with the EventObject beforehand (will raise exception otherwise).
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
        Removes one or more events from this EventObject's event registry; unregistered events are no longer allowed to be triggered.

        :param str events: the event(s) that should be removed from the registry
        """
        for event in events:
            self.valid_events.remove(event)

    def unregister_all_events(self):
        """
        Unregisters all events from this GameObject (see 'unregister_event').
        """
        self.valid_events.clear()

    def check_event(self, event: str):
        """
        Checks whether the given event is in this EventObject's registry (raises exception if not).

        :param str event: the event to be checked
        """
        # make sure the event is valid (registered)
        if event not in self.valid_events:
            raise Exception("ERROR: event '{}' not valid in this EventObject ({}); event has not been registered!".format(event, type(self).__name__))

    def on_event(self, event, target=None, callback=None, register=False):
        """
        Binds a callback to an event on this EventObject.
        If you provide a `target` object, that object will add this event to it's list of binds, allowing it to automatically remove it when
        it is destroyed.
        From here on, if the event gets triggered, the callback will be called on the target object.
        Note: Only previously registered events may be triggered (we can register the event here by setting register=True).

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
        Triggers an event and specifies the parameters to be passed to the bound event handlers (callbacks) as \*params.

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
        Unbinds an event from a target/callback.
        Can be called with 1, 2, or 3 parameters, each of which unbinds a more specific listener.

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
        Called to remove any listeners from this object.
        E.g. when this object is destroyed you'll want all the event listeners to be removed from this object.
        """
        if hasattr(self, "event_binds"):
            for source, event, _ in self.event_binds:
                source.off_event(event, self)
