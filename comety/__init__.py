# vim:fileencoding=UTF-8 
#
# Copyright 2016, 2017 Stan Livitski
#
# This file is part of Comety. Comety is
# Licensed under the Apache License, Version 2.0 with modifications,
# (the "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#  https://raw.githubusercontent.com/StanLivitski/Comety/master/LICENSE
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""
    Comety is a simple toolkit for adding Comet_ functionality to
    a web application.
    
    Comet_ is a web programming model that allows a web server to
    push data to a browser. Comety enables the Comet_ model in web
    applications that use a multi-threaded server without the
    expense of configuring and maintaining complex dependencies.

    The root package `MUST NOT` have dependencies on Django_ or
    any other web framework, so it can be used by projects across
    frameworks.

    The view code is factored into a subpackage called `django`,
    and templates are stored in its ``templates`` directory.

    Key elements
    ------------
    Dispatcher : Queues events for delivery to the browsers of Comety
        pages and detects client connection timeouts.
    Timer : A thread-based class that augments `threading.Timer` with
        stop and reset functions.
    django : Elements of the Comety toolkit that depend on the
        Django_ framework.

    .. _Comet: https://en.wikipedia.org/wiki/Comet_%28programming%29
    .. _Django: https://www.djangoproject.com
"""

import version

version.requirePythonVersion(3, 2)

from numbers import Number
import math
import threading
import time
import sys

class Timer:
    """
    Reusable timer with an internal thread that runs a
    user-supplied handler function.
    
    Each object of this class runs an internal thread that waits for
    a certain time and than runs a user-supplied `handler` function,
    if any, and changes its internal `status`. Before the timer goes
    off, the object may be asked to `cancel` it. After the timer goes
    off, or is cancelled, it may be reset to run the same or different
    `handler` function again at some time in future. This class
    implements the context manager protocol to allow locking the timer
    using ``with`` statement as it is being manipulated.
    
    Parameters
    --------------------
    handler : collections.Callable | object, optional
        A callable object that will be called when the timer goes off.

    Attributes
    -----------------
    state
    error : BaseException
        Any uncaught exception that occurred in the `handler` last time
        it was run, otherwise ``None``.

    Methods
    ---------------
    start(delay,handler,args,kwargs)
        Activate the timer and allow the caller to change the handler.
    cancel()
        Stop the timer if it is active.
    discard()
        Dispose of the internal thread and objects used to synchronize
        this timer. 

    Raises
    ----------
    TypeError
        If the supplied `handler` object is not callable.

    Examples
    ----------------
    >>> Timer(1)
    Traceback (most recent call last):
    ...
    TypeError: type "int" is not callable
    >>> t=Timer(print)
    >>> t.state
    'idle'
    >>> import time
    >>> t.start(.2, args=['wake up!'])
    >>> t.state
    'started'
    >>> time.sleep(.25)
    wake up!
    >>> t.state
    'idle'
    >>> t.error is None
    True
    >>> t.start(.2, args=['wake up!'])
    >>> t.state
    'started'
    >>> t.cancel()
    >>> t.state
    'idle'
    >>> t.start(0, all)
    >>> time.sleep(.15)
    >>> t.state
    'idle'
    >>> t.error
    TypeError('all() takes exactly one argument (0 given)',)
    >>> t.discard()
    >>> t.state
    'discarded'
    """

    def __init__(self, handler = None):
        if handler is not None and not callable(handler):
            raise TypeError('type "%s" is not callable' % type(handler).__name__)
        self._monitor = threading.Condition(threading.RLock())
        self._thread = None
        self._handler = handler
        self._state = 'idle'
        self.error = None

    def __enter__(self):
        self._monitor.acquire()

    def __exit__(self, exc_type, exc_value, traceback):
        self._monitor.release()

    def start(self, delay, handler = None, args = (), kwargs = {}):
        """
        Activate the timer and set the delay after which it'll go off.

        If the object is ``'idle'``, calling this method moves it to the
        ``'started'`` state and clears the `error` attribute. It also
        activates a background thread that will wait for a specified time,
        then switch the object back to the ``'idle'`` state and call any
        `handler` with optional arguments passed to this method. If a
        handler is passed to this method, it overrides the constructor's
        argument.
        
        Parameters
        ----------
        delay : int | float | str
            The number of seconds, or fractions thereof, to wait on the
            background before performing the scheduled action.
        handler : collections.Callable | object | None, optional
            A callable object that will be called when the timer goes off.
            If ``None`` is passed, then the handler supplied to the most
            recent `start` invocation, if any, or this object's
            constructor otherwise, will be called.
    
        Other parameters
        ----------
        args : collections.Iterable, optional
            Positional arguments, if any, to be passed to the `handler`
            when it is called.
        kwargs : collections.Mapping, optional
            Keyword arguments, if any, to be passed to the `handler`
            when it is called.
    
        Raises
        ------
        TypeError
            If the supplied `handler` object is not callable, 
        ValueError
            If `delay` is negative or cannot be converted to
            a number.
        RuntimeError
            If this timer is already started, or has been discarded. 
    
        See Also
        --------    
        state : The current state of this object.
    
        Examples
        --------
        >>> t=Timer()
        >>> import time
        >>> t.start(.1, print, ['wake up!'])
        >>> t.state
        'started'
        >>> time.sleep(.15)
        wake up!
        >>> t.state
        'idle'
        >>> t.start(-1)
        Traceback (most recent call last):
        ...
        ValueError: delay -1 must be a finite positive number or zero
        >>> t.start('foo')
        Traceback (most recent call last):
        ...
        ValueError: could not convert string to float: 'foo'
        >>> t.start(1,'foo')
        Traceback (most recent call last):
        ...
        TypeError: type "str" is not callable
        >>> t.state
        'idle'
        >>> def repeat(interval_, call_, *args, _skip=True, **kwargs):
        ...  if not _skip:
        ...   call_(*args, **kwargs)
        ...  kwargs.update(_skip=False)
        ...  t.start(interval_, repeat, (interval_,call_)+args, kwargs)
        >>> repeat(.33, print, ':)', end='')
        >>> t.state
        'started'
        >>> time.sleep(1)
        :):):)
        >>> t.start(1, print)
        Traceback (most recent call last):
        ...
        RuntimeError: this timer has been started, cannot start it again
        >>> t.error is None
        True
        >>> t.discard()
        """

        delay = float(delay)
        if 0 > delay or not math.isfinite(delay):
            raise ValueError(
                'delay %g must be a finite positive number or zero' % delay)
        if handler is None:
            pass
        elif not callable(handler):
            raise TypeError('type "%s" is not callable' % type(handler).__name__)
        def reusableTimer():
            nonlocal self
            with self._monitor:
                while True:
                    if self._state == 'idle':
                        self._monitor.wait()
                    elif self._state == 'started':
                        if not self._monitor.wait(self._delay) and self._state == 'started':
                            self._state = 'idle'
                            if self._handler is not None:
                                handler, args, kwargs = (
                                     self._handler, self._args, self._kwargs )
                                self._args, self._kwargs, error = (None,) * 3
                                self._monitor.release()
                                try:
                                    handler(*args, **kwargs)
                                except:
                                    error = sys.exc_info()[1]
                                finally:
                                    self._monitor.acquire()
                                    self.error = error
                                    del error
                    else:
                        break
        with self._monitor:
            if self._state != 'idle':
                raise RuntimeError(
                   'this timer has been %s, cannot start it again' % self._state)
            if handler is not None:
                self._handler = handler
            self.error = None
            if self._thread is None:
                self._thread = threading.Thread(
                    target=reusableTimer,
                    name=type(self).__name__
                )
                self._thread.daemon = True
                self._thread.start()
            self._delay = delay
            self._args = args
            self._kwargs = kwargs
            self._state = 'started'
            self._monitor.notify()

    def cancel(self):
        """
        Stop the timer if it is active.
        
        If the object is in the ``'started'`` `state`, this method
        cancels any pending action and changes its state to ``'idle'``.
        If the object is in the ``'idle'`` `state`, this method does
        nothing.
    
        See Also
        --------    
        state : The current state of this object.
    
        Raises
        ------
        RuntimeError
            If this timer has been discarded. 
    
        Examples
        --------
        >>> t=Timer()
        >>> t.start(.1, print, ['wake up!'])
        >>> t.state
        'started'
        >>> t.cancel()
        >>> t.state
        'idle'
        >>> import time
        >>> time.sleep(.35) 
        >>> t.cancel()
        >>> t.state
        'idle'
        >>> t.discard()
        """
        with self._monitor:
            if self._state == 'idle':
                pass
            elif self._state == 'started':
                self._state = 'idle'
                self._args = self._kwargs = None
                self._monitor.notify()
            else:
                raise RuntimeError(
                   'this timer has been %s, cannot cancel it' % self._state)

    def discard(self, timeout=.5):
        """
        Dispose of the internal thread and objects used to synchronize
        this timer.
        
        Call this method to free up resources taken by this timer when
        it is no longer needed. The call will cancel any pending `handler`
        call, change this object's `state` to ``'discarded'``, and prevent
        it from scheduling any further actions. However, you will still be
        able to read the `error` attribute after it returns. Repeat calls
        of this method do nothing.

        Parameters
        ----------
        timeout : int | float | str | NoneType
            The number of seconds, or fractions thereof, to wait for the
            timer thread to stop, or ``None`` to wait indefinitely.
    
        Raises
        ------
        RuntimeError
            If the timer thread fails to stop within the `timeout`.
        ValueError
            If `timeout` is negative or cannot be converted to
            a number.
    
        See Also
        --------    
        state : The current state of this object.
    
        Examples
        --------
        >>> t=Timer()
        >>> t.start(.1, print, ['wake up!'])
        >>> t.state
        'started'
        >>> t.discard()
        >>> t.state
        'discarded'
        >>> import time
        >>> time.sleep(.2)
        >>> t.start(1)
        Traceback (most recent call last):
        ...
        RuntimeError: this timer has been discarded, cannot start it again
        >>> t.cancel()
        Traceback (most recent call last):
        ...
        RuntimeError: this timer has been discarded, cannot cancel it
        >>> t.discard()
        """

        if timeout is not None:
            timeout = float(timeout)
            if 0 > timeout or not math.isfinite(timeout):
                raise ValueError(
                    'Thread disposal timeout %g must'
                    ' be a finite positive number or zero'
                    % timeout
                )
        with self._monitor:
            if self._state == 'discarded':
                return
            self._state = 'discarded'
            self._args = self._kwargs = None
            self._monitor.notify()
        if self._thread is not None:
            if threading.current_thread() is self._thread:
                # hold the monitor until the current timer thread exits its context
                self._monitor.acquire()
            else:
                self._thread.join(timeout)
                if self._thread.is_alive():
                    raise RuntimeError(
                       'the timer thread did not stop in %s seconds.' % timeout
                    )
            self._thread = None
        del self._handler
        class DummyContext:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_value, traceback):
                return False
            def acquire(self):
                pass
        self._monitor = DummyContext()

    def getState(self):
        """
        The current state of this object.

        This attribute can take one of the following values:
        
        - ``'idle'`` when the object has just been created, or
          finished a scheduled action, and is ready to schedule a
          new action
        - ``'started'`` when the object has an action scheduled for
          the future
        - ``'discarded'`` when the object has been disposed of and can
          no longer be used
    
        Returns
        -------
        {'idle', 'started', 'discarded'}
            The current state of this object.
    
        See Also
        --------    
        start : Moves an ``'idle'`` timer object to the ``'started'``
                state.
        cancel : Moves a ``'started'`` timer object to the ``'idle'``
                 state and cancels pending action.
        discard : Moves a timer object to the ``'discarded'`` state.
        """
        return self._state     

    state = property(getState)

class JSONSerializable:
    """
    Marks an object that knows how to convert its data into
    JSON-serializable structures.

    Methods
    ---------------
    _json_data_()
        Override this method to return a Python data structure
        that can be coverted to JSON by `json.JSONEncoder`, or
        `django.core.serializers.json.DjangoJSONEncoder` for
        Django applications.
    
    See also
    --------
    json.JSONEncoder : defines basic data elements and structures
        serializable into JSON
    django.core.serializers.json.DjangoJSONEncoder : serializes
        additional data types and structures within the Django
        framework
    """

    def _json_data_(self):
        raise NotImplementedError(
            'JSON encoding not implemented for %s' % type(self)
        )

class Dispatcher:
    """
    Queues events for delivery to the browsers of Comety pages and detects
    client connection timeouts.
    
    This class defines an object that receives signals from the server,
    wraps them into events, queues those events for delivery to the
    clients, and maintains optional heartbeat timers to handle
    timeouts of client connections.

