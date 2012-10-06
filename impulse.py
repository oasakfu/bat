#
# Copyright 2012 Alex Fraser <alex@phatcore.com>
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

import logging

import bge
import mathutils

import bat.bats
import bat.containers
import bat.utils
import bat.event

INITIAL_REPEAT_DELAY = 30
REPEAT_DELAY = 5

class Input(metaclass=bat.bats.Singleton):
	'''
	Provides a unified interface to input devices such as keyboard and
	joysticks.
	'''
	_prefix = ""

	log = logging.getLogger(__name__ + '.Input')

	PRI = {'PLAYER': 0, 'STORY': 1, 'DIALOGUE': 2, 'MENU': 3}

	def __init__(self):
		self.handlers = bat.containers.SafePriorityStack()
		self.buttons = []

		self.sequence_map = {}
		self.max_seq_len = 0
		self.sequence = ""

	@bat.bats.expose
	@bat.utils.controller_cls
	@bat.bats.once_per_tick
	def process(self, c):
		'''Distribute all events to the listeners.'''
		js = c.sensors['Joystick']

		for btn in self.buttons:
			btn.update(js)

		# Run through the handlers separately for each event type, because a
		# handler may accept some events and not others.

		for btn in self.buttons:
			for h in self.handlers:
				if h.can_handle_input(btn):
					Input.log.debug("%s handled by %s", btn, h)
					if hasattr(h, 'scene'):
						bat.event.SceneDispatch.call_in_scene(h.scene,
								h.handle_input, btn)
					else:
						h.handle_input(btn)
					break

		self.check_sequences()

	def check_sequences(self):
		'''
		Build up strings of button presses, looking for known combinations.
		Primarily for things like cheats, but could be used for combo moves too.
		'''
		# Add all pressed buttons to the sequence.
		new_char = False
		for btn in self.buttons:
			if btn.triggered:
				char = btn.get_char()
				if char is None:
					continue
				self.sequence += char
				new_char = True

		if not new_char:
			return

		# Scan for acceptable cheats. We don't bother doing this inside the loop
		# above, because this is all happening in one frame: if multiple buttons
		# are pressed in one frame, the order that they are added to the
		# sequence is undefined anyway, so there's no point checking after each
		# character.
		for seq in self.sequence_map.keys():
			if self.sequence.endswith(seq):
				evt = self.sequence_map[seq]
				Input.log.info("Sequence %s triggered; sending %s", seq, evt)
				evt.send()

		# Truncate
		if len(self.sequence) > self.max_seq_len:
			self.sequence = self.sequence[-self.max_seq_len:]

	def clear_buttons(self):
		self.buttons = []

	def add_button(self, sensor):
		'''
		Add a button to the input manager. It will be evaluated on every logic
		tick, and the handers will be notified.
		'''
		self.buttons.append(sensor)

	def add_handler(self, handler, priority='PLAYER'):
		'''
		Let an object receive input from the user. On every logic tick, the
		handlers will be processed in-order for all buttons. First,
		'handler.can_handle_input(state)' will be called, where 'state' is the
		button's state. If that returns True, 'handler.handle_input(state)' will
		be called. handle_input is guaranteed to be called in the context of the
		handler's own scene, if it has one. Note that that may occur one tick
		after the input was received.
		@see Handler
		'''
		self.handlers.push(handler, Input.PRI[priority])
		Input.log.info("Handlers: %s", self.handlers)

	def remove_handler(self, handler):
		self.handlers.discard(handler)
		Input.log.info("Handlers: %s", self.handlers)

	def add_sequence(self, sequence, event):
		"""
		Adds a sequence that will cause an event to be fired. Should be in the
		form for a string using characters that would be returned from
		Button.get_char - e.g. "ud1" would be Up, Down, Button1.
		"""
		self.sequence_map[sequence] = event
		if self.max_seq_len < len(sequence):
			self.max_seq_len = len(sequence)

