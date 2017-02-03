# vim:fileencoding=UTF-8 
#
# Copyright © 2016 Stan Livitski
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
    Implements views that deliver events within Comety-enabled
    Django apps.
    
    TODOdoc <Extended description>

    Key elements
    ------------
    ViewWithEvents : Abstract view class that helps a Django_
        application process requests from clients polling the server
        for events.

[    See Also
    --------
    <python_name> : <Description of code named on this line
    and how it is related to the documented module.>
    ... ]

[    Notes
    -----
    <Additional information about the code, possibly including
    discussion of the algorithms. Follow it with a 'References'
    section if citing any references.>
]

[    Examples
    --------
    <In the doctest format, illustrate how to use this module.>
]
"""

import abc
import logging
import math
import numbers
import time
import comety

from importlib import import_module

from django.conf import settings
from django.contrib.sessions.backends.base import SessionBase
import django.core.cache
from django.core.serializers.json import DjangoJSONEncoder
from django.dispatch import Signal
from django.http.response import \
    JsonResponse, HttpResponseForbidden, HttpResponseServerError
from django.views.generic import View

class JSONEncoder(DjangoJSONEncoder):
    """
    A JSON encoder that knows how to sertalize
    `comety.Dispather.Event` objects.
    

[   Examples
    ----------------
    <In the doctest format, illustrate how to use this class.>
     ]
    """
    def default(self, obj):
        if isinstance(obj, comety.Dispatcher.Event):
            return (str(obj.sender), obj.kwargs)
        else:
            return super().default(obj)

class ViewWithEvents(View, metaclass=abc.ABCMeta):
    """
    Help a Django_ application serve 
    events to pages that update asynchronously.
    
    An abstract view with infrastructure for serving
    update events to Comety-enabled web pages. Implementations
    must provide at least the `dispatcherFor` method that
    locate a Comety dispatcher for a request. By default,
    this class allows only GET requests to its derived views.
    To enable other request types (e.g. POST for asynchronous
    push updates), change the ``http_method_names``
    attribute of the view object or a subclass.
    
    Parameters
    --------------------
    **kwargs : dict, optional
        Any properties to be set within the new view keyed by
        their names.

    Attributes
    -----------------
    cometyDispatcher : Dispatcher
        Comety dispatcher to be used with the current request,
        initialized by `dispatch`. Note that the dispatcher may
        still be called by the timeout handlers after this
        property is cleared or changed.
    RESPONSE_TIMEOUT_FACTOR : float
        The number between 0 and 1 multiplied by the maximum timeout
        stated by the client to compute the actual timeout that a
        request will be allowed to wait for new events on the queue.  
    HEARTBEAT_TIMEOUT : float
        The number of seconds that, after adjusting for the network
        delay, is entered in users' heartbeat timers.
    DELAY_HISTORY_VAR : str
        Name of the session variable used by `expectedDelay` method
        to store delay statistics.
    DELAY_SINCE_VAR : str
        Name of the session variable used by `measureDelay` method
        to store the delay measurement baseline.
    USER_TIMEOUT_SIGNAL : Signal
        A `django.dispatch.Signal` that is sent when a user's
        heartbeat times out. The arguments are Comety dispatcher that
        registered that user and the user's identity. The offending
        user is unregistered by the default handler after sending
        the signal unless any receiver returns a boolean equivalent
        of ``True`` not derived from Python’s `Exception` class.

    Methods
    ---------------
    cometyDispatcherFor(request, *args, **kwargs)
        Abstract method to locate the Comety dispatcher
        for a request.
    identifyUser(self, request, *args, **kwargs)
        Abstract method to determine user's identity from the request.
    dispatch(request, *args, **kwargs)
        Locate the Comety dispatcher and delegate further processing
        to the superclass.
    createHeartbeatHandler()
        Create a callback that handles user's inactivity timeout.
        Override to implement custom timeout handling.
    heartbeat(userId, callback, networkDelay)
        Set a timer to track the user's heartbeat, or stop
        an existing timer.
    fetchEvents(userId, lastSeqConfirmed, maximumTimeout, networkDelay)
        Adjust the timeout and fetch Comety events for a specific user.
    sessionKey(self, userIdString)
        Return the session key for a specific user.
    updateSessionKey(self, userIdString, session)
        Update the session key for a specific user.
    sessionByUser(self, userIdString)
        Retrieve the session object for a specific user.
    expectedDelay(session, latestDelay)
        Retrieve the expected network delay for this session and/or
        adjust it using the latest measured delay.
    measureDelay(self, session, reset)
        Begin or end network delay measurement for a session.
    get(self, request, *args, **kwargs):
        Handle the GET request to update a user on the Comety events.

    Raises
    ----------
    Exception
        If a property referenced by the constructor's keyword argument
        cannot be assigned, or cannot accept the passed value. 

