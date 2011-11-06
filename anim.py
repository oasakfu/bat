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
    bxt.anim.add_trigger_end(ob, LAYER, cb)

'''

import bge

class TriggerEnd:
    '''Runs a callback when an animation finishes.'''

    def __init__(self, layer, callback):
        self.layer = layer
        self.callback = callback

    def evaluate(self, ob):
        if not ob.isPlayingAction(self.layer):
            self.callback()
            return True
        else:
            return False

class TriggerGTE:
    '''Runs a callback on or after an animation frame.'''

    def __init__(self, layer, frame, callback):
        self.layer = layer
        self.frame = frame
        self.callback = callback

    def evaluate(self, ob):
        if ob.getActionFrame(self.layer) >= self.frame:
            self.callback()
            return True
        else:
            return False

class TriggerLT:
    '''Runs a callback before an animation frame.'''

    def __init__(self, layer, frame, callback):
        self.layer = layer
        self.frame = frame
        self.callback = callback

    def evaluate(self, ob):
        if ob.getActionFrame(self.layer) < self.frame:
            self.callback()
            return True
        else:
            return False

def _find_scene(ob):
    '''Finds the scene that an object belongs to.'''
    for sce in bge.logic.getSceneList():
        if ob in sce.objects:
            return sce
    raise ValueError("Can't find object in any active scene.")

def add_trigger(ob, trigger):
    '''Adds an animation trigger. The trigger will be evaluated once per frame
    until it succeeds, or the object is destroyed.'''

    sce = _find_scene(ob)
    triggers = None
    try:
        triggers = sce['action_triggers']
    except KeyError:
        sce['action_triggers'] = triggers = {}
        sce.pre_draw.append(_run_triggers)

    if not ob in triggers:
        triggers[ob] = []
    triggers[ob].append(trigger)

def add_trigger_end(ob, layer, callback):
    '''Adds a trigger that runs once at the end of the animation.'''
    add_trigger(ob, TriggerEnd(layer, callback))

def add_trigger_gte(ob, layer, frame, callback):
    '''Adds a trigger that runs once when 'frame' is reached (or before 'frame'
    is reached if running backwards).'''
    add_trigger(ob, TriggerGTE(layer, frame, callback))

def add_trigger_lt(ob, layer, frame, callback):
    '''Adds a trigger that runs once before 'frame' is reached (or after 'frame'
    is reached if running backwards).'''
    add_trigger(ob, TriggerLT(layer, frame, callback))

def _run_triggers():
    '''Runs all triggers for the current scene. This is run as a drawing
    callback of the scene.'''

    # Traverse list of object triggers. 'action_triggers' should exist, because
    # it is added to the scene before this callback ('_run_triggers') is.
    triggers = bge.logic.getCurrentScene()['action_triggers']
    for ob in list(triggers.keys()):
        if ob.invalid:
            # Object has been deleted.
            del triggers[ob]
            continue

        # Traverse list of triggers.
        obTriggers = triggers[ob]
        for trigger in list(obTriggers):
            if trigger.evaluate(ob):
                obTriggers.remove(trigger)
