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

import bge
from bge import logic
import mathutils

import bxt.types
import bxt.bmath
import bxt.effectors

# The angle to rotate successive ripples by (giving them a random appearance),
# in degrees.
ANGLE_INCREMENT = 81.0
# Extra spacing to bubble spawn points, in Blender units.
BUBBLE_BIAS = 0.4

DEBUG = False

class Water(bxt.types.BX_GameObject, bge.types.KX_GameObject):
	_prefix = ''

	S_INIT = 1
	S_IDLE = 2
	S_FLOATING = 3

	def __init__(self, old_owner):
		'''
		Create a water object that can respond to things touching it. The mesh
		is assumed to be a globally-aligned XY plane that passes through the
		object's origin.
		'''
		self['IsWater'] = True

		self.set_default_prop('RippleInterval', 20)
		self.set_default_prop('DampingFactor', 0.1)
		self.set_default_prop('Buoyancy', 0.1)
		# Colour to use as filter when camera is under water
		# (see Camera.CameraCollider)
		self.set_default_prop('VolumeCol', '#22448880')

		self.InstanceAngle = 0.0
		self.currentFrame = 0

		if DEBUG:
			self.floatMarker = bxt.utils.add_object('VectorMarker', 0)

		self.floatingActors = bxt.types.SafeSet()
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
		decal.setParent(self)

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
		pos += bxt.bmath.getRandomVector() * 0.05

		#
		# Create object.
		#
		bubble = self.scene.addObject('Bubble', self)
		bubble.worldPosition = pos
		self.floatingActors.add(bubble)
		self.set_state(Water.S_FLOATING)

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
		submergedFactor = bxt.bmath.clamp(0.0, 1.0, submergedFactor)

		if not inside:
			# The object is submerged, but its base is outside the water object.
			# Invert the submergedFactor, since it is the object's top that is
			# protruding into the water.
			# This must be a shaped water object (such as honey).
			submergedFactor = 1.0 - submergedFactor

		return submergedFactor

	def apply_damping(self, linV, submergedFactor):
		return bxt.bmath.lerp(linV, bxt.bmath.ZEROVEC, self['DampingFactor'] * submergedFactor)

	def apply_buoyancy(self, actor):
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
				if hasattr(actor, 'on_oxygen_set'):
					actor.on_oxygen_set()
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
			if hasattr(actor, 'on_oxygen_set'):
				actor.on_oxygen_set()

		if submergedFactor <= 0.1 and not self.isBubble(actor):
			# Object has emerged.
			actor['CurrentBuoyancy'] = actor['Buoyancy']
			return submergedFactor

		#
		# Object is partially submerged. Apply acceleration away from the
		# water (up). Acceleration increases linearly with the depth, until the
		# object is fully submerged.
		#
		submergedFactor = bxt.bmath.clamp(0.0, 1.0, submergedFactor)
		accel = mathutils.Vector((0.0, 0.0,
				submergedFactor * actor['CurrentBuoyancy']))
		actor.worldLinearVelocity = bxt.bmath.integrate_v(actor.worldLinearVelocity,
				accel, self['DampingFactor'] * submergedFactor)

		actor.worldAngularVelocity = bxt.bmath.integrate_v(actor.worldAngularVelocity,
				bxt.bmath.ZEROVEC, self['DampingFactor'] * submergedFactor)

		if DEBUG:
			self.floatMarker.worldPosition = actor.worldPosition
			self.floatMarker.localScale = bxt.bmath.ONEVEC * accel

		#
		# Update buoyancy (take on water).
		#
		targetBuoyancy = (1.0 - submergedFactor) * actor['Buoyancy']
		if targetBuoyancy > actor['CurrentBuoyancy']:
			actor['CurrentBuoyancy'] += actor['SinkFactor']
		else:
			actor['CurrentBuoyancy'] -= actor['SinkFactor']

		if hasattr(actor, 'on_float'):
			actor.on_float(self)

		return submergedFactor

	def spawn_ripples(self, actor, force = False):
		if self.isBubble(actor):
			return

		if not force and 'Water_LastFrame' in actor:
			# This is at least the first time the object has touched the water.
			# Make sure it has moved a minimum distance before adding a ripple.
			if actor['Water_LastFrame'] == self.currentFrame:
				actor['Water_CanRipple'] = True

			if not actor['Water_CanRipple']:
				# The object has rippled too recently.
				return

			linV = actor.getLinearVelocity(False)
			if linV.magnitude < actor['MinRippleSpeed']:
				# The object hasn't moved fast enough to cause another event.
				return

		actor['Water_LastFrame'] = self.currentFrame
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

		forceFields = []
		for child in self.children:
			if isinstance(child, bxt.effectors.ForceField):
				forceFields.append(child)

		# Transfer floatation to hierarchy root (since children can't be
		# dynamic). This accounts for the case where an object has started
		# interacting with the water, but then changes its hierarchy.
		old_floating_actors = self.floatingActors.copy()
		self.floatingActors.update(hitActors)
		for actor in self.floatingActors.copy():
			root = actor
			while root.parent != None:
				root = root.parent
			if root is not actor:
				self.floatingActors.remove(actor)
				self.set_defaults(root)
				root['CurrentBuoyancy'] = min(actor['CurrentBuoyancy'], root['Buoyancy'])
				root['Oxygen'] = actor['Oxygen']
				self.floatingActors.add(root)

		# Apply buoyancy to actors.
		for actor in self.floatingActors.copy():
			self.set_defaults(actor)
			submergedFactor = self.apply_buoyancy(actor)

			#
			# Tell the actor how much it is submerged, in case it is not moved
			# using the game engine's velocity model (e.g. if its position is
			# set manually).
			#
			actor['SubmergedFactor'] = submergedFactor

			if submergedFactor < 0.1:
				self.floatingActors.discard(actor)
			elif actor['Oxygen'] <= 0.0 and hasattr(actor, 'drown'):
				actor.drown()
				self.floatingActors.discard(actor)
			else:
				actor['Floating'] = True
				for ff in forceFields:
					ff.touchedSingle(actor, submergedFactor)

		# Reset actors that are no longer floating.
		no_longer_floating = old_floating_actors.difference(self.floatingActors)
		for actor in no_longer_floating:
			actor['Oxygen'] = 1.0
			if hasattr(actor, 'on_oxygen_set'):
				actor.on_oxygen_set()
			actor['Floating'] = False
			actor['CurrentBuoyancy'] = actor['Buoyancy']
			actor['SubmergedFactor'] = 0.0

		if len(self.floatingActors) > 0:
			self.set_state(self.S_FLOATING)
		else:
			self.set_state(self.S_IDLE)

		#
		# Increase the frame counter.
		#
		self.currentFrame = ((self.currentFrame + 1) %
			self['RippleInterval'])

	def set_defaults(self, actor):
		if '_bxt.waterInit' in actor:
			return
		bxt.utils.set_default_prop(actor, 'Oxygen', 1.0)
		if hasattr(actor, 'on_oxygen_set'):
			actor.on_oxygen_set()
		bxt.utils.set_default_prop(actor, 'OxygenDepletionRate', 0.005)
		bxt.utils.set_default_prop(actor, 'Buoyancy', 0.1)
		bxt.utils.set_default_prop(actor, 'CurrentBuoyancy', actor['Buoyancy'])
		bxt.utils.set_default_prop(actor, 'FloatRadius', 1.1)
		bxt.utils.set_default_prop(actor, 'SinkFactor', 0.002)
		bxt.utils.set_default_prop(actor, 'MinRippleSpeed', 1.0)
		actor['_bxt.waterInit'] = True

	@bxt.types.expose
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
		actors = set()
		for s in c.sensors:
			if not s.positive:
				continue
			for ob in s.hitObjectList:
				actors.add(ob)

		#
		# Call Water.on_collision regardless of collisions: this allows for one more
		# frame of processing to sink submerged objects.
		#
		self._on_collision(actors)

	def isBubble(self, actor):
		return actor.name == 'Bubble'

class ShapedWater(Water):
	'''Special water that does not need to be flat.'''

	def __init__(self, owner):
		Water.__init__(self, owner)

	def apply_damping(self, linV, submergedFactor):
		return bxt.bmath.lerp(linV, bxt.bmath.ZEROVEC, self['DampingFactor'])

	def spawn_bubble(self, actor):
		'''No bubbles in shaped water.'''
		pass

	def spawn_ripples(self, actor, force = False):
		'''No ripples in shaped water: too hard to find surface.'''
		pass
