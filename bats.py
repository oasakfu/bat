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
import weakref
import logging

import bge

import bat.utils

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
				return "BX_GameObject(%s) (was %s)" % (super(BX_GameObject, self).__repr__(),
						self._orig_name)
			else:
				return "BX_GameObject(%s)" % self.name

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
		return o
	else:
		return cls(o)

def add_and_mutate_object(scene, ob, other=None, time=0):
	'''Add an object to the scene, and mutate it according to its Class
	property.'''

	if other == None:
		other = ob
	o = scene.addObject(ob, other, time)
	return mutate(o)

#
# Containers
#

def weakprop(name):
	'''Creates a property that stores a weak reference to whatever is assigned
	to it. If the assignee is deleted, the getter will return None. Example
	usage:

	class Baz:
		foo = bat.bats.weakprop('foo')

		def bork(self, gameObject):
			self.foo = gameObject

		def update(self):
			if self.foo != None:
				self.foo.worldPosition.z += 1
	'''
	hiddenName = '_wp_' + name

	def createweakprop(hiddenName):
		def wp_getter(slf):
			ref = None
			try:
				ref = getattr(slf, hiddenName)
			except AttributeError:
				pass

			value = None
			if ref != None:
				value = ref()
				if value == None:
					setattr(slf, hiddenName, None)
				elif hasattr(value, 'invalid') and value.invalid:
					setattr(slf, hiddenName, None)
					value = None
			return value

		def wp_setter(slf, value):
			if value == None:
				setattr(slf, hiddenName, None)
			else:
				ref = weakref.ref(value)
				setattr(slf, hiddenName, ref)

		return property(wp_getter, wp_setter)

	return createweakprop(hiddenName)


class SafeList:
	'''
	A list that only stores references to valid objects. An object that has the
	'invalid' attribute will be ignored if ob.invalid is False. This has
	implications for the indices of the list: indices may change from one frame
	to the next, but they should remain consistent during a frame.
	'''

	def __init__(self, iterable = None):
		self._list = []
		if iterable is not None:
			self.extend(iterable)

	def __contains__(self, item):
		if hasattr(item, 'invalid') and item.invalid:
			return False
		return self._list.__contains__(item)

	def __iter__(self):
		def _iterator():
			i = self._list.__iter__()
			while True:
				item = next(i)
				if hasattr(item, 'invalid') and item.invalid:
					continue
				yield item
		return _iterator()

	def __len__(self):
		n = 0
		for item in self._list:
			if hasattr(item, 'invalid') and item.invalid:
				continue
			n += 1
		return n

	def append(self, item):
		self._expunge()
		if hasattr(item, 'invalid') and item.invalid:
			return
		return self._list.append(item)

	def index(self, item):
		i = 0
		for item2 in self._list:
			if hasattr(item2, 'invalid') and item2.invalid:
				continue
			if item2 is item:
				return i
			else:
				i += 1
		raise ValueError("Item is not in list")

	def remove(self, item):
		self._expunge()
		if hasattr(item, 'invalid') and item.invalid:
			raise ValueError("Item has expired.")
		return self._list.remove(item)

	def pop(self, index=-1):
		self._expunge()
		return self._list.pop(index)

	def extend(self, iterable):
		for item in iterable:
			self.append(item)

	def count(self, item):
		if hasattr(item, 'invalid') and item.invalid:
			return 0
		return self._list.count(item)

	def __getitem__(self, index):
		# Todo: allow negative indices.
		if index < 0:
			i = -1
			for item in reversed(self._list):
				if hasattr(item, 'invalid') and item.invalid:
					continue
				if i == index:
					return item
				else:
					i -= 1
		else:
			i = 0
			for item in self._list:
				if hasattr(item, 'invalid') and item.invalid:
					continue
				if i == index:
					return item
				else:
					i += 1
		raise IndexError("list index out of range")

	def __setitem__(self, index, item):
		self._expunge()
		# After expunging, the all items in the internal list will have the
		# right length - so it's OK to just call the wrapped method.
		if hasattr(item, 'invalid') and item.invalid:
			return item
		return self._list.__setitem__(index, item)

	def __delitem__(self, index):
		self._expunge()
		return self._list.__delitem__(index)

	def insert(self, index, item):
		self._expunge()
		if hasattr(item, 'invalid') and item.invalid:
			return
		self._list.insert(index, item)

	def _expunge(self):
		new_list = []
		for item in self._list:
			if hasattr(item, 'invalid') and item.invalid:
				self._on_automatic_removal(item)
			else:
				new_list.append(item)
		self._list = new_list

	def __str__(self):
		return str(list(self))

	def _on_automatic_removal(self, item):
		pass


