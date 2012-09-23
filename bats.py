#
# Copyright 2009-2012 Alex Fraser <alex@phatcore.com>
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

import sys
import logging
from functools import wraps

import bge

import bat.utils

log = logging.getLogger(__name__)

PROFILE_BASIC = False
PROFILE_STOCHASTIC = False

prof = None
def _print_stats(c):
	if not c.sensors['sInfo'].positive:
		return
	if prof == None:
		return

	def timekey(stat):
		return stat[1] / float(stat[2])
	stats = sorted(prof.values(), key=timekey, reverse=True)

	print('=== Execution Statistics ===')
	print('Times are in milliseconds.')
	print('{:<55} {:>6} {:>7} {:>6}'.format('FUNCTION', 'CALLS', 'SUM(ms)', 'AV(ms)'))
	for stat in stats:
		print('{:<55} {:>6} {:>7.0f} {:>6.2f}'.format(
				stat[0], stat[2],
				stat[1] * 1000,
				(stat[1] / float(stat[2])) * 1000))
def _print_stats2(c):
	bat.statprof.stop()
	bat.statprof.display()
print_stats = None
if PROFILE_BASIC:
	import time
	prof = {}
	print_stats = _print_stats
elif PROFILE_STOCHASTIC:
	import bat.statprof
	bat.statprof.reset(1000)
	bat.statprof.start()
	print_stats = _print_stats2
class profile:
	def __init__(self, name):
		self.name = name

	def __call__(self, fun):
		if not PROFILE_BASIC:
			return fun
		else:
			def profile_fun(*args, **kwargs):
				start = time.clock()
				try:
					return fun(*args, **kwargs)
				finally:
					duration = time.clock() - start
					if not fun in prof:
						prof[fun] = [self.name, duration, 1]
					else:
						prof[fun][1] += duration
						prof[fun][2] += 1
			return profile_fun

#
# Game object wrappers and such
#

def expose(f):
	'''Expose a method as a top-level function. Must be used in conjunction with
	the GameOb metaclass.'''
	f._expose = True
	return f

class Singleton(type):
	'''A metaclass that makes singletons. Methods marked with the expose
	decorator will be promoted to top-level functions, and can therefore be
	called from a logic brick.'''

	log = logging.getLogger(__name__ + '.Singleton')

	def __init__(self, name, bases, attrs):
		'''Runs just after the class is defined.'''

		Singleton.log.info('Creating Singleton %s' % name)

		module = sys.modules[attrs['__module__']]
		prefix = name + '_'
		if '_prefix' in attrs:
			prefix = attrs['_prefix']
		for attrname, value in attrs.items():
			if getattr(value, '_expose', False):
				self.expose_method(attrname, value, module, prefix)
				# Prevent this from running again for subclasses.
				value._expose = False

		self.instance = None

		super(Singleton, self).__init__(name, bases, attrs)

	def __call__(self):
		'''Provide the current game object as an argument to the constructor.
		Runs when the class is instantiated.'''
#		print("Singleton.__call__(%s)" % (self))
		if self.instance == None:
			self.instance = super(Singleton, self).__call__()
		return self.instance

	def expose_method(self, methodName, method, module, prefix):
		'''Expose a single method as a top-level module funciton. This must
		be done in a separate function so that it may act as a closure.'''

		@profile('%s.%s%s' % (module.__name__, prefix, methodName))
		def method_wrapper():
			try:
				return getattr(self(), methodName)()
			except:
				bge.logic.getCurrentScene().suspend()
				bat.utils._debug_leaking_objects()
				raise

		method_wrapper.__name__ = '%s%s' % (prefix, methodName)
		method_wrapper.__doc__ = method.__doc__
		setattr(module, method_wrapper.__name__, method_wrapper)

class GameOb(type):
	'''A metaclass that makes a class neatly wrap game objects:
	 - The class constructor can be called from a logic brick, to wrap the
	   logic brick's owner.
	 - Methods marked with the expose decorator will be promoted to
	   top-level functions, and can therefore be called from a logic brick.
	For example:

	class Foo(bge.types.KX_GameObject, metaclass=bat.bats.GameOb):
		def __init__(self, old_owner):
			# Do not use old_owner; it will have been destroyed! Also, you don't
			# need to call KX_GameObject.__init__.
			pass

		@bat.bats.expose
		def update(self):
			self.worldPosition.z += 1.0

	See also BX_GameObject.
	'''

	log = logging.getLogger(__name__ + '.GameOb')

	def __init__(self, name, bases, attrs):
		'''Runs just after the class is defined.'''
