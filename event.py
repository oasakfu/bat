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

import bat.bats
import bat.containers

class EventBus(metaclass=bat.bats.Singleton):
	'''Delivers messages to listeners.'''

	_prefix = ''

	log = logging.getLogger(__name__ + '.EventBus')

	def __init__(self):
		self.listeners = bat.containers.SafeSet()
		self.eventQueue = []
		self.eventCache = {}
		self.lastCaller = (None, 0)
		self.last_frame_num = bat.bats.Timekeeper().get_frame_num()

	def add_listener(self, listener):
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
	def process_queue(self, ob):
		'''Send queued messages that are ready. It is assumed that several
		objects may be calling this each frame; however, only one per frame will
		succeed.'''
		if len(self.eventQueue) == 0:
			return

		# Acquire lock for this frame.
		frame_num = bat.bats.Timekeeper().get_frame_num()
		if frame_num == self.last_frame_num:
			return
		self.last_frame_num = frame_num

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
		@param delay The time to wait, in rendered frames (not logic ticks).
		'''

		if delay <= 0:
			self._notify(event)
		else:
			self._enqueue(event, delay)

	def _notify(self, event):
		EventBus.log.info("Sending %s", event)
		for listener in self.listeners.copy():
			EventBus.log.debug('\ttarget = %s', str(listener))
			listener.on_event(event)
		self.eventCache[event.message] = event

	def replay_last(self, target, message):
		'''Re-send a message. This should be used by new listeners that missed
		out on the last message, so they know what state the system is in.'''

		if message in self.eventCache:
			event = self.eventCache[message]
			target.on_event(event)

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
