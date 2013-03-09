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

import logging

import bge

import bat.bats
import bat.containers

class EventBus(metaclass=bat.bats.Singleton):
	'''
	Delivers messages to listeners. The listeners will be notified in the
	contexts of their own scenes.
	'''

	_prefix = ''

	log = logging.getLogger(__name__ + '.EventBus')

	def __init__(self):
		self.listeners = bat.containers.SafeSet()
		self.eventQueue = []
		self.eventCache = {}

	def add_listener(self, listener):
		'''
		Registers an object that is to be notified of events. When an event is
		sent, the listener's on_event(evt) method will be called. That method
		will be called in the context of the listener's own scene, if it has
		one.
		'''
		EventBus.log.info("Added event listener %s", listener)
		self.listeners.add(listener)

	def remove_listener(self, listener):
		self.listeners.discard(listener)

	def _enqueue(self, event, delay):
		'''Queue a message for sending after a delay.

		@param event The event to send.
		@param delay The time to wait, in frames.'''
		def queued_event_key(item):
			return item[1]
		self.eventQueue.append((event, delay))
		self.eventQueue.sort(key=queued_event_key)

	@bat.bats.expose
	@bat.utils.owner_cls
	@bat.bats.once_per_frame
	def process_queue(self, ob):
		'''Send queued messages that are ready. It is assumed that several
		objects may be calling this each frame; however, only one per frame will
		succeed.'''
		if len(self.eventQueue) == 0:
			return

		# Decrement the frame counter for each queued message.
		newQueue = []
		pending = []
		for event, delay in self.eventQueue:
			delay -= 1
			if delay <= 0:
				#print("Dispatching", event.message)
				pending.append(event)
			else:
				#print("Delaying", event.message, delay)
				newQueue.append((event, delay))

		# Replace the old queue. As the list was iterated over in-order, the new
		# queue should already be sorted.
		self.eventQueue = newQueue

		# Actually send the messages now. Doing this now instead of inside the
		# loop above allows the callee to send another delayed message in
		# response.
		for event in pending:
			self.notify(event)

	def notify(self, event, delay=0):
		'''
		Send a message.

		@param event The event to send.
		@param delay The time to wait, in rendered frames (not logic ticks). If
				zero, the event will be sent to the listeners immediately.
				However, listeners that are not in the current scene will
				receive it next time that scene is active - which may be during
				the following logic tick.
		'''

		if delay <= 0:
			self._notify(event)
		else:
			self._enqueue(event, delay)

	def _notify(self, event):
		EventBus.log.info("Sending %s", event)
		for listener in self.listeners.copy():
			EventBus.log.debug('\ttarget = %s (may get delayed)', str(listener))
			if hasattr(listener, 'scene'):
				SceneDispatch.call_in_scene(listener.scene, listener.on_event, event)
			else:
				listener.on_event(event)
		self.eventCache[event.message] = event

	def replay_last(self, target, message):
		'''Re-send a message. This should be used by new listeners that missed
		out on the last message, so they know what state the system is in.'''

		if message in self.eventCache:
			event = self.eventCache[message]
			target.on_event(event)

	def read_last(self, message):
		'''
		Fetch the last message. Note that this is a once-off operation. It's
		usually better to call replay_last.
		@raise KeyError: if no such message has been sent.
		'''
		return self.eventCache[message]

#class EventListener:
#	'''Interface for an object that can receive messages.'''
#	def on_event(self, event):
#		pass

class Event:
	def __init__(self, message, body=None):
		self.message = message
		self.body = body

	def __str__(self):
		return "Event(%s, %s)" % (str(self.message), str(self.body))

	def send(self, delay=0):
		'''Shorthand for bat.event.EventBus().notify(event).'''
		EventBus().notify(self, delay)

class WeakEvent(Event):
	'''An event whose body may be destroyed before it is read. Use this when
	the body is a game object.'''

	body = bat.containers.weakprop('body')

	def __init__(self, message, body):
		super(WeakEvent, self).__init__(message, body)

@bat.utils.all_sensors_positive
@bat.utils.owner
def send(o):
	'''Send an event from an object. Bind this to a Python logic brick.'''
	msg = o['message']

	if 'delay' in o:
		delay = o['delay']
	else:
		delay = 0

	if 'body' in o:
		if o['body'] == 'self':
			WeakEvent(msg, o).send(delay)
		else:
			Event(msg, o['body']).send(delay)
	else:
		Event(msg).send(delay)


class SceneDispatch(bat.bats.BX_GameObject, bge.types.KX_GameObject):
	'''
	Calls functions in the context of a particular scene. This is necessary
	for some BGE operations, such as LibLoad which always loads data into
	the current scene. Also, KX_Scene.addObject seems to be buggy when called
	in the context of another scene (leading to zombie objects).

	To use, make sure the BXT_Dispatcher object is in the target scene, and then
	call call_in_scene.
	'''

	log = logging.getLogger(__name__ + '.SceneDispatch')

	_prefix = 'SD_'

	def __init__(self, old_owner):
		SceneDispatch.log.info("Creating SceneDispatch in %s", self.scene)
		self.pending = []

	def enqueue(self, function, *args, **kwargs):
		self.pending.append((function, args, kwargs))

	@bat.bats.expose
	def process(self):
		for fn, args, kwargs in list(self.pending):
			SceneDispatch.log.debug("Calling deferred function %s in %s", fn,
					bge.logic.getCurrentScene())
			try:
				fn(*args, **kwargs)
			except Exception:
				SceneDispatch.log.error("Exception while executing deferred "
						"function %s in %s", fn,
						bge.logic.getCurrentScene(), exc_info=1)
		self.pending = []

	@staticmethod
	def call_in_scene(scene, fn, *args, **kwargs):
		if scene is None or scene is bge.logic.getCurrentScene():
			# Call immediately.
			SceneDispatch.log.info("Calling immediate function %s in %s", fn,
					bge.logic.getCurrentScene())
			fn(*args, **kwargs)
			return

		SceneDispatch.log.debug("Deferring function call %s from %s to %s", fn,
				bge.logic.getCurrentScene(), scene)
		try:
			dispatcher = scene.objects['BXT_Dispatch']
		except KeyError:
			raise KeyError("No dispatcher in scene %s. Ensure the group G_BXT "
					"is linked." % scene)
		try:
			dispatcher.enqueue(fn, *args, **kwargs)
		except AttributeError:
			dispatcher = bat.bats.mutate(dispatcher)
			dispatcher.enqueue(fn, *args, **kwargs)