#		print("GameOb.__init__(%s, %s, %s, %s)" % (self, name, bases, attrs))

		module = sys.modules[attrs['__module__']]
		prefix = name + '_'
		if '_prefix' in attrs:
			prefix = attrs['_prefix']
		for attrname, value in attrs.items():
			if getattr(value, '_expose', False):
				self.expose_method(attrname, value, module, prefix)
				# Prevent this from running again for subclasses.
				value._expose = False

		super(GameOb, self).__init__(name, bases, attrs)

	def __call__(self, ob=None):
		'''Provide the current game object as an argument to the constructor.
		Runs when the class is instantiated.'''
#		print("GameOb.__call__(%s, %s)" % (self, ob))
		if ob == None:
			ob = bge.logic.getCurrentController().owner

		GameOb.log.debug("Mutating %s to %s", ob.__class__, self)
		if 'Class' in ob and not ob['Class'].endswith(self.__name__):
			GameOb.log.warn("Mutating object specifies class %s, but mutating "
					"to %s", ob['Class'], self.__name__)
		orig_name = ob.name
		if 'template' in ob:
			ob = bat.utils.replaceObject(ob['template'], ob)
		new_ob = super(GameOb, self).__call__(ob)
		new_ob._orig_name = orig_name
		return new_ob

	def expose_method(self, methodName, method, module, prefix):
		'''Expose a single method as a top-level module funciton. This must
		be done in a separate function so that it may act as a closure.'''

		@profile('%s.%s%s' % (module.__name__, prefix, methodName))
		def method_wrapper():
			try:
				o = bge.logic.getCurrentController().owner
				return getattr(o, methodName)()
			except:
				bge.logic.getCurrentScene().suspend()
				bat.utils._debug_leaking_objects()
				raise

		method_wrapper.__name__ = '%s%s' % (prefix, methodName)
		method_wrapper.__doc__ = method.__doc__
		setattr(module, method_wrapper.__name__, method_wrapper)

class BX_GameObject(metaclass=GameOb):
	'''Basic convenience extensions to KX_GameObject. Use as a mixin.'''

	def add_state(self, state):
		'''Add a set of states to this object's state.'''
		bat.utils.add_state(self, state)

	def rem_state(self, state):
		'''Remove a state from this object's state.'''
		bat.utils.rem_state(self, state)

	def set_state(self, state):
		'''Set the object's state. All current states will be un-set and replaced
		with the one specified.'''
		bat.utils.set_state(self, state)

	def has_state(self, state):
		'''Test whether the object is in the specified state.'''
		return bat.utils.has_state(self, state)

	def set_default_prop(self, propName, defaultValue):
		'''Sets the value of a property, but only if it doesn't already
		exist.'''
		bat.utils.set_default_prop(self, propName, defaultValue)

	@property
	def scene(self):
		'''Get the scene that this object exists in. Sometimes this is preferred
		over bge.logic.getCurrentScene, e.g. if this object is responding to an
		event sent from another scene.'''
		try:
			return self._scene
		except AttributeError:
			self._scene = bat.utils.get_scene(self)
			return self._scene

	def find_descendant(self, propCriteria):
		'''Finds a descendant of this object that matches a set of criteria.
		This is a recursive, breadth-first search.

		@param propCriteria: A list of tuples: (property name, value). If any
				one of these doesn't match a given child, it will not be
				returned. If value is None, it always matches (the object need
				only have a property of the given name).
		@return: The first descendant that matches the criteria, or None if no
				such child exists.'''
		def find_recursive(objects):
			match = None
			for child in objects:
				matches = True
				for (name, value) in propCriteria:
					if name in child and (value == None or child[name] == value):
						continue
					else:
						matches = False
						break
				if matches:
					match = child

			if match != None:
				return match
			for child in objects:
				match = find_recursive(child.children)
				if match:
					return match
			return None

		return find_recursive(self.children)

	def to_local(self, point):
		return bat.bmath.to_local(self, point)

	def to_world(self, point):
		return bat.bmath.to_world(self, point)

	def __repr__(self):
		if hasattr(self, 'invalid') and self.invalid:
			if hasattr(self, '_orig_name'):
				return "<Dead game object> (was %s)" % self._orig_name
			else:
				return "<Dead game object>"
		else:
			if hasattr(self, '_orig_name') and self._orig_name != self.name:
				return "BX(%s) (was %s)" % (super(BX_GameObject, self).__repr__(),
						self._orig_name)
			else:
				return "BX(%s)" % self.name

clsCache = {}
def _get_class(qualifiedName):
	if qualifiedName in clsCache:
		return clsCache[qualifiedName]

	parts = qualifiedName.split('.')
	modName = '.'.join(parts[:-1])
	m = __import__(modName)
	for part in parts[1:]:
		m = getattr(m, part)

	clsCache[qualifiedName] = m
	return m

