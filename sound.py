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

from collections import namedtuple
from functools import wraps

import aud
import mathutils
import bge

import bxt

MIN_VOLUME = 0.001



_aud_locked = False
def aud_lock(f):
	'''
	Function decorator.
	Locks the audio device before a function call, and unlocks it afterwards -
	unless it was already locked, in which case the function is just called as
	normal.
	'''
	@wraps(f)
	def _aud_lock(*args, **kwargs):
		global _aud_locked

		if _aud_locked:
			return f(*args, **kwargs)

		else:
			_aud_locked = True
			dev = aud.device()
			dev.lock()
			try:
				return f(*args, **kwargs)
			finally:
				dev.unlock()
				_aud_locked = False

	return _aud_lock


#
# A mapping from sound name to actuator index. This lets play_with_random_pitch
# cycle through different samples for a named sound.
#
_SoundActuatorIndices = {}
_volume_map = {}

def set_volume(object_name, volume):
	'''
	Sets the volume for a particular object. If that object later calls one the
	methods in this module to play a sound, the volume specified here will be
	used.
	'''
	_volume_map[object_name] = volume

@bxt.utils.all_sensors_positive
@bxt.utils.controller
def play_with_random_pitch(c):
	'''
	Play a sound with a random pitch. The pitch range is defined by the
	controller's owner using the properties PitchMin and PitchMax.

	Sensors:
	<one>:  If positive and triggered, a sound will be played.

	Actuators:
	<one+>: Each will be played in turn.

	Controller properties:
	PitchMin: The minimum pitch (float).
	PitchMax: The maximum pitch (float).
	SoundID:  The name of the sound (any type). This lets different objects with
	          the same SoundID coordinate the sequence that the sounds are
	          played in. Note that if controllers with the same SoundID have
	          different numbers of actuators, the additional actuators are not
	          guaranteed to play.
	'''
	o = c.owner

	try:
		o['PitchMin']
	except KeyError:
		o['PitchMin'] = 0.8
	try:
		o['PitchMax']
	except KeyError:
		o['PitchMax'] = 1.2

	#
	# Select an actuator.
	#
	i = 0
	try:
		i = _SoundActuatorIndices[o.name]
	except KeyError:
		_SoundActuatorIndices[o.name] = 0
		i = 0

	i = i % len(c.actuators)
	a = c.actuators[i]
	_SoundActuatorIndices[o.name] = i + 1

	#
	# Set the pitch and activate!
	#
	a.pitch = bxt.bmath.lerp(o['PitchMin'], o['PitchMax'], bge.logic.getRandomFloat())
	try:
		a.volume = _volume_map[o.name]
	except KeyError:
		pass
	c.activate(a)

@bxt.utils.controller
def fade(c):
	'''
	Causes a sound to play a long as its inputs are active. On activation, the
	sound fades in; on deactivation, it fades out. The fade rate is determined
	by the owner's SoundFadeFac property (0.0 <= SoundFadeFac <= 1.0).

	Sensors:
	sAlways:  Fires every frame to provide the fading effect.
	<one+>:   If any are positive, the sound will turn on. Otherwise the sound
	          will turn off.

	Actuators:
	<one>:    A sound actuator.

	Controller properties:
	VolumeMult:    The maximum volume (float).
	SoundFadeFac:  The response factor for the volume (float).
	'''
	_fade(c, 1.0)

def _fade(c, maxVolume):
	a = c.actuators[0]
	o = a.owner

	# Wait a few frames before allowing sound to be played. This is a filthy
	# hack to prevent objects from being noisy when they spawn - i.e. when they
	# tend to have a bit of initial velocity.
	try:
		if o['SoundWait'] > 0:
			o['SoundWait'] -= 1
			return
	except:
		o['SoundWait'] = 20
		return

	try:
		o['SoundFadeFac']
	except KeyError:
		o['SoundFadeFac'] = 0.05

	if o.name in _volume_map:
		maxVolume *= _volume_map[o.name]

	targetVolume = 0.0
	for s in c.sensors:
		if s.name == "sAlways":
			continue
		if s.positive:
			targetVolume = maxVolume
			break

	a.volume = bxt.bmath.lerp(a.volume, targetVolume, o['SoundFadeFac'])
	if a.volume > MIN_VOLUME:
		c.activate(a)
	else:
		c.deactivate(a)

