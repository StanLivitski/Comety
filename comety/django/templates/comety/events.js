{% comment %}
===========================================================================
 Copyright 2016, 2017 Stan Livitski

 This file is part of Comety. Comety is
 Licensed under the Apache License, Version 2.0 with modifications,
 (the "License"); you may not use this file except in compliance
 with the License. You may obtain a copy of the License at

  https://raw.githubusercontent.com/StanLivitski/Comety/master/LICENSE

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
===========================================================================
{% endcomment %}
{% comment %}

Django template with client-side Comety helper script
=====================================================

This template may be embedded in a <script> element of a Comety
page, or used as a standalone "text/javascript" resource. In both
cases, it is best to place the script within the page's <head>
before any elements that may change in response to the Comety
events. You should also include or link jQuery_ 1.11 or newer
on your page before the Comety API scripts.

Before rendering a Comety page, you should confirm the receipt of
all events that updated that page, unless the rendering is done for
a user that just registered. That will help you avoid superfluous
changes to rendered elements. 

This template accepts the following parameters passed via its context:

renderAPI
		A boolean switch that requests this template to render
		Comety's API scripts. Comety's API **must** be
		rendered in the global scope of a web page's JavaScript.
		Turn it off if the scripts are already linked or embedded
		on your page. Defaults to ``True``.

.. _renderTiming :
renderTiming :
		A boolean switch that requests this template to render
		the script that takes the current timestamp and stores
		it in the API object. The page should do this as early
		as possible, before loading any external resources. When
		the code is rendered more than once on the same page,
		the first instance does the work, and the others are
		skipped. If your page does any substantial
		processing, such as loading external resources, before
		this code is run, you should adjust the value of
		``_updateTimestamp`` property of the API object to ensure
		accurate measurement of network delays by Comety.
		Defaults to ``True``.

.. _autoStart:
autoStart
		A boolean switch that requests this template to render
		the script that starts receiving Comety notifications
		automatically when the page is done loading, using the
		default configuration, and stops the notification loop
		before the page unloads. Turn this on if your page uses
		the default configuration of such notifications. You may
		customize the updates loop by changing the ``defaults``
		object or its contents before the page's DOM is rendered.
		If your page uses a ``beforeunload`` event handler that
		may cancel the event, that handler should check whether
		the update loop has been stopped and restart it if the
		user chooses to stay on the page.
		Defaults to ``False``.
			  
.. _APIvar:
APIvar
		Name of the client-side variable that will expose the
		Comety's API. Defaults to ``comety``.

jQueryVar
		Name of the client-side object that exposes the
		jQuery API used by Comety. Defaults to ``jQuery``.

The API rendered by this template exposes the following key elements
as properties of the API object (see APIvar_ above):

.. _startUpdates:
startUpdates(settings)
		Starts the loop that will notify this page of Comety
		events. Call this function when the page has done loading,
		unless autoStart_ is enabled for this template. You can
		also call this function to change settings within the active
		notifications' loop, however the new settings will not apply
		to any request for updates in progress. The settings along
		with their names are documented as the default_ object's
		properties below. Any setting can be undefined, which causes
		Comety to use an old value, if any, or the default otherwise,
		for the respective loop parameter. This function may be called
		within any of its handlers. When called from errorHandler_, it
		restarts the update loop once the error is handled.
	
stopUpdates()
		Stops the loop that notifies this page of Comety events,
		if such loop is running, otherwise does nothing. This
		function may be called within a handler that is passed to
		startUpdates_. Note, however, that the loop stops
		automatically once handler_ returns 0 or before
		errorHandler_ is called.

.. _defaults:
defaults.url
		The URL to be queried for the update events. This should be
		a relative URL to avoid issues with cross-domain requests.
		The default is "updates".

defaults.timeout
		Default timeout value to be used in AJAX requests sent by the
		Comety event loop. This value is used unless startUpdates_
		receives a different one as the argument. Timeout values
		here and in startUpdates_ are expressed in seconds and
		fractions thereof, as floating-point numbers. The default is
		10 seconds.

.. _handler:
defaults.handler(events, loopParams)
		Function that receives Comety event notifications, unless
		startUpdates_ receives a different handler as the argument.
		Receives the array of events that haven't been handled yet
		and the object with startUpdates_ parameters having
		the same keys as the parent defaults_ property.
		Returns the number of event notifications consumed by the
		handler. This must be a non-negative integer not exceeding
		the number of events passed. If the handler returns 0,
		the notifications' loop stops to avoid endless looping.
		Default implementation reloads the current page using a
		GET request and returns 0.

.. _errorHandler:
defaults.errorHandler(jqXHR, textStatus, errorThrown, loopParams)
		Function that is called in response to AJAX errors in
		the Comety event retrieval loop. Besides the arguments from
		the error handler spec from the ``jQuery.ajax()`` API, the
		object with startUpdates_ parameters having a subset of 
		keys from the parent defaults_ property is also passed.
		No return value is expected. The notifications' loop
		stops automatically when errorHandler_ is called. To restart
		it after handling the error, call startUpdates_ from the
		handler. Default implementation alerts the user of the error
		with information from textStatus and errorThrown, if any.

