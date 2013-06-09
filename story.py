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
import sys

'''
State machines for driving story.
'''

import time
import logging
import inspect
import os

import bge

import bat.bats
import bat.containers
import bat.event
import bat.utils
import bat.bmath
import bat.sound
import bat.store

class StoryError(Exception):
	pass

#
# Step progression conditions. These determine whether a step may execute.
#
class Condition:
	def enable(self, enabled):
		pass

	def evaluate(self):
		raise NotImplementedError()

	def get_short_name(self):
		raise NotImplementedError()

	def find_source(self, c, ob_or_name, descendant_name=None):
		ob = ob_or_name
		if ob is None:
			ob = c.owner
		elif isinstance(ob, str):
			ob = bge.logic.getCurrentScene().objects[ob]

		if descendant_name is not None:
			ob = ob.childrenRecursive[descendant_name]

		return ob

class CNot(Condition):
	'''Inverts a condition.'''
	def __init__(self, wrapped):
		self.wrapped = wrapped

	def evaluate(self, c):
		return not self.wrapped.evaluate(c)

	def get_short_name(self):
		return "!%s" % self.wrapped.get_short_name()

class CondSensor(Condition):
	'''Allow the story to progress when a particular sensor is true.'''
	def __init__(self, name):
		self.Name = name

	def evaluate(self, c):
		s = c.sensors[self.Name]
		return s.positive

	def get_short_name(self):
		return "Sens(%s)" % self.Name

class CondSensorNot(Condition):
	'''Allow the story to progress when a particular sensor is false.'''
	def __init__(self, name):
		self.Name = name

	def evaluate(self, c):
		s = c.sensors[self.Name]
		return not s.positive

	def get_short_name(self):
		return "!Sens(%s)" % self.Name

class CondAttrEq(Condition):
	'''Allow the story to progress when an attribute equals a value.'''
	def __init__(self, name, value, ob=None, target_descendant=None):
		self.name = name
		self.value = value
		self.target_descendant = target_descendant
		self.ob = ob

	def evaluate(self, c):
		ob = self.find_source(c, self.ob, self.target_descendant)
		return getattr(ob, self.name) == self.value

	def get_short_name(self):
		return "AttrEq(%s, %s)" % (self.name, self.value)

class CondPropertyGE(Condition):
	'''Allow the story to progress when a property matches an inequality. In
	this case, when the property is greater than or equal to the given value.'''
	def __init__(self, name, value):
		self.Name = name
		self.Value = value

	def evaluate(self, c):
		return c.owner[self.Name] >= self.Value

	def get_short_name(self):
		return "PropGE(%s, %s)" % (self.Name, self.Value)

class CondActionGE(Condition):
	FRAME_EPSILON = 0.01

	def __init__(self, layer, frame, tap=False, ob=None, targetDescendant=None):
		'''
		@param layer: The animation layer to watch.
		@param frame: The frame to trigger from.
		@param tap: If True, the condition will only evaluate True once while
			the current frame is increasing. If the current frame decreases (as
			it may when an animation is looping) the condition will be reset,
			and may trigger again. This is often required for sub-steps;
			otherwise, the actions will trigger every frame until the parent
			progresses to the next state. This is especially true for starting
			animations and sounds.
		@param ob: The object whose action should be tested. If None, the object
			that evaluates this condition is used.
		'''
		self.layer = layer
		self.frame = frame
		self.ob = ob
		self.descendant_name = targetDescendant

		self.tap = tap
		self.triggered = False

	def evaluate(self, c):
		ob = self.find_source(c, self.ob, self.descendant_name)

		cfra = ob.getActionFrame(self.layer) + CondActionGE.FRAME_EPSILON
		if not self.tap:
			# Simple mode
			return cfra >= self.frame
		else:
			# Memory (loop) mode
			if self.triggered and cfra < self.frame:
				self.triggered = False
				return False
			elif not self.triggered and cfra >= self.frame:
				self.triggered = True
				return True
			else:
				return False

	def get_short_name(self):
		return "ActGE(%s)" % self.frame