class Button:
	'''A simple button (0 dimensions).'''

	log = logging.getLogger(__name__ + '.Button')

	def __init__(self, name, char):
		self.name = name
		self.char = char
		self.sensors = []

		self.positive = False
		self.triggered = False

	@property
	def activated(self):
		'''
		True if the button is down on this frame, for the first time. On the
		following frame, this will be false even if the button is still held
		down.
		'''
		return self.positive and self.triggered

	def update(self, js):
		positive = False
		for s in self.sensors:
			if s.evaluate(bge.logic.keyboard.active_events, js):
				positive = True
				break

		if positive != self.positive:
			self.triggered = True
			self.positive = positive
			Button.log.debug("%s", self)
		else:
			self.triggered = False

	def get_char(self):
		if self.activated:
			return self.char
		else:
			return None

	def __str__(self):
		return "Button %s - positive: %s, triggered: %s" % (self.name, 
				self.positive, self.triggered)

class DPad1D:
	'''
	Accumulates directional input (1 dimension). Useful for things like L/R
	shoulder buttons.
	'''

	def __init__(self, name, char_next, char_prev):
		self.name = name
		self.char_next = char_next
		self.char_prev = char_prev

		# Discrete buttons
		self.next = Button("next", char_next)
		self.prev = Button("prev", char_prev)
		# Continuous sensors
		self.axes = []

		self.direction = 0.0
		self.bias = 0.0
		self.dominant = None
		self.triggered = False

	def update(self, js):
		self.next.update(js)
		self.prev.update(js)

		x = 0.0
		if self.next.positive:
			x += 1.0
		if self.prev.positive:
			x -= 1.0
		for axis in self.axes:
			x += axis.evaluate(bge.logic.keyboard.active_events, js)

		if x > 1.0:
			x = 1.0
		elif x < -1.0:
			x = -1.0

		self.direction = x

		self.find_dominant_direction()

	def find_dominant_direction(self):
		"""
		Find which direction is dominant. Uses a bit of fuzzy logic to prevent
		this from switching rapidly.
		"""
		biased_direction = self.direction + self.bias * 0.1
		x = biased_direction
		bias = 0.0
		dominant = None
		if x > 0.5:
			dominant = self.char_next
			bias = 1.0
		elif x < -0.5:
			dominant = self.char_prev
			bias = -1.0

		if dominant != self.dominant:
			self.dominant = dominant
			self.bias = bias
			self.triggered = True
			Button.log.debug("%s", self)
		else:
			self.triggered = False

	def get_char(self):
		return self.dominant

	def __str__(self):
		return "Button %s - direction: %s" % (self.name, self.direction)

