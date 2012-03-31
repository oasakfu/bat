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

from . import anim
from . import c
from . import bmath
from . import render
from . import sound
from . import music
from . import types
from . import utils
from . import effectors
from . import water
from . import debug

#
# Now that everything has been imported, create singletons.
#
types.EventBus()