class CondEvent(Condition):
	'''
	Continue if an event is received.
	'''
	def __init__(self, message, owner):
		self.message = message
		self.triggered = False
		self.owner = owner

	@property
	def invalid(self):
		return self.owner.invalid

	def enable(self, enabled):
		# This should not result in a memory leak, because the EventBus uses a
		# SafeSet to store the listeners. Thus when the object that owns this
		# state machine dies, so will this condition, and it will be removed
		# from the EventBus.
		if enabled:
			bat.event.EventBus().add_listener(self)
		else:
			bat.event.EventBus().remove_listener(self)
			self.triggered = False

	def on_event(self, evt):
		if evt.message == self.message:
			self.triggered = True

	def evaluate(self, c):
		return self.triggered

	def get_short_name(self):
		return "Evt(%s)" % self.message

class CondEventEq(Condition):
	'''
	Continue if an event is received, and its body is equal to the specified
	value.
	'''
	def __init__(self, message, body, owner):
		self.message = message
		self.body = body
		self.triggered = False
		self.owner = owner

	@property
	def invalid(self):
		return self.owner.invalid

	def enable(self, enabled):
		if enabled:
			bat.event.EventBus().add_listener(self)
		else:
			bat.event.EventBus().remove_listener(self)
			self.triggered = False

	def on_event(self, evt):
		if evt.message == self.message and evt.body == self.body:
			self.triggered = True

	def evaluate(self, c):
		return self.triggered

	def get_short_name(self):
		return "EvtEQ(%s, %s)" % (self.message, self.body)

# This cannot be replaced by CNot(CondEventEq)
class CondEventNe(Condition):
	'''
	Continue if an event is received, and its body is NOT equal to the specified
	value. Note that this will not be True until the event is received;
	therefore, this is NOT equivalent to CNot(CondEventEq).
	'''
	def __init__(self, message, body, owner):
		self.message = message
		self.body = body
		self.triggered = False
		self.owner = owner

	@property
	def invalid(self):
		return self.owner.invalid

	def enable(self, enabled):
		if enabled:
			bat.event.EventBus().add_listener(self)
		else:
			bat.event.EventBus().remove_listener(self)
			self.triggered = False

	def on_event(self, evt):
		if evt.message == self.message and evt.body != self.body:
			self.triggered = True

	def evaluate(self, c):
		return self.triggered

	def get_short_name(self):
		return "EvtNE(%s, %s)" % (self.message, self.body)

class CondStore(Condition):
	def __init__(self, path, value, default=None):
		self.path = path
		self.value = value
		self.default = default

	def evaluate(self, c):
		return self.value == bat.store.get(self.path, self.default)

	def get_short_name(self):
		return "StoreEQ(%s, %s)" % (self.path, self.value)

class CondWait(Condition):
	'''A condition that waits for a certain time after being enabled.'''
	def __init__(self, duration):
		self.duration = duration
		self.start = None
		self.triggered = False

	def enable(self, enabled):
		if enabled:
			self.start = time.time()
		else:
			self.start = None

	def evaluate(self, c):
		return time.time() - self.duration > self.start

	def get_short_name(self):
		return "Wait(%s)" % self.duration

#
# Actions. These belong to and are executed by steps.
#
class BaseAct:
	def execute(self, c):
		pass

	def resolve(self, ob, descendant_name=None):
		if hasattr(ob, '__call__'):
			# Object is a function; call it to resolve.
			sig = inspect.signature(ob)
			if len(sig.parameters) == 1:
				ob = ob(self)
			else:
				ob = ob()

		if ob is None:
			ob = bge.logic.getCurrentController().owner
		elif isinstance(ob, str):
			# Object is a name; dereference it.
			ob = bge.logic.getCurrentScene().objects[ob]

		if descendant_name is not None:
			ob = ob.childrenRecursive[descendant_name]
		return ob

	def __str__(self):
		return self.__class__.__name__

class TargetedAct:
	def __init__(self, ob_or_name, descendant_name):
		self.ob_or_name = ob_or_name
		self.descendant_name = descendant_name

	@property
	def target(self):
		return self.resolve(self.ob_or_name, self.descendant_name)

