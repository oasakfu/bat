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
- `story`: State machine for describing multi-step story interactions. The
  important thing to note is that this does not happen in one function call;
  the steps are evaluated over many frames so the game can continue while the
  state machine runs. Allows the creation of sequences like:
    1. Play animation X.
    1. When animation X reaches frame 25, play a sound.
    1. When the animation finishes, show the user a message and wait for input.
    1. If the user presses button 1 then do Y, else do Z.


## IO

- `impulse`: User input abstraction, allowing run-time configuration of input
  devices such as keyboards and joysticks. All devices are presented using the
  same interfaces, e.g. a mouse has two axes just like a joystick.
- `sound`: Enhanced API for playing sounds and layering effects. Includes
  event-driven music track switching with support for cross-fading.


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
