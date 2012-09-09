#
# Copyright 2009-2011 Alex Fraser <alex@phatcore.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


import logging
import logging.config

import bge

try:
	logging.config.fileConfig(bge.logic.expandPath('//logging.conf'))
except:
	print("Warning: Couldn't open logging config file //logging.conf.")

#
# For debugging things like
#    File "/usr/lib/python3.2/logging/__init__.py", line 317, in getMessage
#        msg = msg % self.args
#    TypeError: not all arguments converted during string formatting
#
#def handleError(self, record):
#	raise
#logging.Handler.handleError = handleError


try:
	#
	# Connect to PyDev debug server if one is available. This will raise an
	# ImportError if the debug libraries aren't in the PYTHONPATH, which implies
	# that Blender isn't being run from within the debugger.
	#
	# To get this to work:
	#  1. Start the PyDev debug server.
	#  2. Add the pydevd source directory to the PYTHONPATH.
	#  3. Launch Blender, and start the game. Any breakpoints you set in Eclipse
	#     will then be caught by PyDev.
	#
	# The external tool file "Game/Blender PyDebug.launch" will execute steps 2
	# and 3 for you.
	#
	# For more information, see:
	#     http://pydev.org/manual_adv_remote_debugger.html
	#
	import pydevd
	pydevd.settrace(stdoutToServer=True, stderrToServer=True, suspend=False)
except ImportError:
	pass



import bat.event

#
# Now that everything has been imported, create singletons.
#
bat.event.EventBus()