class ActStoreSet(BaseAct):
	'''Write to the save game file.'''
	def __init__(self, path, value):
		self.path = path
		self.value = value

	def execute(self, c):
		bat.store.put(self.path, self.value)

class ActAttrSet(TargetedAct, BaseAct):
	'''Set a Python attribute on the object.'''
	def __init__(self, name, value, ob=None, target_descendant=None):
		TargetedAct.__init__(self, ob, target_descendant)
		self.name = name
		self.value = value

	def execute(self, c):
		setattr(self.target, self.name, self.value)

	def __str__(self):
		return "ActAttrSet(%s <- %s)" % (self.name, self.value)

class ActAttrLerp(TargetedAct, BaseAct):
	'''Interpolate an attribute between two values.'''

	log = logging.getLogger(__name__ + '.ActAttrLerp')

	def __init__(self, name, a, b, duration, clamp=True, ob=None, target_descendant=None):
		TargetedAct.__init__(self, ob, target_descendant)
		self.name = name
		self.interpolator = bat.bmath.LinearInterpolator.from_duration(a, b, duration)
		self.interpolator.clamp = clamp

	def execute(self, c):
		ob = self.target
		val = getattr(ob, self.name)
		new_val = self.interpolator.interpolate(val)
		ActAttrLerp.log.debug("%s = %s -> %s", self.name, val, new_val)
		setattr(ob, self.name, new_val)

	def __str__(self):
		return "ActAttrLerp(%s <- %s - %s)" % (self.name, self.interpolator.a, self.interpolator.b)

class ActPropSet(TargetedAct, BaseAct):
	'''Set a game property on the object.'''
	def __init__(self, name, value, ob=None, target_descendant=None):
		TargetedAct.__init__(self, ob, target_descendant)
		self.name = name
		self.value = value

	def execute(self, c):
		self.target[self.name] = self.value

	def __str__(self):
		return "ActPropSet(%s <- %s)" % (self.name, self.value)

class ActPropLerp(TargetedAct, BaseAct):
	'''Interpolate a property between two values.'''

	log = logging.getLogger(__name__ + '.ActPropLerp')

	def __init__(self, name, a, b, duration, clamp=True, ob=None, target_descendant=None):
		TargetedAct.__init__(self, ob, target_descendant)
		self.name = name
		self.interpolator = bat.bmath.LinearInterpolator.from_duration(a, b, duration)
		self.interpolator.clamp = clamp

	def execute(self, c):
		ob = self.target
		val = ob[self.name]
		new_val = self.interpolator.interpolate(val)
		ActPropLerp.log.debug("%s = %s -> %s", self.name, val, new_val)
		ob[self.name] = new_val

	def __str__(self):
		return "ActPropLerp(%s <- %s - %s)" % (self.name, self.a, self.b)

class ActStateChange(TargetedAct, BaseAct):
	'''Set a game property on the object.'''
	def __init__(self, operation, value, ob=None, target_descendant=None):
		TargetedAct.__init__(self, ob, target_descendant)
		self.operation = operation
		self.value = value

	def execute(self, c):
		if self.operation == 'SET':
			bat.utils.set_state(self.target, self.value)
		if self.operation == 'ADD':
			bat.utils.add_state(self.target, self.value)
		if self.operation == 'REM':
			bat.utils.rem_state(self.target, self.value)

	def __str__(self):
		return "ActStateChange(%s %s)" % (self.operation, self.value)

class ActActuate(BaseAct):
	'''Activate an actuator.'''
	def __init__(self, actuatorName):
		self.ActuatorName = actuatorName

	def execute(self, c):
		c.activate(c.actuators[self.ActuatorName])

	def __str__(self):
		return "ActActuate(%s)" % self.ActuatorName

class ActAction(TargetedAct, BaseAct):
	'''Plays an animation.'''
	def __init__(self, action, start, end, layer=0, targetDescendant=None,
			play_mode=bge.logic.KX_ACTION_MODE_PLAY, ob=None, blendin=0.0):
		TargetedAct.__init__(self, ob, targetDescendant)
		self.action = action
		self.start = start
		self.end = end
		self.layer = layer
		self.playMode = play_mode
		self.blendin = blendin

	def execute(self, c):
		self.target.playAction(self.action, self.start, self.end, self.layer,
			blendin=self.blendin, play_mode=self.playMode)

	def __str__(self):
		return "ActAction(%s, %d -> %d)" % (self.action, self.start, self.end)

