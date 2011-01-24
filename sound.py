#
# Copyright 2009-2010 Alex Fraser <alex@phatcore.com>
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

import bxt
import mathutils
from bge import logic

MIN_VOLUME = 0.001

#
# A mapping from sound name to actuator index. This lets play_with_random_pitch
# cycle through different samples for a named sound.
#
_SoundActuatorIndices = {}

@bxt.utils.controller
def play_with_random_pitch(c):
	'''
	Play a sound with a random pitch. The pitch range is defined by the
	controller's owner using the properties PitchMin and PitchMax.
	
	Sensors:
	<one>:  If positive and triggered, a sound will be played.
	
	Actuators:
	<one+>: Each will be played in turn.
	
	Controller properties:
	PitchMin: The minimum pitch (float).
	PitchMax: The maximum pitch (float).
	SoundID:  The name of the sound (any type). This lets different objects with
	          the same SoundID coordinate the sequence that the sounds are
	          played in. Note that if controllers with the same SoundID have
	          different numbers of actuators, the additional actuators are not
	          guaranteed to play.
	'''
	s = c.sensors[0]
	if not s.triggered or not s.positive:
		return
	o = c.owner

	try:
		o['SoundID']
	except KeyError:
		o['SoundID'] = None
	try:
		o['PitchMin']
	except KeyError:
		o['PitchMin'] = 0.8
	try:
		o['PitchMax']
	except KeyError:
		o['PitchMax'] = 1.2

	#
	# Select an actuator.
	#
	i = 0
	soundID = o['SoundID']
	try:
		i = _SoundActuatorIndices[soundID]
	except KeyError:
		_SoundActuatorIndices[soundID] = 0
		i = 0
	
	i = i % len(c.actuators)
	a = c.actuators[i]
	_SoundActuatorIndices[soundID] = i + 1
	
	#
	# Set the pitch and activate!
	#
	a.pitch = bxt.math.lerp(o['PitchMin'], o['PitchMax'], logic.getRandomFloat())
	c.activate(a)

@bxt.utils.controller
def fade(c):
	'''
	Causes a sound to play a long as its inputs are active. On activation, the
	sound fades in; on deactivation, it fades out. The fade rate is determined
	by the owner's SoundFadeFac property (0.0 <= SoundFadeFac <= 1.0).
	
	Sensors:
	sAlways:  Fires every frame to provide the fading effect.
	<one+>:   If any are positive, the sound will turn on. Otherwise the sound
	          will turn off.
	
	Actuators:
	<one>:    A sound actuator.
	
	Controller properties:
	VolumeMult:    The maximum volume (float).
	SoundFadeFac:  The response factor for the volume (float).
	'''
	_fade(c, 1.0)

def _fade(c, maxVolume):
	a = c.actuators[0]
	o = a.owner

	try:
		o['VolumeMult']
	except KeyError:
		o['VolumeMult'] = 1.0
	try:
		o['SoundFadeFac']
	except KeyError:
		o['SoundFadeFac'] = 0.05

	maxVolume = maxVolume * o['VolumeMult']
	
	targetVolume = 0.0
	for s in c.sensors:
		if s.name == "sAlways":
			continue
		if s.positive:
			targetVolume = maxVolume
			break
	
	a.volume = bxt.math.lerp(a.volume, targetVolume, o['SoundFadeFac'])
	if a.volume > MIN_VOLUME:
		c.activate(a)
	else:
		c.deactivate(a)

def _modulate(speed, c):
	o = c.owner

	try:
		o['SoundModScale']
	except KeyError:
		o['SoundModScale'] = 0.01
	try:
		o['PitchMin']
	except KeyError:
		o['PitchMin'] = 0.8
	try:
		o['PitchMax']
	except KeyError:
		o['PitchMax'] = 1.2

	factor = 0.0
	if speed > 0.0:
		factor = bxt.math.approach_one(speed, o['SoundModScale'])
	
	a = c.actuators[0]
	a.pitch = bxt.math.lerp(o['PitchMin'], o['PitchMax'], factor)
	
	_fade(c, factor)

@bxt.utils.controller
def modulate_by_linv(c):
	'''
	Change the pitch and volume of the sound depending on the angular velocity
	of the controller's owner.
	
	Sensors:
	sAlways:  Fires every frame to provide the fading effect.
	<others>: At least one other. If any are positive, the sound will turn on.
	          Otherwise the sound will turn off.
	
	Actuators:
	<one>:    A sound actuator.
	
	Controller properties:
	SoundModScale: The rate at which the pitch increases (float).
	PitchMin:      The minimum pitch (when speed = 0) (float).
	PitchMax:      The maximum pitch (as speed approaches infinity) (float).
	VolumeMult:    The maximum volume (as speed approaches infinity) (float).
	SoundFadeFac:  The response factor for the volume (float).
	'''
	o = c.owner
	linV = mathutils.Vector(o.getLinearVelocity(False))
	_modulate(linV.magnitude, c)

@bxt.utils.controller
def modulate_by_angv(c):
	'''
	Change the pitch and volume of the sound depending on the angular velocity
	of the controller's owner.
	
	Sensors:
	sAlways:  Fires every frame to provide the fading effect.
	<others>: At least one other. If any are positive, the sound will turn on.
	          Otherwise the sound will turn off.
	
	Actuators:
	<one>:    A sound actuator.
	
	Controller properties:
	SoundModScale: The rate at which the pitch increases (float).
	PitchMin:      The minimum pitch (when speed = 0) (float).
	PitchMax:      The maximum pitch (as speed approaches infinity) (float).
	VolumeMult:    The maximum volume (as speed approaches infinity) (float).
	SoundFadeFac:  The response factor for the volume (float).
	'''
	o = c.owner
	angV = mathutils.Vector(o.getAngularVelocity(False))
	_modulate(angV.magnitude, c)

