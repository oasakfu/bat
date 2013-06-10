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
import abc

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

	PRI = {'PLAYER': 0, 'STORY': 1, 'DIALOGUE': 2, 'MENU': 3, 'MAINMENU': 4}

	def __init__(self):
		self.handlers = bat.containers.SafePriorityStack()
		self.clear_buttons()

		self.clear_sequences()
		self.sequence = ""
		self.capturing = None

	@bat.bats.expose
	@bat.utils.controller_cls
	@bat.bats.once_per_tick
	def process(self, c):
		'''Distribute all events to the listeners.'''

		if self.capturing is not None:
			self._capture()

		self.update_buttons(c)
		self.distribute_events()
		self.check_sequences()

	@bat.bats.profile()
	def update_buttons(self, c):
		js = c.sensors['Joystick']
		for btn in self.buttons:
			btn.update(js)

	@bat.bats.profile()
	def distribute_events(self):
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

	@bat.bats.profile()
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

	def add_controller(self, controller):
		'''
		Add a button to the input manager. It will be evaluated on every logic
		tick, and the handers will be notified.
		'''
		self.buttons.append(controller)

	def get_controller(self, name):
		for controller in self.buttons:
			if controller.name == name:
				return controller
		raise KeyError('No controller named %s' % name)

	def get_root_controller(self, path):
		pathcs = path.split('/')
		controller = self.get_controller(pathcs[0])
		return controller, '/'.join(pathcs[1:])

	def bind(self, path, sensor_type, *sensor_opts):
		'Bind a sensor to a controller with the given path.'
		Input.log.info('Binding %s to %s', sensor_type, path)
		controller, remainder = self.get_root_controller(path)
		controller.bind(remainder, sensor_type, *sensor_opts)

	def unbind(self, sensor_type, *sensor_opts):
		'Unbind a sensor from all controllers.'
		Input.log.info('Unbinding %s', sensor_type)
		for controller in self.buttons:
			controller.unbind(sensor_type, *sensor_opts)

	def unbind_all(self, path=None):
		if path is None:
			for controller in self.buttons:
				controller.unbind_all()
		else:
			controller = self.get_root_controller(path)
			controller.unbind_all()

	def sensor_def_to_human_string(self, sensor_type, *sensor_opts):
		cls = get_sensor_class(sensor_type)
		return cls.parms_to_human_string(*sensor_opts)

	@bat.bats.profile()
	def _capture(self):
		Input.log.debug('Capturing...')
		def _input_captured(params):
			Input.log.info('Captured %s', params)
			bat.event.Event('InputCaptured', params).send(1)

		keyboard = bge.logic.keyboard
		if 'BUTTON' in self.capturing:
			for key in keyboard.active_events:
				key = from_keycode(key)
				_input_captured(('keyboard', key))
				return

		js = get_joystick()
		if js is not None:
			if 'BUTTON' in self.capturing:
				if len(js.activeButtons) > 0:
					_input_captured(('joybutton', js.activeButtons[0]))
					return
			if 'BUTTON' in self.capturing:
				for i, hat_value in enumerate(js.hatValues):
					if hat_value == 0:
						continue
					if hat_value & 1 != 0:
						hat_value = hat_value & 1
					elif hat_value & 2 != 0:
						hat_value = hat_value & 2
					elif hat_value & 4 != 0:
						hat_value = hat_value & 4
					elif hat_value & 8 != 0:
						hat_value = hat_value & 8
					_input_captured(('joydpad', i, hat_value))
					return
			if 'AXIS' in self.capturing:
				for i, axis_value in enumerate(js.axisValues):
					if abs(axis_value) < 0.5:
						continue
					_input_captured(('joystick', i))
					return

		mouse = bge.logic.mouse
		if 'BUTTON' in self.capturing:
			for key in mouse.active_events:
				if key in {bge.events.MOUSEX, bge.events.MOUSEY}:
					# Mouse movement generates events... :[
					continue
				key = from_keycode(key)
				_input_captured(('mousebutton', key))
				return
		if 'AXIS' in self.capturing:
			pos = mouse.position
			for i in range(2):
				if abs(pos[i] - self.capture_mouse_pos[i]) > 0.2:
					_input_captured(('mouselook', i))
					return

	def start_capturing(self, sensor_categories):
		Input.log.info('Starting capture for %s', sensor_categories)
		self.capture_mouse_pos = bge.logic.mouse.position
		self.capturing = sensor_categories

	def start_capturing_for(self, path):
		controller, remainder = self.get_root_controller(path)
		sensor_cats = controller.get_sensor_categories(remainder)
		self.start_capturing(sensor_cats)

	def stop_capturing(self):
		Input.log.info('Stopping capture')
		self.capturing = None

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

	def clear_sequences(self):
		self.sequence_map = {}
		self.max_seq_len = 0