class ActActionStop(TargetedAct, BaseAct):
	'''Stops an animation.'''
	def __init__(self, layer, targetDescendant=None, ob=None):
		TargetedAct.__init__(self, ob, targetDescendant)
		self.layer = layer
		self.targetDescendant = targetDescendant
		self.ob = ob

	def execute(self, c):
		self.target.stopAction(self.layer)

	def __str__(self):
		return "ActActionStop(%d)" % self.layer

class ActConstraintSet(TargetedAct, BaseAct):
	'''
	Adjusts the strength of a constraint on an armature over a range of frames
	of an animation. It is recommended that this be used in a sub-step with no
	condition.
	'''
	def __init__(self, bone_name, constraint_name, fac, ob=None,
			target_descendant=None):
		TargetedAct.__init__(self, ob, target_descendant)
		self.name = "{}:{}".format(bone_name, constraint_name)
		self.fac = fac

	def execute(self, c):
		con = self.target.constraints[self.name]
		con.enforce = self.fac

	def __str__(self):
		return "ActConstraintSet(%s)" % (self.name)

class ActConstraintFade(TargetedAct, BaseAct):
	'''
	Adjusts the strength of a constraint on an armature over a range of frames
	of an animation. It is recommended that this be used in a sub-step with no
	condition.
	'''
	def __init__(self, bone_name, constraint_name, fac1, fac2, frame1, frame2,
			layer, ob=None, target_descendant=None):
		TargetedAct.__init__(self, ob, target_descendant)
		self.name = "{}:{}".format(bone_name, constraint_name)
		self.fac1 = fac1
		self.fac2 = fac2
		self.frame1 = frame1
		self.frame2 = frame2
		self.layer = layer

	def execute(self, c):
		ob = self.target
		con = ob.constraints[self.name]
		cfra = ob.getActionFrame(self.layer)
		k = bat.bmath.unlerp(self.frame1, self.frame2, cfra)
		power = bat.bmath.clamp(0.0, 1.0,
				bat.bmath.lerp(self.fac1, self.fac2, k))
		con.enforce = power

	def __str__(self):
		return "ActConstraintFade(%s)" % (self.name)

class ActCopyTransform(TargetedAct, BaseAct):
	'''
	Makes the targeted object copy the transform of another. If a referential is
	provided, the transform will applied to the target as though it was the
	referential object being transformed. This effectively uses the referential
	as an offset for the transform.
	'''
	def __init__(self, other, referential=None, halt=True, ob=None, target_descendant=None):
		TargetedAct.__init__(self, ob, target_descendant)
		self.other = other
		self.referential = referential
		self.halt = halt

	def execute(self, c):
		target = self.target
		other = self.resolve(self.other)
		if self.referential is not None:
			referential = self.resolve(self.referential)
		else:
			referential = self.target

		bat.bmath.set_rel_orn(target, other, referential)
		bat.bmath.set_rel_pos(target, other, referential)
		if self.halt == True:
			target.localLinearVelocity = (0, 0, 0)
			target.localAngularVelocity = (0, 0, 0)

	def __str__(self):
		return "ActCopyTransform(%s)" % (self.other)

class ActParentSet(TargetedAct, BaseAct):
	'''
	Makes the targeted object a child of another. After this, the target will be
	constrained to the parent; physics simulations will not be run on it, and
	animations will be applied in local space.
	'''
	def __init__(self, parent, referential=None, ob=None, target_descendant=None):
		TargetedAct.__init__(self, ob, target_descendant)
		self.parent = parent
		self.referential = referential

	def execute(self, c):
		parent = self.resolve(self.parent)
		self.target.setParent(parent)

	def __str__(self):
		return "ActParentSet(%s)" % (self.parent)