[    See Also
    --------------
    <python_name> : <Description of code referred by this line
    and how it is related to the documented code.>
     ... ]

[    Notes
    ----------
    <Additional information about the code, possibly including
    a discussion of the algorithm. Follow it with a 'References'
    section if citing any references.>
    ]

[   Examples
    ----------------
    <In the doctest format, illustrate how to use this class.>
     ]
    """

    http_method_names = [ 'get' ]

    RESPONSE_TIMEOUT_FACTOR = 0.5
    HEARTBEAT_TIMEOUT = 10
    DELAY_HISTORY_VAR = 'comety.delay.history'
    DELAY_SINCE_VAR = 'comety.delay.since'
    USER_TIMEOUT_SIGNAL = Signal(providing_args = ['cometyDispatcher', 'userId'])
    SESSION_KEY_CACHE_ALIAS = 'default'
    SESSION_KEY_CACHE_PREFIX = locals()['__module__'] + '.sessions.byuserid.'
    SESSION_KEY_CACHE_EXPIRATION_MARGIN = lambda self, t: round(t / 10) if t > 50 else 5 

    @abc.abstractmethod
    def cometyDispatcherFor(self, request, *args, **kwargs):
        """
        Override this method to locate the Comety dispatcher for a request.
        
        Parameters
        ----------
        request : django.http.request.HttpRequest
            HTTP request served by this view.
        *args : list
            Optional positional arguments passed to the view.
        **kwargs : dict
            Optional keyword arguments passed to the view.
    
        Returns
        -------
        Dispatcher | None
            Comety dispatcher that will service this request or
            `None` if no dispatcher is available. Properly configured
            implementations should not return `None`.
    
        See Also
        --------    
        dispatch : Calls this method. You should not call it directly.
        cometyDispatcher : Receives the result of this call.
        """

        pass

    @abc.abstractmethod
    def identifyUser(self, request, *args, **kwargs):
        """
        Override this method to determine user's identity from the request.

        If this method returns ``None``, the default `get` request
        implementation will result in `HttpResponseForbidden`, since
        Comety updates can only be provided to known users.
        If an implementation uses identities of any other type than ``str``
        or ``int``, it will need to convert and update session keys as
        it processes requests to ensure the correct work of `sessionKey`.
        
        Parameters
        ----------
        request : django.http.request.HttpRequest
            HTTP request served by this view.
        *args : list
            Optional positional arguments passed to the view.
        ***kwargs : dict
            Optional keyword arguments passed to the view.
    
        Returns
        -------
        collections.Hashable | NoneType
            Identity of the user that sent the request or
            ``None`` if no valid user is associated with this
            session.
    
        See Also
        --------
        sessionKey : Returns the session key for a specific user. 
        dispatch : Calls this method when processing requests. 
        """
        pass

    def sessionKey(self, userIdString):
        """
        Return the session key for a specific user.
        
        Retrrieves the key of a session object mapped to a user's
        identity in the cache configured for this object or its class.
        
        Parameters
        ----------
        userIdString : str
            Identity of the user to look up, converted
            to a unique string.
    
        Returns
        -------
        str | NoneType
            The session key for that user or ``None`` if there
            is no mapping for ``userIdString`` in the cache.
    
        Raises
        ------
        TypeError
            If ``userIdString`` is not a string.
    
        See Also
        --------
        SESSION_KEY_CACHE_ALIAS : TODOdoc 
        SESSION_KEY_CACHE_PREFIX : TODOdoc 
    
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

        key = self.SESSION_KEY_CACHE_PREFIX + userIdString
        cache = django.core.cache.caches[self.SESSION_KEY_CACHE_ALIAS]
        try:
            return cache.get(key)
        finally:
            cache.close()

    def updateSessionKey(self, userIdString, session):
        """
        Update the session key for a specific user.
        
        Maps a user's identity to the key of a session object
        in the cache configured for this object or its class.
        A mapping will last until its session expires,
        plus `SESSION_KEY_CACHE_EXPIRATION_MARGIN`, but not shorter
        than `HEARTBEAT_TIMEOUT` ``* 10 / 3`` seconds. For sessions
        that expire on browser close, mappings will be
        cached forever.
        
        Parameters
        ----------
        userIdString : str
            Identity of the user that owns the session, converted
            to a unique string.
        session : SessionBase
            The session object to retrieve the key from.
    
        Raises
        ------
        TypeError
            If ``userIdString`` is not a string, or ``session`` is not
            a `SessionBase` object.
    
        See Also
        --------
        SESSION_KEY_CACHE_ALIAS : TODOdoc 
        SESSION_KEY_CACHE_EXPIRATION_MARGIN : TODOdoc 
        SESSION_KEY_CACHE_PREFIX : TODOdoc 
    
    [   Examples
        --------
        <In the doctest format, illustrate how to use this method.>
         ]
        """

        if not isinstance(session, SessionBase):
            raise TypeError(
                'Object of type %s is not a session'
                % type(session).__name__
            )
        key = self.SESSION_KEY_CACHE_PREFIX + userIdString
        session_key = session.session_key
        cache = django.core.cache.caches[self.SESSION_KEY_CACHE_ALIAS]
        try:
            expiry = None if session.get_expire_at_browser_close() \
                else session.get_expiry_age()
            if expiry is not None:
                expiry += self.SESSION_KEY_CACHE_EXPIRATION_MARGIN(expiry)
                lowLimit = math.ceil(self.HEARTBEAT_TIMEOUT * 10. / 3)
            cache.set(key, session_key, expiry if lowLimit < expiry else lowLimit)
        finally:
            cache.close()

    def sessionByUser(self, userIdString):
        """
        Retrieve the session object for a specific user.
        
        If the `sessionKey` method can find a session id
        for a user in its cache, this method retrieves a
        session object based on that key. Otherwise, it raises
        an error. If the session has expired and the mapping
        for `sessionKey` hasn't, returned session object will
        be empty.
        
        Parameters
        ----------
        userIdString : str
            Identity of the user to look up, converted
            to a unique string.
    
        Returns
        -------
        SessionBase
            The session object for that user.
    
        Raises
        ------
        TypeError
            If ``userIdString`` is not a string.
        KeyError
            If there is no mapping for ``userIdString`` in the cache.
    
        See Also
        --------    
        sessionKey : retrieves session id for the requested user
    
    [   Examples
        --------
        <In the doctest format, illustrate how to use this method.>
         ]
        """

        session_key = self.sessionKey(userIdString)
        if session_key is None:
            raise KeyError(
               'No mapping for user "%s" in the session id cache'
               % userIdString
            )
        SessionStore = import_module(settings.SESSION_ENGINE).SessionStore
        session = SessionStore(session_key = session_key)
        return session

    def dispatch(self, request, *args, **kwargs):
        """
        Locate the Comety dispatcher, determine the user identity,
        cache the user's session key, and delegate further processing
        to the superclass.

        This method will call `updateSessionKey` to cache the user's
        session key if, and only if, `identifyUser` returns an ``str``
        or an ``int`` value. With other types of user ids, you'll need
        to convert and update session keys as you process requests
        in a subclass. 
   
        See Also
        --------    
        cometyDispatcherFor : Called by this method to locate the
            Comety dispatcher.
        cometyDispatcher : Referencess the Comety dispatcher as the
            view does further processing.
        """

        self.cometyDispatcher = self.cometyDispatcherFor(request, *args, **kwargs)
        self._userId = self.identifyUser(request, *args, **kwargs)
        if type(self._userId) in (str, int):
            self.updateSessionKey(str(self._userId), request.session)
        return super().dispatch(request, *args, **kwargs)

    def createHeartbeatHandler(self):
        """
        Create a callback that handles user's inactivity timeout.

        This method is called in context of a `dispatch` operation
        and should store the value of `cometyDispatcher` attribute
        within a callback it returns. You should not call this method
        directly, except for test purposes. Note that when the timeout
        occurs, initial request had already been dispatched, and the
        `cometyDispatcher` reference may be different or empty.
    
        Returns
        -------
        collections.Callable | None
            A callback that handles user's inactivity timeout. This
            object must comply with the callback requirements in
            ``scheduleTimeout`` method of `comety.Dispatcher`.

        See Also
        --------    
        dispatch : Provides the context for this method's calls, usually
            by dispatching a request to more specific methods.
        cometyDispatcher : The Comety dispatcher relevant to the request
            that starts the timer.
        USER_TIMEOUT_SIGNAL : Sent by the default callback returned
            before un-registering the user.  
        """

        comety = self.cometyDispatcher
        def callback(userId):
            nonlocal comety, self
            responses = self.USER_TIMEOUT_SIGNAL.send_robust(
                type(self), cometyDispatcher = comety, userId = userId
            )
            cancel = False
            log = None
            for response in responses:
                if isinstance(response[1], Exception):
                    if log is None:
                        log = logging.getLogger(type(self).__module__)
                    exc_info = (
                        type(response[1]),
                        response[1],
                        response[1].__traceback__
                    )
                    log.warning(
                        'Handler %s encountered an error processing the'
                        + ' timeout of user "%s"', response[0], userId,
                        exc_info = exc_info
                    )
                elif response[1]:
                    cancel = True
            if not cancel:
                try:
                    comety.unregisterUser(userId)
                except:
                    if log is None:
                        log = logging.getLogger(type(self).__module__)
                    log.info('Could not unregister user "%s"', userId, exc_info=True)
        return callback if comety is not None else None
 
    def fetchEvents(self,
            userId, lastSeqConfirmed = None,
            maximumTimeout = None, networkDelay = 0):
        """
        Adjust the timeout and fetch Comety events for a specific user.
        
        Polls the `cometyDispatcher` associated with this view
        for new events destined to a specific user. This is done by
        delegating the call to the dispather's ``pollEvents`` method.
        Besides delegation, this method allows the caller to confirm
        receipt of prior event notifications and computes
        the timeout to be given to the dispatcher from the maximum
        given by the client and the expected network delay.  
        
        Parameters
        ----------
        userId : collections.Hashable
            Identity of the polling user.
        lastSeqConfirmed : int, optional
            Sequence number of the last event received and processed
            on behalf of the calling user. If omitted, no events are
            confirmed by this call.
        maximumTimeout : float | NoneType, optional
            The number of seconds the client is going to wait
            for an update. If ``None``, `fetchEvents` is
            allowed to wait for events indefinitely.
        networkDelay : float, optional
            The total number of seconds expected to be spent by the
            request and response en route through the network.
    
        Returns
        -------
        ( int, tuple | NoneType | bool )
            The value returned by ``pollEvents`` method of `comety.Dispatcher`.
    
        Raises
        ------
        ValueError
            If ``lastSeqConfirmed`` is negative ``maximumTimeout`` is
            negative, infinite, or NaN, or a `ValueError` is raised by the
            ``pollEvents`` method of `cometyDispatcher`.
        RuntimeError
            If `cometyDispatcher` is corrupt or missing.
        TypeError
            If ``networkDelay``, ``maximumTimeout``, or ``lastSeqConfirmed``
            are non-numberic objects.
    
        See Also
        --------    
        comety.Dispatcher : Defines the ``pollEvents`` method used
            here for delegation.   
        RESPONSE_TIMEOUT_FACTOR : float
            The number multiplied by the maximum timeout allowed by the
            client to compute the timeout supplied to the delegate.  
    
    [   Examples
        --------
        <In the doctest format, illustrate how to use this method.>
         ]
        """

        if self.cometyDispatcher is None:
            raise RuntimeError(
               'Comety dispatcher is not configured for this view')
        if lastSeqConfirmed is None:
            pass
        elif 0 > lastSeqConfirmed:
            raise ValueError(
               '"lastSeqConfirmed" is negative: %d' % lastSeqConfirmed)
        else:
            self.cometyDispatcher.confirmEvents(userId, lastSeqConfirmed)
        if maximumTimeout is None:
            timeout = None
        elif 0 > maximumTimeout or not math.isfinite(maximumTimeout):
            raise ValueError(
               '"maximumTimeout" must be a finite positive number or zero, got %g'
               % maximumTimeout
            )
        else:
            timeout = maximumTimeout * self.RESPONSE_TIMEOUT_FACTOR - networkDelay
            if 0 > timeout: timeout = 0
        return self.cometyDispatcher.pollEvents(userId, timeout)

    def heartbeat(self, userId, callback = None,
                  networkDelay = 5 * HEARTBEAT_TIMEOUT):
        """
        Set a timer to track the user's heartbeat, or stop
        an existing timer.
                
        Delegates calls to the dispather's ``scheduleTimeout``
        method to manage heartbeat timer for a specific user.
        The timeout duration is taken from this view's
        `HEARTBEAT_TIMEOUT` attribute and adjusted by adding
        the ``networkDelay`` parameter.
        
        Parameters
        ----------
        userId :  collections.Hashable
            Identity of the user to track.
        callback : collections.Callable | object | NoneType, optional
            An object that will be called when the timeout expires, or
            ``None`` to cancel any existing timer. The ``callback``
            object must comply with the callback requirements in
            ``scheduleTimeout`` method of `comety.Dispatcher`.
        networkDelay : float, optional
            The total number of seconds expected to be spent by the
            request and response en route through the network. Defaults
            to `5 * HEARTBEAT_TIMEOUT`, which multiplies the effective timeout
            by ``6`` when the actual delay has not yet been measured.
    
        Returns
        -------
        bool
            ``True`` if the user had an existing timer reset or canceled
            by this call, ``False`` otherwise.
    
        Raises
        ------
        ValueError
            If ``userId`` is not registered with the dispather,
            or had its registration revoked before the timer could be set.
        RuntimeError
            If `cometyDispatcher` is missing.
        TypeError
            If ``networkDelay`` is not a number, or ``callback`` is not
            callable.
    
        See Also
        --------
        createHeartbeatHandler : By default, this method is called to
            create the ``callback`` argument passed here.     
        HEARTBEAT_TIMEOUT : The number of seconds that, after adjusting
            for the network delay, users' heartbeat timers are set to.
    
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

        if self.cometyDispatcher is None:
            raise RuntimeError(
                'Comety dispatcher is not configured for this view')
        timeout = 0 if callback is None else (
            self.HEARTBEAT_TIMEOUT + networkDelay)
        result = self.cometyDispatcher.scheduleTimeout(
            userId, timeout, callback)
        if result is None:
            raise ValueError(
               'User with id "%s" is no longer registered' % userId)
        return result

    def expectedDelay(self, session, latestDelay = None):
        """
        Retrieve the expected network delay for this session and/or
        adjust it using the latest measured delay.
        
        This method should return a pessimistic estimate of network
        delay to be expected with request-response pairs belonging to
        a specific session. It should accumulate statistics within
        the session's data storage, update it with any recent delay
        measurements supplied, and must return the resulting estimate.
        When run with a new session and a recent delay
        measurement, it shall return a value equal or greater than
        that measurement. When run with a new session and no recent
        delay measurement, it shall return a default delay constant. 
        
        Parameters
        ----------
        session : backends.base.SessionBase
            Session storage for network delay statistics.
        latestDelay : float, optional
            The most recent measured delay for this session in seconds,
            if available. 
    
        Returns
        -------
        float
            Expected network delay for this session, in seconds.
            This value cannot be negative.
    
        Raisesses
        ------
        TypeError
            If ``latestDelay`` is present and isn't a number.
    
        See Also
        --------    
        DELAY_HISTORY_VAR : Name of the session variable used
            by this method to store delay statistics.
    
        Notes
        -----
        The default implementation stores 6 most recent delay
        measurements in the session and returns the 2nd largest
        item stored. When called without any stored data and any
        measurements, it returns ``0``. When called with fewer than
        6 total measurements, stored or supplied, it returns the
        largest known item.   
    
    [   Examples
        --------
        <In the doctest format, illustrate how to use this method.>
         ]
        """

        if latestDelay is not None and not isinstance(latestDelay, numbers.Number):
            raise TypeError(
               'latestDelay must be a number, got: %s'
               % type(latestDelay).__name__
            )
        history = session.get(self.DELAY_HISTORY_VAR)
        if history is None:
            history = []
            session[self.DELAY_HISTORY_VAR] = history
        delay = None
        if latestDelay is not None:
            history.append(latestDelay)
            session.modified = True
        if len(history) == 0:
            delay = 0
        elif len(history) > 6:
            del history[0]
            session.modified = True
        elif len(history) < 6:
            delay = max(history)
        if delay is None:
            delay = sorted(history, reverse = True)[1]
        return delay

    @classmethod
    def measureDelay(cls, session, reset = False):
        """
        Begin or end a network delay measurement for a session.
        
        This method works like a stopwatch that uses a Django session
        to store the measurement baseline. First, you call it with
        a ``reset`` argument equal to ``True``, usually at the end of
        an HTTP request processing, to create a measurement baseline
        (start the stopwatch). Then you call it without a ``reset``
        argument to obtain the delay measurement (read the stopwatch).
        This usually happens early during the processing of a subsequent
        HTTP request. Then you can repeat the measurement by setting
        a new baseline, or obtain more measurements with an existing
        baseline.
        
        Parameters
        ----------
        session : backends.base.SessionBase
            Session storage for network delay statistics.
        reset : bool, optional
            A flag to reset the measurement to the current time.
            When ``True``, this method establishes a baseline for
            the delay measurement. When ``False`` or omitted, this
            method returns the time elapsed since the most recent
            baseline. 
    
        Returns
        -------
        float | NoneType
            The time elapsed since the most recent baseline established
            by this method, or ``None`` if there were no baseline, or
            the ``reset`` argument was ``True``.
    
        See Also
        --------    
        DELAY_SINCE_VAR : Name of the session variable used
            by this method to store baseline for the delay measurement.
    
    [   Examples
        --------
        <In the doctest format, illustrate how to use this method.>
         ]
        """

        if reset:
            session[cls.DELAY_SINCE_VAR] = time.time()
        elif cls.DELAY_SINCE_VAR in session:
            delay = time.time() - session[cls.DELAY_SINCE_VAR]
            return delay
        return None

    def get(self, request, *args, **kwargs):
        """
        Handle the GET request to update a user on the Comety events.

        Default implementation of a GET request to the Comety update
        view: takes the delay measurement, if there is a baseline;
        determines user id from the session; stops the user's heartbeat
        timer, if any; updates her event window if a confirmation is
        received; obtains new events from the queue; and re-starts
        the user's heartbeat timer. If any of the above methods
        that is allowed to raise exceptions raises an exception,
        while processing a request here, that exception is logged
        as an error within this module.
        
        Request parameters
        ------------------
        request.GET['timeout'] : str(float)
            The maximum timeout the client will wait, in seconds.
        request.GET['confirm'] : str(int), optional
            The serial number of last event confirmed by the
            client.
        request.GET['elapsed'] : str(float), optional
            The time elapsed on client while processing page or
            script that sent this request.

        Returns
        -------
        JsonResponse | HttpResponseForbidden | HttpResponseServerError
            On success, the result is a `django.http.JsonResponse` with
            keys 'lastId', and 'events' containing the sequence number of
            the last retrieved event, and the retrieved events, if any, or
            the sequence number of the first expected event minus ``1`` and
            a ``null`` value, if none.
            On failure, the response reflects the type of failure.
        """

        if self.cometyDispatcher is None:
            log = logging.getLogger(type(self).__module__)
            log.critical('Cannot send updates - Comety dispatcher is not configured')
            return HttpResponseServerError()
        measuredDelay = self.measureDelay(request.session)
        expectedDelay = 0
        if self._userId is None:
            log = logging.getLogger(type(self).__module__)
            log.warning(
                'Received an update request from unauthorized or expired session'
            )
            return HttpResponseForbidden()
        try:
            self.heartbeat(self._userId)
            maxTimeout = float(request.GET['timeout'])
            confirm = request.GET.get('confirm')
            if confirm is not None:
                confirm = int(confirm)
            if measuredDelay is not None:
                elapsed = request.GET.get('elapsed')
                if elapsed is None:
                    pass
                else:
                    elapsed = float(elapsed)
                    if 0 > elapsed or not math.isfinite(elapsed):
                        log = logging.getLogger(type(self).__module__)
                        log.warning(
                            'Query parameter "elapsed" = %g is negative or undefined',
                            elapsed
                        )
                    else:
                        measuredDelay -= float(elapsed)
                        if 0 > measuredDelay:
                            log = logging.getLogger(type(self).__module__)
                            log.warning(
                                'Query parameter "elapsed" = %g is larger than measured delay of %g',
                                elapsed, measuredDelay + elapsed
                            )
                            measuredDelay = 0
                expectedDelay = self.expectedDelay(request.session, measuredDelay)
            events = self.fetchEvents(self._userId, confirm, maxTimeout, expectedDelay)
            return JsonResponse(
                {
                    'lastId': events[0],
                    'events': events[1] if events[1] else None  
                },
                encoder=JSONEncoder
            )
        except:
            log = logging.getLogger(type(self).__module__)
            log.error('Error serving Comety updates to user "%s"',
                      self._userId, exc_info=True)
            return HttpResponseServerError()
        finally:
            try:
                callback = self.createHeartbeatHandler()
                self.heartbeat(self._userId, callback, expectedDelay)
            except:
                log = logging.getLogger(type(self).__module__)
                log.error(
                    'Error setting up heartbeat timer for user "%s" with handler %s',
                    self._userId,
                    None if callback is None else callback.__name__, exc_info=True)
            finally:
                self.measureDelay(request.session, True)
