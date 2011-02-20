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

from . import c
from . import math
from . import render
from . import sound
from . import types
from . import utils
from . import effectors
from . import water