class ActParentRemove(TargetedAct, BaseAct):
	'''
	Un-sets the parent of the target. After this, the target will be free to
	move independently of the old parent.
	'''
	def __init__(self, ob=None, target_descendant=None):
		TargetedAct.__init__(self, ob, target_descendant)

	def execute(self, c):
		target = self.target
		target.removeParent()

	def __str__(self):
		return "ActParentRemove()"

class ActSound(BaseAct):
	'''Plays a short sound.'''

	# NOTE: Not a TargetedAct because sometimes you don't want the sound to be
	# localised! TODO: split into two Acts.

	emitter = bat.containers.weakprop("emitter")

	def __init__(self, *filenames, vol=1, pitchmin=1, pitchmax=1, emitter=None,
			mindist=None, maxdist=None):
		self.sample = bat.sound.Sample(*filenames)
		self.sample.volume = vol
		self.sample.pitchmin = pitchmin
		self.sample.pitchmax = pitchmax

		if emitter is not None:
			if maxdist is not None and mindist is not None:
				localise = bat.sound.Localise(emitter, distmin=mindist, distmax=maxdist)
			elif maxdist is not None :
				localise = bat.sound.Localise(emitter, distmax=maxdist)
			elif mindist is not None :
				localise = bat.sound.Localise(emitter, distmin=mindist)
			else:
				localise = bat.sound.Localise(emitter)
			self.sample.add_effect(localise)

	def execute(self, c):
		self.sample.copy().play()

	def __str__(self):
		return "ActSound(%s)" % self.sample

class ActMusicPlay(TargetedAct, BaseAct):
	'''
	Plays a music track. The previous track will be stopped, but will remain
	queued in the jukebox.

	Music is associated with a real object (the 'target'). If the object dies,
	the music will stop. To stop music manually, use ActMusicStop with the same
	object.
	'''
	def __init__(self, *filepaths, volume=1.0, loop=True, introfile=None,
			ob=None, target_descendant=None, priority=2, fade_in_rate=None,
			fade_out_rate=None, name=None):
		TargetedAct.__init__(self, ob, target_descendant)
		self.filepaths = filepaths
		self.introfile = introfile
		self.volume = volume
		self.loop = loop
		self.priority = priority
		self._name = name

		self.fade_in_rate = bat.sound.FADE_RATE if fade_in_rate is None else fade_in_rate
		self.fade_out_rate = bat.sound.FADE_RATE if fade_out_rate is None else fade_out_rate

	@property
	def name(self):
		if self._name is None:
			return self.target.name
		else:
			return self._name

	def execute(self, c):
		# Play the track. Use priority 1 for this kind of music, because it's
		# important for the story.
		target = self.target
		bat.sound.Jukebox().play_files(self.name, target, self.priority,
				*self.filepaths, introfile=self.introfile, volume=self.volume,
				fade_in_rate=self.fade_in_rate, fade_out_rate=self.fade_out_rate)

	def __str__(self):
		return "ActMusicPlay(%s)" % str(self.name)

class ActMusicStop(TargetedAct, BaseAct):
	'''
	Stops a music track. The previous track on the jukebox stack will then play
	again.

	Music is associated with a real object. See ActMusicPlay for details.
	'''
	def __init__(self, fade_rate=None, ob=None, target_descendant=None, name=None):
		TargetedAct.__init__(self, ob, target_descendant)
		if fade_rate is not None and not hasattr(fade_rate, '__sub__'):
			raise TypeError('fade_rate must be numeric.')
		self.fade_rate = fade_rate
		self._name = name

	@property
	def name(self):
		if self._name is None:
			return self.target.name
		else:
			return self._name

	def execute(self, c):
		bat.sound.Jukebox().stop(self.name, self.fade_rate)

	def __str__(self):
		return "ActMusicStop(%s)" % str(self.name)

class ActGeneric(BaseAct):
	'''Run any function.'''
	def __init__(self, f, *args):
		self.Function = f
		self.args = args

	def execute(self, c):
		try:
			self.Function(*self.args)
		except Exception as e:
			raise StoryError("Error executing " + str(self.Function), e)

	def __str__(self):
		return "ActGeneric(%s)" % self.Function.__name__

