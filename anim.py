#
# Copyright 2011 Alex Fraser <alex@phatcore.com>
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

'''
Animation controls.

In the following example, the object will be hidden once the animation reaches
the end:

	LAYER = 0
	ob.playAction('ActionName', 1, 25, layer=LAYER)
	def cb():
		ob.setVisible(False, False)
	bat.anim.add_trigger_end(ob, LAYER, cb)

'''

import bge

import bat.bats
import bat.utils

DEBUG = False

class Trigger:
	def __init__(self):
		self.current_frame = bat.bats.Timekeeper().current_frame

	def is_next_frame(self):
		'''
		Only consider animation to be complete if the next frame has actually
		been drawn.
		'''
		frame_num = bat.bats.Timekeeper().current_frame
		if self.current_frame == frame_num:
			return False
		self.current_frame = frame_num
		return True

class TriggerEnd(Trigger):
	'''Runs a callback when an animation finishes.'''

	def __init__(self, layer, callback):
		Trigger.__init__(self)
		self.layer = layer
		self.callback = callback

	def evaluate(self, ob):
		if not self.is_next_frame():
			return False
		if not ob.isPlayingAction(self.layer):
			self.callback()
			return True
		else:
			return False

class TriggerGTE(Trigger):
	'''Runs a callback on or after an animation frame.'''

	def __init__(self, layer, frame, callback):
		Trigger.__init__(self)
		self.layer = layer
		self.frame = frame
		self.callback = callback

	def evaluate(self, ob):
		if not self.is_next_frame():
			return False
		if ob.getActionFrame(self.layer) >= self.frame:
			self.callback()
			return True
		else:
			return False

class TriggerLT(Trigger):
	'''Runs a callback before an animation frame.'''

	def __init__(self, layer, frame, callback):
		Trigger.__init__(self)
		self.layer = layer
		self.frame = frame
		self.callback = callback

	def evaluate(self, ob):
		if not self.is_next_frame():
			return False
		if ob.getActionFrame(self.layer) < self.frame:
			self.callback()
			return True
		else:
			return False

class Animator(bat.bats.BX_GameObject, bge.types.KX_GameObject):
	_prefix = ""

	def __init__(self, old_owner):
		self.triggers = {}

	def add_trigger(self, ob, trigger):
		'''Adds an animation trigger. The trigger will be evaluated once per
		frame until it succeeds, or the object is destroyed.'''
		if not ob in self.triggers:
			self.triggers[ob] = []
		self.triggers[ob].append(trigger)

	@bat.bats.expose
	def run_triggers(self):
		'''Runs all triggers for the current scene.'''
		for ob in list(self.triggers.keys()):
			if ob.invalid:
				# Object has been deleted.
				if DEBUG:
					print("anim: Discarding dead object.")
				del self.triggers[ob]
				continue

			# Traverse list of triggers.
			obTriggers = self.triggers[ob]
			for trigger in list(obTriggers):
				if DEBUG:
					print("anim: Evaluating trigger")
				if trigger.evaluate(ob):
					if DEBUG:
						print("success")
					obTriggers.remove(trigger)

def get_animator(ob):
	'''Gets the animator of the given object.'''
	if hasattr(ob, 'scene'):
		# BX_GameObjects hold a reference to their scene.
		scene = ob.scene
	else:
		# KX_GameObjects don't, so we have to search for it.
		scene = bat.utils.get_scene(ob)
	return scene.objects["BXT_Animator"]

def add_trigger_end(ob, layer, callback):
	'''Adds a trigger that runs once at the end of the animation.'''
	get_animator(ob).add_trigger(ob, TriggerEnd(layer, callback))

def add_trigger_gte(ob, layer, frame, callback):
	'''Adds a trigger that runs once when 'frame' is reached (or before 'frame'
	is reached if running backwards).'''
	get_animator(ob).add_trigger(ob, TriggerGTE(layer, frame, callback))

def add_trigger_lt(ob, layer, frame, callback):
	'''Adds a trigger that runs once before 'frame' is reached (or after 'frame'
	is reached if running backwards).'''
	get_animator(ob).add_trigger(ob, TriggerLT(layer, frame, callback))


def play_children_with_offset(objects, action, start, end, layer=0,
		play_mode=bge.logic.KX_ACTION_MODE_LOOP, speed=1.0):
	'''
	Plays an action on each child of an object. Each child will start on a
	different frame, evenly spaced between 'start' and 'end'. This is especially
	useful for animating a set of objects that follow each other along a path.
	'''
	if len(objects) == 0:
		return

	offset = (end - start) / len(objects)
	for i, child in enumerate(objects):
		offset_start = (offset * i) + start
		offset_end = (offset * i) + end
		# Seems to be a bug: setActionFrame works only for one frame.
		#child.playAction(action, start, end, layer, play_mode=play_mode)
		#child.setActionFrame(offset_start, layer)
		child.playAction(action, offset_start, offset_end, layer, play_mode=play_mode, speed=speed)