.. _jQuery: https://jquery.com/
{% endcomment %}{% if renderTiming|default_if_none:True %}{% comment %}
{% endcomment %}{% with api=APIvar|default:"comety" %}
	var {{api}};
	if ({{api}} === undefined)
		{{api}} = {};
	if ({{api}}._updateTimestamp == null)
		{{api}}._updateTimestamp = (new Date()).getTime();
{% endwith %}{% endif %}
{% if renderAPI|default_if_none:True %}{% comment %}
{% endcomment %}{% with api=APIvar|default:"comety" jq=jQueryVar|default:"jQuery" %}
	var {{api}};
	if ({{api}} === undefined)
		{{api}} = { _lastReceivedId: null };{% comment %}
		// Do not assign any values here, except null and undefined
		{% endcomment %} 
	if (typeof {{api}} != 'object')
		throw 'Comety API variable "{{api}}" already has a non-object value: ' + {{api}};
	if ({{api}}.defaults !== undefined)
		throw 'Comety API variable "{{api}}" already has the "defaults" property: ' + {{api}}.defaults;
	{{api}}.defaults = {
		url: "updates",
		timeout: 10,
		handler: function(events, loopParams)
		{
			location.replace(location);
			return 0;
		},
		errorHandler: function(jqXHR, textStatus, errorThrown, loopParams)
		{
			var suffix = textStatus == 'parsererror' ?
					'parsing page updates'
					: 'querying server for page updates';
			var message = null == errorThrown ? 'Unknown error'
					: errorThrown.toString();
			var ERROR_SUFFIX = ' error';
			if (ERROR_SUFFIX !=
					message.trim().toLowerCase().split(-ERROR_SUFFIX.length))
				message += ERROR_SUFFIX;
			alert(message + ' ' + suffix);
		}
	};
	if ({{api}}._loop !== undefined)
		throw 'Comety API variable "{{api}}" already has the "_loop" property: ' + {{api}}._loop;
	{{api}}._loop = function()
	{
		this._runningLoop = true;
		var timeout = this._updateParams.timeout
		if (undefined === timeout)
			timeout = this.defaults.timeout;
		var url = this._updateParams.url
		if (undefined === url)
			url = this.defaults.url;
		var ajax = {
			cache: false,
			context: this,
			data:
			{
				timeout: timeout
			},
			dataType: 'json',
			complete: function()
			{
				delete {{api}}._jqXHR;
				if (this._runningLoop)
					setTimeout(function() { {{api}}._loop(); })
			},
			dataFilter: function(data, type)
			{
				data = data.trim();
				if (data.charAt(0) != '{')
				{
					if ('console' in window && 'error' in window.console)
						console.error(
							'Unexpected AJAX response type for a(n) '
							+ type + ' URL'
						);
					return '{}';
				}
				else
					return data;
			},
			error: function(jqXHR, textStatus, errorThrown)
			{
				if (textStatus == 'abort')
					return;
				var errorHandler = this._updateParams.errorHandler;
				if (undefined === errorHandler)
					errorHandler = this.defaults.errorHandler;
				this._errorResume = false;
				errorHandler(jqXHR, textStatus, errorThrown, this._updateParams);
				if (!this._errorResume)
					this._runningLoop = false;
				delete this._errorResume;
			},
			success: function(data, textStatus, jqXHR)
			{
				if (!('lastId' in data))
					ajax.error.call(this, jqXHR, 'parsererror',
						'Could not find "lastId" property in the response data');
				else if (!('events' in data))
					ajax.error.call(this, jqXHR, 'parsererror',
						'Could not find "events" property in the response data');
				else
				{
					this._updateTimestamp = {{jq}}.now();
					if (null == data.events) 
					{
						if (null == this._lastReceivedId)
							this._lastReceivedId = data.lastId;
						return;
					}
					var handler = this._updateParams.handler;
					if (undefined === handler)
						handler = this.defaults.handler;
					var remaining = data.events.length;
					while (this._runningLoop && 0 < remaining)
					{
						var consumed = handler(data.events, this._updateParams);
						if (typeof consumed != 'number' || 0 > consumed || remaining < consumed)
						{
							ajax.error.call(this, jqXHR, 'parsererror',
							'Comety event handler returned invalid value "' + consumed
							+ '", expected an integer from 0 to ' + remaining);
						}
						else if (0 == consumed)
							this._runningLoop = false;
						else
						{
							data.events = data.events.slice(consumed);
							remaining -= consumed;
						}
					}
					this._lastReceivedId = data.lastId - remaining;
				}
			},
			timeout: timeout * 1000,
			url: url
		}
		if (null != this._lastReceivedId)
			ajax.data.confirm = this._lastReceivedId;
		ajax.data.elapsed = null == this._updateTimestamp ?
			0 : ({{jq}}.now() - this._updateTimestamp) / 1000.0;
		this._jqXHR = {{jq}}.ajax(ajax);
	};
	if ({{api}}.startUpdates !== undefined)
		throw 'Comety API variable "{{api}}" already has the "startUpdates" property: ' +
			{{api}}.startUpdates;
	{{api}}.startUpdates = function(settings)
	{
		if (settings === undefined)
			settings = {}
		if (this._updateParams === undefined)
			this._updateParams = {}
		for (var setting in this.defaults)
			if (settings[setting] !== undefined)
				this._updateParams[setting] = settings[setting]
		if (this._errorResume != undefined)
			this._errorResume = true;
		else if (!this._runningLoop)
			this._loop();
	};
	if ({{api}}.stopUpdates !== undefined)
		throw 'Comety API variable "{{api}}" already has the "stopUpdates" property: ' +
			{{api}}.stopUpdates;
	{{api}}.stopUpdates = function()
	{
		this._runningLoop = false;
		if (null != this._jqXHR)
			this._jqXHR.abort();
	};
{% endwith %}{% endif %}
{% if autoStart %}{% comment %}
{% endcomment %}{% with api=APIvar|default:"comety" jq=jQueryVar|default:"jQuery" %}
	{{jq}}(function()
	{
		if ({{api}} !== undefined && 'startUpdates' in {{api}})
		{
			$(window).on('beforeunload', function() { {{api}}.stopUpdates(); });
			{{api}}.startUpdates();
		}
	});
{% endwith %}{% endif %}