class ActGenericContext(ActGeneric):
	'''Run any function, passing in the current controller as the first
	argument.'''
	def execute(self, c):
		try:
			self.Function(c, *self.args)
		except Exception as e:
			raise StoryError("Error executing " + str(self.Function), e)

class ActEvent(BaseAct):
	'''Fire an event.'''
	def __init__(self, event):
		self.event = event

	def execute(self, c):
		bat.event.EventBus().notify(self.event)

	def __str__(self):
		return "ActEvent(%s)" % self.event.message

class ActEventOb(TargetedAct, BaseAct):
	'''Fire an event, using this object or a specified object as the body.'''
	def __init__(self, message, delay=0, ob=None, target_descendant=None):
		TargetedAct.__init__(self, ob, target_descendant)
		self.message = message
		self.delay = delay

	def execute(self, c):
		evt = bat.event.WeakEvent(self.message, self.target)
		evt.send(delay=self.delay)
		bat.event.EventBus().notify(self.event)

	def __str__(self):
		return "ActEventOb(%s)" % self.event.message

class ActAddObject(TargetedAct, BaseAct):
	'''Add an object to the scene at the same location as target.'''
	def __init__(self, name, lifetime=0, ob=None, target_descendant=None):
		TargetedAct.__init__(self, ob, target_descendant)
		self.name = name
		self.lifetime = lifetime

	def execute(self, c):
		sce = bge.logic.getCurrentScene()
		sce.addObject(self.name, self.target, self.lifetime)

class ActDestroy(TargetedAct, BaseAct):
	'''Remove an object from the scene.'''
	def __init__(self, ob=None, target_descendant=None):
		TargetedAct.__init__(self, ob, target_descendant)

	def execute(self, c):
		self.target.endObject()


class AnimBuilder:
	'''
	Simplifies creation of animation steps in a story graph. AnimBuilders are
	bound to an object and action; sections of the action can then be added to
	the story by calling the play, loop or recall methods.
	'''
	def __init__(self, action, layer=0, blendin=0, ob=None, target_descendant=None):
		self.action = action
		self.layer = layer
		self.blendin = blendin
		self.ob = ob
		self.target_descendant = target_descendant
		self.named_actions = {}

	def play(self, state, start, end, loop_end=None, blendin=None):
		'''
		Add a section of this animation to a state.
		@param start: The start frame of the section.
		@param end: The end frame of the animation.
		@param loop_end: If not None, the end frame of the loop. The loop will
				play after the first nominated section of the animation.

		E.g. play(s, 1, 40, 90) will add an ActAction action to state s. The
		animation will play from frame 1 to 40, and will then loop from frame 40
		to 90.
		'''
		if blendin is None:
			blendin = self.blendin

		act = bat.story.ActAction(self.action, start, end, layer=self.layer,
				blendin=blendin, ob=self.ob,
				targetDescendant=self.target_descendant)

		state.add_action(act)
		if loop_end is not None:
			self.loop(state, end, loop_end, after=end, blendin=blendin)

	def loop(self, state, loop_start, loop_end, after=None, blendin=None):
		'''
		Add a looping section of an animation to a state.
		@param loop_start: The start frame of the loop.
		@param loop_end: The end frame of the loop.
		@param after: If not None, the animation will wait until the currently-
				playing animation reaches this frame number.
		'''
		if blendin is None:
			blendin = self.blendin

		act = bat.story.ActAction(self.action, loop_start, loop_end,
				self.layer, blendin=blendin,
				play_mode=bge.logic.KX_ACTION_MODE_LOOP,
				ob=self.ob, targetDescendant=self.target_descendant)
		self._enqueue(state, act, after)

	def store(self, name, start, end, loop=False, blendin=None):
		'''
		Bake an animation segment so it can be reused easily.
		@param name: The name of this segment.
		@param start: The start frame of the segment.
		@param end: The end frame of the segment.
		@param loop: Whether the animation should loop.
		'''
		if blendin is None:
			blendin = self.blendin

		if loop:
			play_mode = bge.logic.KX_ACTION_MODE_LOOP
		else:
			play_mode = bge.logic.KX_ACTION_MODE_PLAY

		act = bat.story.ActAction(self.action, start, end, layer=self.layer,
				blendin=blendin, play_mode=play_mode, ob=self.ob,
				targetDescendant=self.target_descendant)
		self.named_actions[name] = act

	def recall(self, state, name, after=None):
		'''
		Add a stored animation segment to a state.
		@param state: The state to add the action to.
		@param after: If not None, the animation will wait until the currently-
				playing animation reaches this frame number.
		'''
		act = self.named_actions[name]
		self._enqueue(state, act, after)

	def _enqueue(self, state, action, after):
		if after is not None:
			sub = state.create_sub_step()
			sub.add_condition(bat.story.CondActionGE(0, after,
					targetDescendant=self.target_descendant, tap=True))
			sub.add_action(action)
		else:
			state.add_action(action)