# Source constants can be used to determine which devices caused a button to
# become active.
SRC_NONE = 0
SRC_KEYBOARD = 1<<0
SRC_JOYSTICK = 1<<1
SRC_JOYSTICK_AXIS = 1<<2
SRC_MOUSE = 1<<3
SRC_MOUSE_AXIS = 1<<4

class Controller(metaclass=abc.ABCMeta):
	def create_sensor(self, sensor_type, *sensor_opts):
		return get_sensor_class(sensor_type)(*sensor_opts)

	@abc.abstractclassmethod
	def update(self, js):
		pass
	@abc.abstractclassmethod
	def get_char(self):
		return None

	@abc.abstractclassmethod
	def bind(self, path, sensor_type, *sensor_opts):
		pass
	@abc.abstractclassmethod
	def unbind(self, sensor_type, *sensor_opts):
		pass
	@abc.abstractclassmethod
	def unbind_all(self):
		pass
	@abc.abstractclassmethod
	def get_bindings(self, path):
		return []
	@abc.abstractclassmethod
	def get_sensor_categories(self, path):
		return set()

class Button(Controller):
	'''A simple button (0 dimensions).'''

	log = logging.getLogger(__name__ + '.Button')

	def __init__(self, name, char):
		self.name = name
		self.char = char
		self.sensors = []

		self.positive = False
		self.triggered = False
		self.source = SRC_NONE

	def bind(self, path, sensor_type, *sensor_opts):
		if path != '':
			raise KeyError('No controller called "%s"' % path)
		sensor = self.create_sensor(sensor_type, *sensor_opts)
		Button.log.info('Binding %s to %s', sensor, self.name)
		self.sensors.append(sensor)

	def unbind(self, sensor_type, *sensor_opts):
		for sensor in self.sensors[:]:
			if sensor.matches(sensor_type, *sensor_opts):
				Button.log.info('Unbinding %s from %s', sensor, self.name)
				self.sensors.remove(sensor)

	def unbind_all(self):
		self.sensors = []

	def get_bindings(self, path):
		return self.sensors

	def get_sensor_categories(self, path):
		if path != '':
			raise KeyError('No controller called "%s"' % path)
		return {'BUTTON'}

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
		src = SRC_NONE
		for s in self.sensors:
			if s.evaluate(bge.logic.keyboard.active_events, js):
				positive = True
				src |= s.source

		if positive != self.positive:
			self.triggered = True
			self.positive = positive
			Button.log.debug("%s", self)
		else:
			self.triggered = False
		self.source = src

	def get_char(self):
		if self.activated:
			return self.char
		else:
			return None

	def __str__(self):
		return "Button %s - positive: %s, triggered: %s" % (self.name, 
				self.positive, self.triggered)

AXIS_EPSILON = 0.01

