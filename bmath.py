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

import math

import bge
import mathutils

import bat.utils
import bat.render
import bat.bats

DEBUG = False

XAXIS  = mathutils.Vector([1.0, 0.0, 0.0])
YAXIS  = mathutils.Vector([0.0, 1.0, 0.0])
ZAXIS  = mathutils.Vector([0.0, 0.0, 1.0])
ORIGIN = mathutils.Vector([0.0, 0.0, 0.0])
ZEROVEC = ORIGIN
ONEVEC = mathutils.Vector([1.0, 1.0, 1.0])
EPSILON = 0.000001
MINVECTOR = mathutils.Vector([0.0, 0.0, EPSILON])

def lerp(a, b, fac):
	'''
	Linearly interpolate between two values. Works for scalars and vectors.

	Parameters:
	a:   The value to interpolate from.
	b:   The value to interpolate to.
	fac: The amount that the result should resemble b.

	Returns: a if fac == 0.0; b if fac == 1.0; a value in between otherwise.
	'''
	return a + ((b - a) * fac)

def unlerp(a, b, value):
	'''Find how far between two numbers a value is.'''
	if a.__class__ == mathutils.Vector:
		_, frac = mathutils.geometry.intersect_point_line(value, a, b)
		return frac
	else:
		return (value - a) / (b - a)

class LinearInterpolator:
	'''Calculates a linear interpolation in discrete steps.'''
	def __init__(self, a, b, rate):
		self.a = a
		self.b = b
		self.rate = rate
		self.clamp = clamp

	@staticmethod
	def from_duration(a, b, duration):
		rate = 1 / (bge.logic.getLogicTicRate() * duration)
		return LinearInterpolator(a, b, rate)

	def interpolate(self, current_value):
		frac = unlerp(self.a, self.b, current_value)
		frac += self.rate
		if self.clamp and frac < 0:
			frac = 0
		if frac > 1:
			frac = 1
		return bat.bmath.lerp(self.a, self.b, frac)

def smerp(currentDelta, currentValue, target, speedFactor, responsiveness):
	'''
	Smooth exponential average interpolation
	For each time step, try to move toward the target by some fraction of
	the distance (as is the case for normal exponential averages). If this
	would result in a positive acceleration, take a second exponential
	average of the acceleration. The resulting motion has smooth acceleration
	and smooth deceleration, with minimal oscillation.

	@see: integrate
	'''

	targetDelta = (target - currentValue) * speedFactor
	if (targetDelta * targetDelta > currentDelta * currentDelta):
		currentDelta = currentDelta * (1.0 - responsiveness) + targetDelta * responsiveness
	else:
		currentDelta = targetDelta

	currentValue = currentValue + currentDelta
	return currentDelta, currentValue

def integrate(pos, vel, accel, damp):
	'''
	Apply acceleration and damping to a position and velocity.
	@param pos: The current position (scalar or vector of degree N).
	@param vel: The current velocity (scalar or vector of degree N).
	@param accel: The acceleration (scalar or vector of degree N).
	@param damp: The damping (scalar).
	@return: tuple(new position, new velocity).
	'''
	vel_new = (vel + accel) * (1.0 - damp)
	pos_new = pos + vel_new
	return pos_new, vel_new

def integrate_v(vel, accel, damp):
	'''
	Apply acceleration and damping to a velocity.
	@param vel: The current velocity (scalar or vector of degree N).
	@param accel: The acceleration (scalar or vector of degree N).
	@param damp: The damping (scalar).
	@return: new velocity.
	'''
	vel_new = (vel + accel) * (1.0 - damp)
	return vel_new

def approach_one(x, c):
	'''Shift a value to be in the range 0.0 - 1.0. The result increases
	monotonically. For low values, the result will be close to zero, and will
	increase quickly. High values will be close to one, and will increase
	slowly.

	To visualise this function, try it in gnuplot:
		f(x, c) =  1.0 - (1.0 / ((x + (1.0 / c)) * c))
		plot [0:100] f(x, 0.5)

	Parameters:
	x: The value to shift. 0.0 <= x.
	c: An amount to scale the result by.

	Returns: the shifted value, y. 0.0 <= y < 1.0.'''

	return 1.0 - (1.0 / ((x + (1.0 / c)) * c))

def safe_invert(x, c = 2.0):
	'''
	Invert a value, but ensure that the result is not infinity. Only works for
	positive numbers.

	To visualise this function, try it in gnuplot:
		f(x, c) = 1.0 / ((x * c) + 1.0)
		plot [0:1] f(x, 2.0)

	Parameters:
	x: The value to invert. 0.0 <= x
	c: An amount to scale the result by.

	Returns: the inverted value, y. 0.0 < y <= 1.0.'''

	return 1.0 / ((x * c) + 1.0)

