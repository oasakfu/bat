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

import sys
import weakref

import bge

import bxt.utils

DEBUG = False
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
	bxt.statprof.stop()
	bxt.statprof.display()
print_stats = None
if PROFILE_BASIC:
	import time
	prof = {}
	print_stats = _print_stats
elif PROFILE_STOCHASTIC:
	import bxt.statprof
	bxt.statprof.start()
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

	def __init__(self, name, bases, attrs):
		'''Runs just after the class is defined.'''
#		print("Singleton.__init__(%s, %s, %s, %s)" % (self, name, bases, attrs))

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
				bxt.utils._debug_leaking_objects()
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

	class Foo(bge.types.KX_GameObject, metaclass=bxt.types.GameOb):
		def __init__(self, old_owner):
			# Do not use old_owner; it will have been destroyed! Also, you don't
			# need to call KX_GameObject.__init__.
			pass

		@bxt.types.expose
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
		if 'template' in ob:
			ob = bxt.utils.replaceObject(ob['template'], ob)
		return super(GameOb, self).__call__(ob)

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
				bxt.utils._debug_leaking_objects()
				raise

		method_wrapper.__name__ = '%s%s' % (prefix, methodName)
		method_wrapper.__doc__ = method.__doc__
		setattr(module, method_wrapper.__name__, method_wrapper)

class BX_GameObject(metaclass=GameOb):
	'''Basic convenience extensions to KX_GameObject. Use as a mixin.'''

	def add_state(self, state):
		'''Add a set of states to this object's state.'''
		bxt.utils.add_state(self, state)

	def rem_state(self, state):
		'''Remove a state from this object's state.'''
		bxt.utils.rem_state(self, state)

	def set_state(self, state):
		'''Set the object's state. All current states will be un-set and replaced
		with the one specified.'''
		bxt.utils.set_state(self, state)

	def has_state(self, state):
		'''Test whether the object is in the specified state.'''
		return bxt.utils.has_state(self, state)

	def set_default_prop(self, propName, defaultValue):
		'''Sets the value of a property, but only if it doesn't already
		exist.'''
		bxt.utils.set_default_prop(self, propName, defaultValue)

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

@bxt.utils.owner
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

def add_and_mutate_object(scene, object, other=None, time=0):
	'''Add an object to the scene, and mutate it according to its Class
	property.'''

	if other == None:
		other = object
	o = scene.addObject(object, other, time)
	return mutate(o)

#
# Containers
#