def _modulate(speed, c):
	o = c.owner

	try:
		o['SoundModScale']
	except KeyError:
		o['SoundModScale'] = 0.01
	try:
		o['PitchMin']
	except KeyError:
		o['PitchMin'] = 0.8
	try:
		o['PitchMax']
	except KeyError:
		o['PitchMax'] = 1.2

	factor = 0.0
	if speed > 0.0:
		factor = bxt.bmath.approach_one(speed, o['SoundModScale'])

	a = c.actuators[0]
	a.pitch = bxt.bmath.lerp(o['PitchMin'], o['PitchMax'], factor)

	_fade(c, factor)

@bxt.utils.controller
def modulate_by_linv(c):
	'''
	Change the pitch and volume of the sound depending on the angular velocity
	of the controller's owner.

	Sensors:
	sAlways:  Fires every frame to provide the fading effect.
	<others>: At least one other. If any are positive, the sound will turn on.
	          Otherwise the sound will turn off.

	Actuators:
	<one>:    A sound actuator.

	Controller properties:
	SoundModScale: The rate at which the pitch increases (float).
	PitchMin:      The minimum pitch (when speed = 0) (float).
	PitchMax:      The maximum pitch (as speed approaches infinity) (float).
	VolumeMult:    The maximum volume (as speed approaches infinity) (float).
	SoundFadeFac:  The response factor for the volume (float).
	'''
	o = c.owner
	linV = mathutils.Vector(o.getLinearVelocity(False))
	_modulate(linV.magnitude, c)

@bxt.utils.controller
def modulate_by_angv(c):
	'''
	Change the pitch and volume of the sound depending on the angular velocity
	of the controller's owner.

	Sensors:
	sAlways:  Fires every frame to provide the fading effect.
	<others>: At least one other. If any are positive, the sound will turn on.
	          Otherwise the sound will turn off.

	Actuators:
	<one>:    A sound actuator.

	Controller properties:
	SoundModScale: The rate at which the pitch increases (float).
	PitchMin:      The minimum pitch (when speed = 0) (float).
	PitchMax:      The maximum pitch (as speed approaches infinity) (float).
	VolumeMult:    The maximum volume (as speed approaches infinity) (float).
	SoundFadeFac:  The response factor for the volume (float).
	'''
	o = c.owner
	angV = mathutils.Vector(o.getAngularVelocity(False))
	_modulate(angV.magnitude, c)

# These are sounds that have a location. We manage their location manually to
# work around this bug:
# http://projects.blender.org/tracker/?func=detail&atid=306&aid=32096&group_id=9
_playing_samples = set()

#class _Volume:
#	def __init__(self, value):
#		self.value = value
#
#	def transform(self, factory):
#		return factory.volume(self.value)
#
#class _PitchRange:
#	def __init__(self, pitchmin, pitchmax):
#		self.pitchmin = pitchmin
#		self.pitchmax = pitchmax
#
#	def transform(self, factory):
#		pitch = bxt.bmath.lerp(self.pitchmin, self.pitchmax,
#				bge.logic.getRandomFloat())
#		return factory.pitch(pitch)
#
#class _Loop:
#	def __init__(self, times=-1):
#		self.times = times
#
#	def transform(self, factory):
#		return factory.loop(self.times)

class _MultiSource:
	def __init__(self, *filenames):
		self.filenames = filenames

	def get(self):
		i = int(len(self.filenames) * bge.logic.getRandomFloat())
		return aud.Factory(bge.logic.expandPath(self.filenames[i]))

	def __repr__(self):
		return repr(self.filenames)

class _SingleSource:
	def __init__(self, filename):
		self.filename = filename

	def get(self):
		return aud.Factory(bge.logic.expandPath(self.filename))

	def __repr__(self):
		return repr(self.filename)


class Localise:
	'''Gives a sample a location in 3D space.'''
	def __init__(self, ob, distmin=10.0, distmax=1000000.0, attenuation=10.0):
		self.owner = ob
		self.distmin = distmin
		self.distmax = distmax
		self.attenuation = attenuation
		self._first = True

	def apply(self, sample, handle):
		if self.owner.invalid:
			sample.stop()
			return
		if not handle.status:
			return

		handle.location = self.owner.worldPosition
		if self._first:
			handle.relative = False
			handle.distance_reference = self.distmin
			handle.distance_maximum = self.distmax
			handle.attenuation = self.attenuation
			self._first = False