def clamp(lower, upper, value):
	'''Ensure a value is within the given range.

	Parameters:
	lower: The lower bound.
	upper: The upper bound.
	value: The value to clamp.'''

	return min(upper, max(lower, value))

def manhattan_dist(pA, pB):
	'''Get the Manhattan distance between two points (the sum of the vector
	components).'''

	dx = abs(pA[0] - pB[0])
	dy = abs(pA[1] - pB[1])
	dz = abs(pA[2] - pB[2])

	return dx + dy + dz

def to_local(referential, point):
	'''Transform 'point' (specified in world space) into the coordinate space of
	the object 'referential'.

	Parameters:
	referential: The object that defines the coordinate space to transform to.
	             (KX_GameObject)
	point:       The point, in world space, to transform. (mathutils.Vector)
	'''

	return referential.worldTransform.inverted() * point

def to_world(referential, point):
	'''Transform 'point' into world space. 'point' must be specified in the
	coordinate space of 'referential'.

	Parameters:
	referential: The object that defines the coordinate space to transform from.
	             (KX_GameObject)
	point:       The point, in local space, to transform. (mathutils.Vector)
	'''

	return referential.worldTransform * point

def to_local_vec(referential, direction):
	return referential.worldOrientation.inverted() * direction

def to_world_vec(referential, direction):
	'''Transform direction vector 'dir' into world space. 'dir' must be
	specified in the coordinate space of 'referential'.

	Parameters:
	referential: The object that defines the coordinate space to transform from.
	             (KX_GameObject)
	point:       The point, in local space, to transform. (mathutils.Vector)
	'''

	return referential.worldOrientation * direction

def copy_transform(source, target):
	target.worldPosition = source.worldPosition
	target.worldOrientation = source.worldOrientation

def reset_orientation(ob):
	orn = mathutils.Quaternion()
	orn.identity()
	ob.worldOrientation = orn

def ray_cast_p2p(objto, objfrom, dist = 0.0, prop = ''):
	face = 1
	xray = 1
	poly = 0
	return bat.utils.get_cursor().rayCast(objto, objfrom, dist, prop,
			face, xray, poly)

def slow_copy_rot(o, goal, factor):
	'''Slow parenting (Rotation only). 'o' will copy the rotation of the 'goal'.
	'o' must have a SlowFac property: 0 <= SlowFac <= 1. Low values will result
	in slower and smoother movement.
	'''

	goalOrn = goal.worldOrientation.to_quaternion()
	orn = o.worldOrientation.to_quaternion()
	orn = orn.slerp(goalOrn, factor)
	#orn = orn.to_matrix()

	o.localOrientation = orn

def slow_copy_loc(o, goal, factor):
	'''Slow parenting (Rotation only). 'o' will copy the position of the 'goal'.
	'o' must have a SlowFac property: 0 <= SlowFac <= 1. Low values will result
	in slower and smoother movement.
	'''

	goalPos = goal.worldPosition
	pos = o.worldPosition

	o.worldPosition = lerp(pos, goalPos, factor)

def set_rel_orn(ob, target, ref):
	'''Sets the orientation of 'ob' to match that of 'target' using 'ref' as the
	referential. The final orientation will be offset from 'target's by the
	difference between 'ob' and 'ref's orientations.
	'''

	oOrn = ob.worldOrientation

	rOrn = mathutils.Matrix(ref.worldOrientation)
	rOrn.invert()

	localOrn = rOrn * oOrn

	ob.localOrientation = target.worldOrientation * localOrn

def set_rel_pos(ob, target, ref):
	'''Sets the position of 'ob' to match that of 'target' using 'ref' as the
	referential. The final position will be offset from 'target's by the
	difference between 'ob' and 'ref's positions.
	'''

	offset = ref.worldPosition - ob.worldPosition
	ob.worldPosition = target.worldPosition - offset

class DistanceKey:
	'''A key function for sorting lists of objects based on their distance from
	some reference point.
	'''

	def __init__(self, referencePoint):
		self.referencePoint = referencePoint

	def __call__(self, ob):
		return ob.getDistanceTo(self.referencePoint)

class ZKey:
	'''Sorts objects into ascending z-order.'''
	def __call__(self, ob):
		return ob.worldPosition.z

def quadNormal(p0, p1, p2, p3):
	'''Find the normal of a 4-sided face.
	@deprecated: Use mathutils.geometry.normal'''
	# Use the diagonals of the face, rather than any of the sides. This ensures
	# all vertices are accounted for, and doesn't require averaging.
	va = p0 - p2
	vb = p1 - p3
	normal = va.cross(vb)
	normal.normalize()

	if DEBUG:
		centre = (p0 + p1 + p2 + p3) / 4.0
		bge.render.drawLine(centre, centre + normal, bat.render.RED.xyz)
		bat.render.draw_polyline([p0, p1, p2, p3], bat.render.GREEN, cyclic=True)

	return normal

