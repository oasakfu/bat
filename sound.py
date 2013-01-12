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
import logging

import aud
import bge

import bat.containers
import bat.bmath

FADE_RATE = 0.01

DIST_MAX = 10000.0
DIST_MIN = 10.0
ATTENUATION = 1.0

log = logging.getLogger(__name__)

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


@aud_lock
def use_linear_clamped_falloff(dist_min=10, dist_max=50, attenuation=1.0):
	global DIST_MAX
	global DIST_MIN
	global ATTENUATION

	log.info("Setting sound falloff to linear")
	try:
		aud.device().distance_model = aud.AUD_DISTANCE_MODEL_LINEAR_CLAMPED
	except aud.error as e:
		log.warn("Can't set 3D audio model: %s", e)
		return

	DIST_MIN = dist_min
	DIST_MAX = dist_max
	ATTENUATION = attenuation

@aud_lock
def use_inverse_clamped_falloff(dist_min=10, dist_max=10000, attenuation=1.0):
	global DIST_MAX
	global DIST_MIN
	global ATTENUATION

	log.info("Setting sound falloff to inverse linear")
	try:
		aud.device().distance_model = aud.AUD_DISTANCE_MODEL_INVERSE_CLAMPED
	except aud.error as e:
		log.warn("Can't set 3D audio model: %s", e)
		return

	DIST_MIN = dist_min
	DIST_MAX = dist_max
	ATTENUATION = attenuation


class Jukebox(metaclass=bat.bats.Singleton):
	'''
	Plays music. This uses a stack of tracks to organise a playlist. Typically,
	this would be used to have some level-wide music playing, and replace it
	from time to time with other music when some event happens (e.g. when a
	character enters a locality). For example:

		# Start playing level music
		bat.sound.Jukebox().play_files('bg', level_empty, 0, '//background_music.ogg')
		...
		# Enter a locality
		bat.sound.Jukebox().play_files('house', house, 0, '//background_music.ogg')
		...
		# Return to main level music
		bat.sound.Jukebox().stop('house')

	Notice that both of these tracks have a priority of 0, but the second will
	still override the first. If the first had had a priority of 1, the second
	track would not have started. For example:

		# Start playing high-priority music
		bat.sound.Jukebox().play_files('bg', level_empty, 1, '//first.ogg')
		...
		# Enqueue low-priority music
		bat.sound.Jukebox().play_files('house', house, 0, '//second.ogg')
		...
		# second.ogg will start now
		bat.sound.Jukebox().stop('bg', level_empty)
	'''


	def __init__(self):
		# Use of SafePriorityStack means tracks are discarded automatically if
		# the owning object dies.
		self.stack = bat.containers.SafePriorityStack()
		self.current_track = None
		self.track_cache = {}

	def play_track(self, name, track, priority):
		self.stack.push(track, priority)
		self.track_cache[name] = track
		self.update()

	def play_files(self, name, ob, priority, *files, introfile=None, volume=1.0,
				fade_in_rate=FADE_RATE, fade_out_rate=FADE_RATE, loop=True):
		if name in self.track_cache:
			# Re-use track and take ownership
			track = self.track_cache[name]
			track.ob = ob
		else:
			sample = Sample()
			sample.source = ChainMusicSource(*files, introfile=introfile, loop=loop)
			sample.volume = volume
			track = Track(sample, ob, fade_in_rate=fade_in_rate,
					fade_out_rate=fade_out_rate)
		self.play_track(name, track, priority)

	def play_permutation(self, name, ob, priority, *files, introfile=None,
				volume=1.0, fade_in_rate=FADE_RATE, fade_out_rate=FADE_RATE,
				loop=True):
		if name in self.track_cache:
			# Re-use track and take ownership
			track = self.track_cache[name]
			track.ob = ob
		else:
			sample = Sample()
			sample.source = PermuteMusicSource(*files, introfile=introfile, loop=loop)
			sample.volume = volume
			track = Track(sample, ob, fade_in_rate=fade_in_rate,
					fade_out_rate=fade_out_rate)
		self.play_track(name, track, priority)

	def update(self):
		# Purge dead tracks
		for name, track in list(self.track_cache.items()):
			if track.invalid and not track.playing:
				Jukebox.log.debug("Removing dead track '%s'", name)
				del self.track_cache[name]

		if len(self.stack) == 0:
			track = None
		else:
			track = self.stack.top()

		if track == self.current_track:
			if track is not None and not track.playing:
				# Track has stopped by itself, so play next on the stack
				self.stack.discard(track)
			return

		if self.current_track is not None:
			self.current_track.stop()
		if track is not None:
			track.play()
		self.current_track = track
		print(self.current_track)

	def stop(self, name, fade_rate=None):
		try:
			track = self.track_cache[name]
		except KeyError:
			Jukebox.log.warn("Tried to stop track that isn't playing or queued")
			return
		track.special_fade_out_rate = fade_rate
		self.stack.discard(track)
		self.update()

