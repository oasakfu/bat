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

import itertools

import aud
import bge

import bxt

VOLUME_INCREMENT = 0.005

# Hold two handles: one for the current track (latest result of calling 'play'),
# and another for the previous one. This is required to do cross-fading.
current_handle = None
old_handles = []

def play(*filepaths, volume=1.0, loop=True):
	'''
	Start playing a new track.
	@param *filepaths: These sound files will be played in order.
	@param loop: Make the track loop. Only the last file specified in
		'filepaths' will loop; the others will form the introduction.
	'''

	# Construct a factory for each file.
	segments = []
	for filepath in filepaths:
		path = bge.logic.expandPath(filepath)
		segments.append(aud.Factory(path))

	# Make just the last segment loop.
	if loop:
		segments[-1] = segments[-1].loop(-1)

	# Join the segments together.
	track = _concatenate_factories(segments)

	try:
		_play(track, volume)
	except aud.error as e:
		print("Error playing", filepaths)
		print(e)

def play_permutation(*filepaths, volume=1.0, loop=True):
	'''
	Play a set of tracks in various orders - e.g. 3 files each 20s long will
	play for

		3! * (3 * 20) = 6 * 60 = 360s

	before repeating.

	@param loop: Make the track loop. All files in 'filepaths' will loop, in the
		sequence described above.
	'''
	# Construct a factory for each file.
	segments = []
	for filepath in filepaths:
		path = bge.logic.expandPath(filepath)
		segments.append(aud.Factory(path))

	# Note that itertools.permutations() returns a 2D array of permutations, so
	# we need to join the inner sequences first, then join them all together at
	# the end.
	perms = []
	for p in itertools.permutations(segments):
		perms.append(_concatenate_factories(p))
	track = _concatenate_factories(perms)

	# Make just the last segment loop.
	if loop:
		track = track.loop(-1)

	try:
		_play(track, volume)
	except aud.error as e:
		print("Error playing", filepaths)
		print(e)

def _concatenate_factories(factories):
	combined = None
	for factory in factories:
		if combined is None:
			combined = factory
		else:
			combined = combined.join(factory)
	return combined

def _play(track, volume):
	global current_handle
	# Set volume globally for whole track.
	if volume != 1.0:
		track = track.volume(volume)

	# Retire old track.
	stop()
	# Play new track.
	dev = aud.device()
	current_handle = dev.play(track)
	current_handle.volume = 0.0


def stop():
	'''Fade out the current track.'''
	global current_handle
	# This will cause the old track to fade out in update().
	if current_handle != None:
		old_handles.append(current_handle)
		current_handle = None

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
