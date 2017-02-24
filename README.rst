..
   Copyright © 2016 Stan Livitski

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

----------------
 Comety toolkit
----------------

*Comety* is a simple toolkit for building web applications that
can promptly react to server-side events using a technique
called Comet_.

Comet_ is a web programming model that allows a web server to
push data to a browser. *Comety* enables the Comet_ model in web
applications that use a multi-threaded server without the
expense of configuring and maintaining complex dependencies such
as *Tornado* or *Twisted*. *Comety* is designed for applications with
small numbers of concurrent users.

About this repository
---------------------

This repository contains the source code of the *Comety toolkit*.
Its top-level components are:

=========================    ===============================================
``comety``                   Python package with the toolkit's common
                             code. Modules from this package can be used by
                             any *Comety* application, regardless of its
                             framework. This does not apply to
                             subpackages, which may be dependent on
                             frameworks.  
``comety/django``            Python package with elements of the toolkit
                             that depend on the Django_ framework. Its
                             contents can be added as an application to a
                             *Django project*.
``LICENSE``                  Document that describes the project's licensing
                             terms.
``NOTICE``                   Summary of license terms that apply to
                             *Comety*. 
``README.rst``               This document.
=========================    ===============================================

Using Comety
------------

Requirements
^^^^^^^^^^^^

*Comety* is designed for use in web applications. Modern web applications are
typically built within web frameworks, such as Django_. Core parts of *Comety*,
however, do not depend on Django_, or any other framework. The toolkit's design
allows for adding support of other frameworks in future.

Dependencies listed in the `Core dependencies`_ section below must be met in
all environments that use *Comety*. Dependencies listed in the following
sections apply only to parts of *Comety* built for frameworks specified in
those sections.

Core dependencies
'''''''''''''''''

+-----------------------------------------------------------+---------------+
|  Name / Download URL                                      | Version       |
+===========================================================+===============+
| | Python                                                  | 3.2 or newer  |
| | https://www.python.org/downloads/ or an OS distribution |               |
+-----------------------------------------------------------+---------------+
| | ``python-runtime`` package                              | any available |
| | https://github.com/StanLivitski/python-runtime          |               |
+-----------------------------------------------------------+---------------+

Django apps' dependencies
'''''''''''''''''''''''''

You must meet these dependencies to run the code in ``comety/django``:

+-----------------------------------------------------------+---------------+
|  Name / Download URL                                      | Version       |
+===========================================================+===============+
| | Django                                                  | 1.8.7 or newer|
| | https://www.djangoproject.com/download/                 |               |
|   or an OS distribution                                   |               |
+-----------------------------------------------------------+---------------+
| | jQuery                                                  | 1.11 or newer |
| | http://code.jquery.com/                                 |               |
+-----------------------------------------------------------+---------------+

Browser compatibility
'''''''''''''''''''''

*Comety* is designed for compatibility with the following browsers:

+-----------------------------------------------------------+---------------+
|  Name                                                     | Version       |
+===========================================================+===============+
| Firefox                                                   | 41 or newer   |
+-----------------------------------------------------------+---------------+
| Chrome                                                    | 37 or newer   |
+-----------------------------------------------------------+---------------+
| Internet Explorer                                         | 9 or newer    |
+-----------------------------------------------------------+---------------+

.. |                                                           |               |

Comety and your application
^^^^^^^^^^^^^^^^^^^^^^^^^^^

To make *Comety* available to your application, you have to:

#. Comply with the toolkit's license terms. Please review the ``NOTICE``
   file at the root of this repository for licensing information.
#. Place a copy of the ``comety`` directory from this repository, or
   install the toolkit's distribution, on your application's
   ``PYTHONPATH``. 

Please refer to the PyDoc comments within the toolkit's packages for usage
details.

Comety in a Django project
^^^^^^^^^^^^^^^^^^^^^^^^^^

For web applications that use Django_ framework, the toolkit offers a template
that generates a script that receives events in a browser, and a view class
that talks to that script and manages timeouts.

The above facilities can be made available to a Django_ project by adding
``comety.django`` as an application to the project's ``INSTALLED_APPS``
setting and enabling the ``APP_DIRS`` option in the ``TEMPLATES`` setting.

.. _Comet: https://en.wikipedia.org/wiki/Comet_%28programming%29
.. _Django: https://www.djangoproject.com