class DPad1D(Controller):
	'''
	Accumulates directional input (1 dimension). Useful for things like L/R
	shoulder buttons.
	'''

	log = logging.getLogger(__name__ + '.DPad1D')

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
		self.source = SRC_NONE

	def bind(self, path, sensor_type, *sensor_opts):
		if path == 'next':
			self.next.bind('', sensor_type, *sensor_opts)
		elif path == 'prev':
			self.prev.bind('', sensor_type, *sensor_opts)
		elif path == 'axis':
			sensor = self.create_sensor(sensor_type, *sensor_opts)
			DPad1D.log.info('Binding %s to %s/axis', sensor, self.name)
			self.axes.append()
		else:
			raise KeyError('No controller called "%s"' % path)

	def unbind(self, sensor_type, *sensor_opts):
		self.next.unbind(sensor_type, *sensor_opts)
		self.prev.unbind(sensor_type, *sensor_opts)
		for sensor in self.axes[:]:
			if sensor.matches(sensor_type, *sensor_opts):
				DPad1D.log.info('Unbinding %s from %s/axis', sensor, self.name)
				self.axes.remove(sensor)

	def unbind_all(self):
		self.next.unbind_all()
		self.prev.unbind_all()
		self.axes = []

	def get_bindings(self, path):
		if path == 'next':
			self.next.get_bindings('')
		elif path == 'prev':
			self.prev.get_bindings('')
		elif path == 'axis':
			return self.axes
		else:
			raise KeyError('No controller called "%s"' % path)

	def get_sensor_categories(self, path):
		if path in {'next', 'prev'}:
			return {'BUTTON'}
		elif path == 'axis':
			return {'AXIS'}
		else:
			raise KeyError('No controller called "%s"' % path)

	def update(self, js):
		self.next.update(js)
		self.prev.update(js)

		src = SRC_NONE
		x = 0.0
		if self.next.positive:
			src |= self.next.source
			x += 1.0
		if self.prev.positive:
			src |= self.prev.source
			x -= 1.0
		for axis in self.axes:
			val = axis.evaluate(bge.logic.keyboard.active_events, js)
			if abs(val) > AXIS_EPSILON:
				src |= axis.source
				x += val

		if x > 1.0:
			x = 1.0
		elif x < -1.0:
			x = -1.0

		self.direction = x
		self.source = src

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

class DPad2D(Controller):
	'''
	Accumulates directional input (2 dimensions) - from directional pads,
	joysticks, and nominated keyboard keys.
	'''

	log = logging.getLogger(__name__ + '.DPad2D')

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
		self.source = SRC_NONE

	def bind(self, path, sensor_type, *sensor_opts):
		if path == 'up':
			self.up.bind('', sensor_type, *sensor_opts)
		elif path == 'down':
			self.down.bind('', sensor_type, *sensor_opts)
		elif path == 'left':
			self.left.bind('', sensor_type, *sensor_opts)
		elif path == 'right':
			self.right.bind('', sensor_type, *sensor_opts)
		elif path == 'xaxis':
			sensor = self.create_sensor(sensor_type, *sensor_opts)
			DPad2D.log.info('Binding %s to %s/xaxis', sensor, self.name)
			self.xaxes.append(self.create_sensor(sensor_type, *sensor_opts))
		elif path == 'yaxis':
			sensor = self.create_sensor(sensor_type, *sensor_opts)
			DPad2D.log.info('Binding %s to %s/yaxis', sensor, self.name)
			self.yaxes.append(self.create_sensor(sensor_type, *sensor_opts))
		else:
			raise KeyError('No controller called "%s"' % path)

	def unbind(self, sensor_type, *sensor_opts):
		self.up.unbind(sensor_type, *sensor_opts)
		self.down.unbind(sensor_type, *sensor_opts)
		self.left.unbind(sensor_type, *sensor_opts)
		self.right.unbind(sensor_type, *sensor_opts)
		for sensor in self.xaxes[:]:
			if sensor.matches(sensor_type, *sensor_opts):
				DPad2D.log.info('Unbinding %s from %s/xaxis', sensor, self.name)
				self.xaxes.remove(sensor)
		for sensor in self.yaxes[:]:
			if sensor.matches(sensor_type, *sensor_opts):
				DPad2D.log.info('Unbinding %s from %s/yaxis', sensor, self.name)
				self.yaxes.remove(sensor)

	def unbind_all(self):
		self.up.unbind_all()
		self.down.unbind_all()
		self.left.unbind_all()
		self.right.unbind_all()
		self.xaxes = []
		self.yaxes = []

	def get_bindings(self, path):
		if path == 'up':
			return self.up.get_bindings('')
		elif path == 'down':
			return self.down.get_bindings('')
		elif path == 'left':
			return self.left.get_bindings('')
		elif path == 'right':
			return self.right.get_bindings('')
		elif path == 'xaxis':
			return self.xaxes
		elif path == 'yaxis':
			return self.yaxes
		else:
			raise KeyError('No controller called "%s"' % path)

	def get_sensor_categories(self, path):
		if path in {'up', 'down', 'left', 'right'}:
			return {'BUTTON'}
		elif path in {'xaxis', 'yaxis'}:
			return {'AXIS'}
		else:
			raise KeyError('No controller called "%s"' % path)

	def update(self, js):
		self.up.update(js)
		self.down.update(js)
		self.left.update(js)
		self.right.update(js)

		src = SRC_NONE
		y = 0.0
		if self.up.positive:
			src |= self.up.source
			y += 1.0
		if self.down.positive:
			src |= self.down.source
			y -= 1.0
		for axis in self.yaxes:
			# Note: Invert Y-axis
			val = axis.evaluate(bge.logic.keyboard.active_events, js)
			if abs(val) > AXIS_EPSILON:
				src |= axis.source
				y -= val

		if y > 1.0:
			y = 1.0
		elif y < -1.0:
			y = -1.0

		x = 0.0
		if self.right.positive:
			src |= self.right.source
			x += 1.0
		if self.left.positive:
			src |= self.left.source
			x -= 1.0
		for axis in self.xaxes:
			val = axis.evaluate(bge.logic.keyboard.active_events, js)
			if abs(val) > AXIS_EPSILON:
				src |= axis.source
				x += val

		if x > 1.0:
			x = 1.0
		elif x < -1.0:
			x = -1.0

		self.direction.x = x
		self.direction.y = y
		self.source = src

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

