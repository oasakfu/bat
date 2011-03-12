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

'''Wraps some useful features of the game engine API to allow it to be extended.
This makes it easy to add functionality to KX_GameObjects. Use it like this:
 
 	@bxt.types.gameobject('update', prefix='ED_')
 	class ExtensionDemo(bxt.types.ProxyGameObject):
 		@bxt.utils.all_sensors_positive
 		def update(self):
 			currentpos = self.worldPosition.x
 			currentpos += 1.0
 			currentpos %= 5.0
 			self.worldPosition.x = currentpos
 
 Note that:
  - ExtensionDemo inherits all KX_GameObject attributes.
  - Call module.ExtensionDemo from a Python controller to bind it to an object.
  - Call module.ED_update to run ExtensionDemo.update for a given object.
  - ExtensionDemo.update will only execute if all sensors are positive.
'''

import sys
import inspect
from functools import wraps
import weakref

import bge

import bxt.utils

def has_wrapper(owner):
	if owner == None:
		return False
	else:
		return '__wrapper__' in owner

def get_wrapper(owner):
	try:
		return owner['__wrapper__']
	except KeyError as e:
		raise KeyError('The object %s is not wrapped.' % owner.name) from e

def is_wrapper(ob):
	return hasattr(ob, 'unwrap')

def unwrap(ob):
	if hasattr(ob, 'unwrap'):
		return ob.unwrap()
	else:
		return ob

class weakprops:
	'''Creates attributes on an object that store weak references to whatever
	is assigned to them. If the assignee is deleted, the corresponding attribute
	will be set to None. The initial value is also None. Example usage:

	@bxt.types.weakprops('foo', 'bar')
	class Baz:
		def bork(self, gameObject):
			self.foo = gameObject
			self.bar = gameObject.parent

		def update(self):
			if self.foo != None:
				self.foo.worldPosition.z += 1
	'''

	def __init__(self, *propnames):
		self.propnames = propnames
		self.converted = False

	def __call__(self, cls):
		if not self.converted:
			self.create_props(cls)
			self.converted = True
		return cls

	def create_props(self, cls):
		for name in self.propnames:
			hiddenName = '_wp_' + name
			self.create_prop(cls, name, hiddenName)

	def create_prop(self, cls, name, hiddenName):
		def wp_getter(slf):
			value = getattr(slf, hiddenName)
			if value != None:
				return value()
			else:
				return None

		def wp_setter(slf, value):
			def autoremove(ref):
				setattr(slf, hiddenName, None)

			if value == None:
				setattr(slf, hiddenName, None)
			else:
				setattr(slf, hiddenName, weakref.ref(value, autoremove))

		def wp_del(slf):
			delattr(slf, hiddenName)

		setattr(cls, hiddenName, None)
		setattr(cls, name, property(wp_getter, wp_setter, wp_del))

def expose_fun(f):
	'''Expose a method as a top-level function. Must be used in conjunction with
	the GameOb metaclass.'''
	f._expose = True
	return f

