# Blender Adventure Toolkit

This is the Blender Adventure Toolkit (*bat*) - a Python library for use with
the Blender Game Engine (BGE). *Bat* provides classes and functions that can
help with the creation of games in BGE. It was designed with adventure games in
mind (hence the `story` module), but it would be useful for any kind of game.

To use this library, link to `bat_assets.blend` and add the `G_BXT` group to
your scene. Then you can use the Python modules from your code, for example:

- Write custom game object classes by inheriting from `bats.BX_GameObject` as a
  mixin.
- Send same-frame events between objects using the `event` module.
- Create story sequences using the `story` module.
- Respond to animation events using the `anim` module.

Modules are described in more detail below.


## Object Management

- `bats`: [Metaclasses][mc] for creating extended objects and singletons. This
  provides a convenient mechanism for subclassing Blender's `KX_GameObject`
  class, and allows the custom *methods* to be called from logic bricks. The
  `BX_GameObject` class should be mixed in with `KX_GameObject`,
  `BL_ArmartureObject` or similar.
- `containers`: "Safe" collections (lists and sets) for storing game objects.
  If an object is removed from the scene, it will automatically be removed from
  the list - so you never need to check while iterating.
- `event`: An event bus for loosely-coupled communication between objects.
  This is similar to the BGE's messages, but events can be received on the *same
  frame* or delayed and sent some number of frames in the future.
- `utils`: Basic object management functions such as:
    - Get/set states without using bitmasks.
    - Decorators to make calling functions with owners from logic bricks (or
      not!) easier.


## Story Progression

- `store`: Adds path support to Blender's saved game files. Defines some
  special paths such as `/game/`, which allows easy IO of saved game data for
  the current game (in a game that supports multiple saved games).
- `story`: State machine for describing multi-step story interactions, e.g. conversations. The
  important thing to note is that this does not happen in one function call;
  the steps are evaluated over many frames so the game can continue while the
  state machine runs. Allows the creation of sequences like:
    1. Play animation X.
    1. When animation X reaches frame 25, play a sound.
    1. When the animation finishes, show the user a message and wait for input.

```python
s = (self.rootState.create_successor('Init')
    (bat.story.ActAction("B_Final", 1, 60))
    (bat.story.State()
        (bat.story.CondActionGE(0, 25, tap=True))
        (bat.story.ActSound('//Sound/cc-by/BirdSquarkSmall.ogg', pitchmin=0.9, pitchmax=1.1))
    )
)

s = (s.create_successor()
    (bat.story.CondActionGE(0, 60))
    ("ShowDialogue", "Hi there, little snail! It's nice of you to come to visit.")
)
```

In the example above, there are three states:

- The first state succeeds from the root state and has no conditions, so it
  will become active at the start. There is one action that plays an
  animation (`ActAction`). There is also a sub-state.
- The sub-state is evaluated for every frame that its parent is active. In
  this case it has a condition that says it will only run when the animation
  frame is greater than or equal to `25` (`CondActionGE`). It will only run
  once, because `tap=True`. It has one action that plays a sound (`ActSound`).
- The third state succeeds from the first state. It will become active when
  the animation reaches frame `25` (`CondActionGE`), and at that point the
  first state will become inactive. It has one action, which is to send an
  event. Events can be sent using the special syntax `subject, body` - this
  is a shortcut for the `ActEvent` class.

Note that only one state can be active at a time, and sub-states are never really active.

The syntax above is made passible by the `State.__call__` method and [chaining][ch].
If you don't like it, you can write more explicit code like this:

```python
ssquark = bat.story.State()
ssquark.add_condition(bat.story.CondActionGE(0, 25, tap=True))
ssquark.add_action(bat.story.ActSound('//Sound/cc-by/BirdSquarkSmall.ogg', pitchmin=0.9, pitchmax=1.1))

s = self.rootState.create_successor('Init')
s.add_action(bat.story.ActAction("B_Final", 1, 60))
s.add_sub_step(ssquark)

s = s.create_successor()
s.add_condition(bat.story.CondActionGE(0, 60))
s.add_event("ShowDialogue", "Hi there, little snail! It's nice of you to come to visit.")
```

[ch]: http://en.wikipedia.org/wiki/Method_chaining


## IO

- `impulse`: User input abstraction, allowing run-time configuration of input
  devices such as keyboards and joysticks. All devices are presented using the
  same interfaces, e.g. a mouse has two axes just like a joystick. Multiple
  physical keys and buttons can be bound to the same logical button, e.g. "Up"
  could have bindings `w`, `uparrow`, `joystick axis 1 (positive)` and
  `joystick dpad 1` simultaneously.
- `sound`: Enhanced API for playing sounds and layering effects. Includes
  event-driven music track switching with support for cross-fading - allowing
  the music to change as your character moves around the level, or when
  something happens in the story. Music tracks can be given priorities, e.g.
  music for a battle situation might have a high priority while background music
  would have a low priority.


## Dynamics and Kinematics

- `anim`: Animation utils. Allows registration of callbacks for animations,
  e.g. run a function when an animation reaches a certain frame.
- `bmath`: Handy maths functions for interpolation, spatial sorting and ray
  casting.
- `c`: Basic dynamic behaviours, such as slow parenting (with proper smooth
  rotational interpolation), and following at a distance.
- `effectors`: Force fields that push objects around, e.g. wind and vortices.
- `render`: Colour conversion and decoding e.g.
  `white -> #fff -> (1.0, 1.0, 1.0)`
- `water`: Special shaped force fields (shaped by water surface) implementing
  basic buoyancy.


## Meta

- `debug`: Debugging utilities e.g. pretty printers for console.
- `statprof`: Statistical profiler for finding hotspots (slow parts) of Python
  code.



[mc]: http://stackoverflow.com/a/100146/320036