def to_keycode(name):
	return bge.events.__dict__[name.upper()]
def from_keycode(key):
	return bge.events.EventToString(key).lower()
def get_joystick():
	if len(bge.logic.joysticks) > 0:
		return bge.logic.joysticks[0]
	else:
		return None

class Sensor(metaclass=abc.ABCMeta):
	@abc.abstractmethod
	def evaluate(self, active_keys, js):
		pass

	def matches(self, sensor_type, *parameters):
		if sensor_type != self.s_type:
			return False
		if parameters != self.get_parameters():
			return False
		return True

	@abc.abstractmethod
	def get_parameters(self):
		return ()

	@classmethod
	@abc.abstractmethod
	def parms_to_human_string(cls, *parameters):
		return ''

	def __str__(self):
		return self.__class__.parms_to_human_string(*self.get_parameters())

class KeyboardSensor(Sensor):
	'''For keyboard keys.'''
	source = SRC_KEYBOARD
	s_type = "keyboard"

	def __init__(self, k):
		self.k = to_keycode(k)

	def evaluate(self, active_keys, js):
		return self.k in active_keys

	def get_parameters(self):
		return (from_keycode(self.k),)

	@classmethod
	def parms_to_human_string(cls, key_name):
		if key_name.endswith('key'):
			key_name = key_name[:-3]
		if key_name.endswith('arrow'):
			key_name = key_name[:-5]
		return key_name

class JoystickButtonSensor(Sensor):
	'''For regular joystick buttons.'''
	source = SRC_JOYSTICK
	s_type = "joybutton"

	def __init__(self, button):
		self.button = button

	def evaluate(self, active_keys, js):
		return self.button in js.getButtonActiveList()

	def get_parameters(self):
		return (self.button,)

	@classmethod
	def parms_to_human_string(cls, button):
		return "jbtn.%d" % button

class JoystickDpadSensor(Sensor):
	'''For detecting DPad presses.'''
	source = SRC_JOYSTICK
	s_type = "joydpad"

	def __init__(self, hat_index, button_flag):
		self.hat_index = hat_index
		self.button_flag = button_flag

	def evaluate(self, active_keys, js):
		try:
			return js.hatValues[self.hat_index] & self.button_flag
		except IndexError:
			# Joystick may not be plugged in.
			return False

	def get_parameters(self):
		return (self.hat_index, self.button_flag)

	@classmethod
	def parms_to_human_string(cls, hat_index, button_flag):
		return "jpad.%d.%d" % (hat_index, button_flag)

