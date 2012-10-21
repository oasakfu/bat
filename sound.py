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

import bat.containers
import bat.bmath

FADE_RATE = 0.01

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
			dev = aud.device()
			dev.lock()
			try:
				_aud_locked = True
				return f(*args, **kwargs)
			finally:
				dev.unlock()
				_aud_locked = False

	return _aud_lock


class Jukebox(metaclass=bat.bats.Singleton):
	'''
	Plays music. This uses a stack of tracks to organise a playlist. Typically,
	this would be used to have some level-wide music playing, and replace it
	from time to time with other music when some event happens (e.g. when a
	character enters a locality). For example:

		# Start playing level music
		bat.sound.Jukebox().play_files(level_empty, 0, '//background_music.ogg')
		...
		# Enter a locality
		bat.sound.Jukebox().play_files(house, 0, '//background_music.ogg')
		...
		# Return to main level music
		bat.sound.Jukebox().stop(house)

	Notice that both of these tracks have a priority of 0, but the second will
	still override the first. If the first had had a priority of 1, the second
	track would not have started. For example:

		# Start playing high-priority music
		bat.sound.Jukebox().play_files(level_empty, 1, '//first.ogg')
		...
		# Enqueue low-priority music
		bat.sound.Jukebox().play_files(house, 0, '//second.ogg')
		...
		# second.ogg will start now.
		bat.sound.Jukebox().stop(level_empty)
	'''


	def __init__(self):
		self.stack = bat.containers.SafePriorityStack()
		self.current_track = None
		self.discarded_tracks = []

	def play_sample(self, sample, ob, priority, fade_rate=FADE_RATE):
		track = Track(sample, ob, fade_rate=fade_rate)
		self.stack.push(track, priority)
		self.update()

	def play_files(self, ob, priority, *files, introfile=None, volume=1.0, fade_rate=FADE_RATE):
		sample = Sample()
		sample.source = ChainMusicSource(*files, introfile=introfile)
		sample.volume = volume
		# No need to loop: ChainMusicSource does that already.
		self.play_sample(sample, ob, priority, fade_rate=fade_rate)
		return sample

	def play_permutation(self, ob, priority, *files, introfile=None, volume=1.0, fade_rate=FADE_RATE):
		sample = Sample()
		sample.source = PermuteMusicSource(*files, introfile=introfile)
		sample.volume = volume
		# No need to loop: PermuteMusicSource does that already.
		self.play_sample(sample, ob, priority, fade_rate=fade_rate)
		return sample

	def update(self):
		if len(self.stack) == 0:
			track = None
		else:
			track = self.stack.top()

		if track == self.current_track:
			return

		if self.current_track is not None:
			self.current_track.stop()
		if track is not None:
			track.play()
		self.current_track = track
		print(self.current_track)

	def stop(self, ob_or_sample, fade_rate=None):
		for track in self.stack:
			if track.ob is ob_or_sample or track.sample is ob_or_sample:
				if fade_rate is not None:
					track.fade_rate = fade_rate
				self.stack.discard(track)
				self.update()
				return

class Track:

	def __init__(self, sample, ob, fade_rate=FADE_RATE):
		self.sample = sample
		self.ob = ob
		self.fade_rate = fade_rate
		self.fader = Fader(fade_rate)

	@property
	def invalid(self):
		return self.ob.invalid

	@property
	def playing(self):
		return self.sample.playing

	def play(self):
		# Add the fader (fade-in mode). Even if it was added before, it won't be
		# counted twice.
		self.fader.rate = self.fade_rate
		self.sample.add_effect(self.fader)
		self.sample.play()

	def stop(self):
		# Fade out. When the volume reaches zero, the sound will stop.
		self.fader.rate = -self.fade_rate
		self.sample.add_effect(self.fader)

	def __repr__(self):
		return "Track({})".format(repr(self.sample))

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
	def __init__(self, *loopfiles, introfile=None):
		self.introfile = introfile
		self.loopfiles = loopfiles

	def get(self):
		loop = self._get_loop()
		if self.introfile is None:
			return loop
		else:
			intro = aud.Factory(bge.logic.expandPath(self.introfile))
			return intro.join(loop)

	def _get_loop(self):
		segments = []
		for filepath in self.loopfiles:
			path = bge.logic.expandPath(filepath)
			segments.append(aud.Factory(path))
		sequence = self._concatenate_factories(segments)
		return sequence.loop(-1)

	def _concatenate_factories(self, factories):
		combined = None
		for factory in factories:
			if combined is None:
				combined = factory
			else:
				combined = combined.join(factory)
		return combined

	def __repr__(self):
		return "Chain({}, {}...)".format(repr(self.introfile), repr(self.loopfiles[0]))