def triangleNormal(p0, p1, p2):
	'''Find the normal of a 3-sided face.
	@deprecated: Use mathutils.geometry.normal'''
	va = p1 - p0
	vb = p2 - p0
	normal = va.cross(vb)
	normal.normalize()

	if DEBUG:
		centre = (p0 + p1 + p2) / 3.0
		bge.render.drawLine(centre, centre + normal, bat.render.RED.xyz)
		bat.render.draw_polyline([p0, p1, p2], bat.render.GREEN, cyclic=True)

	return normal

def getRandomVector():
	vec = mathutils.Vector((bge.logic.getRandomFloat() - 0.5,
		bge.logic.getRandomFloat() - 0.5,
		bge.logic.getRandomFloat() - 0.5))
	vec.normalize()
	return vec

class Box2D:
	'''A 2D bounding box.'''

	def __init__(self, xLow, yLow, xHigh, yHigh):
		self.xLow = xLow
		self.yLow = yLow
		self.xHigh = xHigh
		self.yHigh = yHigh

	def intersect(self, other):
		if other.xHigh < self.xHigh:
			self.xHigh = other.xHigh
		if other.yHigh < self.yHigh:
			self.yHigh = other.yHigh

		if other.xLow > self.xLow:
			self.xLow = other.xLow
		if other.yLow > self.yLow:
			self.yLow = other.yLow

		#
		# Ensure box is not inside-out.
		#
		if self.xLow > self.xHigh:
			self.xLow = self.xHigh
		if self.yLow > self.yHigh:
			self.yLow = self.yHigh

	def get_area(self):
		w = self.xHigh - self.xLow
		h = self.yHigh - self.yLow
		return w * h

	def __repr__(self):
		return "Box(x={:g}, y={:g}), a={:g})".format(self.xHigh - self.xLow,
				self.yHigh - self.yLow, self.get_area())

class ArcRay(bat.bats.BX_GameObject, bge.types.KX_GameObject):
	'''Like a Ray sensor, but the detection is done along an arc. The arc
	rotates around the y-axis, starting from the positive z-axis and sweeping
	around to the positive x-axis.'''

	RADIUS = 2.0
	ANGLE = 180.0
	RESOLUTION = 6

	def __init__(self, old_owner):
		self.set_default_prop('angle', ArcRay.ANGLE)
		self.set_default_prop('resolution', ArcRay.RESOLUTION)
		self.set_default_prop('radius', ArcRay.RADIUS)

		try:
			self.prop = self['prop']
		except KeyError:
			self.prop = ""

		self._createPoints()
		self.lastHitPoint = ORIGIN.copy()
		self.lastHitNorm = ZAXIS.copy()

		if DEBUG:
			self.marker = bat.utils.add_object('PointMarker', 0)

	def _createPoints(self):
		'''Generate an arc of line segments to cast rays along.'''
		self.path = []

		revolutions = self['angle'] / 360.0
		endAngle = math.radians(self['angle'])

		numSegments = int(math.ceil(revolutions * self['resolution']))
		increment = endAngle / numSegments
		if DEBUG:
			print(numSegments, increment)

		for i in range(numSegments + 1):
			angle = increment * i
			point = mathutils.Vector()
			point.x = math.sin(angle) * self['radius']
			point.z = math.cos(angle) * self['radius']
			self.path.append(point)
		try:
			self.raylen = (self.path[1] - self.path[0]).magnitude
		except IndexError:
			self.raylen = 0.0

	def getHitPosition(self):
		"""Return the hit point of the first child ray that hits.
		If none hit, the default value of the first ray is returned."""
		ob = None
		norm = None

		# Save a bit of time by reusing matrices (instead of using to_world etc
		# functions.
		refMat = self.worldTransform
		refOrn = refMat.to_quaternion()
		refMatInv = refMat.inverted()
		refOrnInv = refMatInv.to_quaternion()

		worldPath = []
		for point in self.path:
			worldPath.append(refMat * point)

		for A, B in zip(worldPath, worldPath[1:]):
			ob, p, norm = self.rayCast(B, A, self.raylen, self.prop, True, True,
					False)
			if ob:
				self.lastHitPoint = refMatInv * p
				self.lastHitNorm = refOrnInv * norm
				if DEBUG:
					bge.render.drawLine(A, p, bat.render.ORANGE.xyz)
				break
			else:
				if DEBUG:
					bge.render.drawLine(A, B, bat.render.YELLOW.xyz)

		wp = refMat * self.lastHitPoint
		wn = refOrn * self.lastHitNorm
		return ob, wp, wn
