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
import abc
import itertools

import aud
import bge

import bxt


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
# The following could be used instead of the code in Sample._construct_factory,
# to make it more extensible. It's not clear if it's worth it, though.
#
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


class Source(metaclass=abc.ABCMeta):
	'''A factory for sound factories.'''

	@abc.abstractmethod
	def get(self):
		'''@return: an aud.Factory instance.'''

class SingleSource(Source):
	'''Creates a Factory for a single file.'''
	def __init__(self, filename):
		self.filename = filename

	def get(self):
		return aud.Factory(bge.logic.expandPath(self.filename))

	def __repr__(self):
		return repr(self.filename)

class MultiSource(Source):
	'''
	Stores a collection of file names; each time get() is called, a Factory is
	constructed for one of the files (chosen at random).
	'''
	def __init__(self, *filenames):
		self.filenames = filenames

	def get(self):
		i = int(len(self.filenames) * bge.logic.getRandomFloat())
		return aud.Factory(bge.logic.expandPath(self.filenames[i]))

	def __repr__(self):
		return repr(self.filenames)

class ChainMusicSource(Source):
	'''Plays two sounds back-to-back; the second sound will loop.'''
	def __init__(self, introfile, loopfile):
		self.introfile = introfile
		self.loopfile = loopfile

	def get(self):
		intro = aud.Factory(bge.logic.expandPath(self.introfile))
		loop = aud.Factory(bge.logic.expandPath(self.loopfile)).loop(-1)
		return intro.join(loop)

class PermuteMusicSource(Source):
	'''
	Plays a series of sounds in all possible orders. The entire sequence will
	loop. E.g. 3 files each 20s long will play for

		3! * (3 * 20) = 6 * 60 = 360s

	before repeating.
	'''
	def __init__(self, *loopfiles):
		self.loopfiles = loopfiles

	def get(self):
		segments = []
		for filepath in self.loopfiles:
			path = bge.logic.expandPath(filepath)
			segments.append(aud.Factory(path))

		perms = []
		for p in itertools.permutations(segments):
			perms.append(self._concatenate_factories(p))
		track = self._concatenate_factories(perms)

		return track.loop(-1)

	def _concatenate_factories(self, factories):
		combined = None
		for factory in factories:
			if combined is None:
				combined = factory
			else:
				combined = combined.join(factory)
		return combined


class Effect(metaclass=abc.ABCMeta):
	'''Effects are run while a sound plays.'''

	@abc.abstractmethod
	def prepare(self, sample):
		'''
		Do any preparation required for this frame. You should not manipulate
		any sound handles here; do that in apply().
		'''

	@abc.abstractmethod
	def apply(self, sample, handle):
		'''
		Modify the playing sound for this frame. Do not do any intensive tasks
		in here, or the sound may "click". Long calculations (such as vector
		math) should be done in prepare().
		'''

class Localise(Effect):
	'''Gives a sample a location in 3D space.'''
	# These are sounds that have a location. We manage their location manually
	# to work around this bug:
	# http://projects.blender.org/tracker/?func=detail&atid=306&aid=32096&group_id=9
	def __init__(self, ob, distmin=10.0, distmax=1000000.0, attenuation=10.0):
		self.ob = ob
		self.distmin = distmin
		self.distmax = distmax
		self.attenuation = attenuation
		self._handleid = None

	def prepare(self, sample):
		try:
			self.loc = self.ob.worldPosition
		except SystemError:
			sample.stop()

	@aud_lock
	def apply(self, sample, handle):
		if not handle.status:
			return

		handle.location = self.loc

		if self._handleid != id(handle):
			# This is the first time this particular handle has been localised.
			handle.relative = False
			handle.distance_reference = self.distmin
			handle.distance_maximum = self.distmax
			handle.attenuation = self.attenuation
			self._handleid = id(handle)

class FadeOut(Effect):
	'''Causes a sample to fade out and stop. Then, it removes itself.'''
	def __init__(self, rate=0.05):
		self.rate = rate
		self.multiplier = 1.0

	def prepare(self, sample):
		self.multiplier -= self.rate

	@aud_lock
	def apply(self, sample, handle):
		if not handle.status:
			return

		# A multiplier is used to allow this to work together with other volume
		# effects.
		if self.multiplier <= 0.0:
			sample.stop()
			sample.remove_effect(self)
		else:
			handle.volume *= self.multiplier

class FadeByLinV(Effect):
	'''Plays a sound loudly when the object is moving fast.'''
	def __init__(self, ob, scale=0.05):
		self.ob = ob
		self.scale = scale

	def prepare(self, sample):
		try:
			speed = self.ob.worldAngularVelocity.magnitude
		except SystemError:
			sample.stop()
			return
		self.multiplier = bxt.bmath.approach_one(speed, self.scale)

	@aud_lock
	def apply(self, sample, handle):
		if not handle.status:
			return

		# A multiplier is used to allow this to work together with other volume
		# effects.
		handle.volume *= self.multiplier

class PitchByAngV(Effect):
	'''Plays a sound loudly when the object is moving fast.'''
	def __init__(self, ob, scale=0.05, pitchmin=0.8, pitchmax=1.2):
		self.ob = ob
		self.scale = scale
		self.pitchmin = pitchmin
		self.pitchmax = pitchmax

	def prepare(self, sample):
		try:
			speed = self.ob.worldAngularVelocity.magnitude
		except SystemError:
			sample.stop()
			return
		factor = bxt.bmath.approach_one(speed, self.scale)
		self.multiplier = bxt.bmath.lerp(self.pitchmin, self.pitchmax, factor)

	def apply(self, sample, handle):
		if not handle.status:
			return

		# A multiplier is used to allow this to work together with other volume
		# effects.
		handle.pitch *= self.multiplier


class Sample:
	'''
	A sound sample. Similar to aud.Handle, but it can be retained and replayed
	without wasting resources when it is stopped.

	A Sample can only play one instance of its sound at a time. If you want to
	play a second instance, call Sample.copy().
	'''

	def __init__(self, *filenames):
		'''
		Create a new sound sample. If multiple file names are provided, one will
		be chosen at random each time the sample is played. If no filenames are
		given, the source will be undefined; it may be set later by assigning
		a Source to the Sample.source property.
		'''
		if len(filenames) == 0:
			self.source = None
		elif len(filenames) == 1:
			self.source = SingleSource(filenames[0])
		else:
			self.source = MultiSource(*filenames)

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
		'''Create a new Sample instance with the same settings'''
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

	def update(self):
		''''Run effects for this frame.'''
		# NOTE: Some preparation is done outside of the lock; this is to
		# minimise the time spent holding the lock, which should reduce
		# clicking.

		# Copy the set of effects, because some of them may remove themselves
		# when finished.
		self._pre_update()
		self._update()

	def _pre_update(self):
		effects = self._effects.copy()
		for effect in effects:
			effect.prepare(self)

	@aud_lock
	def _update(self):
		if not self.playing:
			return

		handle = self._handle
		handle.volume = self.volume
		handle.pitch = self.pitch
		effects = self._effects.copy()
		for effect in effects:
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
			self._pre_update()
			self._play(factory)
		except aud.error as e:
			print("Error playing sound" % self)
			print(e)

	def stop(self):
		'''Stop playing the sound. If it is not playing, nothing happens.'''
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
		self._update()

	def __repr__(self):
		return "Sample({})".format(self.source)

_playing_samples = set()
def update():
	'''
	Process the sounds that are currently playing, e.g. update 3D positions.
	'''
	for s in _playing_samples.copy():
		if not s.playing:
			_playing_samples.discard(s)
			continue
		s.update()
