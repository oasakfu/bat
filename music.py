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

import aud
import bge

import bxt

VOLUME_INCREMENT = 0.005

# Hold two handles: one for the current track (latest result of calling 'play'),
# and another for the previous one. This is required to do cross-fading.
current_handle = None
old_handles = []

def play(filepath, volume=1.0, loop=True):
	'''Start playing a new track.'''
	global current_handle

	dev = aud.device()
	path = bge.logic.expandPath(filepath)
	track = aud.Factory(path)
	if volume != 1.0:
		track = track.volume(volume)
	if loop:
		track = track.loop(-1)

	# Retire old track.
	stop()
	# Play new track. 
	current_handle = dev.play(track)
	current_handle.volume = 0.0

def stop():
	'''Fade out the current track.'''
	# This will cause the old track to fade out in update().
	if current_handle != None:
		old_handles.append(current_handle)

def update():
	'''Fade in current track, and fade out old tracks.'''
	# Fade in current handle (front of queue).
	if current_handle is not None and current_handle.volume < 1.0:
		vol = current_handle.volume
		vol = min(vol + VOLUME_INCREMENT, 1.0)
		current_handle.volume = vol

	# Fade out older handles.
	for handle in old_handles[:]:
		vol = handle.volume
		if vol > 0.0:
			vol = max(vol - VOLUME_INCREMENT, 0.0)
			handle.volume = vol
		else:
			handle.stop()
			old_handles.remove(handle)