def weakprop(name):
	'''Creates a property that stores a weak reference to whatever is assigned
	to it. If the assignee is deleted, the getter will return None. Example
	usage:

	class Baz:
		foo = bxt.types.weakprop('foo')

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

class GameObjectSet:
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
		clone = GameObjectSet()
		clone.bag = self.bag.copy()
		clone.deadBag = self.deadBag.copy()
		clone._clean_refs()
		return clone

	def __contains__(self, item):
		if item.invalid:
			if item in self.bag:
				self._flag_removal(item)
			return False
		else:
			return item in self.bag

	def __iter__(self):
		for item in self.bag:
			if item.invalid:
				self._flag_removal(item)
			else:
				yield item

	def __len__(self):
		# Unfortunately the only way to be sure is to check each object!
		count = 0
		for item in self.bag:
			if item.invalid:
				self._flag_removal(item)
			else:
				count += 1
		return count

	def add(self, item):
		self._clean_refs()
		if not item.invalid:
			self.bag.add(item)

	def discard(self, item):
		self.bag.discard(item)
		self._clean_refs()

	def remove(self, item):
		self.bag.remove(item)
		self._clean_refs()

	def update(self, iterable):
		self.bag.update(iterable)
		self._clean_refs()

	def difference_update(self, iterable):
		self.bag.difference_update(iterable)
		self._clean_refs()

	def intersection_update(self, iterable):
		self.bag.intersection_update(iterable)
		self._clean_refs()

	def clear(self):
		self.bag.clear()
		self.deadBag.clear()

	def _flag_removal(self, item):
		'''Mark an object for garbage collection. Actual removal happens at the
		next explicit mutation (add() or discard()).'''
		self.deadBag.add(item)

	def _clean_refs(self):
		'''Remove objects marked as being dead.'''
		self.bag.difference_update(self.deadBag)
		self.deadBag.clear()

class WeakPriorityQueue:
	'''A poor man's associative priority queue. This is likely to be slow. It is
	only meant to contain a small number of items. Don't use this to store game
	objects; use GameObjectPriorityQueue instead.
	'''

	def __init__(self):
		'''Create a new, empty priority queue.'''

		self.queue = []
		self.priorities = {}

	def __len__(self):
		return len(self.queue)

	def __getitem__(self, y):
		'''Get the yth item from the queue. 0 is the bottom (oldest/lowest
		priority); -1 is the top (youngest/highest priority).
		'''

		return self.queue[y]()

	def __contains__(self, item):
		ref = weakref.ref(item)
		return ref in self.priorities

	def _index(self, ref, *args, **kwargs):
		return self.queue.index(ref, *args, **kwargs)

	def index(self, item, *args, **kwargs):
		return self._index(weakref.ref(item), *args, **kwargs)

	def push(self, item, priority):
		'''Add an item to the end of the queue. If the item is already in the
		queue, it is removed and added again using the new priority.

		Parameters:
		item:     The item to store in the queue.
		priority: Items with higher priority will be stored higher on the queue.
		          0 <= priority. (Integer)
		'''

		def autoremove(r):
			self._discard(r)

		ref = weakref.ref(item, autoremove)

		if ref in self.priorities:
			self.discard(item)

		i = len(self.queue)
		while i > 0:
			refOther = self.queue[i - 1]
			priOther = self.priorities[refOther]
			if priOther <= priority:
				break
			i -= 1
		self.queue.insert(i, ref)

		self.priorities[ref] = priority

		return i

	def _discard(self, ref):
		try:
			self.queue.remove(ref)
			del self.priorities[ref]
		except KeyError:
			pass

	def discard(self, item):
		'''Remove an item from the queue.

		Parameters:
		key: The key that was used to insert the item.
		'''
		self._discard(weakref.ref(item))

	def pop(self):
		'''Remove the highest item in the queue.

		Returns: the item that is being removed.

		Raises:
		IndexError: if the queue is empty.
		'''

		ref = self.queue.pop()
		del self.priorities[ref]
		return ref()

	def top(self):
		return self[-1]

class GameObjectPriorityQueue:
	def __init__(self):
		self.q = WeakPriorityQueue()
		self.deadBag = weakref.WeakSet()

	def __contains__(self, item):
		if item.invalid:
			return False
		return item in self.q

	def push(self, item, priority):
		print('push', item)
		self.q.push(item, priority)
		self._clean_refs()

	def discard(self, item):
		print('discard', item)
		self.q.discard(item)
		self._clean_refs()

	def top(self):
		for item in reversed(self.q):
			if item.invalid:
				self._flag_removal(item)
			else:
				return item
		raise IndexError('This queue is empty.')

	def _flag_removal(self, item):
		'''Mark an object for garbage collection. Actual removal happens at the
		next explicit mutation (add() or discard()).'''
		self.deadBag.add(item)

	def _clean_refs(self):
		'''Remove objects marked as being dead.'''
		for item in self.deadBag:
			self.q.discard(item)
		self.deadBag.clear()

#
# Events
#

class EventBus(metaclass=Singleton):
	'''Delivers messages to listeners.'''

	def __init__(self):
		self.listeners = weakref.WeakSet()
		self.gamobListeners = GameObjectSet()
		self.eventQueue = []
		self.eventCache = {}

	def add_listener(self, listener):
		if DEBUG:
			print("added event listener", listener)
		if hasattr(listener, 'invalid'):
			self.gamobListeners.add(listener)
		else:
			self.listeners.add(listener)

	def remove_listener(self, listener):
		if hasattr(listener, 'invalid'):
			self.gamobListeners.discard(listener)
		else:
			self.listeners.discard(listener)

	def enqueue(self, event, delay):
		'''Queue a message for sending after a delay.

		@param event The event to send.
		@param delay The time to wait, in frames.'''
		def queued_event_key(item):
			return item[1]
		self.eventQueue.append((event, delay))
		self.eventQueue.sort(key=queued_event_key)

	@expose
	def process_queue(self):
		'''Send queued messages that are ready.'''
		if len(self.eventQueue) == 0:
			return

		# Decrement the frame counter for each queued message.
		newQueue = []
		pending = []
		for event, delay in self.eventQueue:
			delay -= 1
			if delay <= 0:
				print("Dispatching", event.message)
				pending.append(event)
			else:
				print("Delaying", event.message, delay)
				newQueue.append((event, delay))

		# Replace the old queue. As the list was iterated over in-order, the new
		# queue should already be sorted.
		self.eventQueue = newQueue

		# Actually send the messages now. Doing this now instead of inside the
		# loop above allows the callee to send another delayed message in
		# response.
		for event in pending:
			self.notify(event)

	def notify(self, event):
		'''Send a message.'''
		if DEBUG:
			print('Sending', event)
		for listener in self.listeners:
			listener.on_event(event)
		for listener in self.gamobListeners:
			listener.on_event(event)
		self.eventCache[event.message] = event

	def replay_last(self, target, message):
		'''Re-send a message. This should be used by new listeners that missed
		out on the last message, so they know what state the system is in.'''

		if message in self.eventCache:
			event = self.eventCache[message]
			target.on_event(event)

#class EventListener:
#	'''Interface for an object that can receive messages.'''
#	def on_event(self, event):
#		pass

class Event:
	def __init__(self, message, body=None):
		self.message = message
		self.body = body

	def __str__(self):
		return "Event(%s, %s)" % (str(self.message), str(self.body))

	def send(self):
		'''Shorthand for bxt.types.EventBus().notify(event).'''
		EventBus().notify(self)

class WeakEvent(Event):
	'''An event whose body may be destroyed before it is read. Use this when
	the body is a game object.'''

	body = weakprop('body')

	def __init__(self, message, body):
		super(WeakEvent, self).__init__(message, body)

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