class JoystickAxisSensor(Sensor):
	'''For detecting joystick movement.'''
	source = SRC_JOYSTICK | SRC_JOYSTICK_AXIS
	s_type = "joystick"

	def __init__(self, axis_index):
		self.axis_index = axis_index

	def evaluate(self, active_keys, js):
		try:
			return js.axisValues[self.axis_index] / 32767.0
		except IndexError:
			# Joystick may not be plugged in.
			return False

	def get_parameters(self):
		return (self.axis_index,)

	@classmethod
	def parms_to_human_string(cls, axis_index):
		return "js.%d" % axis_index


class MouseAdapter(metaclass=bat.bats.Singleton):
	'''
	Ensures that mouse position is only read once per frame. This allows
	multiple callers to get and set the mouse position.
	'''
	def __init__(self):
		self._read_pos()
		#bge.logic.mouse.visible = True

	@bat.bats.once_per_tick
	def _read_pos(self):
		pos = bge.logic.mouse.position
		self._pos = list(pos)
		#print(self._pos)

	@property
	def position(self):
		self._read_pos()
		return self._pos
	@position.setter
	def position(self, pos):
		self._pos = pos
		bge.logic.mouse.position = tuple(pos)

allow_mouse_capture = True
'''
If set to false, the mouse will not be captured. When the mouse is captured, it
is returned to the centre of the screen on every frame. This is required for the
mouse look sensor, so if this is set to False the mouse look sensors will always
return zero.
'''

class MouseLookSensor(Sensor):
	'''
	For detecting mouse movement in joystick-emulation mode (i.e. not for
	pointing).
	'''

	source = SRC_MOUSE | SRC_MOUSE_AXIS
	s_type = "mouselook"
	multiplier = 1.0

	def __init__(self, axis_index):
		self.first = True
		self.axis_index = axis_index
		self.current_position = None

	def evaluate(self, active_keys, js):
		if not allow_mouse_capture:
			return 0

		# Because the mouse is placed on pixels, sometimes the centre of the
		# screen is not at (0.5, 0.5).
		if self.axis_index == 0:
			extent = bge.render.getWindowWidth()
		else:
			extent = bge.render.getWindowHeight()
		actual_centre = int(extent / 2.0) / extent

		pos = MouseAdapter().position
		offset = bat.bmath.clamp(-1, 1, (pos[self.axis_index] - actual_centre) * 2.0)
		offset *= self.multiplier
		pos[self.axis_index] = 0.5
		MouseAdapter().position = pos
		if self.first:
			# Throw first frame away so position can be reset.
			self.first = False
			return 0
		else:
			return offset

	def get_parameters(self):
		return (self.axis_index,)

	@classmethod
	def parms_to_human_string(cls, axis_index):
		return "mouse.%d" % axis_index

class MouseButtonSensor(Sensor):
	'''For detecting mouse button presses.'''
	source = SRC_MOUSE
	s_type = "mousebutton"

	def __init__(self, k):
		self.k = to_keycode(k)

	def evaluate(self, active_keys, js):
		return self.k in bge.logic.mouse.active_events

	def get_parameters(self):
		return (from_keycode(self.k),)

	@classmethod
	def parms_to_human_string(cls, button_name):
		if button_name.endswith('mouse'):
			button_name = button_name[:-5]
		return 'm.%s' %button_name

sensor_types = {
	KeyboardSensor.s_type: KeyboardSensor,
	JoystickButtonSensor.s_type: JoystickButtonSensor,
	JoystickDpadSensor.s_type: JoystickDpadSensor,
	JoystickAxisSensor.s_type: JoystickAxisSensor,
	MouseLookSensor.s_type: MouseLookSensor,
	MouseButtonSensor.s_type: MouseButtonSensor,
	}

def get_sensor_class(sensor_type):
	return sensor_types[sensor_type]