[    Attributes
    -----------------
    <name_of_a_property_having_its_own_docstring> # or #
    <var>[, <var>] : <type | value-list>
        <Description of an attribute>
    ...]

    Methods
    ---------------
    registerUser(userId, notifyUsers)
        Register a user that will receive events from this dispatcher.
    unregisterUser(userId, notifyOthers)
        Revoke registration of a user that was receiving events from
        this dispatcher.
    postEvent(sender_, kwargs)
        Create a new event object and place it on the queue.
    pollEvents(userId, timeout)
        Poll the queue for new events on behalf of a specific user.
    confirmEvents(userId, lastSeq)
        Confirm receipt of event notifications on behalf of a user.
    discard()
        Dispose of the dispatcher when it's no longer needed.

[    See Also
    --------------
    <python_name> : <Description of code referred by this line
    and how it is related to the documented code.>
     ... ]

    Examples
    ----------------
    >>> dispatcher = Dispatcher()
    >>> regEventId = dispatcher.registerUser('foo')
    >>> type(regEventId) is int
    True
    >>> source = object()
    >>> dummyEventId = dispatcher.postEvent(source, event='test', description='event example')
    >>> type(dummyEventId) is int
    True
    >>> events = dispatcher.pollEvents('foo')
    >>> len(events)
    2
    >>> events[0] == dummyEventId
    True
    >>> len(events[1])
    2
    >>> events[1][0].sender == Dispatcher
    True
    >>> events[1][1].sender == source
    True
    >>> events[1][0].kwargs == {'userId': 'foo', 'event': 'register-user'}
    True
    >>> events[1][1].kwargs == {'event': 'test', 'description': 'event example'}
    True
    >>> dispatcher.confirmEvents('foo', dummyEventId)
    >>> events = dispatcher.pollEvents('foo', 0)
    >>> len(events)
    2
    >>> events[0] == dummyEventId
    True
    >>> bool(events[1])
    False
    >>> dispatcher.scheduleTimeout('foo', .1, print)
    False
    >>> import time
    >>> time.sleep(.2)
    foo
    >>> dispatcher.unregisterUser('foo')
    >>> dispatcher.discard()
    """

    class Event(JSONSerializable):
        """
        Container that stores information about a UI event.
        
        TODOdoc: <Extended description>
        
        Parameters
        ----------
        sender_ : object
            The value of the event's ``sender_`` attribute.
    
        Attributes
        -----------------
        sender : object
            A reference to the object that originated this event, or
            its class. Objects passed here should have a
            non-default ``str`` representation to avoid revealing
            their in-memory addresses to JSON clients. Type objects
            (classes) don't have that problem.
        kwargs : dict
            Key-value pairs that store any additional information about
            this event.
    
    [    Methods
        ---------------
        <name>([<param>, ...])
            <One-line description of a method to be emphasized among many others.>
        ...]
    
        Other parameters
        ----------------
        Any extra keyword arguments shall be stored in the `kwargs`
        attribute as the additional information about this
        event.       
    
    [    Raises
        ----------
        <exception_type>
            <Description of an error that the constructor may raise and under what conditions.
            List only errors that are non-obvious or have a large chance of getting raised.>
        ... ]
    
    [    See Also
        --------------
        <python_name> : <Description of code referred by this line
        and how it is related to the documented code.>
         ... ]
    
    [   Examples
        ----------------
        <In the doctest format, illustrate how to use this class.>
         ]
        """
        # TODO: make objects of this class immutable,
        def __init__(self, sender_, **kwargs_):
            self.sender = sender_
            self.kwargs = kwargs_

        def _json_data_(self):
            return (str(self.sender), self.kwargs)


    def __init__(self):
        self._lowestWindow = self._baseSeq = 1
        # for now, lock _accessGuard when updating the above 
        self._userEntries = dict() # of [ window, timer ]
        # for now, lock _accessGuard when updating the above, or its entries 
        self._eventQueue = []
        # This list is read concurrently by processes that SHOULD
        # make a copy of its reference while holding an _accessGuard
        # lock and use that copy to access the queue. Therefore, the
        # list MUST NOT be updated in-place. The only allowed changes
        # are appending elements and replacing the reference with another
        # list. Reference replacement MUST be done while _accessGuard is
        # locked. 
        self._eventQueueBeingPurged = False
        self._accessGuard = threading.Condition()

    EVENT_TYPE_KEY = 'event'
    REGISTER_USER_EVENT_TYPE = 'register-user'
    UNREGISTER_USER_EVENT_TYPE = 'unregister-user'
    USER_ID_KEY = 'userId'

    QUEUE_SLACK_RATIO = 1
    """
    A float greater than 0 that equals the least acceptable ratio
    of pending to delivered events on the queue. When the actual
    ratio falls to or below this figure, `confirmEvents`() will
    trigger purging old events from the queue, subject to
    `QUEUE_PURGE_MINIMUM` limitation.
    """

    QUEUE_PURGE_MINIMUM = 20
    """
    An integer greater than 0 that equals the smallest size of the
    queue that may be purged by `confirmEvents`().
    """

    def registerUser(self, userId, notifyUsers = True):
        """
        Register a user that will receive events from this dispatcher.
        
        This method makes an entry with this object about a new user
        that will poll the event queue herein. It also generates an
        event to notify users about the new registration, unless
        the caller requests not to do so. 
        
        Parameters
        ----------
        userId : collections.Hashable
            Identity of the new user. This value must be distinct from
            other users' identities. It shall also be immutable. 
        notifyUsers : bool, optional
            A flag requesting the `Dispatcher` to post an
            event notifying other users about the new registration.
            This is on by default. Note that the new user shall also
            receive this event.

        Returns
        -------
        int | NoneType
            Serial number assigned to the event notifying other users
            about the new registration, or ``None`` if no such event
            has been generated. 
    
        Raises
        ------
        ValueError
            If ``userId`` is not unique, or already registered
            with this object.
    
        See Also
        --------
        pollEvents : Registered users call that method to receive
            event notifications from a dispatcher. 
        unregisterUser : The method that revokes user registrations
            herein.
    
    [   Examples
        --------
        <In the doctest format, illustrate how to use this method.>
         ]
        """

        badId = userId in self._userEntries
        if not badId:
            entry = [ None, Timer() ]
            with self._accessGuard:
                if userId in self._userEntries:
                    badId = True
                else:
                    entry[0] = (self._baseSeq + len(self._eventQueue)
                                if self._eventQueue
                                else self._lowestWindow)
                    self._userEntries[userId] = entry
        if badId:
            raise ValueError(
                'User with id "%s" is already registered' % userId)
        if notifyUsers:
            return self.postEvent(type(self), **{
                    self.EVENT_TYPE_KEY: self.REGISTER_USER_EVENT_TYPE,
                    self.USER_ID_KEY: userId
                })
        else:
            return None

    def unregisterUser(self, userId, notifyOthers = True):
        """
        Revoke registration of a user that was receiving events from
        this dispatcher.
        
        This method removes the entry with this object about a user
        that was poll the event queue herein. It also generates an
        event to notify other users about the revoked registration,
        unless the caller requests not to do so.
        
        Parameters
        ----------
        userId : collections.Hashable
            Identity of the removed user. This value must be equal to
            the id the user was registered with. 
        notifyOthers : bool, optional
            A flag requesting the `Dispatcher` to post an event
            notifying other users about the revocation. This is on
            by default. Note that the unregistered user shall not receive
            this event. 

        Returns
        -------
        int | NoneType
            Serial number assigned to the event notifying other users
            about the revoked registration, or ``None`` (nothing) if no
            such event has been generated. 
    
        Raises
        ------
        ValueError
            If ``userId`` is not registered with this object, or already
            has its registration revoked.
    
        See Also
        --------    
        registerUser : The method that creates user registrations
            herein.
    
    [   Examples
        --------
        <In the doctest format, illustrate how to use this method.>
         ]
        """

        entry = None
        if userId in self._userEntries:
            with self._accessGuard:
                entry = self._userEntries.pop(userId, None)                    
        if entry is None:
            raise ValueError(
                'User with id "%s" is not registered' % userId)
        try:
            if notifyOthers:
                return self.postEvent(type(self), **{
                        self.EVENT_TYPE_KEY: self.UNREGISTER_USER_EVENT_TYPE,
                        self.USER_ID_KEY: userId
                    })
            else:
                return None
        finally:
            entry[1].discard()

    def postEvent(self, sender_, **kwargs):
        """
        Create a new event object and place it on the queue.
        
        This method, bound to an object, can be used as a receiver
        function for Django_ signals. It will create an event object,
        post it to this object's event queue, and notify waiting
        users of the new posting.
        
        Parameters
        ----------
        sender_ : object
            A reference to the object that originated this event, or
            its class.

        Returns
        -------
        int | NoneType
            Sequence number assigned to the new event by the queue, or
            ``None`` if the event hasn't been placed on the queue due
            to lack of receivers.

        Other parameters
        ----------------
        Any extra keyword arguments shall be stored in the `kwargs`
        attribute as the additional information about this
        event.       
    
        See Also
        --------    
        Dispatcher.Event : Defines objects that contain information about
            posted events on the queue. This method creates
            `Dispatcher.Event` objects for you.  
    
    [   Examples
        --------
        <In the doctest format, illustrate how to use this method.>
         ]
        """

        event = self.Event(sender_, **kwargs)
        seq = None
        with self._accessGuard:
            if self._userEntries:
                seq = self._baseSeq + len(self._eventQueue)  
                self._eventQueue.append(event)
                self._accessGuard.notify_all()
        return seq

    def pollEvents(self, userId, timeout = None):
        """
        Poll the queue for new events on behalf of a specific user.
        
        Examines the event queue for events that have not yet been
        acknowledged by the calling user. If there are such new
        events, they are returned immediately. Otherwise, the call
        will result in the current thread waiting for any new events
        to be posted. The new events, if any, are then returned.
        
        Parameters
        ----------
        userId : collections.Hashable
            Identity of the calling user.
        timeout : float, optional
            The time in seconds, or fractions thereof, that
            the call shall be waiting for new events if none are
            present on the queue. Omitting this argument allows the
            call to wait indefinitely. Zero means poll the queue
            without waiting.
    
        Returns
        -------
        ( int, collections.Sequence | NoneType | bool )
            A tuple with the sequence number of the last event retrieved, or
            first event expected minus ``1``, followed by: either a sequence
            of new events retrieved from the queue, or an object equivalent to
            ``False`` when converted to a `bool` if no events were encountered
            in the allotted time.
    
        Raises
        ------
        ValueError
            If ``timeout`` is negative, or ``userId`` is not registered
            with this object, or has its registration revoked.
        RuntimeError
            If the internal data structures get corrupt.
    
        See Also
        --------    
        Dispatcher.Event : Defines event information objects that
            any non-empty returned tuple may contain.   
        registerUser : The method that creates user registrations
            herein.
        unregisterUser : The method that revokes user registrations
            herein.

        Notes
        -----
        To deliver events in the same order as they are posted,
        each event is assigned a sequence number. This method returns
        events with strictly ascending sequence numbers, without gaps.
        Thus, if the returned tuple contains 3 elements and the last
        reported sequence number is ``5``, then the first returned event
        has the number of ``3``, and the second has number ``4``. 
    
    [   Examples
        --------
        #>>> type(events).__name__
        'tuple'
        #>>> type(events[1]).__name__
        'tuple'
        <In the doctest format, illustrate how to use this method.>
         ]
        """

        if timeout is not None and (0 > timeout or not math.isfinite(timeout)):
            raise ValueError('Negative or undefined timeout value: %g' % timeout)
        userEntry, firstIndex, lastIndex, events, lastSeq = (None, )*5
        if userId in self._userEntries:
            with self._accessGuard:
                userEntry = self._userEntries.get(userId)
                if userEntry is not None:
                    firstIndex = userEntry[0] - self._baseSeq
                    if 0 > firstIndex:
                        raise RuntimeError (
                            'Event window for user id "%s" (%d) is out of sync with queue start %d'
                            % (userId, userEntry[0], self._baseSeq)
                        )
                    waited = False
                    while True:
                        if self._eventQueue:
                            lastIndex = len(self._eventQueue) - 1
                            lastSeq = self._baseSeq + lastIndex
                            events = self._eventQueue
                        else:
                            lastSeq = self._lowestWindow - 1
                        if waited or userEntry[0] <= lastSeq:
                            break
                        else:
                            if 0 < timeout:
                                self._accessGuard.wait(timeout)
                            waited = True
        if userEntry is None:                    
            raise ValueError(
                'User with id "%s" is not registered' % userId)
        if userEntry[0] > lastSeq:
            return userEntry[0] - 1, None
        assert events is not None, (
            'Event window for user id "%s" (%d) is out of sync with empty queue at %d'
            % (userId, userEntry[0], lastSeq)
        )
        # TODO: filter events while copying based on recipients' whitelist
        return lastSeq, tuple(events[firstIndex:(lastIndex + 1)])

    def confirmEvents(self, userId, lastSeqConfirmed = None):
        """
        Confirm receipt of event notifications on behalf of a user.
        
        All event notifications are kept on the queue and re-sent to a
        user each time it calls `pollEvents`, until the user confirms
        successful delivery. Calling this method instructs the dispatcher
        to stop sending user events up to a certain sequence number,
        or all events currently posted on the queue.
        The call may also trigger purging events from the queue that
        have been delivered to all users registered at the time such
        events were posted.
        
        Parameters
        ----------
        userId : collections.Hashable
            Identity of the calling user.
        lastSeqConfirmed : int | NoneType, optional
            Sequence number of the last event received and processed
            on behalf of the calling user. The call will have no effect
            if this precedes or equals the highest event number already
            confirmed by this user, or the highest event number preceding
            its registration. If omitted, the caller confirms that all
            events currently on the queue are of no interest to this user.
            Users may choose to do that when they refresh the entire page
            rather than receiving incremental updates. Such refresh
            operations should make this call before rendering any page
            elements that may be updated asynchronously. 
    
        Raises
        ------
        ValueError
            If ``userId`` is not registered with this object,
            or has its registration revoked, or `lastSeqConfirmed` follows the
            last event posted with this dispatcher.
        RuntimeError
            If the internal data structures get corrupt.
        TypeError
            If ``lastSeqConfirmed`` is not an integer.

    [    See Also
        --------    
        <python_name> : <Description of code referred by this line
        and how it is related to the documented code.>
         ... ]
    
    [    Notes
        -----
        <Additional information about the code, possibly including
        a discussion of the algorithm. Follow it with a 'References'
        section if citing any references.>
        ]
    
    [   Examples
        --------
        <In the doctest format, illustrate how to use this method.>
         ]
        """
        if lastSeqConfirmed is None:
            with self._accessGuard:
                lastSeqConfirmed = self._baseSeq + len(
                   self._eventQueue) - 1
        elif not isinstance(lastSeqConfirmed, int):
            raise TypeError(
               'lastSeqConfirmed must be an integer, got: %s'
               % type(lastSeqConfirmed).__name__
            )
        discardCount = None
        with self._accessGuard:
            userEntry = self._userEntries.get(userId)
            if userEntry is None:                    
                raise ValueError(
                    'User with id "%s" is not registered' % userId)
            oldWindow = userEntry[0]
            if oldWindow > lastSeqConfirmed:
                return
            nextSeq = self._baseSeq + len(self._eventQueue)
            if nextSeq <= lastSeqConfirmed:
                raise ValueError(
                    'Event number %d confirmed by user with id "%s" is'
                    + ' out of range (must be less than %d)' %
                    ( lastSeqConfirmed, userId, nextSeq )
                )
            userEntry[0] = lastSeqConfirmed + 1
            if oldWindow <= self._lowestWindow:
                self._lowestWindow = min(
                    entry[0] for entry in self._userEntries.values()
                )
                if (not self._eventQueueBeingPurged
                    and len(self._eventQueue) >= self.QUEUE_PURGE_MINIMUM
                ):
                    discardCount = self._lowestWindow - self._baseSeq
                    if 0 > discardCount:
                        raise RuntimeError(
                            ('Event queue sequencing out of sync with user'
                            + ' window(s), lowest at %d, queue base %d') %
                            (self._lowestWindow, self._baseSeq)
                        )
                    elif (int(discardCount * (1 + self.QUEUE_SLACK_RATIO))
                        >= len(self._eventQueue)
                    ):
                        self._eventQueueBeingPurged = True
                    else:
                        discardCount = None
        if discardCount is not None:
            try:
                assert 0 < discardCount
                endIndex = len(self._eventQueue)
                newQueue = self._eventQueue[discardCount:endIndex]
                with self._accessGuard:
                    if endIndex < len(self._eventQueue):
                        newQueue.extend(self._eventQueue[endIndex:])
                    self._eventQueue = newQueue
                    self._baseSeq += discardCount
            finally:
                self._eventQueueBeingPurged = False

    def scheduleTimeout(self, userId, timeout = 5, callback = None):
        """
        Start a timer to track the user's heartbeat, or reset
        an existing timer.
        
        Each registered user can only have one heartbeat timer
        set at any moment. If the timer is set for a user, this
        method can be run to stop that timer or replace it with a
        new one. Otherwise, run it to set a new timer for that
        user. When the timer goes off, the function passed via
        ``callback`` argument is called. This usually means that
        the user is no longer connected.
        
        Parameters
        ----------
        userId : collections.Hashable
            Identity of the user whose timer is being updated.
        timeout : int | float, optional
            The number of seconds, or fractions thereof, to wait before
            running the ``callback``. Ignored if ``callback`` is ``None``.
        callback : collections.Callable | object | NoneType, optional
            A callable object that will be called when the timer goes
            off, or ``None`` to cancel the user's timer. The ``callback``
            function should accept a single positional argument - the
            identity of the user that has no heartbeat. The callback
            should handle any errors it might raise.
    
        Returns
        -------
        bool | NoneType
            ``True`` if the user had an existing timer reset or canceled
            by this call, ``False`` otherwise; or ``None`` if the user was
            not registered or un-registered before the timer could be
            (re)set.
    
        Raises
        ------
        TypeError
            If ``timeout`` is not a number, or ``callback`` is not
            callable.
        ValueError
            If ``userId`` is not registered with this object,
            or has its registration revoked, or ``timeout`` is negative.
            However, an attempt to reset the timer for a non-existent
            user will be ignored and won't raise this error.
    
        See Also
        --------
        Timer : each registered user has an instance of that class,
        which is used by this method.