class DPad2D:
	'''
	Accumulates directional input (2 dimensions) - from directional pads,
	joysticks, and nominated keyboard keys.
	'''

	def __init__(self, name, char_up, char_down, char_left, char_right):
		self.name = name
		self.char_up = char_up
		self.char_down = char_down
		self.char_left = char_left
		self.char_right = char_right

		# Discrete buttons
		self.up = Button("up", char_up)
		self.down = Button("down", char_down)
		self.left = Button("left", char_left)
		self.right = Button("right", char_right)
		# Continuous sensors
		self.xaxes = []
		self.yaxes = []

		self.direction = mathutils.Vector((0.0, 0.0))
		self.bias = mathutils.Vector((0.0, 0.0))
		self.dominant = None
		self.triggered = False
		self.triggered_repeat = False
		self.repeat_delay = 0

	def update(self, js):
		self.up.update(js)
		self.down.update(js)
		self.left.update(js)
		self.right.update(js)

		y = 0.0
		if self.up.positive:
			y += 1.0
		if self.down.positive:
			y -= 1.0
		for axis in self.yaxes:
			# Note: Invert Y-axis
			y -= axis.evaluate(bge.logic.keyboard.active_events, js)

		if y > 1.0:
			y = 1.0
		elif y < -1.0:
			y = -1.0

		x = 0.0
		if self.right.positive:
			x += 1.0
		if self.left.positive:
			x -= 1.0
		for axis in self.xaxes:
			x += axis.evaluate(bge.logic.keyboard.active_events, js)

		if x > 1.0:
			x = 1.0
		elif x < -1.0:
			x = -1.0

		self.direction.x = x
		self.direction.y = y

		self.find_dominant_direction()

	def find_dominant_direction(self):
		"""
		Find the dominant direction (up, down, left or right). Uses a bit of
		fuzzy logic to prevent this from switching rapidly.
		"""
		biased_direction = self.direction + self.bias * 0.1
		x = biased_direction.x
		y = biased_direction.y

		dominant = None
		bias = mathutils.Vector((0.0, 0.0))
		if abs(x) > 0.5 + abs(y):
			if x > 0.5:
				dominant = self.char_right
				bias = mathutils.Vector((1.0, 0.0))
			elif x < -0.5:
				dominant = self.char_left
				bias = mathutils.Vector((-1.0, 0.0))
		elif abs(y) > 0.5 + abs(x):
			if y > 0.5:
				dominant = self.char_up
				bias = mathutils.Vector((0.0, 1.0))
			elif y < -0.5:
				dominant = self.char_down
				bias = mathutils.Vector((0.0, -1.0))

		if dominant != self.dominant:
			self.dominant = dominant
			self.bias = bias
			self.triggered = True
			self.triggered_repeat = True
			self.repeat_delay = INITIAL_REPEAT_DELAY
			Button.log.debug("%s", self)
		elif self.repeat_delay <= 0:
			self.triggered = False
			self.triggered_repeat = True
			self.repeat_delay = REPEAT_DELAY
		else:
			self.triggered = False
			self.triggered_repeat = False
			self.repeat_delay -= 1

	def get_char(self):
		"""
		Get the character of the dominant axis (used for sequences). If both
		axes are roughly equal, neither is dominant and this method will return
		None.
		"""
		return self.dominant

	def __str__(self):
		return "Button %s - direction: %s" % (self.name, self.direction)

class KeyboardSensor:
	'''For keyboard keys.'''
	def __init__(self, key):
		self.key = key

	def evaluate(self, active_keys, js):
		return self.key in active_keys

class JoystickButtonSensor:
	'''For regular joystick buttons.'''
	def __init__(self, button):
		self.button = button

	def evaluate(self, active_keys, js):
		return self.button in js.getButtonActiveList()

class JoystickDpadSensor:
	'''For detecting DPad presses.'''
	def __init__(self, hat_index, button_flag):
		self.hat_index = hat_index
		self.button_flag = button_flag

	def evaluate(self, active_keys, js):
		try:
			return js.hatValues[self.hat_index] & self.button_flag
		except IndexError:
			# Joystick may not be plugged in.
			return False

class JoystickAxisSensor:
	'''For detecting DPad presses.'''
	def __init__(self, axis_index):
		self.axis_index = axis_index

	def evaluate(self, active_keys, js):
		try:
			return js.axisValues[self.axis_index] / 32767.0
		except IndexError:
			# Joystick may not be plugged in.
			return False

class Handler:
	'''
	Use as a mixin to handle input from the user. Any methods that are not
	overridden will do nothing. By default, non-overridden functions will
	capture the event (preventing further processing from lower-priority
	handlers). To allow such events to pass through, set
	self.default_handler_response = False.
	'''

	def can_handle_input(self, state):
		'''
		Handle a button press.
		@param state: The state of the button. state.name
		@return: True if the input can be consumed.
		'''
		return True
	def handle_input(self, state):
		'''
		Handle a movement request from the user.
		@param state: The state of the button. Try state.positive,
				state.triggered, state.direction - depending on button type
		'''
		pass