class Handler:
	'''Use as a mixin to handle input from the user.'''

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

class DirectionMapperLocal:
	'''
	Converts 2D vectors (e.g. from a player's controller) into 3D vectors that
	can be used to control a character.

	This type returns the forward vector of the character.
	'''

	log = logging.getLogger(__name__ + '.DirectionMapperLocal')

	def __init__(self):
		self.direction = None
		self.car_mode = False

	def update(self, target, impulse_vec):
		if self.car_mode and impulse_vec.y < 0:
			iv = impulse_vec.copy()
			iv.x = -iv.x
		else:
			iv = impulse_vec
		fwd_impulse = target.getAxisVect(bat.bmath.YAXIS)
		right_impulse = target.getAxisVect(bat.bmath.XAXIS)
		direction = right_impulse * iv.x
		direction += fwd_impulse * iv.y
		direction.normalize()
		self.direction = direction

class DirectionMapperView:
	'''
	Converts 2D vectors (e.g. from a player's controller) into 3D vectors that
	can be used to control a character.

	This type returns the direction that best matches the screen vector, i.e.
	y = up, x = right.
	'''

	log = logging.getLogger(__name__ + '.DirectionMapperView')

	def __init__(self):
		self.up_vec = None
		self.right_vec = None
		self.fwd_vec = None
		self.direction = None
		# Stateful flag, used to avoid singularities.
		self.use_fwd_dir = True

	def update(self, target, impulse_vec):
		cam = bge.logic.getCurrentScene().active_camera
		right_view = cam.getAxisVect(bat.bmath.XAXIS)
		#up_view = cam.getAxisVect(bat.bmath.YAXIS)
		fwd_view = cam.getAxisVect(bat.bmath.ZAXIS)
		fwd_view.negate()

		self.update_coord_space(target)

		# Decide which vector to use as a reference. Unfortunately it's not
		# possible to always use the same vector (e.g. the camera's Z axis),
		# because the cross product of two parallel vectors is zero.
		if self.use_fwd_dir:
			if abs(fwd_view.dot(self.up_vec)) > 0.9:
				self.use_fwd_dir = False
				DirectionMapperView.log.info("Using right view vector")
		else:
			if abs(right_view.dot(self.up_vec)) > 0.9:
				self.use_fwd_dir = True
				DirectionMapperView.log.info("Using forward view vector")

		if self.use_fwd_dir:
			right_impulse = fwd_view.cross(self.up_vec)
			right_impulse.normalize()
			fwd_impulse = self.up_vec.cross(right_impulse)
		else:
			fwd_impulse = self.up_vec.cross(right_view)
			fwd_impulse.normalize()
			right_impulse = fwd_impulse.cross(self.up_vec)

		direction = right_impulse * impulse_vec.x
		direction += fwd_impulse * impulse_vec.y
		direction.normalize()
		self.direction = direction

		if DirectionMapperView.log.isEnabledFor(logging.INFO):
			origin = target.worldPosition
			bge.render.drawLine(origin, (fwd_impulse * 4) + origin, bat.render.GREEN[0:3])
			bge.render.drawLine(origin, (right_impulse * 4) + origin, bat.render.RED[0:3])
			bge.render.drawLine(origin, (direction * 4) + origin, bat.render.WHITE[0:3])
			#print(direction.magnitude, right_impulse.magnitude, fwd_impulse.magnitude)

class DirectionMapperViewLocal(DirectionMapperView):
	'''Finds a direction vector on the target's XY plane.'''
	def update_coord_space(self, target):
		self.up_vec = target.getAxisVect(bat.bmath.ZAXIS)
		self.fwd_vec = target.getAxisVect(bat.bmath.YAXIS)
		self.right_vec = target.getAxisVect(bat.bmath.XAXIS)

class DirectionMapperViewGlobal(DirectionMapperView):
	'''Finds a direction vector on the global XY plane.'''
	def update_coord_space(self, target):
		self.up_vec = bat.bmath.ZAXIS
		self.fwd_vec = bat.bmath.YAXIS
		self.right_vec = bat.bmath.XAXIS