class Track:

	def __init__(self, sample, ob, fade_in_rate=FADE_RATE, fade_out_rate=FADE_RATE):
		self.sample = sample
		self.ob = ob
		self.fade_in_rate = fade_in_rate
		self.fade_out_rate = fade_out_rate
		self.special_fade_out_rate = None

	@property
	def invalid(self):
		# Used by SafePriorityStack
		return self.ob.invalid

	@property
	def playing(self):
		return self.sample.playing

	def play(self):
		# Add the fader (fade-in mode). Even if it was added before, it won't be
		# counted twice.
		self.sample.remove_effect("Fader")
		self.sample.add_effect(Fader(self.fade_in_rate))
		self.sample.play()

	def stop(self):
		# Fade out. When the volume reaches zero, the sound will stop.
		if self.special_fade_out_rate is not None:
			# Allows once-off different fade out.
			rate = -self.special_fade_out_rate
			self.special_fade_out_rate = None
		else:
			rate = -self.fade_out_rate
		self.sample.remove_effect("Fader")
		self.sample.add_effect(Fader(rate))

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
	'''
	Plays two sounds back-to-back; the second sound can loop independently.
	'''
	def __init__(self, *loopfiles, introfile=None, loop=True):
		self.introfile = introfile
		self.loopfiles = loopfiles
		self.loop = loop

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
		if self.loop:
			return sequence.loop(-1)
		else:
			return sequence

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

		if self.loop:
			return sequence.loop(-1)
		else:
			return sequence

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

	log = logging.getLogger(__name__ + '.Localise')

	def __init__(self, ob, distmin=None, distmax=None, attenuation=None):
		self.ob = ob
		self.distmin = DIST_MIN if distmin is None else distmin
		self.distmax = DIST_MAX if distmax is None else distmax
		self.attenuation = ATTENUATION if attenuation is None else attenuation
		self._handleid = None

	def prepare(self, sample):
		try:
			self.loc = self.ob.worldPosition
		except SystemError:
			sample.stop()

	@aud_lock
	def apply(self, sample, handle):
		if not handle.status:
			Localise.log.debug("Not localising dead handle of %s", self.ob)
			return

		handle.location = self.loc

		if True:#self._handleid != id(handle):
			# This is the first time this particular handle has been localised.
			# Actually this doesn't always work. Sometimes the handleid is wrong?
			# Safer to set these properties on each frame.
			handle.relative = False
			handle.distance_reference = self.distmin
			handle.distance_maximum = self.distmax
			handle.attenuation = self.attenuation
			self._handleid = id(handle)

	def __repr__(self):
		return "Localise(%s, %g)" % (self.ob, self.distmax)

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

	def __repr__(self):
		return "Fader(%g)" % self.rate

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

	def __repr__(self):
		return "FadeByLinV(%s)" % self.ob

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

	def __repr__(self):
		return "PitchByAngV(%s)" % self.ob


class Sample:
	'''
	A sound sample. Similar to aud.Handle, but it can be retained and replayed
	without wasting resources when it is stopped.

	A Sample can only play one instance of its sound at a time. If you want to
	play a second instance, call Sample.copy().
	'''

	log = logging.getLogger(__name__ + '.Sample')

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
		self.name = None

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
		Sample.log.debug("Adding effect %s to %s", effect, self)
		self._effects.add(effect)

	def remove_effect(self, effect):
		if isinstance(effect, str):
			# Remove effect by name
			for ef in self._effects:
				if ef.__class__.__name__ == effect:
					effect = ef
					break
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

		Sample.log.info("Playing %s", self)
		try:
			factory = self._construct_factory(self.source.get())
			self._pre_update()
			self._play(factory)
		except aud.error as e:
			Sample.log.error("%s: %s", self, e)

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