[    
        <python_name> : <Description of code referred by this line
        and how it is related to the documented code.>
         ... ]
    
        Examples
        --------
        >>> dispatcher = Dispatcher()
        >>> dispatcher.registerUser('foo', False)
        >>> dispatcher.scheduleTimeout('foo', .1, print)
        False
        >>> dispatcher.scheduleTimeout('foo') # cancels the callback
        True
        >>> import time
        >>> time.sleep(.2)
        >>> dispatcher.unregisterUser('foo')
        >>> dispatcher.discard()
        """

        if callback is not None:
            if not callable(callback):
                raise TypeError('Callback of type "%s" is not callable'
                                % type(callback).__name__)
            if not isinstance(timeout, Number):
                raise TypeError('Timeout of type "%s" is not a number'
                                % type(timeout).__name__)
            if 0 > timeout or not math.isfinite(timeout):
                raise ValueError('Timeout %g is negative or undefined' % timeout)
        userEntry = None
        if userId in self._userEntries:
            with self._accessGuard:
                userEntry = self._userEntries.get(userId)
                timer = None if userEntry is None else userEntry[1]
        if userEntry is None:
            if callback is None:
                return None
            else:
                raise ValueError('User with id "%s" is not registered' % userId)
        if not isinstance(timer, Timer):
            raise RuntimeError(
                'User with id "%s" has invalid timer of type "%s"' % (
                userId, type(timer).__name__))
        with timer:
            status = None
            if 'started' == timer.state:
                timer.cancel()
                status = True
            elif 'idle' == timer.state:
                status = False
            else:
                # The timer has been concurrently discarded,
                # which means that user is no longer registered
                callback = None
            if callback is not None:
                timer.start(timeout, callback, (userId,))
            return status

    def discard(self):
        """
        Dispose of the dispatcher when it's no longer needed.
        
        Releases resources, such as timer threads, used by this
        dispatcher. This has a side effect of un-registering all
        known users and clearing the queue. You should not use
        this object after it's been discarded. Repeat calls of this
        method have no effect.
    
    [    See Also
        --------    
        <python_name> : <Description of code referred by this line
        and how it is related to the documented code.>
         ... ]
    
    [   Examples
        --------
        <In the doctest format, illustrate how to use this method.>
         ]
        """

        while True:
            with self._accessGuard:
                while self._userEntries:
                    entry = self._userEntries.popitem()
                    assert isinstance(entry[1][1], Timer)                    
                    entry[1][1].discard()
                if not self._eventQueueBeingPurged:
                    self._baseSeq += len(self._eventQueue)
                    self._eventQueue = []
                    self._lowestWindow = self._baseSeq
                    break
            time.sleep(0.01)

if __name__ == "__main__":
    import doctest
    doctest.testmod()