class FadeOut:
	'''Causes a sample to fade out and stop. Then, it removes itself.'''
	def __init__(self, rate=0.05):
		self.rate = rate
		self.multiplier = 1.0

	def apply(self, sample, handle):
		if not handle.status:
			return

		# A multiplier is used to allow this to work together with other volume
		# effects.
		if self.multiplier - self.rate <= 0.0:
			sample.stop()
			sample.remove_effect(self)
		else:
			self.multiplier -= self.rate
			handle.volume *= self.multiplier

class FadeByLinV:
	'''Plays a sound loudly when the object is moving fast.'''
	def __init__(self, ob, scale=0.05):
		self.owner = ob
		self.scale = scale

	def apply(self, sample, handle):
		if not handle.status:
			return

		# A multiplier is used to allow this to work together with other volume
		# effects.
		speed = self.owner.worldLinearVelocity.magnitude
		multiplier = bxt.bmath.approach_one(speed, self.scale)
		handle.volume *= multiplier

class PitchByAngV:
	'''Plays a sound loudly when the object is moving fast.'''
	def __init__(self, ob, scale=0.05, pitchmin=0.8, pitchmax=1.2):
		self.owner = ob
		self.scale = scale
		self.pitchmin = pitchmin
		self.pitchmax = pitchmax

	def apply(self, sample, handle):
		if not handle.status:
			return

		# A multiplier is used to allow this to work together with other volume
		# effects.
		speed = self.owner.worldAngularVelocity.magnitude
		factor = bxt.bmath.approach_one(speed, self.scale)
		multiplier = bxt.bmath.lerp(self.pitchmin, self.pitchmax, factor)
		handle.pitch *= multiplier


class Sample:
	'''
	A sound sample. Similar to aud.Handle, but it can be retained and replayed
	without wasting resources when it is stopped.

	A Sample can only play one instance of its sound at a time. If you want to
	play a second instance, call Sample.copy().
	'''

	def __init__(self, *filenames):
		if len(filenames) == 0:
			self.source = None
		elif len(filenames) == 1:
			self.source = _SingleSource(filenames[0])
		else:
			self.source = _MultiSource(*filenames)

		# Universal properties
		self.volume = 1.0
		self.pitchmin = 1.0
		self.pitchmax = 1.0
		self.pitch = 1.0
		self.loop = False

		# Internal state stuff

		self._effects = set()
		self._handle = None

	def copy(self):
		other = Sample()
		other.source = self.source

		other.volume = self.volume
		other.pitchmin = self.pitchmin
		other.pitchmax = self.pitchmax
		other.loop = self.loop

		other._effects = self._effects.copy()

		# Don't copy handle.
		return other

	def add_effect(self, effect):
		self._effects.add(effect)

	def remove_effect(self, effect):
		self._effects.discard(effect)

	@property
	def playing(self):
		return self._handle is not None and self._handle.status

	@aud_lock
	def update(self):
		if not self.playing:
			return

		handle = self._handle
		# Copy the set of effects, because some of them may remove themselves
		# when finished.
		handle.volume = self.volume
		handle.pitch = self.pitch
		for effect in self._effects.copy():
			effect.apply(self, handle)

	def play(self):
		'''
		Play the sound sample - unless it's already playing, in which case
		nothing happens.
		'''
		# Don't play sound if it's already playing.
		# TODO: Make this better: it should:
		#  - Only play sound if it woulnd't bump off a higher-priority sound.
		if self.playing:
			return

		try:
			factory = self._construct_factory(self.source.get())
			self._play(factory)
		except aud.error as e:
			print("Error playing sound" % self)
			print(e)

	def stop(self):
		if self._handle is None:
			return
		self._handle.stop()
		self._handle = None

	def _construct_factory(self, factory):
		if self.volume != 1.0:
			factory = factory.volume(self.volume)

		if self.pitchmax != 1.0 or self.pitchmin != 1.0:
			self.pitch = bxt.bmath.lerp(self.pitchmin, self.pitchmax,
					bge.logic.getRandomFloat())
			factory = factory.pitch(self.pitch)

		if self.loop:
			factory = factory.loop(-1)

		return factory

	@aud_lock
	def _play(self, factory):
		dev = aud.device()
		self._handle = dev.play(factory)
		_playing_samples.add(self)
		self.update()

	def __repr__(self):
		return "Sample({})".format(self.source)


@aud_lock
def update():
	'''
	Process the sounds that are currently playing, e.g. update 3D positions.
	'''
	for s in _playing_samples.copy():
		if not s.playing:
			_playing_samples.discard(s)
			continue
		s.update()
#	print(len(_playing_samples))