class GameOb(type):
	'''A metaclass that makes a class neatly wrap game objects:
	 - The class constructor can be called from a logic brick, to wrap the
	   logic brick's owner.
	 - Methods marked with the expose_fun decorator will be promoted to
	   top-level functions, and can therefore be called from a logic brick.
	For example:

	class Foo(bge.types.KX_GameObject, metaclass=bxt.types.GameOb):
		def __init__(self, old_owner):
			# Do not use old_owner; it will have been destroyed! Also, you don't
			# need to call KX_GameObject.__init__.
			pass

		@bxt.types.expose_fun
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
		def method_wrapper():
			o = bge.logic.getCurrentController().owner
			return method(o)

		method_wrapper.__name__ = '%s%s' % (prefix, methodName)
		method_wrapper.__doc__ = method.__doc__
		setattr(module, method_wrapper.__name__, method_wrapper)

class expose:
	'''Exposes class methods as top-level module functions.

	This decorator accepts any number of strings as arguments. Each string
	should be the name of a member to expose as a top-level function - this
	makes it available to logic bricks in the BGE. The class name is used as a
	function prefix. For example, consider the following class definition in a
	module called 'module':

	@expose('update', prefix='f_')
	class Foo(bge.types.KX_GameObject):
		def __init__(self, *args, **kwargs):
			bge.types.KX_GameObject.__init__(self, *args, **kwargs)
		def update(self):
			self.worldPosition.z += 1.0

	A game object can be bound to the 'Foo' class by calling, from a Python
	controller, 'module.Foo'. The 'update' function can then be called with
	'module.f_update'. The 'prefix' argument is optional; if omitted, the
	functions will begin with <class name>_, e.g. 'Foo_update'.

	This decorator requires arguments; i.e. use '@expose()' instead of
	'@expose'.'''

	def __init__(self, *externs, prefix=None):
		self.externs = externs
		self.converted = False
		self.prefix = prefix

	def __call__(self, cls):
		if not self.converted:
			self.create_interface(cls)
			self.converted = True

		# We only need to override __new__ here; we can't pass the old
		# KX_GameObject instance as "owner" to __init__, because it
		# will have been destroyed (and replaced by) this new one!
		old_new = cls.__new__
		def new_new(inst_cls, owner=None):
			if owner == None:
				owner = bge.logic.getCurrentController().owner
			if 'template' in owner:
				owner = bxt.utils.replaceObject(owner['template'], owner)
			return old_new(cls, owner)
		cls.__new__ = new_new

		return cls

	def create_interface(self, cls):
		'''Expose the nominated methods as top-level functions in the containing
		module.'''
		prefix = self.prefix
		if prefix == None:
			prefix = cls.__name__ + '_'

		module = sys.modules[cls.__module__]

		for methodName in self.externs:
			f = getattr(cls, methodName)
			self.expose_method(methodName, f, module, prefix)

	def expose_method(self, methodName, method, module, prefix):
		'''Expose a single method as a top-level module funciton. This must
		be done in a separate function so that it may act as a closure.'''
		def method_wrapper():
			o = bge.logic.getCurrentController().owner
			return method(o)

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

class gameobject:
	'''Extends a class to wrap KX_GameObjects. This decorator accepts any number
	of strings as arguments. Each string should be the name of a member to
	expose as a top-level function - this makes it available to logic bricks in
	the BGE. The class name is used as a function prefix. For example, consider
	the following class definition in a module called 'Module':

	@gameobject('update', prefix='f_')
	class Foo(ProxyGameObject):
		def __init__(self, owner):
			ProxyGameObject.__init__(self, owner)
		def update(self):
			self.worldPosition.z += 1.0

	A game object can be bound to the 'Foo' class by calling, from a Python
	controller, 'Module.Foo'. The 'update' function can then be called with
	'Module.f_update'. The 'prefix' argument is optional; if omitted, the
	functions will begin with <class name>_, e.g. 'Foo_update'.

	This decorator requires arguments; i.e. use '@gameobject()' instead of
	'@gameobject'.'''

	def __init__(self, *externs, prefix=None):
		self.externs = externs
		self.converted = False
		self.prefix = prefix

	@bxt.utils.all_sensors_positive
	def __call__(self, cls):
		if not self.converted:
			self.create_interface(cls)
			self.converted = True

		old_init = cls.__init__
		def new_init(self, owner=None):
			if owner == None:
				owner = bge.logic.getCurrentController().owner
			if 'template' in owner:
				owner = bxt.utils.replaceObject(owner['template'], owner)
			old_init(self, owner)
			owner['__wrapper__'] = self
		cls.__init__ = new_init

		return cls

	def create_interface(self, cls):
		'''Expose the nominated methods as top-level functions in the containing
		module.'''
		prefix = self.prefix
		if prefix == None:
			prefix = cls.__name__ + '_'

		module = sys.modules[cls.__module__]

		for methodName in self.externs:
			f = getattr(cls, methodName)
			self.expose_method(methodName, f, module, prefix)

	def expose_method(self, methodName, method, module, prefix):
		def method_wrapper(*args, **kwargs):
			o = bge.logic.getCurrentController().owner
			instance = get_wrapper(o)
			args = list(args)
			args.insert(0, instance)
			return method(*args, **kwargs)

		method_wrapper.__name__ = '%s%s' % (prefix, methodName)
		method_wrapper.__doc__ = method.__doc__
		setattr(module, method_wrapper.__name__, method_wrapper)

def dereference_arg1(f):
	'''Function decorator: un-wraps the first argument of a function if
	possible. If the argument is not wrapped, it is passed through unchanged.'''
	@wraps(f)
	def f_new(*args, **kwargs):
		if is_wrapper(args[1]):
			args = list(args)
			args[1] = args[1].unwrap()
		return f(*args, **kwargs)
	return f_new

def dereference_arg2(f):
	'''Function decorator: un-wraps the second argument of a function if
	possible. If the argument is not wrapped, it is passed through unchanged.'''
	@wraps(f)
	def f_new(*args, **kwargs):
		if is_wrapper(args[2]):
			args = list(args)
			args[2] = args[2].unwrap()
		return f(*args, **kwargs)
	return f_new

def get_reference(f):
	'''Function decorator: Changes the function to return the wrapper of a
	wrapped object. If the object has no wrapper, the return value is
	unchanged.'''
	@wraps(f)
	def f_new(*args, **kwargs):
		res = f(*args, **kwargs)
		if has_wrapper(res):
			return get_wrapper(res)
		else:
			return res
	return f_new

# Functions that are used in list manipulation.
LIST_FUNCTIONS = ['__getitem__', '__setitem__', '__delitem__', '__contains__',
				'__len__']

class mixin:
	'''Wraps all the functions of one class so that they may be called from
	another. The class that this is applied to must provide a link back to the
	wrapped object via a unwrap method.'''

	def __init__(self, base, privates=[], refs=[], derefs=[]):
		'''
		@param base The base class to mix-in.
		@param privates Normally, private members are not mixed-in. This
			parameter is a whitelist of private member names to mix in anyway.
		@param refs Names of members that can return a wrapped object.
		@param derefs Names of members that can accept a wrapped object as their
			first argument, or as the value to assign (in the case of
			properties).
		'''
		self.base = base
		self.privates = privates
		self.refs = refs
		self.derefs = derefs
		self.converted = False

	def __call__(self, cls):
		for name, member in inspect.getmembers(self.base):
			self.import_member(cls, name, member)

		def new_repr(slf):
			return "%s(%s)" % (slf.__class__.__name__, repr(slf.unwrap()))
		new_repr.__name__ = '__repr__'
		setattr(cls, '__repr__', new_repr)

		return cls

	def import_member(self, cls, name, member):
		'''Wrap a single member.'''
		if name.startswith('__'):
			if not name in self.privates:
				# This is a private member. Don't wrap it - unless it's a
				# dictionary accessor, in which case we want it!
				return

		if hasattr(cls, name):
			# Assume the class intended to override the attribute.
			return

		if inspect.isroutine(member):
			self.import_method(cls, name, member)
		elif inspect.isgetsetdescriptor(member):
			self.import_property(cls, name, member)

	def import_method(self, cls, name, member):
		'''Wrap a method. This creates a function of the same name in the target
		class.'''
		def proxy_fn(slf, *argc, **argv):
			ret = member(slf.unwrap(), *argc, **argv)
			return ret

		# Wrap/unwrap args and return values.
		if name in self.derefs:
			proxy_fn = dereference_arg1(proxy_fn)
		if name in self.refs:
			proxy_fn = get_reference(proxy_fn)

		proxy_fn.__doc__ = member.__doc__
		proxy_fn.__name__ = name

		setattr(cls, name, proxy_fn)

	def import_property(self, cls, name, member):
		'''Wrap a property or member variable. This creates a property in the
		target class; calling the property's get and set methods operate on the
		attribute with the same name in the wrapped object.'''
		def _get(slf):
			return getattr(slf.unwrap(), name)
		def _set(slf, value):
			setattr(slf.unwrap(), name, value)

		# Wrap/unwrap args and return values.
		if name in self.derefs:
			_set = dereference_arg1(_set)
		if name in self.refs:
			_get = get_reference(_get)

		p = property(_get, _set, doc=member.__doc__)
		setattr(cls, name, p)

@mixin(bge.types.CListValue,
	privates=LIST_FUNCTIONS,
	refs=['__getitem__', 'from_id', 'get'],
	derefs=['__contains__', 'append', 'count', 'index'])
class ProxyCListValue:
	'''Wraps a bge.types.CListValue. When getting a value from the list, its
	wrapper (e.g. a ProxyGameObject) will be returned if one is available.'''
	def __init__(self, owner):
		self._owner = owner

	def unwrap(self):
		return self._owner

class _ProxyObjectBase:
	def __init__(self, owner):
		self._owner = owner

	def unwrap(self):
		return self._owner

	# CListValues need to be wrapped every time, because every time it's a new
	# instance.
	def _getChildren(self):
		return ProxyCListValue(self.unwrap().children)
	children = property(_getChildren)

	# CListValues need to be wrapped every time, because every time it's a new
	# instance.
	def _getChildrenRecursive(self):
		return ProxyCListValue(self.unwrap().childrenRecursive)
	childrenRecursive = property(_getChildrenRecursive)

	# This function is special: the returned object may be wrapped, but it is
	# inside a tuple.
	@dereference_arg1
	@dereference_arg2
	def rayCast(self, *args, **kwargs):
		ob, p, n = self.unwrap().rayCast(*args, **kwargs)
		if ob != None and has_wrapper(ob):
			ob = get_wrapper(ob)
		return ob, p, n

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
		bxt.utils.set_default_prop(self, propName, defaultValue)

@gameobject()
@mixin(bge.types.KX_GameObject,
	privates=LIST_FUNCTIONS,
	refs=['parent', 'rayCastTo'],
	derefs=['getDistanceTo', 'getVectTo', 'setParent', 'rayCastTo', 'reinstancePhysicsMesh'])
class ProxyGameObject(_ProxyObjectBase):
	'''Wraps a bge.types.KX_GameObject. You can directly use any attributes
	defined by KX_GameObject, e.g. self.worldPosition.z += 1.0.'''
	def __init__(self, owner):
		_ProxyObjectBase.__init__(self, owner)

@gameobject()
@mixin(bge.types.KX_Camera,
	privates=LIST_FUNCTIONS,
	refs=['parent', 'rayCastTo'],
	derefs=['getDistanceTo', 'getVectTo', 'setParent', 'rayCastTo', 'reinstancePhysicsMesh'])
class ProxyCamera(_ProxyObjectBase):
	def __init__(self, owner):
		_ProxyObjectBase.__init__(self, owner)

@gameobject()
class ProxyArmature(ProxyGameObject):
	def __init__(self, owner):
		ProxyGameObject.__init__(self, owner)

def wrap(ob, defaultType=ProxyGameObject):
	if is_wrapper(ob):
		return ob
	elif has_wrapper(ob):
		return get_wrapper(ob)
	else:
		return defaultType(ob)

def get_wrapped_cursor():
	'''Gets the 'Cursor' object in the current scene. This object can be used
	when you need to call a method on a KX_GameObject, but you don't care which
	object it gets called on.

	See also bxt.utils.get_cursor.
	'''

	return wrap(bxt.utils.get_cursor())