#
# Steps. These are executed by Characters when their conditions are met and they
# are at the front of the queue.
#

def get_caller_info():
	_, filename, lineno, _, _, _ = inspect.stack()[2]
	return "%s:%d" % (os.path.basename(filename), lineno)

class State:
	'''These comprise state machines that may be used to drive a scripted
	sequence, e.g. a dialogue with a non-player character.

	A State may have links to other states; these links are called
	'transitions'. When a State is active, its transitions will be polled
	repeatedly. When a transitions' conditions all test positive, it will be
	made the next active State. At that time, all actions associated with it
	will be executed.

	@see: Chapter'''

	log = logging.getLogger(__name__ + '.State')

	def __init__(self, name=None):
		if name is None:
			name = get_caller_info()
		self.name = name
		self.conditions = []
		self.actions = []
		self.transitions = []
		self.subSteps = []
		self.blocked_transitions = set()

	def add_condition(self, condition):
		'''
		Conditions control transition to this state.
		@return: self, for chaining.
		'''
		self.conditions.append(condition)
		return self

	def add_action(self, action):
		'''
		Actions will run when this state becomes active.
		@return: self, for chaining.
		'''
		self.actions.append(action)
		return self

	def add_event(self, message, body=None):
		'''
		Convenience method to add an ActEvent action.
		@return: self, for chaining.
		'''
		if hasattr(body, 'invalid'):
			evt = bat.event.WeakEvent(message, body)
		else:
			evt = bat.event.Event(message, body)
		self.actions.append(ActEvent(evt))
		return self

	def add_predecessor(self, preceding_state):
		'''
		Make this state run after another state.
		@see: add_successor
		@see: create_successor
		@return: self, for chaining.
		'''
		preceding_state.add_successor(self)
		return self

	def add_successor(self, following_state):
		'''
		Transitions are links to other states. During evaluation, the state will
		progress from this state to one of its transitions when all conditions
		of that transition are satisfied.

		Transitions are evaluated *in order*, i.e. if two transitions both have
		their conditions met, the one that was added first is progressed to
		next.
		@see: add_predecessor
		@see: create_successor
		@see: add_sub_step
		@return: self, for chaining.
		'''
		self.transitions.append(following_state)
		return self

	def create_successor(self, stateName=None):
		'''Create a new State and add it as a transition of this one.
		@return: the new state.'''
		if stateName is None:
			stateName = get_caller_info()
		s = State(stateName)
		self.add_successor(s)
		return s

	def add_sub_step(self, state):
		'''
		Add a sub-step to this state. Sub-steps are like regular states, but
		they are never transitioned to; instead, they are evaluated every frame
		that the parent is active.
		@see: create_sub_step
		@see: add_successor
		@return: self, for chaining.
		'''
		self.subSteps.append(state)
		return self

	def __call__(self, thing, body=None):
		'''
		Add a condition, action, event or sub-state to this state.
		This is called as though the state is a function, and reduces verbosity
		when chaining. For example, the following code would create a state that
		sends the message "foo" after a half-second delay:

			state = (bat.story.State()
				(bat.story.CondWait(0.5))
				(bar.story.ActDestroy())
				("foo", "bar")
			)

		@see: add_sub_step
		@see: add_condition
		@see: add_action
		@see: add_event
		@return: self, for chaining.
		'''
		if hasattr(thing, 'progress'):
			self.add_sub_step(thing)
		elif hasattr(thing, 'evaluate'):
			self.add_condition(thing)
		elif hasattr(thing, 'execute'):
			self.add_action(thing)
		elif isinstance(thing, str):
			self.add_event(thing, body)
		else:
			raise TypeError("Can't add unrecognised argument %s" % thing.__class__)
		return self

	def create_sub_step(self, stateName=""):
		'''
		@see: add_sub_step
		'''
		s = State(stateName)
		self.add_sub_step(s)
		return s

	def activate(self, c):
		State.log.debug('Activating %s', self)
		for state in self.transitions:
			state.parent_activated(True)
		for state in self.subSteps:
			state.parent_activated(True)
		self.execute(c)

	def deactivate(self):
		State.log.info('Deactivating %s', self)
		for state in self.transitions:
			state.parent_activated(False)
		for state in self.subSteps:
			state.parent_activated(False)

	def parent_activated(self, activated):
		for condition in self.conditions:
			condition.enable(activated)

	def execute(self, c):
		'''Run all actions associated with this state.'''
		for act in self.actions:
			try:
				State.log.info('%s', act)
				act.execute(c)
			except Exception as e:
				State.log.warn('Action %s failed: %s', act, e)
				State.log.debug('Details:', exc_info=1)

	def progress(self, c):
		'''Find the next state that has all conditions met, or None if no such
		state exists.'''
		for state in self.subSteps:
			if state.test(c, None):
				state.execute(c)

		target = None

		# Record debugging information, if enabled.
		if State.log.isEnabledFor(10):
			blocked_transitions = set()
		else:
			blocked_transitions = None

		# Check for transitions.
		for state in self.transitions:
			if state.test(c, blocked_transitions):
				target = state
				break

		# Print debugging information.
		if blocked_transitions is not None and blocked_transitions != self.blocked_transitions:
			if len(blocked_transitions) > 0:
				State.log.debug('Blocked transitions: %s', blocked_transitions)
			self.blocked_transitions = blocked_transitions

		return target

	def test(self, c, blocked_transitions):
		'''Check whether this state is ready to be transitioned to.'''
		failed_condition = None
		for condition in self.conditions:
			if not condition.evaluate(c):
				failed_condition = condition
				break
		if failed_condition is not None:
			if blocked_transitions is not None:
				blocked_transitions.add('%s#%s' % (self.name, failed_condition.get_short_name()))
			return False
		else:
			return True

	def __str__(self):
		return "State({})".format(self.name)

