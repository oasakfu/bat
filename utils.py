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

from functools import wraps

import bge

def replaceObject(name, original, time = 0):
	'''Like bge.types.scene.addObject, but:
	 - Transfers the properies of the original to the new object, and
	 - Deletes the original after the new one is created.'''
	scene = bge.logic.getCurrentScene()
	newObj = scene.addObject(name, original, time)
	for prop in original.getPropertyNames():
		newObj[prop] = original[prop]
	if original.parent != None:
		newObj.setParent(original.parent)
	original.endObject()
	return newObj

def owner(f):
	'''Decorator. Passes a single argument to a function: the owner of the
	current controller.'''
	@wraps(f)
	def f_owner(owner=None):
		if owner is None:
			owner = bge.logic.getCurrentController().owner
		elif owner.__class__.__name__ == 'SCA_PythonController':
			owner = owner.owner
		return f(owner)
	return f_owner

def owner_cls(f):
	@wraps(f)
	def f_owner_cls(self, owner=None):
		if owner is None:
			owner = bge.logic.getCurrentController().owner
		elif owner.__class__.__name__ == 'SCA_PythonController':
			owner = owner.owner
		return f(self, owner)
	return f_owner_cls

def controller(f):
	'''Decorator. Passes a single argument to a function: the current
	controller.'''
	@wraps(f)
	def f_controller(c=None):
		if c is None:
			c = bge.logic.getCurrentController()
		return f(c)
	return f_controller

def controller_cls(f):
	'''Decorator. Passes a single argument to a function: the current
	controller.'''
	@wraps(f)
	def f_controller_cls(self, c=None):
		if c is None:
			c = bge.logic.getCurrentController()
		return f(self, c)
	return f_controller_cls

@controller
def allSensorsPositive(c):
	'''Test whether all sensors are positive.

	Parameters:
	c: A controller.

	Returns: True if all sensors are positive.'''
	for s in c.sensors:
		if not s.positive:
			return False
	return True

@controller
def someSensorPositive(c):
	'''Test whether at least one sensor is positive.

	Parameters:
	c: A controller.

	Returns: True if at least one sensor is positive.'''
	for s in c.sensors:
		if s.positive:
			return True
	return False

def all_sensors_positive(f):
	'''Decorator. Only calls the function if all sensors are positive.'''
	@wraps(f)
	def f_all_sensors_positive(*args, **kwargs):
		if not allSensorsPositive():
			return
		return f(*args, **kwargs)
	return f_all_sensors_positive

def some_sensors_positive(f):
	'''Decorator. Only calls the function if one ore more sensors are
	positive.'''
	@wraps(f)
	def f_some_sensors_positive(*args, **kwargs):
		if not someSensorPositive():
			return
		return f(*args, **kwargs)
	return f_some_sensors_positive

def get_cursor():
	'''Gets the 'Cursor' object in the current scene. This object can be used
	when you need to call a method on a KX_GameObject, but you don't care which
	object it gets called on.'''

	return bge.logic.getCurrentScene().objects['Cursor']

def add_object(name, time = 0):
	'''Like KX_Scene.addObject, but doesn't need an existing object to position
	it. This uses the scene's cursor object (see get_cursor).
	'''

	scene = bge.logic.getCurrentScene()
	return scene.addObject(name, get_cursor(), time)

def set_default_prop(ob, propName, value):
	'''Ensure a game object has the given property.

	Parameters:
	ob:       A KX_GameObject.
	propName: The property to check.
	value:    The value to assign to the property if it dosen't exist yet.
	'''
	if propName not in ob:
		ob[propName] = value

def add_state(ob, state):
	'''Add a set of states to the object's state.'''
	stateBitmask = 1 << (state - 1)
	ob.state |= stateBitmask

def rem_state(ob, state):
	'''Remove a state from the object's state.'''
	stateBitmask = 1 << (state - 1)
	ob.state &= (~stateBitmask)

def set_state(ob, state):
	'''Set the object's state. All current states will be un-set and replaced
	with the one specified.'''
	stateBitmask = 1 << (state - 1)
	ob.state = stateBitmask

def has_state(ob, state):
	'''Test whether the object is in the specified state.'''
	stateBitmask = 1 << (state - 1)
	return (ob.state & stateBitmask) != 0

def get_scene(ob):
	'''Get the scene that this object exists in. Sometimes this is preferred
	over bge.logic.getCurrentScene, e.g. if this object is responding to an
	event sent from another scene.'''
	for sce in bge.logic.getSceneList():
		if ob in sce.objects:
			return sce
	raise ValueError("Object does not belong to any scene.")

def iterate_verts(ob, step=1):
	'''Yields each vertex in an object's mesh. Warning this is slow!'''
	me = ob.meshes[0]
	for mi in range(len(me.materials)):
		for vi in range(0, me.getVertexArrayLength(mi), step):
			yield me.getVertex(mi, vi)

def iterate_polys(ob, step=1):
	'''Yields each vertex in an object's mesh. Warning this is slow!'''
	me = ob.meshes[0]
	for pi in range(0, me.numPolygons, step):
		yield me.getPolygon(pi)

def iterate_poly_verts(mesh, poly, step=1):
	'''Yields each vertex in an object's mesh. Warning this is slow!'''
	mi = poly.getMaterialIndex()
	for vi in range(0, poly.getNumVertex(), step):
		vj = poly.getVertexIndex(vi)
		yield mesh.getVertex(mi, vj)
