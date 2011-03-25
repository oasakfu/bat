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

import bge

import bxt.utils

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