class Chapter(bat.bats.BX_GameObject):
	'''Embodies a story in the scene. Subclass this to define the story
	(add transitions to self.rootState). Then call 'progress' on each frame to
	allow the steps to be executed.'''

	_prefix = ''

	log = logging.getLogger(__name__ + '.Chapter')

	def __init__(self, old_owner):
		# Need one dummy transition before root state to ensure the children of
		# the root get activated.
		self.zeroState = State(name="Zero")
		self.rootState = self.zeroState.create_successor("Root")
		self.currentState = self.zeroState
		self.super_state = None
		self.super_active = False

	@bat.bats.expose
	@bat.utils.controller_cls
	def progress(self, c):
		# Evaluate the current state first to find the next transition.
		if self.currentState is not None:
			next_state = self.currentState.progress(c)
			if next_state is not None:
				self.transition(c, next_state)
				return

		# If no transitions occur, evaluate the super state. This is done second
		# because the super state is global, so the user may want to override it
		# locally.
		if self.super_state is not None:
			if not self.super_active:
				self.super_state.activate(c)
				self.super_active = True
			next_state = self.super_state.progress(c)
			if next_state is not None:
				Chapter.log.info("Super state triggered")
				self.super_state.deactivate()
				self.super_active = False
				self.transition(c, next_state)

	def transition(self, c, state):
		self.currentState.deactivate()
		self.currentState = state
		Chapter.log.info("Transitioned to %s", self.currentState)
		self.currentState.activate(c)