@bat.utils.owner
def mutate(o):
	'''Convert an object to its preferred class, as defined by the object's
	Class property. All existing references to the object will be invalidated,
	unless the object is already of the specified class - in which case this
	function has no effect.

	@return: the new instance, or the old instance if it was already the
	required type.'''

	cls = _get_class(o['Class'])
	if cls == o.__class__:
		log.debug("No-op: %s is already mutated", cls)
		return o
	else:
		return cls(o)

def add_and_mutate_object(scene, ob, other=None, time=0):
	'''Add an object to the scene, and mutate it according to its Class
	property.'''

	if other == None:
		other = ob
	log.debug("Adding and mutating %s at %s in scene %s", ob, other, scene)
	log.debug("Active: %s, Inactive: %s", ob in scene.objects,
			ob in scene.objectsInactive)
	o = scene.addObject(ob, other, time)
	return mutate(o)

#
# Time
#

class Timekeeper(metaclass=Singleton):

	_prefix = 'TK_'

	def __init__(self):
		self._current_frame = 0
		self.current_tick = 0
		self.locked = False
		self.ensure_installed()
		self.callers = set()

	@property
	def current_frame(self):
		# Make sure the timekeeper is running for every scene that wants to use
		# it.
		self.ensure_installed()
		return self._current_frame

	@expose
	@bat.utils.controller_cls
	def update(self, c):
		if len(self.callers) == 0 or c.owner in self.callers:
			# The object calling this method is the first object to do so on
			# this logic tick.
			self.callers.clear()
			self.current_tick += 1
		self.callers.add(c.owner)

	@staticmethod
	def frame_count_pre():
		'''
		Unlock. It doesn't matter which scene this gets called from, because all
		scenes will render before frame_count_post is called.
		'''
		tk = Timekeeper()
		tk.locked = False

	@staticmethod
	def frame_count_post():
		'''
		Lock, to prevent two scene callbacks from updating the counter.
		'''
		tk = Timekeeper()
		if tk.locked:
			return
		tk.locked = True
		tk._current_frame += 1

	def ensure_installed(self):
		sce = bge.logic.getCurrentScene()
		if Timekeeper.frame_count_pre in sce.pre_draw:
			return

		#print("Installing timekeeper")
		sce.pre_draw.append(Timekeeper.frame_count_pre)
		sce.post_draw.append(Timekeeper.frame_count_post)

def once_per_frame(f):
	'''
	Decorator. Ensures that a function runs only once per rendered frame.
	Note: function can not return anything.
	'''
	f._last_frame_num = -1
	@wraps(f)
	def f_once_per_frame(*args, **kwargs):
		frame_num = Timekeeper().current_frame
		if frame_num == f._last_frame_num:
			return
		f._last_frame_num = frame_num
		return f(*args, **kwargs)
	return f_once_per_frame

def once_per_tick(f):
	'''
	Decorator. Ensures that a function runs only once per logic tick. Note:
	function can not return anything.
	'''
	f._last_tick_num = -1
	@wraps(f)
	def f_once_per_tick(*args, **kwargs):
		frame_num = Timekeeper().current_tick
		if frame_num == f._last_tick_num:
			return
		f._last_tick_num = frame_num
		return f(*args, **kwargs)
	return f_once_per_tick

#
# State abstractions
#

class Counter:
	'''Counts the frequency of objects. This should only be used temporarily and
	then thrown away, as it keeps hard references to objects.
	'''

	def __init__(self):
		self.map = {}
		self.mode = None
		self.max = 0
		self.n = 0

	def add(self, ob):
		'''Add an object to this counter. If this object is the most frequent
		so far, it will be stored in the member variable 'mode'.'''
		count = 1
		if ob in self.map:
			count = self.map[ob] + 1
		self.map[ob] = count
		if count > self.max:
			self.max = count
			self.mode = ob
		self.n = self.n + 1

class FuzzySwitch:
	'''A boolean that only switches state after a number of consistent impulses.
	'''

	def __init__(self, delayOn, delayOff, startOn):
		self.delayOn = delayOn
		self.delayOff = 0 - delayOff
		self.on = startOn
		if startOn:
			self.current = self.delayOn
		else:
			self.current = self.delayOff

	def turn_on(self):
		self.current = max(0, self.current)
		if self.on:
			return

		self.current += 1
		if self.current == self.delayOn:
			self.on = True

	def turn_off(self):
		self.current = min(0, self.current)
		if not self.on:
			return

		self.current -= 1
		if self.current == self.delayOff:
			self.on = False

	def is_on(self):
		return self.on