class PermuteMusicSource(ChainMusicSource):
	'''
	Plays a series of sounds in all possible orders. The entire sequence will
	loop. E.g. 3 files each 20s long will play for

		3! * (3 * 20) = 6 * 60 = 360s

	before repeating.
	'''

	def _get_loop(self):
		segments = []
		for filepath in self.loopfiles:
			path = bge.logic.expandPath(filepath)
			segments.append(aud.Factory(path))

		perms = []
		for p in itertools.permutations(segments):
			perms.append(self._concatenate_factories(p))
		sequence = self._concatenate_factories(perms)

		return sequence.loop(-1)

	def __repr__(self):
		return "Permute({}, {}...)".format(repr(self.introfile), repr(self.loopfiles[0]))


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

class Fader(Effect):
	'''
	Causes a sample change volume over time. If rate is negative, the sound will
	fade out and then stop. If positive, it will fade in (and continue). Either
	way, the effect will remove itself from the effect list once it has reached
	its goal.
	'''
	def __init__(self, rate=-0.05):
		self.rate = rate
		if rate < 0.0:
			self.multiplier = 1.0
		else:
			self.multiplier = 0.0

	def prepare(self, sample):
		self.multiplier = bat.bmath.clamp(0.0, 1.0, self.multiplier + self.rate)

		# A multiplier is used to allow this to work together with other volume
		# effects.
		if self.rate > 0.0 and self.multiplier == 1.0:
			# Full volume; stop fading.
			sample.remove_effect(self)
			return
		elif self.rate < 0.0 and self.multiplier == 0.0:
			# Finished fading out; stop sample and remove self.
			sample.stop()
			sample.remove_effect(self)
			return

	@aud_lock
	def apply(self, sample, handle):
		if not handle.status:
			return

#		print(sample, self.multiplier)
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
		self.multiplier = bat.bmath.approach_one(speed, self.scale)

	@aud_lock
	def apply(self, sample, handle):
		if not handle.status:
			return

		# A multiplier is used to allow this to work together with other volume
		# effects.
		handle.volume *= self.multiplier

class PitchByAngV(Effect):
	'''Increases the pitch of a sound the faster an object rotates.'''
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
		factor = bat.bmath.approach_one(speed, self.scale)
		self.multiplier = bat.bmath.lerp(self.pitchmin, self.pitchmax, factor)

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

		self._pre_update()
		self._update()

	def _pre_update(self):
		# Some preparation is done outside of the lock; this is to minimise the
		# time spent holding the lock, which should reduce clicking.

		# Copy the set of effects, because some of them may remove themselves
		# when finished.
		effects = self._effects.copy()
		for effect in effects:
			effect.prepare(self)

	@aud_lock
	def _update(self):
		if not self.playing:
			return

		# Reset properties, to allow non-destructive editing.
		handle = self._handle
		handle.volume = self.volume
		handle.pitch = self.pitch

		# Copy the set of effects, because some of them may remove themselves
		# when finished.
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
			self.pitch = bat.bmath.lerp(self.pitchmin, self.pitchmax,
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
@bat.bats.once_per_tick
def update():
	'''
	Process the sounds that are currently playing, e.g. update 3D positions.
	'''
	for s in _playing_samples.copy():
		if not s.playing:
			_playing_samples.discard(s)
			continue
		s.update()

	Jukebox().update()