class SafeSet:
	'''A set for PyObjectPlus objects. This container ensures that its contents
	are valid (living) game objects.

	As usual, you shouldn't change the contents of the set while iterating over
	it. However, an object dying in the scene won't invalidate existing
	iterators.'''

	def __init__(self, iterable = None):
		self.bag = set()
		self.deadBag = set()
		if iterable != None:
			for ob in iterable:
				self.add(ob)

	def copy(self):
		clone = SafeSet()
		clone.bag = self.bag.copy()
		clone.deadBag = self.deadBag.copy()
		clone._expunge()
		return clone

	def __contains__(self, item):
		if hasattr(item, 'invalid') and item.invalid:
			if item in self.bag:
				self._flag_removal(item)
			return False
		else:
			return item in self.bag

	def __iter__(self):
		for item in self.bag:
			if hasattr(item, 'invalid') and item.invalid:
				self._flag_removal(item)
			else:
				yield item

	def __len__(self):
		# Unfortunately the only way to be sure is to check each object!
		count = 0
		for item in self.bag:
			if hasattr(item, 'invalid') and item.invalid:
				self._flag_removal(item)
			else:
				count += 1
		return count

	def add(self, item):
		self._expunge()
		if hasattr(item, 'invalid') and item.invalid:
			return
		self.bag.add(item)

	def discard(self, item):
		self.bag.discard(item)
		self._expunge()

	def remove(self, item):
		self.bag.remove(item)
		self._expunge()

	def update(self, iterable):
		self.bag.update(iterable)
		self._expunge()

	def union(self, iterable):
		newset = SafeSet()
		newset.bag = self.bag.union(iterable)
		return newset

	def difference_update(self, iterable):
		self.bag.difference_update(iterable)
		self._expunge()

	def difference(self, iterable):
		newset = SafeSet()
		newset.bag = self.bag.difference(iterable)
		return newset

	def intersection_update(self, iterable):
		self.bag.intersection_update(iterable)
		self._expunge()

	def intersection(self, iterable):
		newset = SafeSet()
		newset.bag = self.bag.intersection(iterable)
		return newset

	def clear(self):
		self.bag.clear()
		self.deadBag.clear()

	def _flag_removal(self, item):
		'''Mark an object for garbage collection. Actual removal happens at the
		next explicit mutation (add() or discard()).'''
		self.deadBag.add(item)

	def _expunge(self):
		'''Remove objects marked as being dead.'''
		self.bag.difference_update(self.deadBag)
		self.deadBag.clear()

	def __str__(self):
		return str(self.bag)

class SafePriorityStack(SafeList):
	'''
	A poor man's associative priority queue. This is likely to be slow. It is
	only meant to contain a small number of items.
	'''

	def __init__(self):
		'''Create a new, empty priority queue.'''
		super(SafePriorityStack, self).__init__()
		self.priorities = {}

	def push(self, item, priority):
		'''Add an item to the stack. If the item is already in the stack, it is
		removed and added again using the new priority.

		Parameters:
		item:     The item to place on the stack.
		priority: Items with higher priority will be stored higher on the stack.
		          0 <= priority. (Integer)
		'''

		if item in self.priorities:
			self.discard(item)

		# Insert at the front of the list of like-priority items.
		idx = 0
		for other in self:
			if self.priorities[other] <= priority:
				break
			idx += 1
		super(SafePriorityStack, self).insert(idx, item)

		self.priorities[item] = priority

	def _on_automatic_removal(self, item):
		print("Auto remove", item)
		del self.priorities[item]

	def discard(self, item):
		'''Remove an item from the queue.

		Parameters:
		key: The key that was used to insert the item.
		'''
		print("Discard", item)
		try:
			super(SafePriorityStack, self).remove(item)
			del self.priorities[item]
		except KeyError:
			pass
		except ValueError:
			pass

	def pop(self):
		'''Remove the highest item in the queue.

		Returns: the item that is being removed.

		Raises:
		IndexError: if the queue is empty.
		'''

		item = super(SafePriorityStack, self).pop(0)
		del self.priorities[item]
		return item

	def top(self):
		return self[0]

	def append(self, item):
		raise NotImplementedError("Use 'push' instead.")

	def remove(self, item):
		raise NotImplementedError("Use 'discard' instead.")

	def __setitem__(self, index, item):
		raise NotImplementedError("Use 'push' instead.")

	def insert(self, index, item):
		raise NotImplementedError("Use 'push' instead.")

	def __str__(self):
		string = "["
		for item in self:
			if len(string) > 1:
				string += ", "
			string += "%s@%d" % (item, self.priorities[item])
		string += "]"
		return string

#
# Events
#

class Timekeeper(metaclass=Singleton):
	def __init__(self):
		self.current_frame = 0
		self.locked = False
		self.ensure_installed()

	def get_frame_num(self):
		# Make sure the timekeeper is running for every scene that wants to use
		# it.
		self.ensure_installed()
		return self.current_frame

	@staticmethod
	def frame_count_pre():
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
		tk.current_frame += 1

	def ensure_installed(self):
		sce = bge.logic.getCurrentScene()
		if Timekeeper.frame_count_pre in sce.pre_draw:
			return

		#print("Installing timekeeper")
		sce.pre_draw.append(Timekeeper.frame_count_pre)
		sce.post_draw.append(Timekeeper.frame_count_post)

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
