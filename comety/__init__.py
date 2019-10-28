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
    MultiTimer : Reusable timer with an internal thread that runs
        user-supplied tasks no sooner than their scheduled times.
    django : Elements of the Comety toolkit that depend on the
        Django_ framework.

    .. _Comet: https://en.wikipedia.org/wiki/Comet_%28programming%29
    .. _Django: https://www.djangoproject.com
"""

import version

version.requirePythonVersion(3, 3)

import collections
from numbers import Number
import math
import threading
import time
from sched import scheduler
import sys

class MultiTimer:
    """
    Reusable timer with an internal thread that runs
    user-supplied tasks no sooner than their scheduled times.

    Maintains a thread that runs callables with optional
    arguments no sooner then a certain time after they are
    scheduled. The thread and scheduler are created with this
    object and live until it is `shutdown`, usually along
    with the host application. 

    Attributes
    ----------
    Task
    
    Methods
    -------
    start(delay, action)
        Start a new timer and allow the caller to further query
        or cancel it.
    shutdown(graceful)
        Run all scheduled tasks now, if ``graceful`` flag is set,
        then stop the internal thread and dispose of objects used to
        implement this timer.

    Examples
    ----------------
    >>> import time
    >>> t=MultiTimer()
    >>> started=time.time()
    >>> def ptime():
    ...  t = time.time()
    ...  print('ptime')
    ...  return t - started
    >>> task = t.start(.5, ptime)
    >>> task.status
    'pending'
    >>> time.sleep(.6)
    ptime
    >>> task.status
    'done'
    >>> type(task.result)
    <class 'float'>
    >>> task.result >= .5
    True
    >>> t.shutdown(False, .01)
    """

    def __init__(self):
        self._monitor = threading.Condition(threading.RLock())
        self._shutdown = None
        self._scheduler = scheduler(delayfunc = lambda s: None)
        def schedulerThread():
            nonlocal self
            with self._monitor:
                while self._shutdown is None:
                    wait = None
                    if not self._scheduler.empty():
                        wait = self._scheduler.run(blocking = False)
                    if self._shutdown is None:
                        self._monitor.wait(wait)
                if self._shutdown:
                    queue = self._scheduler.queue
                    self._monitor.release()
                    for pending in queue:
                        action, args, kwargs = pending[2:]
                        try:
                            action(*args, **kwargs)
                        except:
                            pass
                        if not self._shutdown:
                            break
                    self._monitor.acquire()
                    self._thread = self._monitor = self._scheduler = None
            # Releasing former self._monitor and exiting schedulerThread
        self._thread = threading.Thread(
            target=schedulerThread,
            name=type(self).__name__
        )
        self._thread.daemon = True
        self._thread.start()

    def _cancel(self, task):
        with self._monitor:
            if 'pending' != task.status:
                return
            elif self._shutdown is not None:
                raise MultiTimer.ShutdownError(
                    'Cannot cancel task: the timer is shutting down')
            self._scheduler.cancel(task._event)
            task.status = 'aborted'
            self._monitor.notify()

    def start(self, delay, action):
        """
        Start a new timer and allow the caller to further query
        or cancel it.
        
        All scheduled actions run in the same thread, and the timer
        object is locked while they run. Thus, they are expected to
        finish quickly. They may schedule or cancel other tasks
        with this timer as long as they are doing that in the
        same thread. However, an action attempting to schedule or
        cancel tasks during the timer's shutdown will raise a
        `MultiTimer.ShutdownError`, and is expected to handle it.
        
        Parameters
        ----------
        action : collections.Callable | object | tuple, optional
            Function or object that will be called when the delay time
            runs out. This may also be a collection with elements
            (callable, args, kwargs) if the action requires running a
            function with arguments. Last element of the collection
            may be omitted.
    
        Returns
        -------
        MultiTimer.Task
            A handle for querying or canceling the new task.
    
        Raises
        ------
        TypeError
            If the supplied `action` object, or its first element,
            is not callable.
        MultiTimer.ShutdownError
            If the host timer is being shut down.        
    
        Examples
        --------
        >>> import time
        >>> t=MultiTimer()
        >>> class foo:
        ...  def __call__(self, what = 'response'):
        ...    if isinstance(what, BaseException):
        ...        raise what
        ...    else:
        ...        return what
        >>> foo = foo()
        >>> tasks = (t.start(.1, foo),
        ...        t.start(.3, [ foo, (Exception('just testing'),) ]),
        ...        t.start(.5, ( foo, [], { 'what': 11 })),
        ...        t.start(1, foo)
        ...        )
        >>> any(task.status != 'pending' for task in tasks)
        False
        >>> time.sleep(.2)
        >>> [ task.status for task in tasks ]
        ['done', 'pending', 'pending', 'pending']
        >>> tasks[0].result
        'response'
        >>> time.sleep(.2)
        >>> [ task.status for task in tasks ]
        ['done', 'aborted', 'pending', 'pending']
        >>> tasks[1].result
        Exception('just testing',)
        >>> time.sleep(.2)
        >>> [ task.status for task in tasks ]
        ['done', 'aborted', 'done', 'pending']
        >>> tasks[2].result
        11
        >>> tasks[3].cancel()
        >>> [ task.status for task in tasks ]
        ['done', 'aborted', 'done', 'aborted']
        >>> tasks[3].result is None
        True
        >>> t.shutdown()
        """
        with self._monitor:
            if self._shutdown is not None:
                raise MultiTimer.ShutdownError(
                    'Cannot schedule task: the timer is shutting down')
            task = self.Task(self, delay, action)
            self._monitor.notify()
            return task
           

    def shutdown(self, graceful = True, timeout = None):
        """
        Stop the internal thread and dispose of objects used to
        implement this timer.
        
        If ``graceful`` flag is set, runs all scheduled tasks
        immediately before releasing resources. This method may
        be called from the internal thread (i.e. by one of the
        scheduled actions), in which case it either returns
        immediately after switching the timer into the shutdown
        mode, or calls `sys.exit` to interrupt the current task.
        
        Parameters
        ----------
        graceful : boolean, optional
            Requests a graceful shutdown, which means all tasks
            scheduled for the future are run as soon as the
            internal thread becomes available, in the order they
            were scheduled, but without waiting for their designated
            times. Tasks cannot be scheduled or canceled during
            shutdown. Defaults to ``True``.
        timeout : float, optional
            Timeout for the operation in seconds. This includes
            the time needed to run remaining tasks as part of a
            graceful shutdown. If omitted or ``None``, the operation
            will block until the internal thread terminates. If
            the timeout expires during shutdown, `MultiTimer.ShutdownError`
            is raised. Ignored when method is called from the
            internal thread of this timer.
    
        Raises
        ------
        TypeError
            If ``None`` is passed as the argument.
        ShutdownError
            If the timeout was specified and expired before shutdown
            completed. You can re-try calling this method with or without
            a timeout after catching this error.
    
        See Also
        --------    
        ShutdownError : Sent to an action that attempts to modify the
         task queue during shutdown.
    
        Examples
        ----------------
        >>> import threading
        >>> import time
        >>> threads = threading.active_count()
        >>> t=MultiTimer()
        >>> threading.active_count() - threads
        1
        >>> t.shutdown(None)
        Traceback (most recent call last):
        ...
        TypeError: None is not allowed here.
        >>> t.shutdown(False, .1)
        >>> threading.active_count() - threads
        0
        >>> t=MultiTimer()
        >>> threading.active_count() - threads
        1
        >>> task = t.start(.3, (time.sleep, (.5,)))
        >>> task.status
        'pending'
        >>> t.shutdown(True, .1)
        Traceback (most recent call last):
        ...
        MultiTimer.ShutdownError: Shutdown timed out
        >>> task.status
        'running'
        >>> t.shutdown(False, .1)
        Traceback (most recent call last):
        ...
        MultiTimer.ShutdownError: Shutdown timed out
        >>> t.shutdown(False, .4)
        >>> task.status
        'done'
        >>> threading.active_count() - threads
        0
        >>> def doo(wait, action, *args):
        ...  time.sleep(wait)
        ...  return action(*args)
        >>> t=MultiTimer()
        >>> threading.active_count() - threads
        1
        >>> tasks = (t.start(.3, (doo, (.1, print, 'slept .2 sec'))),
        ...            t.start(0, (doo, (.1, t.shutdown, True, 3))),
        ...            t.start(.2, (t.shutdown, (False, 5))))
        >>> tasks[0].status
        'pending'
        >>> tasks[2].status
        'pending'
        >>> time.sleep(.15)
        >>> [ task.status for task in tasks ]
        ['pending', 'done', 'aborted']
        >>> threading.active_count() - threads
        0
        >>> [ type(task.result).__name__ for task in tasks ]
        ['NoneType', 'NoneType', 'SystemExit']
        """
        if graceful is None:
            raise TypeError('None is not allowed here.')
        with self._monitor:
            if self._shutdown is None:
                self._shutdown = graceful
                self._monitor.notify()
        if self._thread is threading.current_thread():
            with self._monitor:
                self._shutdown = self._shutdown and graceful
                if not self._shutdown:
                    sys.exit(-1) 
        elif self._thread is not None:
            self._thread.join(timeout)
            if self._thread and self._thread.is_alive():
                raise MultiTimer.ShutdownError('Shutdown timed out')

    class ShutdownError(RuntimeError):
        """
        Raised when the caller attempts to modify the
        task queue during timer shutdown.
        """

    class Task:
        """
        A handle for querying or canceling scheduled tasks.
        
        You shouldn't create these objects directly,
        but obtain them from a `MultiTimer` object instead.
        Neither should you call these objects, as `MultiTimer`
        will do that for you. The attributes provide information
        about a task and shouldn't be modified externally.
        The ``cancel()`` method cancels a pending task. 
        
        Attributes
        ----------
        action : tuple
            A tuple with elements (callable, args, kwargs) describing 
            the scheduled action and its arguments.
        time : float
            The time for which the action was scheduled in units of the
            default `sched.scheduler` ``timefunc`` function's return value.
        status : ``'pending'`` | ``'running'`` | ``'done'`` | ``'aborted'``
            The status of this task.
        result : object | BaseException | NoneType 
            The return value of this task's action if the task is in the
            ``'done'`` status; any exception that action raised if the task
            is ``'aborted'``; or ``None`` if the task is ``'pending'``
            or ``'running'``.
    
        Methods
        -------
        cancel()
            Cancel the pending task.
    
        See Also
        --------------
        MultiTimer.start : Schedules a task in the timer thread and
         returns an object of this type.
        """

        def __init__(self, timer, delay, action):
            if not isinstance(action, collections.Collection):
                action = (action, (), {})
            if not 1 < len(action) <= 3:
                raise ValueError('Action tuple has unsupported'
                                 ' element count %d' % len(action))
            elif len(action) < 3:
                action = tuple(action) + ({},)
            if not callable(action[0]):
                raise TypeError('type "%s" is not callable' % type(action[0]).__name__)
            elif not isinstance(action, tuple):
                action = tuple(action)
            self._action = action
            self.status = 'pending'
            self.result = None
            self._timer = timer
            self._event = timer._scheduler.enter(delay, 0, self)

        def cancel(self):
            """
            Cancel the pending task. The task transitions into the
            ``'aborted'`` status, while its result remains ``None``.
            The call has no effect if the task is not ``'pending'``.

            Raises
            ------
            MultiTimer.ShutdownError
                If the host timer is being shut down.        
            """
            self._timer._cancel(self)

        def __call__(self):
            assert self.status == 'pending'
            self.status = 'running'
            try:
                action, args, kwargs = self._action
                self.result = action(*args, **kwargs)
            except:
                self.status = 'aborted'
                self.result = sys.exc_info()[1]
            else:
                self.status = 'done'

        @property
        def time(self):
            return self._event.time

        @property
        def action(self):
            return self._action

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

    Attributes
    ----------
    timer
    [
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

        JSON representation of the objects of this type seen by
        the web clients is an array of two elements: the ``sender_``
        object and ``kwargs``.
        
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
    
        Methods
        ---------------
        arg(name)
            retrieves values of arguments provided when the event occurred
    
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

        # TODO: make objects of this class immutable
        # TODO: add positional arguments here and in `arg()`
        def __init__(self, sender_, **kwargs_):
            self.sender = sender_
            self.kwargs = kwargs_

        def _json_data_(self):
            sender = self.sender
            str_num = lambda arg: None if arg is None else (
                        arg.real if isinstance(arg, Number) else str(arg))
            if isinstance(sender, collections.Mapping):
                sender = dict((k, str_num(sender[k])) for k in sender)
            elif isinstance(sender, collections.Iterable):
                sender = tuple(str_num(k) for k in sender)
            else:
                sender = str_num(sender)
            return (sender, self.kwargs)

        def arg(self, name):
            """
            Retrieve value of an argument stored when the event occurred.

            Objects of this class can have named arguments passed
            to their constructors as additional information about an event,
            retrievable by this method.
           
            Parameters
            ----------
            name : str
                The name of an argument to read.
       
            Returns
            -------
            object | None
                The argument's value, or ``None`` if the named
                argument is missing.

            See Also
            --------    
            kwargs : a dictionary with arguments retrievable by this
             method
            """

            return self.kwargs.get(name)

    def __init__(self, timer = None):
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
        self._timer = MultiTimer() if timer is None else timer
        self._sharedTimer = timer is not None

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

    @property
    def timer(self):
        """
        A `MultiTimer` object used to schedule users' timeouts
        and perform maintenance.
        """
        return self._timer

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
        """

        badId = userId in self._userEntries
        if not badId:
            entry = [ None, None ]
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
            if entry[1]:
                entry[1].cancel()

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
        """

        event = self.Event(sender_, **kwargs)
        seq = None
        with self._accessGuard:
            if self._userEntries:
                seq = self._baseSeq + len(self._eventQueue)  
                self._eventQueue.append(event)
                self._accessGuard.notify_all()
        return seq

    def pollEvents(self, userId, timeout = None,
                    eventFilter = None, immutableFilter = False):
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
        eventFilter : collections.Callable | object, optional
            A function, or other callable object, that is applied
            to events on the queue to determine whether an event
            should be included in the result. If ``eventFilter(event)``
            returns True, ``event`` is retuned, otherwise it is omitted.
        immutableFilter : bool, optional
            Set this to ``True`` to allow `pollEvents` to confirm events
            at the head of the queue that did not pass ``eventFilter``.
            Use this flag to optimize `pollEvents` loop and subsequent
            calls **ONLY IF** the user calls this method with the same
            ``eventFilter`` at all times. If ``eventFilter``, or its output
            for the same inputs, may change from one call to the other
            and this flag is set, some relevant events may be lost. This
            flag is ignored when ``eventFilter`` is absent. When
            ``eventFilter`` is present and this flag is not ``True``, the
            caller must pass a ``timeout`` value should confirm events
            it receives on a regular basis to avoid performance
            degradation.
            
    
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
        events with strictly ascending sequence numbers. There will
        be no gaps in the sequence if there is no ``eventFilter`` passed,
        or the filter function rejects no events.
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
        while True:
            startTime = time.perf_counter()
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
            if eventFilter is None:
                return lastSeq, tuple(events[firstIndex:(lastIndex + 1)])
            else:
                filtered = tuple(filter(eventFilter, events[firstIndex:(lastIndex + 1)]))
                if not filtered:
                    # none of the events matched
                    if immutableFilter and firstIndex <= lastIndex:
                        self.confirmEvents(userId, lastSeq) # autoconfirm if enabled
                    if timeout is None: # retry unless timed out
                        continue
                    else: # update timeout before retrying to avoid excess wait
                        elapsed = time.perf_counter() - startTime
                        timeout -= elapsed
                        if 0 < timeout:
                            continue
                return lastSeq, filtered

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
        timer : shared facility for scheduling users' timeouts 
    
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
                task = None if userEntry is None else userEntry[1]
        if userEntry is None:
            if callback is None:
                return None
            else:
                raise ValueError('User with id "%s" is not registered' % userId)
        status = None
        if not task:
            status = False
        else:
            if 'pending' == task.status:
                task.cancel()
                userEntry[1] = None
                status = True
            elif 'aborted' == task.status and task.result is None:
                # The timer has been concurrently discarded,
                # which means that user is no longer registered
                callback = None
            else:
                status = False
        if callback is not None:
            userEntry[1] = self.timer.start(timeout, (callback, (userId,))) 
        return status

    def discard(self):
        """
        Dispose of the dispatcher when it's no longer needed.
        
        Releases resources, such as timer threads, used by this
        dispatcher. This has a side effect of un-registering all
        known users and clearing the queue. You should not use
        this object after it's been discarded. Repeat calls of this
        method have no effect.
        """

        while True:
            with self._accessGuard:
                while self._userEntries:
                    entry = self._userEntries.popitem()
                    if entry[1][1]:
                        assert isinstance(entry[1][1], MultiTimer.Task)                    
                        entry[1][1].cancel()
                if not self._eventQueueBeingPurged:
                    self._baseSeq += len(self._eventQueue)
                    self._eventQueue = []
                    self._lowestWindow = self._baseSeq
                    break
            time.sleep(0.01)
        if not self._sharedTimer:
            self._timer.shutdown()

class FilterByTargetUser:
    """
    A filter for use with `Dispatcher.pollEvents` to retrieve events
    targeted to a specific user.

    Users calling `pollEvents` with this filter containing their own
    id at all times may apply the ``

    Parameters
    --------------------
    userId : collections.Hashable
        Identity of the target user.
    strictMatch : boolean, optional
        Pass ``True`` to filter out `Event` objects that have no property
        with name from `TARGET_USERS_KEY`, or have that property set to ``None``.
        Defaults to ``False``, which enables all users
        to receive such events.

    Attributes
    -----------------
    TARGET_USERS_KEY : str
        The name of a property within `Event` objects that contains
        one or more ids of the target user(s). The property can be ``None``
        or missing, in which case an `Event` is treated according to the
        ``strictMatch`` parameter. It may also contain a single user id,
        or zero or more user ids wrapped in a `collections.Sequence`.

    Methods
    ---------------
    __call__(event)
        Used by a `Dispatcher` to pass event objects to be filtered.

    See Also
    --------------
    Dispatcher : instances of this class can be passed as the
     ``eventFilter`` argument to ``pollEvents`` method thereof.
    Event : objects that are filtered by this class

    Examples
    ----------------
    >>> dispatcher = Dispatcher()
    >>> type(dispatcher.registerUser('boo'))
    <class 'int'>
    >>> type(dispatcher.registerUser('hoo'))
    <class 'int'>
    >>> lenientFilter = FilterByTargetUser('boo')
    >>> strictFilter = FilterByTargetUser('hoo', strictMatch=True)
    >>> booEventId = dispatcher.postEvent('hoo', event='message', text='hello', targetUsers='boo')
    >>> hooEventId = dispatcher.postEvent('boo', event='message', text='hi', targetUsers='hoo')
    >>> bothEventId = dispatcher.postEvent('boo', event='message', text='hi all', targetUsers=('boo','hoo'))
    >>> ignoreEventId = dispatcher.postEvent('boo', event='message', text='get lost', targetUsers=[])
    >>> events = dispatcher.pollEvents('boo', 0, lenientFilter)
    >>> len(events[1])
    4
    >>> max(booEventId, bothEventId) <= events[0]
    True
    >>> any(event.arg('text') == 'hello' for event in events[1])
    True
    >>> any(event.arg('text') == 'hi all' for event in events[1])
    True
    >>> any(event.arg('text') == 'get lost' for event in events[1])
    False
    >>> dispatcher.confirmEvents('boo', events[0])
    >>> events = dispatcher.pollEvents('hoo', 0, strictFilter)
    >>> len(events[1])
    2
    >>> max(hooEventId, bothEventId) <= events[0]
    True
    >>> any(event.arg('text') == 'hi' for event in events[1])
    True
    >>> any(event.arg('text') == 'hi all' for event in events[1])
    True
    >>> any(event.arg('text') == 'get lost' for event in events[1])
    False
    >>> dispatcher.confirmEvents('hoo', events[0])
    >>> dispatcher.discard()
    """

    TARGET_USERS_KEY = 'targetUsers'

    def __init__(self, userId, strictMatch = False):
        self._userId = userId
        self._targetPropertyMissing = not strictMatch

    def __call__(self, event):
        targetUsers = event.arg(self.TARGET_USERS_KEY)
        if targetUsers is None:
            return self._targetPropertyMissing
        elif isinstance(targetUsers, collections.Sequence):
            return self._userId in targetUsers
        else:
            return self._userId == targetUsers

if __name__ == "__main__":
    import doctest
    doctest.testmod()
