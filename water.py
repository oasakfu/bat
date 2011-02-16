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

import weakref

from bge import logic
import mathutils

import bxt.types
import bxt.math

# The angle to rotate successive ripples by (giving them a random appearance),
# in degrees.
ANGLE_INCREMENT = 81.0
# Extra spacing to bubble spawn points, in Blender units.
BUBBLE_BIAS = 0.4

DEBUG = False

@bxt.types.gameobject('on_collision', prefix='')
class Water(bxt.types.ProxyGameObject):
	S_INIT = 1
	S_IDLE = 2
	S_FLOATING = 3

	def __init__(self, owner):
		'''
		Create a water object that can respond to things touching it. The mesh
		is assumed to be a globally-aligned XY plane that passes through the
		object's origin.
		'''
		bxt.types.ProxyGameObject.__init__(self, owner)
		self['IsWater'] = True

		self.set_default_prop('RippleInterval', 20)
		self.set_default_prop('DampingFactor', 0.1)
		self.set_default_prop('Buoyancy', 1.0)
		# Colour to use as filter when camera is under water
		# (see Camera.CameraCollider)
		self.set_default_prop('VolumeCol', '#22448880')

		self.InstanceAngle = 0.0
		self.CurrentFrame = 0

		if DEBUG:
			self.floatMarker = bxt.utils.add_object('VectorMarker', 0)

		self.FloatingActors = weakref.WeakSet()
		self.set_state(self.S_IDLE)

	def spawn_surface_decal(self, name, position):
		pos = position.copy()
		pos.z = self.worldPosition.z

		#
		# Transform template.
		#
		elr = mathutils.Euler()
		elr.z = self.InstanceAngle
		self.InstanceAngle = self.InstanceAngle + ANGLE_INCREMENT
		oMat = elr.to_matrix()

		decal = bxt.utils.add_object(name, 0)
		decal.worldPosition = pos
		decal.worldOrientation = oMat
		decal.setParent(self.unwrap())

	def spawn_bubble(self, actor):
		if self.isBubble(actor):
			return

		#
		# Transform template.
		#
		vec = actor.getLinearVelocity(False)
		if vec.magnitude <= 0.1:
			vec = mathutils.Vector((0.0, 0.0, -1.0))
		else:
			vec.normalize()

		vec = vec * (actor['FloatRadius'] + BUBBLE_BIAS)
		pos = actor.worldPosition.copy()
		pos -= vec
		pos += bxt.math.getRandomVector() * 0.05

		#
		# Create object.
		#
		bubble = logic.getCurrentScene().addObject('Bubble', self.unwrap())
		bubble = bxt.types.wrap(bubble)
		bubble.worldPosition = pos
		self.FloatingActors.add(bubble)
		self.set_state(self.S_FLOATING)

	def get_submerged_factor(self, actor):
		'''Determine the fraction of the object that is inside the water. This
		works vertically only: if the object touches the water from the side
		(shaped water such as honey), and the centre is outside, the factor will
		be zero.'''

		# Cast a ray out from the actor. If it hits this water object from
		# inside, the actor is considered to be fully submerged. Otherwise, it
		# is fully emerged.

		origin = actor.worldPosition.copy()
		origin.z = origin.z - actor['FloatRadius']
		# Force ray to be vertical.
		through = origin.copy()
		through.z = self.worldPosition.z + 1.0
		vec = through - origin
		ob, hitPoint, normal = actor.rayCast(
			through,			 # to
			origin,			  # from
			0.0,				 # dist
			'IsWater',		   # prop
			1,				   # face
			1					# xray
		)

		if ob == None:
			# No hit; object is not submerged.
			return 0.0

		inside = False
		if (ob):
			if normal.dot(vec) > 0.0:
				# Hit was from inside.
				inside = True

		depth = hitPoint.z - origin.z
		submergedFactor = depth / (actor['FloatRadius'] * 2.0)
		submergedFactor = bxt.math.clamp(0.0, 1.0, submergedFactor)

		if not inside:
			# The object is submerged, but its base is outside the water object.
			# Invert the submergedFactor, since it is the object's top that is
			# protruding into the water.
			# This must be a shaped water object (such as honey).
			submergedFactor = 1.0 - submergedFactor

		return submergedFactor

	def apply_damping(self, linV, submergedFactor):
		return bxt.math.lerp(linV, bxt.math.ZEROVEC, self['DampingFactor'] * submergedFactor)

	def float(self, actor):
		'''Adjust the velocity of an object to make it float on the water.
		
		Returns: True if the object is floating; False otherwise (e.g. if it has
		sunk or emerged fully).
		'''
		#
		# Find the distance to the water from the UPPER END
		# of the object.
		#
		submergedFactor = self.get_submerged_factor(actor)

		if submergedFactor > 0.9 and not self.isBubble(actor):
			# Object is almost fully submerged. Try to cause it to drown.
			o2 = actor['Oxygen']
			if o2 > 0.0:
				o22 = o2 - actor['OxygenDepletionRate']
				o22 = max(0.0, o22)
				actor['Oxygen'] = o22
				if int(o2 * 10) != int(o22 * 10):
					self.spawn_bubble(actor)

		elif submergedFactor < 0.9 and self.isBubble(actor):
			# Bubbles are the opposite: they lose 'Oxygen' when they are not
			# fully submerged.
			actor['Oxygen'] -= actor['OxygenDepletionRate']
			if actor['Oxygen'] <= 0.0:
				self.spawn_surface_decal('Ripple', actor.worldPosition)

		else:
			actor['Oxygen'] = 1.0

		if submergedFactor <= 0.1 and not self.isBubble(actor):
			# Object has emerged.
			actor['CurrentBuoyancy'] = actor['Buoyancy']
			return False

		#
		# Object is partially submerged. Apply acceleration away from the
		# water (up). Acceleration increases linearly with the depth, until the
		# object is fully submerged.
		#
		submergedFactor = bxt.math.clamp(0.0, 1.0, submergedFactor)
		accel = submergedFactor * actor['CurrentBuoyancy']
		linV = actor.getLinearVelocity(False)
		linV.z = linV.z + accel
		linV = self.apply_damping(linV, submergedFactor)
		actor.setLinearVelocity(linV, False)

		angV = actor.getAngularVelocity(False)
		angV = self.apply_damping(angV, submergedFactor)
		actor.setAngularVelocity(angV, False)

		if DEBUG:
			self.floatMarker.worldPosition = actor.worldPosition
			self.floatMarker.localScale = bxt.math.ONEVEC * accel

		#
		# Update buoyancy (take on water).
		#
		targetBuoyancy = (1.0 - submergedFactor) * actor['Buoyancy']
		if targetBuoyancy > actor['CurrentBuoyancy']:
			actor['CurrentBuoyancy'] += actor['SinkFactor']
		else:
			actor['CurrentBuoyancy'] -= actor['SinkFactor']

		return True

	def spawn_ripples(self, actor, force = False):
		if self.isBubble(actor):
			return

		if not force and 'Water_LastFrame' in actor:
			# This is at least the first time the object has touched the water.
			# Make sure it has moved a minimum distance before adding a ripple.
			if actor['Water_LastFrame'] == self.CurrentFrame:
				actor['Water_CanRipple'] = True

			if not actor['Water_CanRipple']:
				# The object has rippled too recently.
				return

			linV = actor.getLinearVelocity(False)
			if linV.magnitude < actor['MinRippleSpeed']:
				# The object hasn't moved fast enough to cause another event.
				return

		actor['Water_LastFrame'] = self.CurrentFrame
		actor['Water_CanRipple'] = False
		self.spawn_surface_decal('Ripple', actor.worldPosition)

	def _on_collision(self, hitActors):
		'''
		Called when an object collides with the water. Creates ripples and
		causes objects to float or sink. Should only be called once per frame.
		'''
		for actor in hitActors:
			if not actor.invalid:
				self.spawn_ripples(actor, False)

		# Transfer floatation to hierarchy root (since children can't be
		# dynamic).
		self.FloatingActors.update(hitActors)
		for actor in self.FloatingActors.copy():
			if actor.invalid:
				self.FloatingActors.remove(actor)
				continue

			if actor.parent != None:
				self.FloatingActors.remove(actor)
				parent = bxt.types.wrap(actor.parent)
				parent['CurrentBuoyancy'] = actor['CurrentBuoyancy']
				actor['CurrentBuoyancy'] = actor['Buoyancy']
				parent['Oxygen'] = actor['Oxygen']
				actor['Oxygen'] = 1.0
				self.FloatingActors.add(parent)

		# Apply buoyancy to actors.
		for actor in self.FloatingActors.copy():
			self.set_defaults(actor)
			floating = self.float(actor)
			actor['Floating'] = floating
			if not floating:
				self.FloatingActors.discard(actor)

		if len(self.FloatingActors) > 0:
			self.set_state(self.S_FLOATING)
		else:
			self.set_state(self.S_IDLE)

		#
		# Increase the frame counter.
		#
		self.CurrentFrame = ((self.CurrentFrame + 1) %
			self['RippleInterval'])

	def set_defaults(self, actor):
		if '_bxt.waterInit' in actor:
			return
		actor.set_default_prop('Oxygen', 1.0)
		actor.set_default_prop('OxygenDepletionRate', 0.005)
		actor.set_default_prop('Buoyancy', 3.0)
		actor.set_default_prop('CurrentBuoyancy', actor['Buoyancy'])
		actor.set_default_prop('FloatRadius', 1.1)
		actor.set_default_prop('SinkFactor', 0.002)
		actor.set_default_prop('MinRippleSpeed', 1.0)
		actor['_bxt.waterInit'] = True

	@bxt.utils.controller_cls
	def on_collision(self, c):
		'''
		Respond to collisions with Actors. Ripples will be created, and 

		Sensors:
		<one+>: Near (e.g. Collision) sensors that detect when the water is hit by
				an object. They should respond to any object, but only Actors will
				be processed. Set it to positive pulse mode, f:0.
		'''
		#
		# Create a list of all colliding objects.
		#
		actors = weakref.WeakSet()
		for s in c.sensors:
			if not s.positive:
				continue
			for ob in s.hitObjectList:
				actors.add(bxt.types.wrap(ob))

		#
		# Call Water.on_collision regardless of collisions: this allows for one more
		# frame of processing to sink submerged objects.
		#
		self._on_collision(actors)

	def isBubble(self, actor):
		return actor.name == 'Bubble'

@bxt.types.gameobject()
class ShapedWater(Water):
	'''Special water that does not need to be flat.'''
	
	def __init__(self, owner):
		Water.__init__(self, owner)

	def apply_damping(self, linV, submergedFactor):
		return bxt.math.lerp(linV, bxt.math.ZEROVEC, self['DampingFactor'])

	def spawn_bubble(self, actor):
		'''No bubbles in shaped water.'''
		pass

	def spawn_ripples(self, actor, force = False):
		'''No ripples in shaped water: too hard to find surface.'''
		pass
